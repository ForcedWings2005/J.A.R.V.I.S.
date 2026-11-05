"""Tests for the web endpoints in server.py.

The model, Whisper and Kokoro are all replaced by fakes, so these run anywhere.
"""
import json
import logging
import os
import re
from datetime import datetime
import sys
import types

import pytest
from fastapi.testclient import TestClient

import brain
import config
import jcal
import notes
import server
import speech
import tasks
import urllib.error
import weather_data as data
from fakes import FakeModel, call, say, use


@pytest.fixture
def client():
    # The server only accepts its own address (see TrustedHostMiddleware)
    return TestClient(server.app, base_url="http://127.0.0.1")


@pytest.fixture
def model(monkeypatch):
    """A fresh conversation whose model plays back whatever the test scripts."""
    def start(*rounds):
        fake = FakeModel(*rounds)
        monkeypatch.setattr(server, "assistant", brain.Assistant(chat=fake))
        return fake
    return start


def chat(client, message):
    r = client.post("/chat", json={"message": message})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in r.text.splitlines()]


# ---------- the page and the host check ----------

def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_day_gives_the_work_summary(client):
    """The Work space's strip and deadlines (workday.py, CHANGELOG section 51)."""
    r = client.get("/day")
    assert r.status_code == 200
    assert set(r.json()) == {"free", "next", "deadlines", "deadline_window_days", "day_end"}
    assert r.json()["day_end"] == "22:00"      # so the page can say "after 5:30 PM"


def test_day_with_made_up_data(client):
    """The spec asks for /day with data in it; one task's date is unpadded (review)."""
    jcal.add_event("Dentist", "2030-01-07", "15:00", "16:00")
    tasks.add_task("Essay", "2030-1-9")
    r = client.get("/day")
    assert r.status_code == 200
    body = r.json()
    assert body["next"]["title"] == "Dentist"
    assert body["deadlines"][0]["due"] == "2030-01-09" and body["deadlines"][0]["days_left"] == 2


def test_day_is_read_only(client):
    assert client.post("/day", json={}).status_code == 405


def test_the_page_files_are_served(client):
    """The styles and scripts live in static/css and static/js (CHANGELOG section 40)."""
    css = client.get("/static/css/jarvis.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    js = client.get("/static/js/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]


@pytest.mark.parametrize("path", ["/static/../server.py", "/static/..%2Fserver.py",
                                  "/static/%2e%2e/config.py"])
def test_only_files_inside_static_are_served(client, path):
    r = client.get(path)
    assert r.status_code == 404 or "import" not in r.text


def test_page_files_are_checked_again_on_every_load(client):
    """Without this the browser kept an old stylesheet after an update (CHANGELOG section 40)."""
    for path in ("/", "/static/css/jarvis.css", "/static/js/app.js"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


def test_every_file_the_page_loads_exists(client):
    """A typo in a script or stylesheet link would break the page silently."""
    import re
    page = client.get("/").text
    links = re.findall(r'(?:src|href)="(/static/[^"]+)"', page)
    assert links, "the page loads no files"
    for link in links:
        assert client.get(link).status_code == 200, link


def test_other_host_names_are_refused():
    """Protects against DNS rebinding: a page on another domain pointed at 127.0.0.1."""
    evil = TestClient(server.app, base_url="http://evil.example")
    assert evil.get("/").status_code == 400
    assert TestClient(server.app, base_url="http://localhost").get("/").status_code == 200


def test_json_sent_as_plain_text_is_refused(client):
    """Another website can send text/plain to 127.0.0.1 without a browser preflight check.
    Because these endpoints only accept real JSON, such a request cannot drive JARVIS.
    No Origin header here, so this tests the JSON rule on its own; the Origin check, the
    other lock, has its own tests below."""
    tasks.add_task("Buy milk")
    tid = tasks.tasks_list()[0]["id"]
    r = client.post(f"/tasks/{tid}", content='{"done": true}',
                    headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    assert tasks.tasks_list()[0]["done"] is False
    r = client.post("/chat", content='{"message": "hi"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 422


# ---------- the Content Security Policy (spec: docs/specs/2026-11-05-weather-space.md) ----------

# Written out in full, not read from server.py, so a quiet change to the policy fails here
POLICY = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
          "font-src 'self'; connect-src 'self'; media-src 'self' blob: data:; "
          "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


@pytest.mark.parametrize("path", ["/", "/static/js/app.js", "/static/css/jarvis.css", "/tasks"])
def test_every_response_carries_the_security_policy(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == POLICY


def test_refused_requests_carry_the_security_policy(client):
    """The policy must be the outermost middleware to reach the locks' own refusals."""
    other_site = client.post("/reset", json={}, headers={"Origin": "http://evil.example"})
    assert other_site.status_code == 403
    assert other_site.headers["content-security-policy"] == POLICY
    other_host = TestClient(server.app, base_url="http://evil.example").get("/")
    assert other_host.status_code == 400
    assert other_host.headers["content-security-policy"] == POLICY


def test_missing_files_carry_the_security_policy(client):
    response = client.get("/static/js/no-such-file.js")
    assert response.status_code == 404
    assert response.headers["content-security-policy"] == POLICY


def test_streamed_chat_carries_the_security_policy(client, model):
    model(say("Hello."))
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == POLICY


def test_the_page_has_nothing_inline():
    """The policy forbids inline code, so any would silently stop working."""
    page = (config.STATIC_DIR / "index.html").read_text()
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page) is None
    assert "<style" not in page
    assert re.search(r"\sstyle\s*=", page) is None
    assert re.search(r"\son[a-z]+\s*=", page) is None


def test_the_scripts_use_nothing_the_policy_blocks():
    """eval and friends fail only in the browser, so catch them here first."""
    blocked = ["eval(", "new Function", "setAttribute('style'", 'setAttribute("style"',
               "insertAdjacentHTML", "javascript:"]
    for script in (config.STATIC_DIR / "js").glob("*.js"):
        text = script.read_text()
        for word in blocked:
            assert word not in text, f"{script.name} uses {word}"


@pytest.fixture
def info_env(monkeypatch, tmp_path):
    """/info with a pretend backup folder and a pretend Ollama check (CI has no Ollama)."""
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path)
    state = {"ollama": True}
    monkeypatch.setattr(server, "_ollama_ok", lambda: state["ollama"])
    return tmp_path, state


def test_info_names_the_model_in_use(client, info_env):
    """The header showed 'gemma4' written into the page by hand, wrong after the switch."""
    assert client.get("/info").json()["model"] == config.MODEL


def test_info_gives_the_time_of_the_newest_backup(client, info_env):
    folder, _ = info_env
    assert client.get("/info").json()["last_backup"] is None
    for name, stamp in (("jarvis-2030-01-06.db", 1894060800), ("jarvis-2030-01-07.db", 1894158000)):
        f = folder / name
        f.write_bytes(b"x")
        os.utime(f, (stamp, stamp))
    expected = datetime.fromtimestamp(1894158000).strftime("%Y-%m-%d %H:%M")
    assert client.get("/info").json()["last_backup"] == expected


def test_info_says_whether_ollama_answers(client, info_env):
    _, state = info_env
    assert client.get("/info").json()["ollama"] is True
    state["ollama"] = False
    assert client.get("/info").json()["ollama"] is False


def test_the_ollama_check_gives_up_quickly_and_quietly(monkeypatch):
    """A stopped Ollama must not hang the page or raise: the check has a short timeout."""
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def list(self):
            raise ConnectionError("Ollama is not running")

    monkeypatch.setattr(server.ollama, "Client", FakeClient)
    assert server._ollama_ok() is False
    assert 0 < seen["timeout"] <= 2


# ---------- notes panel (CHANGELOG section 40) ----------

def test_notes_panel_starts_empty(client):
    assert client.get("/notes").json() == {"notes": []}


def test_notes_panel_lists_saved_notes_newest_first(client):
    for text in ("Favourite food is sushi", "Prefers window seats"):
        notes.remember(text).apply()
    listed = client.get("/notes").json()["notes"]
    assert [n["text"] for n in listed] == ["Prefers window seats", "Favourite food is sushi"]
    assert set(listed[0]) == {"id", "text", "created"}


def test_notes_panel_is_read_only(client):
    """Saving and forgetting go only through the chat and the confirmation card."""
    assert client.post("/notes", json={"text": "x"}).status_code == 405


# ---------- chat and confirmation ----------

def test_chat_streams_events(client, model):
    model(say("Good evening, sir."))
    events = chat(client, "Good evening")
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Good evening, sir."
    assert events[-1]["type"] == "done"


def test_chat_with_a_tool(client, model):
    model(use(call("add_task", title="Buy milk")), say("Added."))
    events = chat(client, "Add buy milk")
    assert [e["type"] for e in events].count("step") == 1
    assert client.get("/tasks").json()["tasks"][0]["title"] == "Buy milk"


def test_delete_needs_the_confirm_endpoint(client, model):
    jcal.add_event("Dentist", "2030-01-08", "15:00")
    model(use(call("delete_event", title="dentist", date="2030-01-08")), say("Please confirm."))
    card = chat(client, "Cancel the dentist")[-1]["confirm"]
    assert card["text"].startswith("Delete 'Dentist'")
    assert "Dentist" in jcal.get_events("2030-01-08")
    r = client.post("/confirm", json={"id": card["id"], "approve": True})
    assert r.json() == {"reply": "Done. The event has been deleted."}
    assert jcal.get_events("2030-01-08").startswith("No events")
    r = client.post("/confirm", json={"id": card["id"], "approve": True})
    assert "expired" in r.json()["reply"]


def test_chat_needs_a_message(client):
    assert client.post("/chat", json={}).status_code == 422


def test_chat_passes_the_space_on(client, model):
    fake = model(say("Yes, sir."))
    client.post("/chat", json={"message": "hi", "space": "work"})
    assert fake.seen[0][-1]["content"].endswith(" · Work] hi")


def test_chat_without_a_space_is_home(client, model):
    """An old cached page, or curl, sends no space: that is Home, not an error."""
    fake = model(say("Yes, sir."))
    assert chat(client, "hi")[-1]["type"] == "done"
    assert "·" not in fake.seen[0][-1]["content"]


def test_chat_refuses_an_unknown_space(client, model):
    model()
    assert client.post("/chat", json={"message": "hi", "space": "gym"}).status_code == 422


# ---------- calendar ----------

def test_calendar_range(client):
    jcal.add_event("Gym", "2030-01-08", "18:00", repeat="weekly", repeat_days="tue")
    r = client.get("/calendar", params={"start": "2030-01-07", "end": "2030-01-21"})
    assert [e["date"] for e in r.json()["events"]] == ["2030-01-08", "2030-01-15"]


@pytest.mark.parametrize("start,end", [
    ("2030-01-07", "Friday"),
    ("2030-01-10", "2030-01-07"),        # end before start
    ("2030-01-01", "2031-03-01"),        # more than 400 days
])
def test_calendar_refuses_bad_ranges(client, start, end):
    assert client.get("/calendar", params={"start": start, "end": end}).status_code == 400


# ---------- tasks ----------

def test_task_checkbox(client):
    tasks.add_task("Buy milk")
    tid = client.get("/tasks").json()["tasks"][0]["id"]
    assert client.post(f"/tasks/{tid}", json={"done": True}).json() == {"ok": True}
    assert client.get("/tasks").json()["tasks"][0]["done"] is True
    assert client.post("/tasks/9999", json={"done": True}).status_code == 404


# ---------- speech ----------

def test_speak_returns_wav(client, monkeypatch):
    spoken = []
    monkeypatch.setattr(speech, "synthesize", lambda text: spoken.append(text) or b"RIFF....")
    r = client.post("/speak", json={"text": "  Hello, sir.  "})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert spoken == ["Hello, sir."]


def test_speak_limits_and_refuses_empty_text(client, monkeypatch):
    spoken = []
    monkeypatch.setattr(speech, "synthesize", lambda text: spoken.append(text) or b"")
    assert client.post("/speak", json={"text": "   "}).status_code == 400
    client.post("/speak", json={"text": "a" * 5000})
    assert len(spoken[0]) == 2000


# Whisper's loader asked huggingface.co whether the model had changed, every time the
# server started using it (CHANGELOG section 45). Importing config now turns that off.
# A fresh Python is needed: config is already imported in this one.

def _offline_setting(env_value):
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}
    env["JARVIS_DB"] = ":memory:"
    if env_value is not None:
        env["HF_HUB_OFFLINE"] = env_value
    code = "import config, os; print(os.environ.get('HF_HUB_OFFLINE'))"
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                          text=True, cwd=os.path.dirname(config.__file__), check=True)
    return done.stdout.strip()


def test_importing_config_keeps_whisper_offline():
    assert _offline_setting(None) == "1"


def test_the_owner_can_still_turn_it_off_for_a_deliberate_download():
    assert _offline_setting("0") == "0"


@pytest.fixture
def whisper(monkeypatch):
    """A fake mlx_whisper module that remembers the file it was given."""
    seen = {}

    def transcribe(path, **kwargs):
        seen["path"], seen["existed"] = path, os.path.exists(path)
        return {"text": "  what's on tomorrow  "}

    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=transcribe))
    return seen


def test_transcribe(client, whisper):
    r = client.post("/transcribe", files={"file": ("clip.webm", b"audio bytes", "audio/webm")})
    assert r.json() == {"text": "what's on tomorrow"}
    assert whisper["existed"] and whisper["path"].endswith(".webm")
    assert not os.path.exists(whisper["path"])          # the temporary file is removed


def test_transcribe_odd_file_names_are_treated_as_webm(client, whisper):
    client.post("/transcribe", files={"file": ("clip.exe", b"audio", "application/octet-stream")})
    assert whisper["path"].endswith(".webm")


def test_transcribe_refuses_large_uploads(client, whisper, monkeypatch):
    monkeypatch.setattr(config, "MAX_AUDIO_BYTES", 10)
    r = client.post("/transcribe", files={"file": ("clip.webm", b"x" * 11, "audio/webm")})
    assert r.status_code == 413
    assert "path" not in whisper                         # never reached Whisper


# ---------- other websites: the Origin check ----------
# A page on any other website can make the browser POST a form to 127.0.0.1:8000.
# The browser says where it came from in the Origin header, so the server checks it.
# Proven first with experiments/attack_page.html (CHANGELOG section 36).

STRANGER = "http://localhost:9000"      # where attack_page.html is served


def test_another_website_cannot_make_jarvis_transcribe(client, whisper):
    r = client.post("/transcribe", headers={"Origin": STRANGER},
                    files={"file": ("silence.wav", b"audio", "audio/wav")})
    assert r.status_code == 403
    assert "another website" in r.json()["detail"]
    assert "path" not in whisper                         # Whisper was never started


@pytest.mark.parametrize("path, body", [
    ("/chat", {"message": "hi"}),
    ("/confirm", {"id": "x", "approve": True}),
    ("/reset", {}),
    ("/tasks/1", {"done": True}),
    ("/speak", {"text": "hi"}),
])
def test_another_website_is_refused_on_every_post(client, model, monkeypatch, path, body):
    """The JSON endpoints were already safe; this is a second, independent lock."""
    model()                             # a fake model with no rounds: any call would fail
    monkeypatch.setattr(speech, "synthesize", lambda text: pytest.fail("Kokoro was started"))
    r = client.post(path, json=body, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_a_null_origin_is_refused(client, whisper):
    """Sandboxed frames and local files send Origin: null."""
    r = client.post("/transcribe", headers={"Origin": "null"},
                    files={"file": ("a.wav", b"audio", "audio/wav")})
    assert r.status_code == 403


def test_the_dashboard_itself_is_allowed(whisper):
    for base in ("http://127.0.0.1:8000", "http://localhost:8000"):
        own = TestClient(server.app, base_url=base)
        r = own.post("/transcribe", headers={"Origin": base},
                     files={"file": ("clip.webm", b"audio", "audio/webm")})
        assert r.status_code == 200, base


def test_the_same_machine_on_another_port_or_name_is_another_website(whisper):
    own = TestClient(server.app, base_url="http://127.0.0.1:8000")
    for origin in ("http://127.0.0.1:9000", "http://localhost:8000", "https://127.0.0.1:8000"):
        r = own.post("/transcribe", headers={"Origin": origin},
                     files={"file": ("clip.webm", b"audio", "audio/webm")})
        assert r.status_code == 403, origin
    assert "path" not in whisper


def test_requests_without_an_origin_are_allowed(client, whisper):
    """Browsers always send Origin on a cross-site POST; tools like curl and the tests don't."""
    r = client.post("/transcribe", files={"file": ("clip.webm", b"audio", "audio/webm")})
    assert r.status_code == 200


def test_reading_is_not_affected(client):
    """GET requests change nothing, and the browser never lets another site read the reply."""
    assert client.get("/tasks", headers={"Origin": STRANGER}).status_code == 200


def test_refusals_are_logged(client, whisper, caplog):
    caplog.set_level("WARNING", logger="jarvis")
    client.post("/transcribe", headers={"Origin": STRANGER},
                files={"file": ("a.wav", b"audio", "audio/wav")})
    assert "refused POST /transcribe from another website" in caplog.text
    assert STRANGER in caplog.text


# ---------- logging ----------

def test_starting_the_server_starts_the_log_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    root = logging.getLogger("jarvis")
    before = list(root.handlers)
    try:
        with TestClient(server.app, base_url="http://127.0.0.1"):   # runs the start-up code
            pass
        assert "JARVIS started" in (tmp_path / "jarvis.log").read_text()
    finally:
        for h in root.handlers[len(before):]:
            h.close()
            root.removeHandler(h)


# ---------- starting a new conversation ----------

def test_reset_clears_the_conversation(client, model):
    fake = model(say("Hello, sir."), say("Hello again."))
    chat(client, "Hello")
    assert client.post("/reset", json={}).json() == {"ok": True}
    chat(client, "Hello")
    assert [m["role"] for m in fake.seen[1]] == ["system", "user"]       # nothing from before


def test_reset_cannot_be_sent_by_another_website(client, model):
    model(say("Hello, sir."))
    chat(client, "Hello")
    assert client.post("/reset").status_code == 422                      # no JSON body
    r = client.post("/reset", content="{}", headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    assert len(server.assistant.messages) == 3                           # still there


# ---------- the weather endpoints (docs/specs/2026-11-05-weather-space.md) ----------

WEATHER_PATHS = ["/weather/places", "/weather/confirm", "/weather/home"]


def test_places_endpoint(client, monkeypatch):
    data.serve(monkeypatch, geo=data.geocode(data.PARIS_FR, data.PARIS_TX))
    r = client.post("/weather/places", json={"query": "Paris"})
    assert r.status_code == 200
    matches = r.json()["matches"]
    assert [m["region"] for m in matches] == ["Île-de-France", "Texas"]
    assert set(matches[0]) == {"id", "name", "region", "country", "lat", "lon"}


@pytest.mark.parametrize("query", ["", "   ", "x" * 81])
def test_places_refuses_empty_or_long_queries(client, query):
    assert client.post("/weather/places", json={"query": query}).status_code == 422


def test_confirm_adds_the_spoken_line_to_the_conversation(client, model, monkeypatch):
    model()
    data.serve(monkeypatch, geo=data.geocode(data.PARIS_FR), forecast=data.forecast(),
               air=data.air())
    pid = client.post("/weather/places", json={"query": "Paris"}).json()["matches"][0]["id"]
    r = client.post("/weather/confirm", json={"id": pid})
    assert r.status_code == 200
    spoken = r.json()["spoken"]
    assert spoken.startswith("Paris: 65 degrees") and len(r.json()["hours"]) == 24
    assert server.assistant.messages[-1] == {"role": "assistant", "content": spoken}


def test_confirm_refuses_an_unknown_id(client, model):
    model()
    before = list(server.assistant.messages)
    r = client.post("/weather/confirm", json={"id": "nope"})
    assert r.status_code == 404
    assert r.json()["detail"] == "That place has expired. Search again."
    assert server.assistant.messages == before


def test_the_service_down_is_a_502(client, monkeypatch):
    data.serve(monkeypatch, geo=urllib.error.URLError("down"))
    r = client.post("/weather/places", json={"query": "Paris"})
    assert r.status_code == 502 and r.json()["detail"] == "Couldn't reach the weather service."


def test_home_endpoint(client, model, monkeypatch):
    model()
    data.serve(monkeypatch, forecast=data.forecast(), air=data.air())
    r = client.post("/weather/home", json={"name": " Rome ", "lat": 41.902782, "lon": 12.496366})
    assert r.status_code == 200 and r.json()["place"]["name"] == "Rome"
    assert server.assistant.messages[-1]["content"] == r.json()["spoken"]


@pytest.mark.parametrize("body", [
    {"name": "Home", "lat": 91, "lon": 0}, {"name": "Home", "lat": -91, "lon": 0},
    {"name": "Home", "lat": 0, "lon": 181}, {"name": "x" * 61, "lat": 0, "lon": 0},
    {"name": "", "lat": 0, "lon": 0}, {"name": "  ", "lat": 0, "lon": 0},
    {"name": "Home", "lat": "north", "lon": 0}, {"name": "Home", "lat": 0}])
def test_home_refuses_bad_coordinates(client, body):
    assert client.post("/weather/home", json=body).status_code == 422


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_home_refuses_nan_and_infinity(client, number):
    r = client.post("/weather/home", content='{"name": "Home", "lat": %s, "lon": 0}' % number,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


@pytest.mark.parametrize("path", WEATHER_PATHS)
def test_weather_endpoints_refuse_other_websites(client, path):
    r = client.post(path, json={"query": "Paris"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", WEATHER_PATHS)
def test_weather_endpoints_refuse_plain_text(client, path):
    r = client.post(path, content='{"query": "Paris"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 422


@pytest.mark.parametrize("path", WEATHER_PATHS)
def test_weather_endpoints_only_take_post(client, path):
    assert client.get(path).status_code == 405
