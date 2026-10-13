"""Settings in one place.

Paths are built from this file's folder, so the server works no matter which
folder it is started from.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The real calendar and tasks. Tests and evals set JARVIS_DB=":memory:" before
# importing anything, so they never touch it.
DB_PATH = os.environ.get("JARVIS_DB", str(ROOT / "jarvis.db"))
BACKUP_DIR = ROOT / "backups"
BACKUP_KEEP_DAYS = 7
LOG_DIR = ROOT / "logs"
STATIC_DIR = ROOT / "static"
MODELS_DIR = ROOT / "models"

# Language model (Ollama). Check the pinned ID in README.md after an update.
MODEL = "gemma4:latest"
MAX_ROUNDS = 4          # tool rounds per message, so a confused model can't loop forever
# gemma4 "thinks" (hidden reasoning) before it answers. Keep it ON: with it off, replies
# came 7x faster but the evals fell from 102/102 to 73/102, with wrong arithmetic stated
# as fact and tasks claimed as done without any tool call (CHANGELOG section 27).
# The cost is a pause of up to a few seconds before the first spoken word.
MODEL_THINK = True
# How long Ollama keeps the model loaded after the last request (its default is 5 minutes).
# Reloading costs about 2.4 s on the first message after a pause; the model uses ~1.4 GB.
MODEL_KEEP_ALIVE = "1h"

# Speech
STT_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 10_000_000
VOICE_LANG = "en-gb"
VOICE_SPEED = 1.1       # 1.0 is normal speed
