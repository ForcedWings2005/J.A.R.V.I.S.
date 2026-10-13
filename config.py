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

# Speech
STT_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 10_000_000
VOICE_LANG = "en-gb"
VOICE_SPEED = 1.1       # 1.0 is normal speed
