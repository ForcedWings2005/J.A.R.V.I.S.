# JARVIS

A private personal assistant that runs entirely on this Mac: a web dashboard with a
calendar, to-do list, voice input and spoken replies. Nothing leaves the machine.

## How the pieces fit

```
Browser (static/index.html)
   |  HTTP, 127.0.0.1 only
server.py (FastAPI)
   |-- brain.py   the assistant: calls the model, runs tools, keeps the conversation
   |     |-- Ollama (gemma4)         the language model
   |     `-- jcal.py                 calendar logic  -->  jarvis.db (SQLite)
   |-- speech.py  text to speech (Kokoro)
   `-- mlx-whisper                   speech to text
```

Rule of thumb: anything that must be right (dates, conflicts, deletes) is checked in
code, not left to the model.

## Setup

```bash
cd ~/Desktop/jarvis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You also need:

- Ollama with the model below (`ollama pull gemma4:latest`)
- `ffmpeg` (`brew install ffmpeg`)
- The Kokoro files `kokoro-v1.0.onnx` and `voices-v1.0.bin` in `models/`
  (they are too large for git)

## Run

```bash
source .venv/bin/activate
python -m uvicorn server:app --reload
```

Open http://127.0.0.1:8000 and hard refresh with Cmd+Shift+R.

## Settings and logs

- Settings (model, voice speed, limits, folders) are in `config.py`.
- Each message, tool call and reply is logged with timings to `logs/jarvis.log`
  (and the terminal). The file rotates at 1 MB, keeping 5 old ones. It contains what
  you said to JARVIS, so it stays on this Mac; `logs/` is not in git.
- When JARVIS does something odd, check the log for what it actually did. Its own
  explanation afterwards is a guess, not a record.

## Tests and checks

```bash
python -m pytest        # calendar logic tests (never touches the real database)
ruff check .            # lint
```

Both also run automatically on GitHub for every push, and before every commit once
`pre-commit install` has been run.

## Model evals

The tests check the code. The evals check the model: about 30 real requests ("add piano
every Tuesday at 4pm", "how are we looking tonight") run through the real assistant
against a frozen clock and a throwaway database, and are scored on the tools it calls
and what it says. Ollama must be running. A full run takes about 10 minutes.

```bash
python -m evals                     # every case, 3 runs each
python -m evals --runs 1 -k delete  # quick: only cases with 'delete' in the name
python -m evals -v                  # also show the reply and tool calls of failures
```

Run it before and after every prompt or model change, and put both scores in the commit
message. Cases live in `evals/cases.py`; results are saved to `evals/results/` (not in git).

## Backups

`jarvis.db` holds the real calendar and tasks and is not in git.

- The first time the server starts each day, it saves a snapshot to `backups/`
  before anything touches the database. The newest 7 days are kept.
- `python backup_db.py` takes a fresh backup of today right now.

To restore (stop the server first):

```bash
cp jarvis.db jarvis.db.broken
cp backups/jarvis-YYYY-MM-DD.db jarvis.db
```

## Pinned model

Ollama's `latest` tag can change when Ollama updates. If JARVIS suddenly behaves
differently, check this first.

| Model | ID (from `ollama list`) | Date recorded |
|---|---|---|
| gemma4:latest | `dc35e8d9c606` | 2026-10-12 |

## Project history

See `CHANGELOG.md`.