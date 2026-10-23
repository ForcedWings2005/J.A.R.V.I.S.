# JARVIS Project Changelog

A local, private personal assistant with a web dashboard, calendar, to-do list and voice.
Runs on a MacBook Pro (M3 Max, 64 GB). Everything runs on this machine.

Written 2026-10-08, last updated 2026-10-12. Entries are in the order the work was done.

---

## Current file layout

```
jarvis/
├── brain.py            The assistant: model calls, tool loop, confirmations, system prompt
├── tools.py            The tool registry (@tool) and NeedsConfirmation
├── tasks.py            To-do list tools
├── calc.py             The calculate tool (safe, no eval)
├── notes.py            Notes and memory: remember, recall, forget (FTS5 search)
├── config.py           Settings: model, paths, limits, voice
├── database.py         The shared database connection and schema migrations
├── jcal.py             Calendar logic and tools: durations, repeats, exceptions, conflicts
├── server.py           Web server (FastAPI): endpoints for the page
├── speech.py           Text-to-speech (Kokoro)
├── speech_text.py      Text clean-up before speaking: numbers, pronunciations
├── backup_db.py        Backs up jarvis.db (SQLite backup API, 7 days kept), then an encrypted copy
├── backup_crypto.py   Encryption for backups: two keys (X25519), the file format
├── backup_keys.py     Makes the backup key pair; run once by the owner only
├── restore_backup.py  Opens an encrypted backup with the paper key; owner only
├── backup_public_key.txt  The public key (only locks; meant to be in git)
├── static/
│   ├── index.html      The dashboard page: only its structure
│   ├── css/jarvis.css  Its styles
│   └── js/             Its scripts, loaded in order: orb, chat, tasks, voice, calendar, app
├── models/
│   ├── kokoro-v1.0.onnx
│   └── voices-v1.0.bin
├── jarvis.db           SQLite database (events and tasks; not in git)
├── .gitignore          Files git should skip
├── requirements.txt    Pinned package versions
├── requirements-dev.txt  What the checks need (CI installs only this)
├── backups/            The backups (not in git)
├── logs/               jarvis.log, rotating (not in git)
├── tests/
│   ├── conftest.py     Test setup: temporary database and frozen clock
│   ├── test_jcal.py    Automated tests for the calendar logic
│   ├── test_database.py  Tests for the schema migrations
│   ├── test_brain.py   Tests for the assistant loop, with a fake model
│   ├── test_tasks_calc_tools.py  Tests for the to-do list, calculator and registry
│   ├── test_server.py  Tests for the web endpoints
│   ├── fakes.py        A fake model that plays back scripted replies
│   ├── test_speech_text.py  Tests for the text clean-up before speaking
│   ├── test_evals.py   Tests for the eval suite's matching rules
│   ├── test_notes.py   Tests for remember, recall and forget
│   └── test_backup.py  Tests for backups: plain, encrypted, restore, keys
├── evals/              Model evaluation suite (python -m evals)
│   ├── cases.py        The 30 cases
│   ├── check.py        How a run is scored
│   ├── __main__.py     The runner
│   └── results/        One JSON file per run (not in git)
├── pytest.ini          Tells pytest where the tests are
├── ruff.toml           Lint settings
├── .pre-commit-config.yaml  Checks that run before every commit
├── .github/workflows/tests.yml  Runs lint and tests on GitHub for every push
├── experiments/        Not part of the app: old scripts, crypto_lab.py, attack_page.html
├── README.md           Setup, run, tests, backups, pinned model
├── CLAUDE.md           Instructions for Claude Code when it works on this project
├── plan.md             The plan from Phase 2 onward
├── SECURITY.md         Threat model: what JARVIS holds, who could harm it, what stops them
└── CHANGELOG.md        This file
```

## Run it

```bash
cd ~/Desktop/jarvis
source .venv/bin/activate
python -m uvicorn server:app --reload
```

Then open http://127.0.0.1:8000 and hard refresh with Cmd+Shift+R.

Note: the project now lives in `~/Desktop/jarvis`. A virtual environment cannot be moved with its folder, so after moving the project it has to be rebuilt (`rm -rf .venv`, `python3 -m venv .venv`, activate, then `pip install ollama fastapi uvicorn mlx-whisper python-multipart kokoro-onnx`). Always start the server from inside the project folder, because the code uses relative paths such as `jarvis.db`, `static/index.html` and `models/`.

Run the tests (from the project folder, venv active): `python -m pytest`. They never touch the real `jarvis.db`.

## Dependencies

- Ollama with the `gemma4:latest` model (also pulled: `mistral:latest`, `qwen3.5:latest`)
- Python packages: `ollama`, `fastapi`, `uvicorn`, `mlx-whisper`, `python-multipart`, `kokoro-onnx`
- Development only: `pytest` (to run the tests)
- System: `ffmpeg` (via Homebrew)
- Downloaded models: Whisper `mlx-community/whisper-large-v3-turbo`, Kokoro `kokoro-v1.0.onnx` and `voices-v1.0.bin`

---

## 1. Foundation: model and tool calling

- Set up the project folder and a Python virtual environment (Python 3.13).
- Wrote `smoke_test.py` to check that a local model can call a function.
- Mistral passed the first test: it chose `get_events` and extracted the date correctly.
- Fixed two beginner errors along the way: a wrong import line (`import ollama.mistral` became `import ollama`) and a placeholder model name.

## 2. Terminal agent (`agent.py`)

- Built the agent loop: the model requests a tool, the code runs it, the result goes back, and the model answers.
- Added a system prompt with the current date, time and timezone, so relative dates like "tomorrow" work.
- Added instructions about when to use tools and when not to.
- Made it a continuing conversation, with the message history kept in a list.
- Added a debug line that prints each tool call.
- Found problems with Mistral: it sometimes printed the tool call as text instead of running it, guessed wrong dates (for example, "next Friday"), and once invented an answer without checking the calendar.

## 3. Model comparison (`compare.py`)

- Wrote an automated test: 5 questions, 3 runs per model, with expected dates computed in code.
- Results (out of 5, three runs each):

| Model | Scores | Avg time per session |
|---|---|---|
| mistral:latest | 3, 4, 3 | 6.2s |
| gemma4:latest | 5, 5, 5 | 17.8s |
| qwen3.5:latest | 5, 5, 5 | 23.2s |

- Chose **gemma4:latest** as the main model. Mistral is no longer used.

## 4. Real calendar with a database

- Replaced the fake event function with a SQLite database (`jarvis.db`, table `events`).
- Added `add_event` with checks done in code, not by the model:
  - invalid date or time format is rejected
  - times in the past are rejected
  - double-booking the same date and time is rejected
- Added rules to the system prompt: ask for a missing time, ask AM or PM when unclear, only claim success if the tool returned success, and report errors plainly.
- Added `run_tool`, which handles unknown tools and bad arguments without crashing.
- Replies are now written to be spoken: one to three short sentences, no markdown.

## 5. Web server and first dashboard

- Split the code into `brain.py` (logic) and `server.py` (web server).
- Added endpoints: `GET /` (page), `POST /chat`, `GET /events`.
- Added locks so the database and the conversation are safe with multiple requests.
- The system prompt is rebuilt on every turn so the date never goes stale.
- Built a first plain chat page with a Today and Tomorrow sidebar.

## 6. HUD redesign

- Agreed the design in a mockup: sci-fi HUD, dark cyan and blue, animated orb in the center, panels around the edges that expand when clicked.
- Replaced `index.html` with the HUD layout (the old page is saved as `index_old.html`).
- The orb is drawn in code from a fixed random seed: dashed rings, radial streaks, circuit-like fragments, swoosh arms and a pulsing core.
- Orb states: idle, listening, thinking, speaking. Each changes the animation speed.
- Click a panel to expand it; press Esc or click the dark area to close.
- Reduce-motion switch (saved in the browser), plus automatic support for the system setting.
- Layout collapses to one column on narrow screens.

## 7. Activity ticker and confirmation card

- `chat()` now returns the reply, the list of tool steps, and any pending confirmation.
- The page shows the steps under the transcript (done, error or waiting).
- Added `delete_event`. The model can only request a deletion; nothing is deleted until the Confirm button is clicked.
- New endpoint `POST /confirm`, called only by the buttons. Only one request can be pending at a time.
- The tool loop can now run several rounds (capped at 4) so a confused model can't loop forever.
- Added a transcript view showing what you said and what JARVIS replied.

## 8. To-do list

- Added a `tasks` table and tools `add_task`, `list_tasks`, `complete_task`.
- Duplicate open tasks are rejected.
- Tasks have no time; events do. The tool descriptions teach the model the difference.
- New endpoints: `GET /tasks`, `POST /tasks/{id}` (checkbox toggle).
- The To-do panel shows live tasks with checkboxes and due dates.
- Fixed a bug where `loadTasks()` was never called, so new tasks didn't appear in the panel.

## 9. Security checks

- Confirmed the server only listens on `127.0.0.1:8000` and Ollama only on `localhost:11434`.
- Added `TrustedHostMiddleware` so requests with any other `Host` header are rejected (protects against DNS rebinding).
- Verified: a request with a fake host returns 400; the normal address returns 200.
- Still to do before any phone or network access: a login on every endpoint, and HTTPS.

## 10. Voice input

- Added `POST /transcribe` using `mlx-whisper` (runs on the Mac's GPU, fully local).
- Browser records with `MediaRecorder` and uploads the clip; the server returns text, which is sent to the assistant like typed input.
- Uploads are limited to 10 MB, written to a temporary file and deleted afterward.
- Clips under half a second are ignored.
- The microphone is only opened during a recording and released afterward.

## 11. Voice output

- Added `speech.py` with the Kokoro text-to-speech model. It started with the British voice `bm_george`; it now uses a 50/50 blend of `bm_daniel` and `bm_lewis` at speed 1.1.
- A small pronunciation table in `speech.py` respells hard words before they are spoken (Hephaestus, Trastevere, piazza). Add more entries there as needed.
- Speaking speed is set by `SPEED` in `speech.py`, currently 1.1 (slightly faster than normal). Change that one number to adjust it.
- Autoplay fix: browsers block audio that starts without a click. The page now plays a tiny silent clip (`unlockAudio`) the first time you click the voice switch or press the mic button. After that, spoken replies are allowed to play on their own.
- New endpoint `POST /speak` returns a WAV file.
- The page plays replies and sets the orb to speaking while audio plays.
- Starting a recording stops JARVIS mid-sentence.
- Markdown characters are stripped before speaking.

## 12. Voice mode master switch

- Added a **VOICE MODE** switch in the header, **off on every page load**.
- While it's off: the mic button is disabled, Space does nothing, the microphone is never requested, and replies are silent.
- Mic button: hold to talk, or tap to start and tap again to stop.
- Recordings stop automatically after 30 seconds.
- Switching voice mode off cancels any recording and discards the audio.
- Space bar works as push-to-talk only when the text box is empty and no button has focus.

## 13. Personality, calculator and honesty rules

These were already in `brain.py` but had not been logged.

- JARVIS now speaks as a composed, polite British butler with dry wit, and addresses the user as "sir".
- Added a `calculate` tool. It evaluates math safely by parsing the expression (numbers, operators, `sqrt`, `sin`, `log`, `pi` and similar), never with `eval`, and it caps huge exponents. The prompt tells the model to use it for anything beyond trivial arithmetic.
- JARVIS is also a general-knowledge assistant and never says a topic is outside its role.
- If it is not confident (names, dates, numbers, quotes, recent events), it must say so instead of guessing or inventing details.
- Reply length: two to four sentences by default, up to about eight when the user asks for more detail. Still plain speech, no markdown.

## 14. Calendar upgrade: durations, repeats, new views

- **Renamed `calendar.py` to `jcal.py`.** The old name matched a Python standard-library module and could shadow it.
- **`jcal.py` now holds all calendar logic.** `brain.py` calls it for `get_events` and `add_event`, and uses `find_for_delete` and `apply_delete` for deletions. The old event code in `brain.py` was removed, and the event tool definitions now come from `jcal.EVENT_TOOLS`.
- **Durations.** Events have a start and an end time (for example 10:00 to 11:15). If no end time is given, it defaults to one hour. Conflict checks now catch overlapping time ranges, not just identical start times.
- **Repeating events.** Repeat options are none, daily, weekdays (Monday to Friday only), weekly, biweekly and monthly, with an optional end date (`repeat_until`). Repeats are stored as one row and expanded when read.
- **Specific weekdays.** New `repeat_days` option (for example `wed,fri`) for events like "every Wednesday and Friday". The start date slides forward to the first listed day that is still in the future.
- **Deleting one occurrence.** New `event_exceptions` table. Deleting with scope "this" skips just that date; scope "all" removes the whole series. The confirmation card says which one.
- **Range queries.** `get_events` accepts an end date, up to 62 days, so "what's my week look like" is one call.
- **Database upgrade.** The `events` table gets the new columns (`end_time`, `repeat_rule`, `repeat_until`, `repeat_days`) automatically on start. Existing events are kept.
- **Prompt changes.** The system prompt now lists the next 14 dates with weekday names, so the model does not count days itself. New rules cover durations, repeats, `repeat_days`, asking when an end is only a month name ("until December"), and describing an added event exactly as the tool result states.
- **Bug found and fixed.** A request for "every Wednesday and Friday" was saved as `weekdays` (every Monday to Friday), because no option could express two specific days, and JARVIS then described it as Wednesday and Friday. Fixed with `repeat_days` and the stricter reply rule.
- **New endpoint.** `GET /calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` returns every occurrence in a range (repeats expanded, maximum 400 days). It replaces `GET /events`, which was removed.
- **Compact Schedule panel.** Shows the next 7 days as an agenda, with larger text, sticky day headings, a "Nothing scheduled" line for empty days, and scrolling.
- **Expanded calendar.** Opens on a year view. Click a month to open it, click a day to see its week, click a day header to see that day. Year, Month, Week and Day tabs, previous and next arrows, and a Today button jump around directly. The week and day views are hour grids where an event's height matches its length, overlapping events sit side by side, and a red line marks the current time. Repeating events show a repeat symbol and a label such as "weekly on Wed, Fri".
- The expanded calendar refreshes after every chat message, so events JARVIS adds appear immediately.

## 15. Streaming replies into speech

- `brain.py` gets a new `chat_stream()` generator. It asks Ollama for the reply as a stream and yields small events as they happen: `delta` (a piece of text), `step` (a tool just ran), `break` (a tool round finished), `done` (steps and any pending confirmation) and `error`. The old `chat()` is left in place but the server no longer uses it.
- `POST /chat` now returns a stream of newline-separated JSON events (NDJSON) instead of one JSON object.
- The page reads the stream, shows the reply as it is written, and updates the ticker live as tools run.
- The page cuts the incoming text into sentences (it will not split after "Dr.", "Mr.", "a.m." and similar) and sends each finished sentence to `/speak` straight away. Clips are played in order, and the next clip is already being made while the current one plays.
- Result: JARVIS starts talking after the first sentence is written, instead of after the whole reply.
- Speech playback was rewritten around a per-reply "speaker" with a queue. Starting a new message, starting a recording or turning voice mode off cancels the queue and stops the audio.
- Confirmation results (after you click Confirm or Cancel) still use the same speaker, one sentence at a time.

## 16. Incident: a finished class listed as still ahead

What happened (evening of 2026-10-09):

- Asked "how are we tonight", JARVIS said it was a quiet evening with one commitment, the class in the calendar. The class had finished that morning.
- Asked why, JARVIS answered that it had focused on the recurring commitment without checking its start time against the time of day, and said it had taken measures to refine how it reads time-sensitive data.

What we learned:

- **JARVIS's explanation is not a diagnosis.** The model writes a plausible reason after the fact. It cannot see why it answered as it did, and it cannot change itself. Nothing was changed, and the conversation resets when the server restarts, so no "measures" were taken.
- **Likely real cause:** `get_events` returns everything on a date with no sign of which events have already ended. The model had to compare each event's time with the current time in the system prompt, and it did not. This fits the earlier finding that the model is unreliable at date and time arithmetic (sections 2, 3 and 14).

Fix (written; the logic is covered by automated tests, but not yet confirmed in a real conversation with JARVIS):

- The time comparison now happens in code. In `jcal.py`, a new helper `_status()` labels each event as `finished`, `in progress` or `upcoming` by comparing its start and end time with the current time. Events on earlier dates are `finished`; events on later dates get no label.
- `get_events` now adds that label to each event (for example `10:00-11:15 Biological anthropology class [finished]`) and states the current day and time at the start of its result.
- If every event today has finished, the result ends with "Nothing further is left today.", so the model reads the answer instead of working it out.
- An event with no end time counts as lasting one hour, the same default used when events are added.
- The system prompt in `brain.py` gained rules: events marked finished have already happened and must not be described as ahead, questions about the rest of the day or evening should check today's events, and if nothing is left the answer is to say so.
- Checked with a copy of the calendar module and a fake clock at 09:00, 10:30, 12:00, 19:30 and 21:00. The labels and the closing sentence came out as expected. Not yet tried with the real assistant.

## 17. Version control (git)

- The project is now a git repository, with a remote repo for backup and history.
- A `.gitignore` keeps these out of the repo: `.venv/` (rebuildable), `__pycache__/`, `.DS_Store`, `.env`, `jarvis.db` (your real schedule and tasks, private) and `models/` (the Kokoro files are too large for GitHub).
- `requirements.txt` (made with `pip freeze`) records the exact package versions, so the environment can be rebuilt with `pip install -r requirements.txt`.
- To set up on a new machine, the Kokoro model files must be downloaded again into `models/`, because they are not in the repo.
- Habit from now on: commit after each change that works, so a bad edit can be undone.
- `models/` and `jarvis.db` are not in git, so git does not back them up. The database needs its own backup.
- Include `CHANGELOG.md` in each commit, so the log and the code stay in step.
- The first push succeeded on 2026-10-10. GitHub's repo already held an automatic "Initial commit", so the push was rejected at first; `git pull origin main --rebase` placed the local commit on top of it and the second push worked. The remote is `origin`, and `main` tracks `origin/main`.
- Status: set up and pushed.

## 18. Automated tests for the calendar

- Added `tests/test_jcal.py` (51 checks) and `tests/conftest.py`, run with `python -m pytest`. `pytest.ini` points pytest at the `tests` folder.
- **One change to `jcal.py`:** the database file name now comes from the `JARVIS_DB` environment variable and falls back to `jarvis.db`. Normal use is unchanged. The tests set it to an in-memory database, so they can never touch the real calendar.
- **Frozen clock:** every test runs as if it were Monday 2030-01-07 at 08:00 (a replacement for `datetime` inside `jcal`). Results do not depend on the real date, and times that would normally be "in the past" can be tested.
- **What is covered:** adding events (defaults, end times, bad input, past times), overlap and back-to-back conflicts, every repeat rule, `repeat_days` (the Wednesday and Friday bug), repeat end dates, conflicts checked into the future, deleting one occurrence or a whole series, sorting, range limits, and the finished / in progress / upcoming labels (the "how are we tonight" bug), including the exact minute boundaries.
- **Known limit pinned by a test:** a monthly repeat on the 31st skips short months.
- Checked by breaking the code on purpose (labels one minute late, back-to-back counted as a clash, `repeat_days` ignored, weekdays including Saturday, deleting one occurrence deleting all, past-time check removed). Every break made at least one test fail.
- Not covered yet: the model's behavior (whether it picks the right tool and arguments), `brain.py`, and the web endpoints.
- `.gitignore` should also list `.pytest_cache/`.
- **First run on the real project (2026-10-10): 46 passed, 5 failed.** All five failures are the delete tests, with the same error: `jcal` has no attribute `find_for_delete`. The copy of `jcal.py` on the Mac is missing that function, and probably `apply_delete`, which sits next to it. This means deleting an event through JARVIS would also have failed. The tests found it before it showed up in use.
- All of the other checks pass on the real code, including repeats, `repeat_days` and the finished / upcoming labels.
- **Fixed:** `find_for_delete` and `apply_delete` were restored in `jcal.py`, and all 51 tests now pass on the Mac. Lesson: the tests caught a lost function that would have broken deleting in real use, which is the reason to keep them and run them before every commit.

## 19. Phase 1: protect what exists

Applied on the Mac on the branch `phase1-protect` (as of 2026-10-12): the first backup file was created, the dead code is removed and the old scripts are in `experiments/`, `ruff check .` passes with no findings, and the pre-commit hook is installed. The branch was merged into `main` on 2026-10-12 (a fast-forward, 13 files changed) and pushed, and the branch was deleted. The GitHub Actions run on `main` is green (confirmed 2026-10-12). The model ID was recorded in section 20. The nightly job turned out to be in place already (section 24).

- **Database backups.** New `backup_db.py` uses SQLite's backup API, which is safe while the server runs (a plain file copy is not). It writes one file per day to `backups/`, checks the copy with `PRAGMA integrity_check` before keeping it, and keeps the newest 7 days. `python backup_db.py` takes a fresh backup now. `server.py` also calls it at startup, before `brain` and `jcal` open the database, but only if today has no backup yet, so the first start of the day keeps a snapshot from before anything changed. If a backup fails, the server still starts and prints the error.
- **Automatic checks on GitHub.** `.github/workflows/tests.yml` runs `ruff check .` and `python -m pytest` on every push and pull request. It installs only `pytest` and `ruff`, which is enough because `jcal` uses only the standard library.
- **Ruff linter.** `ruff.toml` selects the E (style), F (real mistakes) and B (likely bugs) rule sets, ignores long lines, skips `experiments/` and `backups/`, and tells the bugbear rules that FastAPI's `File(...)` default is fine.
- **Pre-commit hook.** `.pre-commit-config.yaml` runs ruff and the tests before every commit using the tools already in the venv, so a failing check stops the commit. Commit from the terminal with the venv active.
- **Dead code removed.** The unused `chat()` function in `brain.py` is deleted (`chat_stream()` replaced it). `agent.py`, `compare.py` and `smoke_test.py` move to `experiments/` with `git mv`, so their history is kept. `agent.py` opens `jarvis.db` in the current folder when run, which is a reason not to leave it in the project root. `static/index_old.html` is removed, since git history already holds it.
- **Lint fixes expected from the change:** the `import ast`, `math` and `operator` lines in the middle of `brain.py` move to the top (E402); `raise HTTPException` inside an `except` in `server.py` gets `from None` (B904); `conftest.py` marks its imports after the environment setting with `# noqa: E402`.
- **Model pinned.** The README records the Ollama model ID, so a change in how JARVIS behaves can be checked against a model update.
- **README added**, with setup, run, tests, backups and restore steps, and a diagram of how the pieces fit.
- `.gitignore` gains `backups/`, `.ruff_cache/` and `*.log`.
- Checked in the sandbox: the backup script (snapshot, no-overwrite, overwrite, 7-day cleanup, missing database), the YAML and TOML files parse, and all 51 tests still pass with the changed `conftest.py`.
- Optional extra: a macOS nightly job (launchd) running `backup_db.py` at 03:00. macOS may block background access to the Desktop folder, so the startup snapshot is the main protection.

## 20. Cleanup after Phase 1

- **`brain.py` respects `JARVIS_DB`**, like `jcal.py` already did, so tests can never open the real database through `brain`.
- **Calculator size cap.** Results above 10^300 are rejected with "the number is too large to work with". Before, something like `(10**1000)**1000` got past the exponent cap, built a million-digit number, and then crashed the whole turn when it was turned into text.
- **A crashing tool no longer aborts the turn.** `run_tool` used to catch only bad arguments. Any other error now becomes an `Error:` tool result the model can report, and the crash is printed in the server log. Before, the stream stopped and left the conversation with a tool call that had no result.
- **`complete_task` matches literally.** It used SQL `LIKE`, so `%` or `_` in the title acted as wildcards. It now uses a plain substring match.
- **Model ID recorded** in the README: `gemma4:latest` is `dc35e8d9c606` (from `ollama list`, 2026-10-12).
- Small tidying: an unused `VOICE = None` in `speech.py`, a commented-out docstring in `brain.py`, and trailing whitespace.
- The file layout above is updated: `agent.py` and `compare.py` live in `experiments/`, `index_old.html` is gone, and `smoke_test.py` is no longer in the project (it never made it into git).

## 21. Phase 2: model evaluation suite

Work on the branch `phase2-evals`. See `plan.md` for why: every incident so far came from the model, and nothing measured it.

- **`python -m evals`** runs 30 real requests through the real `brain.chat_stream`, 3 times each. Every run uses a frozen clock (Monday 2030-01-07) and a throwaway in-memory database, so the real calendar is never touched and the expected dates never change.
- **What is scored:** which tools were called and with which arguments, what a tool reported back (for repeats, where `repeat: weekly` and `repeat_days: tue` both save the same thing), and simple checks on the reply (must mention, must not claim, must ask). A run passes only if every check passes.
- **Cases** cover chat with no tools, admitting it does not know, the calculator, reading the calendar (including the "how are we tonight" incident), adding events (default hour, durations, end times, conflicts), asking when the time, AM/PM or end date is unclear, every repeat rule (including the Wednesday and Friday incident), deleting (one-off, one occurrence, a whole series), and the to-do list.
- **Results** are saved to `evals/results/` as JSON with the model ID and a hash of the system prompt and tool descriptions, so two runs can be compared.
- **`tests/test_evals.py`** (50 checks) tests the scoring rules, and that every case only names tools and arguments that really exist. CI now also installs `ollama`, because the test imports `brain`.
- **Lesson from the first runs:** a reply check written as exact phrases is too strict. JARVIS speaks numbers as words ("four hundred nine and a half"), asks without a question mark ("I will require a specific time"), and says "outside of my knowledge" rather than "outside my knowledge". Six apparent failures were the checks, not JARVIS, and the checks were widened. Phrase lists will keep needing care; a model-graded check is a possible later step.

**Baseline (2026-10-12):** `gemma4:latest` (`dc35e8d9c606`), prompt `e3265f593ce4`: **80/90 runs (89%), 26/30 cases pass every run**, about 7 s per request on average, 10.7 min for the whole suite.

Real failures it found:

| Case | Score | What happens |
|---|---|---|
| `delete_one_off` | 0/3 | "Cancel my dentist appointment" fails when the event is titled "Dentist". `find_for_delete` only matches when the words the user said are inside the title, not the other way round. A code bug. Sometimes the model also asks for the title instead of trying. |
| `delete_series` | 0/3 | "Delete all my piano lessons": `delete_event` requires a date even for the whole series, so JARVIS asks the user for a date instead of acting. |
| `task_complete` | 0/3 | "I bought the milk" gets a witty reply, but `complete_task` is never called. Once it even said "that item has been duly noted" without doing anything. |
| `repeat_weekdays` | 2/3 | "A standup every weekday at 9:30am": once it asked for a start date instead of using the next weekday. |

## 22. Fixes found by the evals, and decimals in speech

Done on `phase2-evals`, which was merged into `main` on 2026-10-12 (a fast-forward) and then deleted. With this, Phase 2 of `plan.md` is complete.

- **Delete matching works both ways.** "Cancel my dentist appointment" now finds an event titled "Dentist". Before, `find_for_delete` only matched when the words the user said were inside the title. New helper `_title_matches` in `jcal.py`.
- **Deleting a whole series no longer needs a date.** `delete_event` takes the date as optional when the scope is "all". Without a date it looks only at events that still have something ahead (a one-off that is today or later, or a series whose end date has not passed), and asks which one if several match. Deleting one occurrence still needs its date. The tool description says never to ask the user for a date just to delete a series.
- **Prompt: completing tasks.** Saying something is done, even casually ("I bought the milk"), now means calling `complete_task`, and JARVIS must never say a task is noted or done unless the tool succeeded.
- **Prompt: repeat start dates.** With no start date given, the first occurrence is the next matching day; JARVIS no longer asks.
- **Tests:** 6 new `jcal` tests for the delete changes (73 jcal checks now).
- **Eval result:** 30 cases × 3 runs went from **80/90 to 90/90** (prompt `cd7cf58d721e`, same model `dc35e8d9c606`). The run itself scored 88/90; the two misses were "outside of my current knowledge base", an honest answer that the phrase check did not accept, so the check was widened and the saved run rescored.

**Bug report from real use: decimals read as huge numbers.** Asked 346/9, JARVIS showed 38.4444444444 but said "38 point 44 billion 444 million ...".

- Cause: espeak, which Kokoro uses to turn text into sounds, takes the decimal point for a full stop when the text also ends with one. "The result is 38.4444444444." was read as "thirty-eight. four billion four hundred and forty-four million ...". Without the final full stop the same number was read correctly, which is why it only happened sometimes.
- Fix: new `speech_text.py` rewrites numbers before speaking: "38.4444444444" becomes "38 point 4 4 4 4" (the word "point", then each digit, rounded to 4 decimal places), and commas inside numbers are dropped ("7,006,652" becomes "7006652"). Checked against Kokoro's phonemes: it now says "thirty-eight point four four four four". The text on screen still shows the full number.
- The pronunciation table moved from `speech.py` to `speech_text.py`, so the text clean-up is tested (14 checks in `tests/test_speech_text.py`) without loading Kokoro, which CI does not have.

## 23. Phase 3: make the code testable

Done on `phase3-testable`, merged into `main` on 2026-10-12 (a fast-forward) and then deleted. Goal from `plan.md`: the code around the model gets tested as well as the calendar.

**Step 1: settings in one place.** New `config.py` holds the model name, `MAX_ROUNDS`, the database path, the folders (backups, logs, static, models), the Whisper model, the upload limit, and the voice language and speed (speed is now `VOICE_SPEED` in `config.py`). Every path is built from the project folder, so the server can be started from any folder. `JARVIS_DB` still overrides the database path.

**Step 2: one database, versioned migrations.** New `database.py` opens the one connection and lock that `brain.py` and `jcal.py` now share (before, each opened its own and both created an `events` table). The schema version is kept in SQLite's `PRAGMA user_version`, and `migrate()` runs each step newer than it, once, in order, each inside a transaction so a failed step leaves nothing half done. Step 1 is the original tables; step 2 is durations, repeats and exceptions, written so it also adopts a database from before versioning whose columns were already added by the old code. A database newer than the code is refused instead of being damaged. To change the schema later, add a step to the end of `MIGRATIONS`.

- `speech.py` loads Kokoro and `server.py` loads Whisper the first time they are used instead of on import, so the server starts faster and tests can import it without the model files.
- 6 tests in `tests/test_database.py`: a new database, running twice, a first-version database keeping its events, adopting a pre-versioning database, rolling back a failed step, and refusing a newer schema.
- The real `jarvis.db` is now at schema version 2. This happened by mistake while checking the migration on a copy (importing `database` opens the real file). Nothing else changed: same tables and rows as that morning's backup, integrity check ok. The server would have done the same on its next start.

**Step 3: one tool registry.** New `tools.py`. Each tool is now written once, with its schema in a `@tool(...)` decorator right above the function. Required arguments are worked out from the function itself (no default value means required), and the decorator refuses a schema whose arguments differ from the function's, so the two can no longer drift apart. The separate `tools` list and `available_functions` dict are gone.

- The code is split by area: calendar tools stay in `jcal.py` (now including `delete_event`), the to-do list moves to new `tasks.py`, and the calculator to new `calc.py`. `brain.py` is only the assistant.
- A tool that must wait for the Confirm button returns a `NeedsConfirmation` (the card text, what to do on Confirm, and what the model is told meanwhile). `delete_event` is the first; editing events can use the same path later.
- Checked: the hash of the system prompt plus tool descriptions is still `cd7cf58d721e`, so the model sees exactly what it saw before the change.
- Ruff caught a name clash on the way: the `/tasks` endpoint function was also called `tasks`, which would have hidden the new module. It is now `list_tasks_endpoint`.

**Step 4: an `Assistant` object.** The conversation, the pending confirmation and the lock used to be module-level globals in `brain.py`. They now belong to `brain.Assistant`, which also takes the function that talks to the model (`ollama.chat` by default). `server.py` makes one; tests and evals make their own, so a test can pass a fake model.

- New tests: `tests/test_brain.py` (17 checks, with a fake model that streams scripted replies and tool calls): a plain reply, history across turns, the prompt rebuilt each turn, the apology when there is no text, a model error, a tool round and its result fed back, several tools in one round, error steps, the round cap, unknown tools, bad arguments, a crashing tool, and the whole delete confirmation flow (card, Confirm, Cancel, a wrong or reused id, the card only on its own turn). `tests/test_tasks_calc_tools.py` (26 checks) covers the to-do list, the calculator including attempts to escape it (`__import__`, `open`), and the registry.
- 171 tests in total, all passing. The evals now use `Assistant` too; a quick live run of the three delete cases passed.

**Step 5: tests for the web endpoints.** `tests/test_server.py` (17 checks) drives the real FastAPI app with FastAPI's test client, with the model, Whisper and Kokoro replaced by fakes: the page, the host check (another host name gets 400), chat streaming with and without tools, the delete card through `/confirm` (including a reused id), `/calendar` and its bad ranges, the task checkbox and its 404, `/speak` (trimming, the 2000-character limit, empty text), and `/transcribe` (the result, the temporary file being removed, odd file names, the upload limit). The fake model now lives in `tests/fakes.py`, shared by both test files.

- **Security finding (from Phase 6 of `plan.md`, checked early):** can a web page open in another tab drive JARVIS? The JSON endpoints refuse a body sent as `text/plain` (422), and `text/plain` is the only way another site can send a body here without the browser asking permission first. So `/chat`, `/confirm` and `/tasks` are safe from that today, and a test now pins it. `/transcribe` takes a form upload, which another site can send, but it only returns text that the other site cannot read. Noted in `plan.md` for the `Origin` check.
- **CI dependencies:** new `requirements-dev.txt` (pytest, ruff, ollama, fastapi, httpx2, python-multipart, pinned to the venv's versions). CI installs it instead of a list in the workflow. Checked in a brand-new virtual environment with only that file installed: 188 passed, no warnings. It uses `httpx2`, because Starlette warns that `httpx` is deprecated for its test client.

**Step 6: logging.** The `print` lines in `brain.py` are replaced by Python's `logging`. When uvicorn starts the server, everything under the `jarvis` logger goes to `logs/jarvis.log` (rotating at 1 MB, 5 old files kept) and to the terminal. Each turn logs the user's message, every tool call with its arguments, result and time in milliseconds, and the reply with the number of rounds and tools, the time to the first text, and the total time. Confirm and Cancel are logged, a crashing tool is logged with its full traceback, and Whisper logs how long each transcription took.

- Section 16 (the "how are we tonight" incident) showed that JARVIS's own explanation of a mistake is a guess. The log is the record of what it actually did.
- The log holds what was said to JARVIS, so `logs/` is in `.gitignore`.
- Logging starts in the server's start-up code, not on import, so the tests never create a log file. 3 new tests: a turn and its tool call are logged, a crash is logged with its traceback, and starting the server writes the log file. 191 tests in total.
- **Checked with the real server:** started with uvicorn from `/tmp` (a different folder) on a spare port, pointed at a copy of the database. The page, `/calendar`, `/tasks`, a real chat with the model and `/speak` all worked. Kokoro loaded on the first `/speak` (1.5 s), and the log showed the turn: first text after 1.7 s, 1.9 s in total.

**Eval after the restructure:** 87/90 runs (prompt `cd7cf58d721e`, unchanged, so the model saw exactly the same input as in the 90/90 run). The run scored 86/90; one miss was the check matching "before anything is deleted" as a claim of deletion, so "is deleted" was dropped from that phrase list and the run rescored. With identical input, the difference from 90/90 is the model's run-to-run variation; 3 runs per case is a small sample. Two real misses worth fixing next:

| Case | Score | What happened |
|---|---|---|
| `calc_multiply` | 1/3 | The calculator returned 7006652 correctly, but JARVIS wrote it out in words wrongly: "seven million sixty-six thousand five hundred two". It spoke a wrong number although the tool had the right one. Likely fix: tell the model to keep numbers as digits, since `speech_text.py` now handles how they are spoken. |
| `ask_am_pm` | 2/3 | Once it assumed 8 AM for "Thursday at 8" instead of asking. |


## 24. CLAUDE.md, and the nightly backup job

- **New `CLAUDE.md`**: project instructions that Claude Code reads at the start of every session. It covers the architecture and what each file does, the coding conventions taken from the code, the security boundaries that exist today (and the gaps: no login, no HTTPS, no `Origin` check on `/transcribe`), the database migration rules, the test, lint and eval commands, dependencies and configuration, logging and documentation, working rules (read before editing, minimal changes, explain risky changes first, commit only when asked) and how to report finished work (exact commands and real results, what could not be verified, mistakes stated plainly). Every claim in it was checked against the code; the review caught one error in the draft (unknown upload extensions are saved as `.webm`, not refused).
- **The nightly backup job already exists.** `~/Library/LaunchAgents/com.jarvis.backup.plist` runs `.venv/bin/python backup_db.py` at 03:00 and is loaded in launchd. Section 19 and the Status table listed it as still open; they are corrected. Not yet checked: whether it has run successfully (its output goes to `/tmp/jarvis-backup.log`). It uses absolute paths, so moving the project folder, the venv or `backup_db.py` breaks it.


## 25. Fix: JARVIS spoke wrong numbers

Found by the Phase 3 eval run (section 23). Asked "What is 1234 times 5678?", the calculator returned 7006652 correctly, but JARVIS wrote the answer out in words and got it wrong: "seven million sixty-six thousand five hundred two", and in another run "seven million and sixty-six thousand, six hundred and fifty-two" (that is 7066652). The tool was right; the model's conversion of a long number into words was not. The prompt asked for replies that can be spoken, so the model spelled numbers out itself.

- **Fix (prompt):** "Always write numbers as digits, never as words, and copy them exactly as a tool result gives them, for example 7006652 or 38.4444; the speech system reads digits aloud correctly." This works because of section 22: `speech_text.py` makes sure digits are spoken correctly. Checked against Kokoro's phonemes: `7006652` is read "seven million six thousand six hundred and fifty-two", `426763565` "four hundred and twenty-six million seven hundred and sixty-three thousand five hundred and sixty-five".
- **Eval cases:** the calculator cases now require the digits (they used to accept words), and two were added: 346 divided by 9 (the decimal bug from section 22) and 98765 times 4321. 32 cases now.
- **Before and after**, the 4 calculator cases × 5 runs: **18/20** with the old prompt (`cd7cf58d721e`), including the wrong 7066652 again, and **20/20** with the new one (`65e58bd83ba7`).
- **Full eval with the new prompt:** **95/96 runs (99%)**, 31/32 cases passed every run. The one miss: `repeat_until_date` once asked for the exact end date, saying March 31st was "outside my immediate reference window". The prompt lists only the next 14 dates and says to take dates from that list, which seems to make it wary of dates further out. It passed 3/3 in every earlier run. A possible follow-up, not fixed here.
- Not yet heard in the real app.


## 26. Small follow-ups: nightly backup checked, dates beyond two weeks

Done on `small-followups`, merged into `main` on 2026-10-13 (a fast-forward) and then deleted. The third follow-up, an `Origin` check for `/transcribe`, was proposed but not done; it stays open in `plan.md` (Phase 6).

- **The nightly backup works.** launchd shows the job ran twice with exit code 0; `/tmp/jarvis-backup.log` says `saved jarvis-2026-10-12.db`, and that file is dated 03:00.
- **Bug: JARVIS thought the calendar ended two weeks from today.** The "March 31st is outside my immediate reference window" miss from section 25 led to two new eval cases with dates beyond the 14 listed in the prompt. With the old prompt (`65e58bd83ba7`) they passed **2/10**: asked "What do I have on February 20th?", JARVIS refused every time ("my calendar records only extend up to January 21st"), and it refused to add a March 3rd appointment 3 times out of 5. The list of upcoming dates in the prompt was meant as a lookup aid so the model does not count days, but the model read it as the limit of the calendar.
- **Fix (prompt):** "The list is only a lookup aid; the calendar itself has no end. For a date beyond the list, such as 'March 3rd', use the next such date that is not in the past and call the tool as usual; never tell the user a date is outside your calendar or range."
- **After** (prompt `98d8bc80df43`): the two new cases **10/10**, `repeat_until_date` 5/5. Full suite (34 cases × 3): **101/102**. The one miss: "Am I free on Friday?" on a Monday once checked the Friday a week later. Rerun 8 times it passed 8/8, so it is treated as run-to-run variation, but it is worth watching since the new rule talks about "the next such date".
- These requests take longer now (about 11-17 s instead of a quick refusal), because the model actually calls the tool.


## 27. Phase 4: conversation memory

Done on `phase4-memory`, merged into `main` on 2026-10-13 (a fast-forward) and then deleted. `plan.md` planned to trim the conversation history because it grows until the server restarts. Step 1 was to measure first.

**Step 1: measure.** Each model call now logs how many tokens the model was given, how long it took to read them, and how many it wrote (from the counts Ollama sends with its last chunk), and `Assistant.last_prompt_tokens` keeps the latest count. 1 new test; it also caught a crash I introduced when the model's stream sends nothing at all.

Findings (Ollama 0.33.1, gemma4 on this Mac):

- **The context window is not the problem.** Ollama loads gemma4 with its full window of 131,072 tokens (`ollama ps`). A first turn uses 2,056 tokens, almost all of it the system prompt (4,412 characters) and the 7 tool descriptions, and each short exchange adds about 60-90 tokens. A normal session will not come close to filling it.
- **The clock in the system prompt slows every reply.** Ollama can reuse the work it did on the previous call, but only up to the first point where the text differs, and the current time (to the minute) sits near the very start of the system prompt. An experiment with 12-turn conversations through the real `Assistant`: with the clock fixed, the first words came after 0.11 s from turn 8 on (the earlier work was reused); with the clock moving one minute per turn, as in real use, they came after 2.5-2.9 s every turn, creeping up as the conversation grew.
- Ollama's `prompt_eval_count` counts the whole conversation on every call, even the part it reuses, so it measures how full the context is, not the time spent.

**Step 2: the time of day moves out of the system prompt.** The system prompt now says only today's date ("Today is Monday, 2030-01-07"), which changes once a day. Each message the user sends is stored with a stamp of when it was sent, for example `[Monday 2030-01-07 09:01] Good morning` (`time_stamp()` in `brain.py`), and the prompt says the stamp on the latest message is the current time and must never be mentioned. Earlier messages never change, so Ollama can reuse its work on them.

- **Speed:** the same 12-turn experiment with the clock moving a minute per turn: the first words now come after about **0.15 s** from turn 4 on, instead of 2.5-2.9 s every turn. A few turns still take 1-4 s; the fixed-clock run had those too, so they are not caused by the clock, and their cause is not known.
- **Side effect found by the evals:** without "The current date and time is ..." near the top, JARVIS started making up answers it cannot know: asked who won the 2029 World Series, it answered "the Miami Marlins", "the Detroit Tigers" and "the Los Angeles Angels" in 3 of 11 runs, against 0 of 11 with the old prompt. Fix: one sentence added to the honesty rule: "Your knowledge stops well before today's date, so you do not know the outcome of recent events such as sports results, elections or news; say so instead of answering." After it: 0 made-up answers in 10 runs.
- **Eval checks:** "does not include", "not within my" and "outside the" added to the accepted "I don't know" phrases (honest replies the check had missed). The `delete_series` check also flagged "Confirmation is required on screen before the event has been deleted", a correct reply, because it contains "has been deleted"; not changed yet.
- **Evals:** before, 101/102 (prompt `98d8bc80df43`, section 26). With the stamps alone (`a5549f3f4b55`): 100/102, including one made-up answer. With the stamps and the honesty sentence (`6cd7ebdef50f`): **102/102**. JARVIS never repeated a stamp in a reply.
- 2 new tests: each message carries the time it was sent, and the system prompt is identical from 00:00 to 23:59 and changes at midnight. 198 tests.
- **Not covered:** all eval cases are a single message, so nothing yet checks that JARVIS uses the latest stamp rather than an older one later in a long conversation.

**The three open points from step 2.**

1. **The occasional slow turns are gemma4 thinking.** The model writes hidden reasoning before its answer; Ollama streams it separately and JARVIS discards it. Measured over 16 turns: reading the conversation took about 0.15 s every time, and the first words came after 0.17 s when the model did not think, about 0.9 s after ~200 characters of thinking, and 2.3-3.6 s after 600-800. The first message after a pause also paid 2.4 s to load the model again, because Ollama unloads it after 5 idle minutes.
   - **Thinking stays on.** With it off (`python -m evals --think off`), replies came 7 times faster (0.9 s against 6.5 s per request), but the evals fell from 102/102 to **73/102**: it skipped the calculator and stated wrong sums as fact ("1234 times 5678 is 7007252"; it is 7006652), said "I have added Buy milk to your to-do list" without calling a tool, and was back to calling March 3rd "outside my immediate calendar range". The pause is the price of JARVIS reasoning before it acts.
   - New settings in `config.py`: `MODEL_THINK = True` (set explicitly, so an Ollama update cannot quietly turn it off) and `MODEL_KEEP_ALIVE = "1h"` (keeps the model loaded for an hour instead of 5 minutes; it uses about 1.4 GB). `Assistant` passes both to Ollama. The evals have a new `--think default|on|off` option and record the setting in their results. 1 new test.
2. **Multi-turn eval cases.** A case can now list earlier messages, each sent at its own time (`before=[("08:00", "Good morning, JARVIS."), ...]`). They run through the real model first and only the last message is scored. 2 new cases (36 in total):
   - `multi_current_time`: messages at 09:00 and 11:10, then "What time is it now?" at 15:42. JARVIS gave the time from the latest stamp in every run.
   - `multi_tonight_after_morning`: "What's on today?" at 08:05 (the class is then upcoming), then "Anything left for tonight?" at 19:30. Over 21 runs: usually it checked the calendar again and said nothing was left. Once it answered correctly from the morning's result without checking again, which the prompt forbids for "tonight" questions.
   - **Rare empty replies:** in 2 of those runs the model returned no text and no tool call after 0.4 s, and JARVIS said "Sorry, I could not finish that." It did not happen in 12 direct attempts to reproduce it, so the cause is unknown. Instead of guessing at a fix, `brain.py` now logs a warning with Ollama's stop reason, the tokens written and the length of the thinking whenever a round returns nothing. 1 new test.
3. **The delete check.** All 84 delete-case replies saved so far were reviewed. The phrase list for "claims it deleted" had 3 hits and all 3 were false ("...confirm on screen before anything is deleted"); every real failure was a reply that did not mention confirming at all. So all three delete cases now require the reply to mention confirming, and only first-person claims ("I've deleted", "has now been deleted") count as false claims. Rescored against the 84 replies: the 3 false failures pass, the 18 real ones still fail.

- **Evals** (prompt `6cd7ebdef50f`, thinking on, 36 cases × 3): **108/108** after adding "does not extend" to the "I don't know" phrases (the run scored 107/108; the miss was the honest "my knowledge does not extend to the outcomes of specific sporting events"). 202 tests.
- `CLAUDE.md` updated: how the system prompt and stamps work, the eval size, and two rules (keep thinking on; nothing that changes more than once a day in the system prompt).

**Step 3: trimming the history, as a safety net.** `Assistant.trim_history()` runs at the end of each turn. It does nothing until the model was last given more than `config.HISTORY_MAX_TOKENS` (60,000; the window is 131,072), and then drops the oldest exchanges in one go, down to about `config.HISTORY_KEEP_TOKENS` (30,000). Every trim changes the start of the conversation, so Ollama has to read it all again once; cutting a lot rarely keeps that cost small. It cuts only just before a user message, so a tool call is never separated from its result, and it always keeps the system prompt and the latest exchange. Ollama gives one token total, so each message's share is estimated from its length. Each trim is logged.

- 4 new tests (206 in total): a short conversation is never trimmed; a long one is trimmed oldest first, in a few big cuts, never far over the limit, always keeping the latest message; a tool call stays with its result; trims are logged.
- **Live check** with the real model and very low limits (trim above 2,700 tokens, down to 2,400): 2 trims in 12 turns, dropping 8 and 6 messages. The first read after a trim took 0.40 s instead of 0.12 s, and speed was back to normal on the next turn. The estimate was close: about 2,309 tokens predicted, 2,540 read on the next call including the new exchange.
- **Does trimming hurt the model's memory of recent messages?** After 12 short exchanges, "Which topic did I ask about just now?" (the answer is the last topic, the Sahara), through the real `Assistant`, 10 fresh conversations each: no trimming 5/10, trimming 7/10, trimming with a note "(Earlier messages in this conversation were removed to save space.)" 9/10. The wrong answers named the second-to-last topic, with or without trimming, so the question itself is ambiguous to the model; there is no sign that trimming makes it worse. An earlier 5-run comparison had suggested it did (5/5 against 3/5); that was too few runs. The note looked promising but is not proven, so it was not added.
- **Measurement lesson:** sending the exact same conversation to Ollama twice in a row gave worse answers (3/6) than the real `Assistant` path on the same messages (6/6). Measure through the real code path, with a fresh conversation for each run.
- The prompt is unchanged, and trimming never triggers in the evals (each case is short), so no eval rerun was needed for this step. Not tested: a real conversation long enough to reach 60,000 tokens.

**Step 4: a "new conversation" button, and delete cards that expire.**

- **NEW CONVERSATION** button in the header. It calls the new `POST /reset`, which runs `Assistant.reset()`: the history goes back to just the system prompt, and any waiting confirmation is dropped (its card disappears, and its id stops working). If a reply is still streaming, the reset waits for it to finish.
- `/reset` takes an empty JSON body (`{}`) on purpose. Without a body, any other website open in the browser could send it and wipe the conversation; requiring JSON keeps the protection from section 23 (other sites cannot send JSON without the browser asking first). A test pins this.
- **Delete cards expire after 5 minutes** (`config.CONFIRM_TIMEOUT_SECONDS = 300`). Clicking Confirm on an older card answers "That request has expired, so nothing was changed. Ask me again if you still want it." The age is measured with a clock that only counts forward (`time.monotonic()`), so changing the Mac's clock cannot affect it.
- 5 new tests (211 in total): an expired card does nothing, a card just inside the limit still works, reset clears the history and the waiting card, `/reset` clears the conversation, and `/reset` refuses requests without a JSON body.
- **Checked in a real browser** against a server on a spare port with a copy of the database: told JARVIS "My favourite colour is teal", clicked NEW CONVERSATION (the page showed "New conversation started."), asked "What is my favourite colour?", and JARVIS said it did not have that detail. The log showed `conversation reset` in between.
- **Noticed, not fixed:** before the reset JARVIS said "I shall ensure this detail is logged for future reference". It has no way to remember anything between conversations, so that is a promise it cannot keep. For the notes and memory tool (Phase 5), or a prompt rule.

**Not done: saving the conversation across restarts.** Considered and deferred (reasons in `plan.md`, Phase 4 item 4). Events and tasks already survive restarts; only the chat wording is lost, and the notes and memory tool in Phase 5 is the better way to keep what matters.


## 28. Phase 5: editing and moving events

Done on `phase5-edit-events`, merged into `main` on 2026-10-14 (a fast-forward) and then deleted. Before this, the only way to change an event was to delete it and add it again.

- **New tool `update_event`** (in `jcal.py`): change an event's time, length, date or title. It finds the event the same way as `delete_event` (titles match both ways; with scope "all" no date is needed) and, like delete, **never changes anything itself**: it returns a confirmation card ("Change 'Dentist' on 2030-01-08 at 15:00-16:00: time to 16:00-17:00?"), and only the Confirm button applies it. Cards expire after 5 minutes like delete cards.
- **What a change does:** a one-off event is updated in place. One occurrence of a repeating event: that date is skipped (the exceptions table, as for delete) and a one-off event with the change is added in its place; the series is untouched. A whole series: its title and times change (past dates show the new time too). Moving a whole series to other days is refused with a clear message (delete and add again), because it interacts with `repeat_days` and the series' start date in ways that are easy to get wrong.
- **Checked in code:** moving keeps the event's length; `new_length_minutes` sets a length ("make it last 90 minutes") so the model never adds up times; formats, the end after the start, not past midnight, not in the past, not an occurrence that has already happened, and at least one real change. Conflicts are checked at the new time, ignoring the event being moved (`_find_clash` gained `ignore_id`; moving 30 minutes later no longer clashes with itself), and for a whole series over the next 90 days, as `add_event` does.
- **Checked again on Confirm.** Everything above runs a second time when the user clicks Confirm. If the slot was taken or the event deleted while the card was waiting, nothing changes and the reply says why ("Nothing was changed. conflicts with 'Dinner' at 18:00 ...").
- The model is told what the card says, so it can describe the waiting change accurately.
- The event-finding code is shared with `delete_event` (`_locate`); all delete tests still pass.
- **Prompt:** changes, like deletes, only ask for confirmation, so JARVIS must never say an event was changed or moved; moves use `update_event`, never delete followed by add; ask when the user has not said when to move it; titles are matched loosely, so never ask for an exact title, date or time the calendar tools can find.
- **Tests:** 37 new (248 in total): every kind of change, the length kept or set, conflicts (including with itself and across a series), re-checking on Confirm, past and finished events, bad input, and through `Assistant`: nothing changes before Confirm, Cancel leaves it. Checked by breaking the code on purpose three ways (the clash check not ignoring the moved event, no second check on Confirm, length not kept): each break made the right tests fail.
- **Evals:** 7 new cases (43 in total): moving a one-off, one occurrence, a whole series, changing the length, renaming, a move into a clash (must report it), and "I need to move my dentist appointment" (must ask when).
  - First full run (prompt `fc52edf3f23e`): 122/129. `edit_whole_series` 0/3 (JARVIS asked for the title, date or days) and `edit_length` 1/3 (it asked for the start time so it could add 90 minutes itself). Fixed with `new_length_minutes` and clearer wording in the tool description and prompt.
  - Second (`1be6fecda01f`): **127/129**; `edit_whole_series` 1/3. One more sentence in the tool description ("For 'all my piano lessons' or 'from now on', call this straight away with scope 'all' and the title") took it to 6/6 on its own.
  - Final (`d3af1e9e7cc8`): **124/129**. Of the 5 misses, 3 were the rare empty reply (below), 1 was `repeat_weekdays` saving Mon-Fri with `repeat_days` instead of `weekdays` (the same result; the check is too strict), and 1 was a real miss: `edit_move_one_off` once put tomorrow's date in `new_date` instead of `date`.
- Eval checks: "beyond the scope" accepted as "I don't know", "advise" accepted as asking.
- **The rare empty reply, now explained.** The warning added in section 27 caught it 4 times: `done_reason=stop`, the model wrote 24-220 tokens of hidden thinking and then stopped without any answer. It is model behaviour, not a JARVIS bug, and it is now the most common failure in the evals (3 of 129 runs in the final run). Not fixed here; proposed separately.
- Not yet tried in the real app.

**Retrying an empty reply.** When a model round brings back no text and no tool call, `chat_stream` now sends the same request once more before giving up with "Sorry, I could not finish that." Nothing is added to the conversation in between. The log says "retrying once", then "the retry worked" or "giving up".

- 3 new tests (250 in total): a retry that works (the model sees exactly the same request twice), a retry after a tool call, and two empty attempts that still end in the apology. All three failed on the code from before the change.
- **Not verified on the real model.** After the change, no empty round happened at all in 219 runs (a full eval of 129, then 90 runs of the multi-turn and editing cases), against about 4 in the 130 runs before it, so the retry never triggered. It costs nothing when it does not trigger. Watch `logs/jarvis.log` for "retrying once".
- Full eval with the retry (prompt `d3af1e9e7cc8`, unchanged): **128/129**; the one miss was `ask_am_pm` assuming 8 AM once.
- **New weak spot found by the 90 runs:** in 4 of 40 editing runs (one each in four cases) JARVIS put the event's current date into `new_date` instead of `date` (for example `update_event(title='dentist appointment', new_date='2030-01-08', new_start_time='16:00')` when the dentist is already on 2030-01-08), got the "give the date of the occurrence" error, and apologised instead of correcting the call. Fixed below.


**Fix: working out the event's current date.** When `update_event` is called without `date` for a one-occurrence change, the new `_date_for_change` in `jcal.py` works it out where that is safe:

1. Exactly one upcoming event has the title and it does not repeat: use its date. So "Move my dentist appointment to Thursday at 4pm" works without the dentist's current date.
2. Otherwise, if the event really is on the date the model put in `new_date`, the model swapped the fields: use it as the current date, and move nothing to another day.
3. Otherwise the error now explains: "date is the event's CURRENT date; new_date is only for moving it to a different day."

Whatever it works out appears on the confirmation card, which names the event, its date and the change, before anything happens. The tool's `date` description now says it is the event's current date and is optional when only one upcoming event has the title.

- 6 new tests (256, then 257 with the eval-case check): no date needed for the only upcoming event, moving it to a new day without its date, the current date given as `new_date` (a series), two dentists with the date in `new_date` picking the right one, the explaining error, and a finished one-off not being guessed. Disabling each rule in turn made exactly its own tests fail.
- New eval case `edit_move_to_another_day` (44 cases in total). The checks for `edit_move_one_off` and `edit_conflict_reported` now judge the outcome (the card shown, or the clash reported) instead of which field the date went in.
- **Evals:** the 8 editing cases × 10 runs: 78/80 (prompt `ebbd75f13e93`, rescored with the outcome checks). The model still put the current date in `new_date` in 3 of those runs, and the code handled all 3. The new case went from 8/10 to 9/10 with the clearer `date` description (prompt `897819a24315`); the miss is JARVIS asking for the dentist's current date although it does not need it. Full suite: **130/132**; the misses were `ask_am_pm` (assumed 8 AM once) and `multi_tonight_after_morning` (answered from the morning's result once). No empty rounds.
- Not yet tried in the real app.


## 29. Dates and times spoken naturally

Done on `fix-spoken-dates`, merged into `main` on 2026-10-14 (a fast-forward) and then deleted. Dates and times are now spoken the way people say them.

**Real-app check of section 28 (by the owner, 2026-10-14): all passed.** Moving an event to 4pm (card, then Confirm moved it and kept its length), making a meeting last 90 minutes (the card showed the new end), moving just tomorrow's occurrence of a repeating event (only that one changed), moving an event to another day without its current date (it was found), and Cancel (nothing changed).

**Bug report from real use:** JARVIS read dates as written, so "2026-10-16" was spoken "two thousand and twenty-six dash ten dash sixteen".

- Fix: `speak_dates()` in `speech_text.py` rewrites `YYYY-MM-DD` before speaking: "2026-10-16" becomes "October the 16th", and the year is added only when it is not the current year ("March the 3rd, 2027"). Kokoro reads ordinals correctly (checked: "October the sixteenth", "March the thirty-first, two thousand and twenty-seven"). Text that only looks like a date (2026-13-45, 2026-02-30) is left alone. Only the speech changes; the screen still shows the date as written.
- It runs before the number clean-up, which would otherwise treat the digits as plain numbers.
- 17 new tests (274 in total): every ordinal ending (1st, 2nd, 3rd, 11th-13th, 21st-23rd, 31st), another year, a range, invalid dates, and the order with the number clean-up.

**Times spoken in 12-hour style** (the owner's choice). 24-hour times were read digit by digit: "15:00" was "fifteen zero zero" and "09:05" "zero nine zero five".

- `speak_times()` in `speech_text.py` rewrites them before speaking: "15:00" becomes "3 pm", "15:30" "3 30 pm", "09:05" "9 oh 5 am", "12:00" "12 noon", "00:00" "midnight", "00:30" "12 30 am", and a range "15:00-16:30" "3 pm to 4 30 pm". These spellings were picked by checking Kokoro's phonemes: with a colon it runs "3:30" together, and it says "zero" for "05", hence the spaces and "oh".
- Times JARVIS already wrote in 12-hour form stay right: "3:00 PM" becomes "3 pm", not "3 am PM". Things that only look like times are left alone ("a 2:1 win", "25:00", "10:00:30").
- Only the speech changes. The screen, the calendar and the tools stay 24-hour.
- Checked against Kokoro's phonemes: "October the sixteenth from three pm to four pm", "nine oh five am", "ten am to eleven fifteen am", "twelve thirty pm".
- 21 new tests (295 in total). Not yet heard in the real app.

## 30. Project moved to ~/Developer/jarvis

The project folder moved from `~/Desktop/jarvis` to `~/Developer/jarvis` (2026-10-14).

- **The virtual environment broke, as the note under "Run it" warned.** A venv stores its full path inside its own files. After `source .venv/bin/activate`, `python` was "command not found", and 26 commands in `.venv/bin` (such as `uvicorn` and `pytest`) still pointed at the old folder. `.venv/bin/python` itself still worked, which is why the nightly backup and the pre-commit hook kept running.
- Fix: the venv was rebuilt in place from a `pip freeze` of the old one, so it has exactly the same 72 packages. Not from `requirements.txt`, which is missing `pre_commit`, `ruff` and their dependencies and has an older `filelock`.
- `requirements.txt` is now a fresh `pip freeze` of the venv again: added `pre_commit`, `ruff` and their dependencies (`cfgv`, `distlib`, `identify`, `nodeenv`, `platformdirs`, `python-discovery`, `virtualenv`), and `filelock` 4.1.0 became 4.1.1. Without this, a venv rebuilt from the README steps would have no `pre_commit`, and the commit hook would stop working.
- Already right before this change: the launchd backup job (`com.jarvis.backup.plist`) and the pre-commit hook use the new path, and the code builds its paths from the project folder. Moving off the Desktop should also remove the risk that macOS blocks the 03:00 job from reading the folder (section 19).
- README setup now says `cd ~/Developer/jarvis`.
- Checked: with the venv activated, `python`, `uvicorn` and `pytest` resolve inside the new `.venv`; `ruff check .` passes; 295 tests pass; `mlx_whisper`, `kokoro_onnx`, `ollama`, `fastapi` and `pre_commit` import. Not checked: the server and voice in the real app, and the 03:00 backup from the new folder (its first run is tomorrow night; output in `/tmp/jarvis-backup.log`).

## 31. Threat model, and a crypto lab before encrypted backups

**Threat model.** New `SECURITY.md`: what JARVIS holds, who could harm it, the ways in, the controls in place (each one checked), known gaps and accepted risks. Written from the owner's answers, as the first step of learning security on this project.

- Main finding: the most likely harm is *losing* the data, and every backup sits on the same disk as the database. FileVault is on; Time Machine is not set up.
- Decisions: daily backups will be encrypted with a public key and copied to iCloud Drive; the private key is kept on paper, never on the Mac. Notes and memory hold trivial preferences only, never passwords.
- `plan.md`: encrypted offsite backups are now Phase 5 item 3, before notes (now item 4). `plan.md` and `CLAUDE.md` point to `SECURITY.md`.
- Checked after the move (section 30): the 03:00 backup ran from the new folder on 2026-10-15 and 2026-10-16.

**Crypto lab.** `experiments/crypto_lab.py`, six small experiments to run one at a time (`python experiments/crypto_lab.py 1`). Not part of the app; it never touches `jarvis.db`.

- Written: 1 (encrypt and decrypt with AES-GCM; a wrong key is refused) and 5 (two keys: X25519 key agreement, HKDF, then AES-GCM, the design planned for backups). The X25519 private key is 32 bytes, 64 hex characters, short enough for paper; an RSA key would not be.
- 2 (change one byte), 3 (same sentence twice), 4 (nonce reuse) and 6 (scrypt) were first left as exercises, then written with line-by-line comments at the owner's request. Results: one flipped bit, or a changed nonce, is refused; the same sentence encrypts differently each time; a reused nonce lets a guessed message reveal the other one without the key; scrypt took about 0.02 s, 0.19 s and 1.6 s at n = 2^14, 2^17 and 2^20 on this Mac.
- New dependency, agreed by the owner: `cryptography` 50.0.2, which brought `cffi` 2.1.1 and `pycparser` 3.11. Added to `requirements.txt`, not to `requirements-dev.txt`: nothing in the tests uses it yet.
- Checked: experiments 1 and 5 run and print the expected results. Not checked: no tests cover the lab (experiments are outside the test suite, as before).

## 32. Encrypted backups (Phase 5, item 3)

Built test-first, as agreed with the owner, from the plan in `SECURITY.md` section 5.

- **Every night, after the plain backup**, `backup_db.main()` writes an encrypted copy to `backups/encrypted/jarvis-YYYY-MM-DD.db.enc` and keeps the newest 30. The plain backup and its 7-day rule are unchanged, and the server's start-up still makes only the plain backup. If encryption fails, the plain backup is already saved and the job exits with code 1, so `/tmp/jarvis-backup.log` shows it.
- **`backup_crypto.py`** does the locking: a throwaway X25519 key pair per file, HKDF, AES-GCM, a fresh nonce. File layout: `JARVISBK` + version 1, the throwaway public key, the nonce, then ciphertext and tag. The header and throwaway key are "associated data": not secret, but covered by the tag. `cryptography` is imported inside `encrypt_copy()`, not at the top of `backup_db.py`, so a broken library can never stop the server or the plain backup.
- **`backup_keys.py`** (owner only, once): makes the key pair, shows the private key as 16 groups of 4 with an 8-character check value, clears the screen and scrollback, asks for the key to be typed back from paper, and only then saves the public key to `backup_public_key.txt`. It refuses to replace an existing public key.
- **`restore_backup.py`** (owner only): asks for the key without echoing it, decrypts, runs `PRAGMA integrity_check`, writes `jarvis-restored.db`, never replaces `jarvis.db`, and never leaves a half-written file. If the key is wrong, it prints the typed key's check value, so a typo (checks differ) can be told apart from the wrong key (checks match).
- **The project rule changed**, with the owner's agreement: "nothing leaves the machine unencrypted, and only the owner holds the key" (CLAUDE.md). CLAUDE.md also says AI tools must never run the two key scripts or see the private key, because anything a tool prints is sent off the Mac.
- **Getting the files to iCloud is by hand for now** (route B). macOS privacy protection (TCC) refused even listing iCloud Drive from here; the 03:00 job has no window to ask for permission, and Full Disk Access for Python would open everything to every Python script.
- Settings in `config.py`: `BACKUP_ENCRYPTED_DIR`, `BACKUP_ENCRYPTED_KEEP_DAYS = 30`, `BACKUP_PUBLIC_KEY`. `cryptography` added to `requirements-dev.txt` for CI. `jarvis-restored.db` is in `.gitignore`.
- **`tests/test_backup.py`, 37 tests**, including the first tests of the existing plain backup (it had none). Each new behaviour was seen failing first; the "plain backup survives a failed encryption" test was also checked by breaking the code on purpose.
- Not checked: no key pair exists yet (the owner makes it with `backup_keys.py`), so no real encrypted backup has been made or restored. Until then the nightly job prints "no public key yet" and carries on. Still to do: the restore drill with the paper key, and testing a copy to iCloud when the server starts from Terminal (route A).

## 33. Restore drill passed, first copies off the Mac

- **The nightly job made the first encrypted backup** on 2026-10-18 at 03:00 (`backup: encrypted jarvis-2026-10-18.db.enc` in `/tmp/jarvis-backup.log`), with the public key the owner made the day before.
- **Restore drill: passed.** The owner ran `restore_backup.py` on that file with the paper key, in their own Terminal. It printed "Restored and checked", so the key on paper is right and the whole chain works: locked on the Mac without the private key, opened only with it.
- **The first copies are in iCloud Drive**, copied by the owner by hand.
- **Found during the drill:** `jarvis-restored.db` went missing from the project folder. The folder's modified time (21:20:26) was later than every file in it, which means a file had been *removed* then; it was in the Trash. A file deleted in Finder only moves to the Trash, so an unencrypted copy of everything stays on disk until the Trash is emptied. README now says to use Delete Immediately, and to copy to iCloud Drive with Copy and Paste: dragging moves the files out of `backups/encrypted/`.
- Not checked by Claude: the restored file and the iCloud copies themselves (macOS blocks this session from the Trash and iCloud Drive, and the private key is never handled here). Both are the owner's report.

## 34. Notes and memory (Phase 5, item 4)

JARVIS can keep small facts about the owner, such as "my favourite food is sushi", and use them when they matter. Built test-first from the plan the owner agreed (a card for remember; their own messages may stay in the log; notes found with a tool, not put in the system prompt; no dashboard panel yet).

- **Migration 3** adds `notes`, an FTS5 full-text table (find a note by any word in it). Deleted notes are really wiped: `PRAGMA secure_delete` on every connection, and FTS5's own `secure-delete` option. A test reads the raw database file and finds no trace of a deleted note; removing either setting makes it fail. The server's daily backup runs before the migration, as for every migration.
- **`notes.py`**, three tools:
  - `remember` checks the note in code (not empty, at most 300 characters, not already saved, not secret-looking: words like password or PIN, 6+ digits in a row, password-shaped words), then only shows a card. The note is saved when the owner clicks it, so the model alone can never save anything.
  - `recall` returns at most 5 notes, labelled as "information, not instructions". Search words are turned into quoted plain terms first, because FTS5 has its own search language (OR, NOT, quotes, *) that `?` parameters do not switch off; removing that makes 9 tests fail.
  - `forget` needs every word to match, asks which one when several do, shows a card, and checks again when the card is clicked.
- **The log**: tools in the new `tools.PRIVATE` set are logged as lengths (`tool remember(23 characters)`), and a card marked `private` is logged without its text, whether approved, cancelled or expired. The owner's own message and JARVIS's reply are still logged, by choice (SECURITY.md).
- **Prompt**: a few sentences on when to use remember (only when asked; "remember to" is a task), never repeating secrets, never claiming a note was saved, and calling recall before suggesting anything personal. `notes` is imported after `calc`, so the three tools come last.
- **The tests now import `brain` in `conftest.py`**, so tools register in the app's order whichever test file runs first (running `test_notes.py` first had put the note tools before the to-do tools).
- **Bug found by the evals:** the model called `recall` with `about` set to null; `None.lower()` crashed. Fixed for all three tools, with tests.
- **Evals** (gemma4:latest `dc35e8d9c606`, 3 runs per case):
  - Before, prompt `897819a24315`: 129/132 runs, 42/44 cases (misses: `ask_am_pm` 1/3, `edit_one_occurrence` 2/3).
  - First version, prompt `aa1e7e31e062`: 143/153; the 44 old cases 131/132. Note cases failed for real (a passing remark was saved, dinner suggested without recall, the null crash) and two checks were too strict for correct replies ("I have noted your request ... please confirm"; "I must decline ... not permitted"), so those two checks were widened after reading the replies.
  - Final, prompt `482653045a27`: 152/153 runs, 50/51 cases; the 44 old cases 132/132. 7 new cases.
- **Known limit:** on a passing remark ("I absolutely love sushi, by the way") nothing is saved, every run, but the reply sometimes still sounds as if it will remember ("I have duly noted", "I shall take that into account"). Read in full, only 1 of the 3 final runs was fully right; the check missed one of them and now also looks for "take that into account" and similar.
- 393 tests (`tests/test_notes.py` new; more in `test_database.py` and `test_brain.py`).
- Not checked: the real app (cards on the dashboard, voice) and the migration on the real `jarvis.db`; both happen the first time the owner starts the server.

## 35. Notes: a preference mentioned in passing gets a card

The known limit from section 34: after "I absolutely love sushi, by the way", nothing was saved, but JARVIS sometimes said "I have duly noted" or "I shall take that into account", which was untrue.

- **First try: an offer in words** ("Would you like me to remember that?", then "yes" saves). Three wordings, each checked with the note cases first. gemma4 could not keep "save when asked" and "offer when mentioned" apart: the more concrete the offer, the more it offered even after "Please remember that my favourite food is sushi" (that case fell from 3/3 to 0/3, then 1/3). More rewording risked fitting these test sentences rather than real ones, so it was stopped and the owner chose a different design.
- **The design chosen by the owner: the card is the offer.** For a lasting preference (a like, dislike, favourite or allergy), whether the user asks or just mentions it, the model calls `remember`, which only shows a card. One rule instead of two, and it matches what the model tended to do anyway (section 34, first eval). Nothing is saved without a click, so the safety rule is unchanged (SECURITY.md). Moods such as "I'm tired" get no card.
- Trade-offs: a card appears when a preference is only mentioned (ignored, it expires after 5 minutes); and only one card waits at a time, so a note card replaces an unanswered delete card.
- **Eval cases**: `note_not_saved_casually` became `note_offered_for_a_preference` (remember must be called and the reply must point to the card); new `note_no_offer_for_a_mood`. Written first and seen failing on the old prompt (0/3). In the offered case, "I have noted your preference ... please confirm on screen" is honest while a card shows, so "noted" alone is allowed there; "has been saved" and "I will remember" are not.
- **Evals** (gemma4:latest `dc35e8d9c606`, 3 runs per case): before, prompt `482653045a27` (the final run of section 34, same prompt, so not run again): 152/153. After, prompt `ea448f0bcc68`: **156/156 runs, 52/52 cases**. Replies for the three note cases read in full; one says "I have recorded your preference ... please confirm ... if you wish for it to be saved", which slightly overstates but corrects itself.
- Not checked: the real app.

## 36. Other websites can no longer make JARVIS work (the Origin check)

Step 5 of the owner's security learning path, and Phase 6 item 1 of `plan.md`. Any website open in the browser can make it send requests to `127.0.0.1:8000`. It cannot read the replies (the same-origin policy), and it cannot send JSON without the browser asking first (a "preflight", which JARVIS never answers), but it can send a form upload. `/transcribe` takes one (`SECURITY.md`, gap 3).

- **The attack, shown first.** `experiments/attack_page.html` is a pretend stranger's website with three buttons, served on another port (`python -m http.server 9000 --bind 127.0.0.1 --directory experiments`). The owner ran it against JARVIS: the form upload worked (`transcribed 32044 bytes`, `POST /transcribe 200`), JSON was stopped by the browser (`OPTIONS /chat 405`, never sent), and JSON labelled as plain text arrived but was refused (`POST /chat 422`). The page could read none of the replies, even for the attack that worked.
- **The fix**: `refuse_other_websites`, a middleware in `server.py`. Every request that is not GET, HEAD or OPTIONS and carries an `Origin` header other than JARVIS's own address (built from the request's scheme and `Host`) gets 403 with a plain reason, before any endpoint runs, and a warning in the log. No `Origin` is allowed: browsers always send it on a cross-site POST, so its absence means the tests or a tool like curl, which already run on this Mac.
- **After the fix**, run again by the owner: `refused POST /transcribe from another website`, `403 Forbidden`, no `transcribed` line; `POST /chat 403`. The page was opened as `127.0.0.1:9000`, the same address on another port, and was still treated as another website, as the browser's rule says. The dashboard was then used normally (voice input, chat, a delete card confirmed, spoken replies) with no refusal.
- **Tests first** (9 failed before the fix): a stranger cannot transcribe and Whisper is never reached; every POST endpoint refuses a stranger; `Origin: null` is refused; another port, another name for the same machine (`localhost` against `127.0.0.1`) and `https` are all other websites; the dashboard's own origin, a request without `Origin`, and GET requests are allowed; refusals are logged. 406 tests.
- **Two locks, tested separately.** The old JSON-only test sent an `Origin` and so now got 403 before the JSON rule was reached; it now sends none, so it tests the JSON rule alone.
- **Found while testing:** the first version of the `/chat` case had no fake model, so before the fix it reached the real Ollama (the suite took 9.9 s instead of 0.4 s). It now uses a fake model. And `python -m http.server` listens on every network by default, so the instructions add `--bind 127.0.0.1`.
- **Noticed, not changed:** each time Whisper loads, the output shows "Fetching 4 files ... 0.00B". Nothing is downloaded, but the Hugging Face library probably asks its servers whether the files changed. Added to `plan.md` (upkeep) to check, and probably to set `HF_HUB_OFFLINE=1`.
- Not changed: this stops other websites, not other people; a login is still Phase 6 item 2.

## 37. A bigger, faster model: gemma4:26b

The owner asked whether a better model would help with JARVIS's personality. Three models were tried against the small `gemma4:latest` (e4b, `dc35e8d9c606`), each first with a 10-message personality test (`experiments/personality_compare.py`), then with the full eval on the unchanged prompt `ea448f0bcc68`.

| | gemma4:latest (e4b) | qwen3.5 | **gemma4:26b** | gemma4:31b |
|---|---|---|---|---|
| ID | `dc35e8d9c606` | `56671c2ab938` | `001e5dafc3c7` | `17ba34c06c80` |
| False claims in 10 messages | 0 | 3 | 0 | 0 |
| Full eval | 156/156 | not run | 154/156 checks, 156/156 read in full | 154/156 checks, 156/156 read in full |
| Full eval time | about 18 min | | 9.3 min | 51.2 min |
| Typical reply (median) | | | 2.8 s | 17.6 s |

- **qwen3.5 was dropped** after the 10-message test: it said a task was on the list and that two cards were on screen when no tool had run. The tools were available to it (it called `get_events` and `recall` elsewhere), but it chose wrongly. The prompt was tuned on gemma4, so this says "not with this prompt", not "never".
- **gemma4:26b is a mixture-of-experts model**: about 4 billion of its 25.2 billion parameters work on each word, so it is faster than the small model while knowing more. Ollama's `gemma4:26b` gave the "mtp" build (`001e5dafc3c7`), not the ID the library page listed for that tag; the ID is what is pinned.
- **gemma4:31b** was as reliable and slightly wittier, but a typical wait of 17.6 s (up to 52 s) before speaking is too slow for voice.
- **Switched**: `config.MODEL = "gemma4:26b"`, README pinned ID and setup command, CLAUDE.md (model, eval time about 10 minutes), `config.py` comments (load about 3 s, measured; context window 262144). `MODEL_THINK` stays on; its 102 to 73 measurement was on the small model and was not repeated on 26b.
- **Two checks widened, after reading the replies**: "strictly prohibited from storing passwords, PINs" is a correct refusal; "I have noted that you like sushi ... please confirm on your screen" is honest while a card shows. Note cases on 26b after that: 24/24.
- **Found:** Ollama's `gemma4:latest` now points to a different build (`009acb0d7fe1`) from the one tested. Running `ollama pull gemma4:latest` would have changed JARVIS silently; the README now says so.
- Not checked: the real app with 26b (voice, and how the speed feels). `ollama ps` reported 3.7 GB in use with the model loaded, against 18 GB on disk; not understood yet, so not written down as a fact.
- Still on the Mac and no longer used: `gemma4:latest`, `gemma4:31b` (20 GB), `qwen3.5:latest`. `ollama rm <name>` removes one.

## 38. A personality for JARVIS

The owner found JARVIS "a bot reading prompts". Measured causes: the personality was 28 words of a 1,075-word prompt; tool results were written as orders ("Tell the user to confirm on screen") that the model read out; and the prompt asked it to describe events "exactly as the tool result says".

- **The character**, chosen by the owner: the butler AI of the Iron Man films, dry and lightly sarcastic, "sir", between "classic" and "playful" humour, noticing things, chatting in casual conversation. He may **offer** things he cannot do yet (a source of feature ideas for the owner), but never claim he did them; when an offer is accepted, he says in character that it is beyond him for now.
- **How it was chosen**, with `experiments/personality_compare.py` on gemma4:26b, the same 12 messages each time, and a counter for replies sharing 5 or more words in a row with an example line:

  | Personality text | Replies copying an example | Wit |
  |---|---|---|
  | 12 example lines | 11 of 12 | strong, but the same lines every time ("coffee remains your department" three greetings in a row) |
  | Examples + "never copy, they are used up" | 6 of 12 | weaker |
  | A description only | 0 of 12 | weak |
  | **A stronger description** (techniques, wit in almost every reply, the remark must belong to this moment) | **0 of 12** | a fitting remark in about 8 of 12 |

  So the prompt describes the humour and shows no lines: the model copied examples however it was told not to.
- **Tool replies** (`delete_event`, `update_event`, `remember`, `forget`): still start with "Confirmation required" (the ticker uses it), now say what the card asks and that it happens only on Confirm. First version: "Say this in your own words". In the eval, note replies then sometimes left out the confirmation ("I shall keep it in mind for your next culinary excursion"). Final version: "Make sure the user knows it needs their Confirm on the card; say that in your own words": say what must be conveyed, leave the wording to the model. Note cases 24/24 afterwards. Tests check the card text is in each reply and no order is.
- The add-event rule became "give its details exactly as the tool result says, in your own words".
- **Evals** (gemma4:26b `001e5dafc3c7`, 3 runs per case; the before run used a separate worktree of `main`, so it could not see the changes):
  - Before, prompt `ea448f0bcc68`: 155/156 (one borderline note reply).
  - First version, prompt `2ccc2082f19d`: 153/156: two note replies without the confirmation (fixed above) and one `ask_until_month` run that guessed 31 December instead of asking. 5 more runs of that case: 5/5 on both prompts, so it was counted as variation.
  - Final version, same prompt hash (tool replies are not part of the hash): 154/156. Both misses were `repeat_until_date` in one run: "every Monday" was added starting **Sunday** 2030-01-13, repeating weekly on Sundays, and the reply said Mondays. 5 more runs: 5/5 on both prompts. In all, 0 wrong of 11 runs on the old prompt, 2 of 11 on the new: perhaps variation, perhaps a slight side effect. Either way the code accepted it, because a Sunday weekly event is valid; a code check for the weekday is the follow-up (plan.md).
- Wit seen in the evals: "One can only hope the acoustics are more forgiving than my processing units"; asking for a December date, "One can only endure so much choral music, I suppose". Note replies carry less wit than others now: with a required point to make, the joke tends to go.
- **Then the owner found JARVIS much slower in the app.** The log (timings only) showed why: the time to the first word went from 3.6 to 8.2 s to **13 to 30 s**, and the tokens the model wrote per reply, nearly all of it hidden thinking, from 156 to 270 to **900 to 1,750**. The checklist in the description (five techniques, "the remark must belong to this moment", "vary it") gave the model a puzzle to think through before every reply, most of all in casual chat. The evals had not shown it: they are mostly short tasks, and they score what is said, not how long it takes.
- **Thinking off was measured, and rejected**: 144/156 in 4.1 minutes. Four cases failed every run, all guesses instead of questions or checks: 08:00 assumed for "8", 31 December assumed for "until December", "tonight" answered from memory without the calendar, and a move to Thursday kept on Tuesday. So `MODEL_THINK = True` stays, now measured on 26b as well. Ollama accepts a thinking level ("low", "high") for gemma4, but it made no difference (low wrote more than high).
- **A lighter personality** (about 120 words instead of 380): the same character and honesty rules, without the checklist. With `personality_compare.py`, thinking on, 12 messages: median reply 2.3 s with no personality, 5.2 s with the long description, **3.2 s with the light one**, and 0 copied lines for all three. The wit mostly survives ("I trust you slept well, or at least managed to find your way out of bed without assistance"; after cancelling the dentist, "One less reason to worry about the drill, sir").
- **Evals, final** (gemma4:26b `001e5dafc3c7`, 3 runs per case):
  - No personality, prompt `ea448f0bcc68`: 155/156, 17.6 min.
  - Long description, prompt `2ccc2082f19d`: 154/156, 15.8 min.
  - Long description, thinking off: 144/156, 4.1 min.
  - **Light personality, prompt `da6dd655f792`: 156/156, 11.3 min.** The yoga case started on a Monday in all 3 runs. Replies read: all accurate, the cards always mentioned.
- Noticed, not changed: for a clash, every version says it "cannot move" the event, although a card is waiting and the move can still be confirmed. Some replies put a blank line before the joke, which only shows in the chat.
- **In the real app, light personality** (2026-10-22, the owner: "the response times were good"). From the log, timings only: first word 3.2 to 9.6 s (the 9.6 s includes loading the model), 234 to 568 tokens written per reply, against 13 to 30 s and 901 to 1,886 tokens with the long version.

## 39. A weekly event must name its weekday

In one eval run (section 38), "yoga every Monday" was added starting on a Sunday and repeating on Sundays, while JARVIS said Mondays. The cause, found in `add_event`: with `repeat_days` given (such as "mon"), the code works out the first date itself; without it, a weekly event simply repeats on whatever weekday the model's date falls on, and the result said only "repeating weekly", so the wrong day was invisible. (Section 38 said the result read "on Sun"; that was wrong.)

- **The rule, in code**: `add_event` refuses a weekly repeat without `repeat_days`, with an error that says what to send ("the weekday or weekdays the user said, such as 'mon'"). Nothing is saved. Naming the day is copying the user's words, which the model gets right; the date arithmetic stays in code.
- **Every result names the weekday**: "Added 'yoga' starting 2030-01-07 (a Monday) ...". The day goes after the date, so existing text such as "starting 2030-01-07" is unchanged.
- **Events already in the calendar** without `repeat_days` still repeat as before (a test checks it); only adding changed.
- Tests: 4 new (the refusal, a Sunday date for "every Monday" landing on Mondays, the weekday in the result, old events unchanged), and 20 existing test setups now name their weekday. 412 tests.
- **First version also changed the tool descriptions** ("repeat_days: required for a weekly repeat"). The full eval then went from 156/156 to 153/156: "I bought the milk" was answered "I have marked Buy milk as finished" without any `complete_task` call, in 3 of 3 runs, and 2 of 5 more (old prompt: 8 of 8 correct). The descriptions were put back word for word: `task_complete` 5/5 again. The code rule does not need them; the error message teaches the model when it matters.
- **Evals** (gemma4:26b `001e5dafc3c7`, 3 runs per case):
  - Before, prompt `da6dd655f792`: 156/156.
  - With new descriptions, prompt `48f04588c47a`: 153/156 (above).
  - **Final, prompt `da6dd655f792` (descriptions unchanged; tool results now name the weekday): 154/156.** Yoga on a Monday in all 3 runs; the model gave `repeat_days` for all 10 weekly events, so no refusals were needed. The 2 misses had already happened in earlier runs and are before or outside the changed results: `ask_until_month` guessed 31 December once (also seen in section 38), and `edit_move_to_another_day` kept the dentist on Tuesday once (the card would show the wrong change). Same prompt as the 156/156 runs, so counted as variation.
- **Known limit, not changed**: fortnightly ("biweekly") and monthly repeats still follow the model's date, because `repeat_days` only works with weekly. Fortnightly has the same risk as weekly had.
- Not checked: the real app.

## 40. A better-looking dashboard

The owner asked for recommendations to make the dashboard look better. Looked at in the built-in browser with a **demo** server: a launcher in the scratch folder that points the database, the backups and the log at scratch files and fills a made-up calendar, so the real `jarvis.db` stayed closed and no real data was shown in a screenshot. Found: 4 of 6 panels say "Coming soon"; at laptop size the page is taller than the window; only the last exchange is shown; the activity ticker looks like a second text box and shows code; small all-caps labels; ISO due dates in the to-do list against "Oct 24" in the schedule; "MODEL gemma4" written into the page by hand; nothing marks what is next. The owner chose to keep the HUD style and make all seven recommended changes, in order, after splitting the page.

**Step 0: `index.html` split into files** (1,044 lines to 67). The styles went to `static/css/jarvis.css`, the scripts to six files in `static/js/` (orb, chat, tasks, voice, calendar, app), by their existing section headings. Mechanical: a script moved the lines and checked that the pieces joined back equal the original exactly. They are plain scripts loaded in order, which share their top-level names just as one script did, so no build step. The server now serves the folder: `app.mount("/static", StaticFiles(...))`, built into FastAPI (no new dependency), GET only, files inside `static/` only. Tests: the files are served with the right types, `../` paths are refused, and every file the page links to exists.

**A check that was not what it seemed.** The first browser check after the split (and the commit message of `c031277`) reported no errors and every panel working. It had in fact tested the **old** page: the browser had kept its copy from before the split, because the server sent no caching instructions. Found during step 1, when a style change did not show: the loaded page had its styles inline and one inline script. The fix is below; the check was then repeated on the real new page (6 scripts and the stylesheet loaded): no console errors, the to-do list, schedule, orb, the calendar in all four views, closing it with Escape, ticking and unticking a task, a chat, and a confirmation card with Cancel all work.

**Caching**: `/` and `/static/...` now send `Cache-Control: no-cache`, so the browser may keep the files but asks the server before using them. Without it, an update to the page could stay invisible until a forced reload. Test: the header is on the page and its files. A browser that already holds an old copy needs one forced reload (Cmd+Shift+R), once.

**Step 1: the dashboard fits the screen.** The page is exactly one screen tall (`height: 100vh`, `overflow: hidden`), the panels scroll inside themselves, and the orb is at most 40% of the screen height so the conversation fits under it. Measured in the demo: at 1440x900 the page was 1,016 px tall with 2 panels cut off, now 900 px with none; at 1280x720 nothing is cut off and the text box is visible. At phone width (under 900 px) the page still scrolls as before, with no sideways scrolling.

**Found while testing, not fixed:** asked to "cancel the dentist" without a date, `delete_event` returned an error (it needs the date), so no card was shown, but JARVIS replied "I'll need you to confirm on screen". A claim about a card that does not exist; added to `plan.md`.

---

## Status

| Area | Status |
|---|---|
| Chat, tools, calendar, tasks, delete confirmation, ticker | Tested and working |
| HUD layout, orb, panel focus, reduce motion | Tested and working |
| Host protection | Tested and working |
| Personality (section 38) | Light version: evals 156/156, tried in the app, response times good |
| Weekday check for weekly events (section 39) | Done in code, evals 154/156 (variation); fortnightly and monthly repeats not covered |
| Other websites (Origin check) | Done: attack shown and then blocked in the real browser, dashboard unaffected, 406 tests (section 36) |
| Voice input, voice output, voice mode switch | Tested and working |
| Calendar views (compact agenda, year/month/week/day) | Layout confirmed good; logic still being tested |
| Event durations and repeating events | Logic tested (51 automated tests pass); real requests to JARVIS, such as "every Wednesday and Friday", not yet re-checked |
| Streaming replies into speech | Written; not tested yet |
| Automated tests for `jcal.py` | Tested and working: 51 of 51 pass |
| Phase 1 (backups, CI, ruff, pre-commit, cleanup, model pin) | Done: merged into `main`, ruff passes, CI green; nightly backup job in place (sections 19, 24) |
| Time-of-day awareness when listing today's events | Logic tested; passes in the evals (section 21), not yet confirmed in a real conversation (section 16) |
| Phase 3 (config, one database with migrations, tool registry, Assistant, endpoint tests, logging) | Done, merged into `main`; 191 tests; evals 87/90 with unchanged prompt (section 23) |
| Phase 4 (time stamps, thinking kept on, trimming, new conversation, expiring cards) | Done, merged into `main`; 211 tests; evals 108/108 (section 27); not yet tried in the real app |
| Editing and moving events (Phase 5, item 1), empty-reply retry | Done, merged into `main`; 257 tests; evals 130/132 (section 28); not yet tried in the real app; the retry has not yet triggered on the real model |
| Model eval suite (Phase 2) | Done, merged into `main`; baseline 80/90 runs, 90/90 after fixes (sections 21, 22) |
| Decimals in speech | Fixed and tested against Kokoro's phonemes; not yet heard in a real conversation (section 22) |
| Notes and memory (Phase 5, item 4) | Done and tried in the real app (section 34); a preference mentioned in passing now gets a card (section 35, evals 156/156), not yet tried in the real app |
| Encrypted backups (Phase 5, item 3) | Done: 37 tests (section 32); key pair made 2026-10-17; first encrypted copy 2026-10-18; restore drill with the paper key passed; copies in iCloud Drive, by hand (section 33). Automatic copy (route A) not tried |

## Known limits

- Speech is made one sentence at a time, so there can be a short pause between sentences.
- Whisper can invent words from near-silence.
- Sports, news, weather and notes panels are placeholders ("Coming soon").
- Pending confirmations and conversation history are lost when the server restarts.
- No login yet. This is safe only while the server stays on `127.0.0.1`.
- Events can only be added or deleted, not edited or moved.
- A monthly repeat on the 29th, 30th or 31st skips months that lack that day.
- For repeating events, the conflict check only looks 90 days ahead.
- Deleting one occurrence of a repeating event hides that date but leaves the series itself unchanged.

## Possible next steps

1. Phase 2: an evaluation suite for the model (turn `compare.py` into real cases), and tests for `brain.py`.
2. Phase 3: one shared database module, versioned migrations, one tool registry, history trimming, logging and a `config.py`.
3. Edit and move events (change time, title or length without deleting and re-adding).
4. Reminders and timers.
5. Real data for weather, news and sports panels.
6. Notes and memory tool.
7. Login and HTTPS before using it from a phone (Tailscale).
8. Google Calendar in place of the local database.
9. Morning briefing view and a phone layout.