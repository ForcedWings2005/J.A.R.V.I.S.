"""Tests for the web endpoints in server.py.

The model, Whisper and Kokoro are all replaced by fakes, so these run anywhere.
"""
import json
import logging
import os
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
