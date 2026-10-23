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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import backup_db
import config

try:
    backup_db.backup(overwrite=False)   # first start of the day only
except Exception as e:                  # a backup problem must never stop JARVIS
    print(f"backup failed: {e}")

import brain  # noqa: E402
import jcal  # noqa: E402
import notes  # noqa: E402
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

# Methods that only read. Everything else can change something or start work.
READ_ONLY = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def refuse_other_websites(request, call_next):
    """Any website open in the browser can make it POST a form here (SECURITY.md section 4).

    The browser adds an Origin header saying which site the request came from, and the
    page cannot change it. Only JARVIS's own address may send requests that do something.
    No Origin at all means it is not a browser request from another site (the tests,
    curl), so it is allowed: such a program already runs on this Mac.
    If JARVIS is ever served through HTTPS or another address (Phase 6), check this again.
    """
    origin = request.headers.get("origin")
    own = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if request.method not in READ_ONLY and origin is not None and origin != own:
        log.warning("refused %s %s from another website (Origin %r)",
                    request.method, request.url.path, origin)
        return JSONResponse(status_code=403, content={
            "detail": "Refused: this request came from another website."})
    return await call_next(request)

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


class ResetRequest(BaseModel):
    """Empty, but requiring a JSON body keeps other websites from sending this request."""


@app.get("/")
def home():
    return FileResponse(config.STATIC_DIR / "index.html")


# The page's styles and scripts (static/css, static/js). StaticFiles serves only files
# inside this folder, and only to GET requests.
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


@app.middleware("http")
async def check_page_files_again(request, call_next):
    """The browser may keep the page and its files, but must ask the server before using
    them, so an update shows at once instead of an old stylesheet (CHANGELOG section 40)."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


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


@app.post("/reset")
def reset_endpoint(req: ResetRequest):
    assistant.reset()
    return {"ok": True}


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


@app.get("/info")
def info_endpoint():
    """For the page's header: which model JARVIS is using."""
    return {"model": config.MODEL}


@app.get("/notes")
def list_notes_endpoint():
    return {"notes": notes.notes_list()}


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