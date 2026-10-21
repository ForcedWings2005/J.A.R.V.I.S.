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
# Encrypted copies, made for leaving this Mac (SECURITY.md section 5). Locked with the
# public key below; the private key that unlocks them is on paper, never on this Mac.
BACKUP_ENCRYPTED_DIR = BACKUP_DIR / "encrypted"
BACKUP_ENCRYPTED_KEEP_DAYS = 30
BACKUP_PUBLIC_KEY = ROOT / "backup_public_key.txt"
LOG_DIR = ROOT / "logs"
STATIC_DIR = ROOT / "static"
MODELS_DIR = ROOT / "models"

# Language model (Ollama). Check the pinned ID in README.md after an update.
# gemma4:26b replaced gemma4:latest (the small e4b) after evals on both: just as reliable,
# and about twice as fast, because only about 4 billion of its 26 billion parameters work
# on each word (CHANGELOG section 37). 31b was as reliable but 6 times slower.
MODEL = "gemma4:26b"
MAX_ROUNDS = 4          # tool rounds per message, so a confused model can't loop forever
# gemma4 "thinks" (hidden reasoning) before it answers. Keep it ON: with it off, replies
# came 7x faster but the evals fell from 102/102 to 73/102, with wrong arithmetic stated
# as fact and tasks claimed as done without any tool call (CHANGELOG section 27; measured
# on the small e4b model, not yet on 26b).
# The cost is a pause of up to a few seconds before the first spoken word.
MODEL_THINK = True
# How long Ollama keeps the model loaded after the last request (its default is 5 minutes).
# Loading gemma4:26b takes about 3 s on the first message after a pause (measured
# 2026-10-21); it is 18 GB on disk.
MODEL_KEEP_ALIVE = "1h"
# The conversation is trimmed when the model was given more than HISTORY_MAX_TOKENS
# (gemma4:26b's window is 262144), down to about HISTORY_KEEP_TOKENS, oldest exchanges
# first. Each trim makes Ollama re-read everything once, so it cuts a lot, rarely.
HISTORY_MAX_TOKENS = 60_000
HISTORY_KEEP_TOKENS = 30_000
# A delete card left unanswered this long can no longer be confirmed (ask again instead).
CONFIRM_TIMEOUT_SECONDS = 300

# Notes and memory (SECURITY.md section 5): trivial preferences, never secrets
NOTE_MAX_CHARS = 300
NOTES_RECALL_LIMIT = 5     # notes given to the model per recall

# Speech
STT_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 10_000_000
VOICE_LANG = "en-gb"
VOICE_SPEED = 1.1       # 1.0 is normal speed
