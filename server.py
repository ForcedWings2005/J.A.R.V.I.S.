import os
import tempfile
import threading
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import RotatingFileHandler

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
import tasks  # noqa: E402

log = logging.getLogger("jarvis.server")


def setup_logging() -> None:
    """Everything under the "jarvis" logger goes to logs/jarvis.log and the terminal.

    The file rotates at 1 MB and keeps 5 old files. It holds what was said to
    JARVIS, so it stays on this Mac (logs/ is not in git).
    """
    config.LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file = RotatingFileHandler(config.LOG_DIR / "jarvis.log", maxBytes=1_000_000,
                               backupCount=5, encoding="utf-8")
    console = logging.StreamHandler()
    root = logging.getLogger("jarvis")
    root.setLevel(logging.INFO)
    for h in (file, console):
        h.setFormatter(fmt)
        root.addHandler(h)


@asynccontextmanager
async def lifespan(app):
    # Runs when uvicorn starts the server, not when tests import this file
    setup_logging()
    log.info("JARVIS started: model %s, database %s", config.MODEL, config.DB_PATH)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

stt_lock = threading.Lock()
assistant = brain.Assistant()


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
        for event in assistant.chat_stream(req.message):
            yield json.dumps(event) + "\n"
    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/confirm")
def confirm_endpoint(req: ConfirmRequest):
    return {"reply": assistant.resolve_pending(req.id, req.approve)}


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
def list_tasks_endpoint():
    return {"tasks": tasks.tasks_list()}


@app.post("/tasks/{task_id}")
def set_task(task_id: int, req: TaskToggle):
    if not tasks.set_task_done(task_id, req.done):
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
            t0 = time.perf_counter()
            result = mlx_whisper.transcribe(path, path_or_hf_repo=config.STT_MODEL, language="en")
            log.info("transcribed %d bytes in %.1f s", len(data), time.perf_counter() - t0)
    finally:
        os.remove(path)
    return {"text": result["text"].strip()}


@app.post("/speak")
def speak_endpoint(req: SpeakRequest):
    text = req.text.strip()[:2000]
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    return Response(content=speech.synthesize(text), media_type="audio/wav")