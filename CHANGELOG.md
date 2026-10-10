# JARVIS Project Changelog

A local, private personal assistant with a web dashboard, calendar, to-do list and voice.
Runs on a MacBook Pro (M3 Max, 64 GB). Everything runs on this machine.

Written 2026-10-08, last updated 2026-10-09. Entries are in the order the work was done.

---

## Current file layout

```
jarvis/
├── brain.py            Assistant logic: model calls, tools, tasks, calculator, rules
├── jcal.py             Calendar logic: durations, repeats, exceptions, conflicts
├── server.py           Web server (FastAPI): endpoints for the page
├── speech.py           Text-to-speech (Kokoro)
├── static/
│   ├── index.html      The dashboard page
│   └── index_old.html  Backup of the first plain chat page
├── models/
│   ├── kokoro-v1.0.onnx
│   └── voices-v1.0.bin
├── jarvis.db           SQLite database (events and tasks; not in git)
├── .gitignore          Files git should skip
├── requirements.txt    Pinned package versions
├── agent.py            Terminal version of the assistant (not used by the dashboard)
├── compare.py          Model comparison test (not used by the dashboard)
├── smoke_test.py       First tool-calling test (not used by the dashboard)
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

## Dependencies

- Ollama with the `gemma4:latest` model (also pulled: `mistral:latest`, `qwen3.5:latest`)
- Python packages: `ollama`, `fastapi`, `uvicorn`, `mlx-whisper`, `python-multipart`, `kokoro-onnx`
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

Fix (written; not tested yet):

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

---

## Status

| Area | Status |
|---|---|
| Chat, tools, calendar, tasks, delete confirmation, ticker | Tested and working |
| HUD layout, orb, panel focus, reduce motion | Tested and working |
| Host protection | Tested and working |
| Voice input, voice output, voice mode switch | Tested and working |
| Calendar views (compact agenda, year/month/week/day) | Layout confirmed good; logic still being tested |
| Event durations and repeating events | Written; the weekday fix (`repeat_days`) has not been tested yet |
| Streaming replies into speech | Written; not tested yet |
| Time-of-day awareness when listing today's events | Fix written (section 16); not tested with JARVIS yet |

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

1. Edit and move events (change time, title or length without deleting and re-adding).
2. Real data for weather, news and sports panels.
3. Notes and memory tool.
4. Login and HTTPS before using it from a phone (Tailscale).
5. Google Calendar in place of the local database.
6. Morning briefing view and a phone layout.