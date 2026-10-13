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
├── config.py           Settings: model, paths, limits, voice
├── database.py         The shared database connection and schema migrations
├── jcal.py             Calendar logic and tools: durations, repeats, exceptions, conflicts
├── server.py           Web server (FastAPI): endpoints for the page
├── speech.py           Text-to-speech (Kokoro)
├── speech_text.py      Text clean-up before speaking: numbers, pronunciations
├── backup_db.py        Backs up jarvis.db (SQLite backup API, 7 days kept)
├── static/
│   └── index.html      The dashboard page
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
│   └── test_evals.py   Tests for the eval suite's matching rules
├── evals/              Model evaluation suite (python -m evals)
│   ├── cases.py        The 30 cases
│   ├── check.py        How a run is scored
│   ├── __main__.py     The runner
│   └── results/        One JSON file per run (not in git)
├── pytest.ini          Tells pytest where the tests are
├── ruff.toml           Lint settings
├── .pre-commit-config.yaml  Checks that run before every commit
├── .github/workflows/tests.yml  Runs lint and tests on GitHub for every push
├── experiments/        Old scripts, not part of the app (agent.py, compare.py)
├── README.md           Setup, run, tests, backups, pinned model
├── CLAUDE.md           Instructions for Claude Code when it works on this project
├── plan.md             The plan from Phase 2 onward
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

---

## Status

| Area | Status |
|---|---|
| Chat, tools, calendar, tasks, delete confirmation, ticker | Tested and working |
| HUD layout, orb, panel focus, reduce motion | Tested and working |
| Host protection | Tested and working |
| Voice input, voice output, voice mode switch | Tested and working |
| Calendar views (compact agenda, year/month/week/day) | Layout confirmed good; logic still being tested |
| Event durations and repeating events | Logic tested (51 automated tests pass); real requests to JARVIS, such as "every Wednesday and Friday", not yet re-checked |
| Streaming replies into speech | Written; not tested yet |
| Automated tests for `jcal.py` | Tested and working: 51 of 51 pass |
| Phase 1 (backups, CI, ruff, pre-commit, cleanup, model pin) | Done: merged into `main`, ruff passes, CI green; nightly backup job in place (sections 19, 24) |
| Time-of-day awareness when listing today's events | Logic tested; passes in the evals (section 21), not yet confirmed in a real conversation (section 16) |
| Phase 3 (config, one database with migrations, tool registry, Assistant, endpoint tests, logging) | Done, merged into `main`; 191 tests; evals 87/90 with unchanged prompt (section 23) |
| Phase 4 (time stamps, thinking kept on, trimming, new conversation, expiring cards) | Done, merged into `main`; 211 tests; evals 108/108 (section 27); not yet tried in the real app |
| Model eval suite (Phase 2) | Done, merged into `main`; baseline 80/90 runs, 90/90 after fixes (sections 21, 22) |
| Decimals in speech | Fixed and tested against Kokoro's phonemes; not yet heard in a real conversation (section 22) |

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