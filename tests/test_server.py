"""Tests for the web endpoints in server.py.

The model, Whisper and Kokoro are all replaced by fakes, so these run anywhere.
"""
import json
import logging
import os
import sys
import types

import pytest
from fastapi.testclient import TestClient

import brain
import config
import jcal
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


def test_other_host_names_are_refused():
    """Protects against DNS rebinding: a page on another domain pointed at 127.0.0.1."""
    evil = TestClient(server.app, base_url="http://evil.example")
    assert evil.get("/").status_code == 400
    assert TestClient(server.app, base_url="http://localhost").get("/").status_code == 200


def test_json_sent_as_plain_text_is_refused(client):
    """Another website can send text/plain to 127.0.0.1 without a browser preflight check.
    Because these endpoints only accept real JSON, such a request cannot drive JARVIS."""
    tasks.add_task("Buy milk")
    tid = tasks.tasks_list()[0]["id"]
    r = client.post(f"/tasks/{tid}", content='{"done": true}',
                    headers={"Content-Type": "text/plain", "Origin": "https://evil.example"})
    assert r.status_code == 422
    assert tasks.tasks_list()[0]["done"] is False
    r = client.post("/chat", content='{"message": "hi"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 422


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
    jcal.add_event("Gym", "2030-01-08", "18:00", repeat="weekly")
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
