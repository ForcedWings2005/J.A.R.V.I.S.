# JARVIS

A private personal assistant that runs entirely on this Mac: a web dashboard with a
calendar, to-do list, notes, voice input and spoken replies. Nothing leaves the machine
unencrypted (only the encrypted backups, see below).

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
cd ~/Developer/jarvis
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements.txt -r requirements-dev.txt
```

`--require-hashes` makes pip check every downloaded file against the fingerprint recorded
for it, and refuse anything that differs (see Dependencies below).

You also need:

- Ollama with the model below (`ollama pull gemma4:26b`)
- `ffmpeg` (`brew install ffmpeg`)
- The Kokoro files `kokoro-v1.0.onnx` and `voices-v1.0.bin` in `models/`
  (they are too large for git)
- The Whisper model (about 1.5 GB). JARVIS loads it offline and never checks for updates
  (CHANGELOG section 45), so download it once yourself. Run the same command later to
  update it on purpose:

  ```bash
  HF_HUB_OFFLINE=0 python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-turbo')"
  ```

## Run

```bash
source .venv/bin/activate
python -m uvicorn server:app --reload
```

Open http://127.0.0.1:8000 and hard refresh with Cmd+Shift+R. The header shows whether
Ollama answers (green or red dot) and when the last backup was made; press / to jump to
the command box.

The header's space names (**1 HOME · 2 WORK**) switch between spaces: Home is the dashboard,
and Work (being built, CHANGELOG section 50) has its own panels, with JARVIS docked on the
right. Click a name, press `1` or `2` (not while typing), or open `127.0.0.1:8000/#work`;
Back returns to the previous space.

Clicking a panel opens it with a short "access" animation; click anywhere or press
Escape to skip it. After 3 minutes without the mouse or keyboard the panels dim and the
orb takes the stage; move the mouse to bring them back. The REDUCE MOTION switch in the
header turns every animation off.

## Settings and logs

- Settings (model, voice speed, limits, folders) are in `config.py`.
- Each message, tool call and reply is logged with timings to `logs/jarvis.log`
  (and the terminal). The file rotates at 1 MB, keeping 5 old ones. It contains what
  you said to JARVIS, so it stays on this Mac; `logs/` is not in git.
- When JARVIS does something odd, check the log for what it actually did. Its own
  explanation afterwards is a guess, not a record.
- The note tools are logged as lengths only, never their words (see Notes below).

## Notes

Tell JARVIS small facts and preferences to keep: "remember that my favourite food is
sushi". It uses them when they matter ("what should I have for dinner?"), or ask "what do
you remember about me?".

- Saving and forgetting show a card; nothing changes until you click it.
- Mention a lasting preference in passing ("I love sushi, by the way") and JARVIS offers
  a card to save it. Ignore the card if you don't want it; it expires after 5 minutes.
  Moods ("I'm tired") get no card.
- "Remember **to** call the bank" is a to-do task, not a note.
- Passwords, PINs and other secrets are refused: keep them in a password manager.
- A forgotten note is wiped from `jarvis.db`, but old backups keep it for up to 7 days
  (plain) or 30 days (encrypted), and copies in iCloud Drive until you delete them.

## Tests and checks

```bash
python -m pytest        # calendar logic tests (never touches the real database)
ruff check .            # lint
```

Both also run automatically on GitHub for every push, and before every commit once
`pre-commit install` has been run.

## Model evals

The tests check the code. The evals check the model: 56 real requests ("add piano
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

It also checks speed (CHANGELOG section 48). Lines appear as each case finishes, even when
the output goes to a file. A run over 30 seconds is marked `SLOW` on its case's line. At the
end come the median time per run and to the first word, the five slowest runs with the
tokens they wrote, and any case at least 1.5 times and 3 seconds slower than in the last
full run of the same model. Speed only warns: timings depend on what else the Mac is doing.

## Backups

`jarvis.db` holds the real calendar and tasks and is not in git.

- The first time the server starts each day, it saves a snapshot to `backups/`
  before anything touches the database. The newest 7 days are kept.
- `python backup_db.py` takes a fresh backup of today right now, then an encrypted copy
  of it. A launchd job runs it every night at 03:00.

To restore (stop the server first):

```bash
cp jarvis.db jarvis.db.broken
cp backups/jarvis-YYYY-MM-DD.db jarvis.db
```

### Encrypted copies (for keeping off this Mac)

The nightly run also saves an encrypted copy to `backups/encrypted/` (newest 30 kept).
They are locked with the public key in `backup_public_key.txt`; only the private key, kept
on paper, can open them. See `SECURITY.md` section 5 for why.

Run these yourself, in your own Terminal (never through an AI tool: the private key must
not leave this Mac).

- **Once, to set up:** `python backup_keys.py`. It shows the private key once, asks you to
  type it back from the paper, then saves only the public key.
- **To keep them off this Mac:** copy `backups/encrypted/` into iCloud Drive in Finder,
  for example once a week.
- **To restore one:** `python restore_backup.py backups/encrypted/jarvis-YYYY-MM-DD.db.enc`.
  It asks for the key without showing it, checks the result, and writes
  `jarvis-restored.db`; it never replaces `jarvis.db` itself.
- **Once after setting up, practise:** restore last night's copy with the paper key. A
  backup that has never been restored is not known to work. Afterwards, remove
  `jarvis-restored.db` with Delete Immediately (or empty the Trash): it is an unencrypted
  copy of everything, and a file deleted in Finder only moves to the Trash.
- **When copying to iCloud Drive, use Copy and Paste, not drag:** dragging into iCloud
  Drive moves the files out of `backups/encrypted/`. Copy only that folder, never the plain
  backups, `jarvis.db` or `logs/`.

## Dependencies

What JARVIS uses directly is listed in `requirements.in` (about 8 packages), and what the
checks need in `requirements-dev.in`. The two `.txt` files are generated from them by
`pip-compile` (from `pip-tools`): every package that gets installed, its exact version, why
it is there (`# via ...`), and a fingerprint (hash) of every file. Never edit the `.txt`
files by hand. To add a package, put it in the right `.in` file (ask first: CLAUDE.md), or to
upgrade one, then regenerate both files in this order and install again:

```bash
pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --allow-unsafe --strip-extras --output-file=requirements-dev.txt requirements-dev.in
pip install --require-hashes -r requirements.txt -r requirements-dev.txt
```

To upgrade one package, add `--upgrade-package <name>` to the first command. Without it,
`pip-compile` keeps every version that is already in the file, so nothing changes by itself.

## Pinned model

A tag such as `gemma4:26b` can point to a newer build after `ollama pull`. If JARVIS
suddenly behaves differently, check this first. (This happened to `gemma4:latest`: by
2026-10-21 it pointed to a different build from the one JARVIS had been tested with.)

| Model | ID (from `ollama list`) | Date recorded |
|---|---|---|
| gemma4:26b | `001e5dafc3c7` | 2026-10-21 |

## Project history

See `CHANGELOG.md`.