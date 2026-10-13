import os
import tempfile
import threading
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

import backup_db
import config

try:
    backup_db.backup(overwrite=False)   # first start of the day only
except Exception as e:                  # a backup problem must never stop JARVIS
    print(f"backup failed: {e}")

import brain  # noqa: E402
import jcal  # noqa: E402
import speech  # noqa: E402

app = FastAPI()
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

stt_lock = threading.Lock()


class ChatRequest(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    id: str
    approve: bool


class TaskToggle(BaseModel):
    done: bool


class SpeakRequest(BaseModel):
    text: str


@app.get("/")
def home():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    def lines():
        for event in brain.chat_stream(req.message):
            yield json.dumps(event) + "\n"
    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/confirm")
def confirm_endpoint(req: ConfirmRequest):
    return {"reply": brain.resolve_pending(req.id, req.approve)}


@app.get("/calendar")
def calendar_range(start: str, end: str):
    try:
        a = datetime.strptime(start, "%Y-%m-%d").date()
        b = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError as err:
        raise HTTPException(
            status_code=400,
            detail="dates must be YYYY-MM-DD",
        ) from err

    if b < a or (b - a).days > 400:
        raise HTTPException(status_code=400, detail="range must be 0 to 400 days")
    return {"events": jcal.events_between(a, b)}


@app.get("/tasks")
def tasks():
    return {"tasks": brain.tasks_list()}


@app.post("/tasks/{task_id}")
def set_task(task_id: int, req: TaskToggle):
    if not brain.set_task_done(task_id, req.done):
        raise HTTPException(status_code=404, detail="no such task")
    return {"ok": True}


@app.post("/transcribe")
def transcribe_endpoint(file: UploadFile = File(...)):
    data = file.file.read(config.MAX_AUDIO_BYTES + 1)
    if len(data) > config.MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="recording too large")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".webm", ".mp4", ".m4a", ".wav", ".ogg", ".mp3"):
        ext = ".webm"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        with stt_lock:
            import mlx_whisper  # loaded on first use, like Kokoro in speech.py
            result = mlx_whisper.transcribe(path, path_or_hf_repo=config.STT_MODEL, language="en")
    finally:
        os.remove(path)
    return {"text": result["text"].strip()}


@app.post("/speak")
def speak_endpoint(req: SpeakRequest):
    text = req.text.strip()[:2000]
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    return Response(content=speech.synthesize(text), media_type="audio/wav")