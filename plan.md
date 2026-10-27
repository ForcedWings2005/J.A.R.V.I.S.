# JARVIS: Plan from here

Written 2026-10-12, after Phase 1 (backups, CI, ruff, pre-commit, cleanup) was merged and CI went green.

Security decisions (what JARVIS holds, who could harm it, what stops them) are in
`SECURITY.md`. Read it before any work on backups, notes, logging or Phase 6.

## Where the project stands

The calendar logic is in good shape: it is checked in code, covered by 51 tests, and has
already caught one real bug. The rest of the system is not at that level yet:

- **The model is the least reliable part, and nothing measures it.** Every incident so far
  (wrong dates, "every Wednesday and Friday" saved as weekdays, a finished class described
  as still ahead) came from the model, not from the code. When `gemma4:latest` changes, or the
  prompt is edited, there is no way to tell whether JARVIS got better or worse.
- **`brain.py` cannot be tested as it is.** The database connection, the conversation,
  the pending confirmation and the Ollama call are all module-level globals. A test cannot
  give it a fake model or a fixed clock.
- **The conversation grows forever.** `messages` is never trimmed. Over a long session it
  will become slow, and eventually it will overflow the model's context and the model will
  start forgetting its own system prompt.
- **The same knowledge lives in two places.** Tool schemas sit in one list and the functions
  in another (`tools` and `available_functions`), and two modules each open the database
  and create an `events` table. Nothing checks that the two copies match.
- **The server only works when started from the project folder.** Paths like `jarvis.db`,
  `models/` and `static/index.html` are relative.

The order below follows one rule: **measure before changing, and make it testable before
adding features.** Each phase ends with something that can be checked.

---

## Phase 2: Measure the model

Goal: one command that says how well JARVIS handles real requests, so any prompt or model
change can be judged by numbers instead of by feel.

1. **An evaluation suite** (`evals/`), built from `experiments/compare.py`.
   - Each case is a user message plus what should happen: which tool, which arguments,
     or "no tool at all". Dates are computed from a frozen "now", the same way the tests do it.
   - Start with about 30 cases taken from the incidents in the changelog: relative dates
     ("next Friday"), durations, `repeat_days` versus `weekdays`, "until December" (should
     ask), AM/PM ambiguity (should ask), tonight with finished events, deleting one
     occurrence versus the series, tasks versus events, greetings (no tool), and arithmetic
     (should call `calculate`).
   - Run each case 3 times, because the model is not deterministic. Report the pass rate
     per case and overall, plus the average time.
   - Save each run's results as a JSON file with the model ID and the prompt's hash, so two
     runs can be compared.
   - It is not part of CI (CI has no Ollama). Run it by hand with `python -m evals`.
2. **Record the baseline** score for the current prompt and model in the changelog.
3. From now on, **every prompt edit comes with an eval run**, and the before and after
   scores go in its commit message.

Done when: `python -m evals` prints a score, and the baseline is recorded.

## Phase 3: Make `brain.py` testable, then test it

Goal: the code around the model is as well tested as the calendar.

1. **Configuration in one place** (`config.py`): the model name, the database path, the
   models folder, the static folder, `MAX_ROUNDS`, and the history limit. All paths are built
   from the project folder (`Path(__file__).parent`), so the server can be started from
   anywhere. `JARVIS_DB` keeps working.
2. **One database module** (`db.py`): one connection, one lock, used by `brain` and `jcal`.
3. **Versioned migrations.** Replace the "add a column if it is missing" code with numbered
   steps tracked in `PRAGMA user_version`. Adding a column later then becomes a numbered
   step that runs once and can be tested.
4. **One tool registry.** Each tool is written once, as its function and its schema side by
   side (a small `@tool(...)` decorator, or a dict of `{name: (func, schema)}`). Then the
   schema and the function cannot drift apart. Add a test that every schema has a matching
   function and that every required argument exists in the function's signature.
5. **An `Assistant` object** that holds the conversation, the pending confirmation and a
   model client that can be swapped out. `server.py` makes one instance. Tests create their
   own, with a fake client that plays back scripted stream chunks and tool calls.
6. **Tests for `brain.py`:**
   - tasks: add, duplicates, complete, ambiguous matches, the checkbox toggle
   - calculator: the safe-eval rules, the size caps, bad input
   - `run_tool`: unknown tool, bad arguments, a tool that crashes
   - `chat_stream` with the fake client: a plain reply; one tool round; several rounds;
     hitting `MAX_ROUNDS`; a model error partway through; the delete confirmation flow
     from request to Confirm or Cancel
7. **Tests for the endpoints** with FastAPI's `TestClient`, with Whisper and Kokoro stubbed
   out. To make that possible, load both models the first time they are used, not when the
   module is imported. That also makes the server start faster.
8. **Replace `print` with `logging`**, written to a file that rotates, with each tool call,
   its result and how long it took. When JARVIS misbehaves, the log shows what it actually
   did, which is better evidence than asking JARVIS why (see section 16 of the changelog).

Done when: CI runs tests for `brain` and `server` as well as `jcal`, and coverage is
reported.

## Phase 4: Conversation memory that holds up (done, CHANGELOG section 27)

1. **Measure first.** Done: the context window (131,072 tokens) was never the problem; the
   current time in the system prompt was, because it stopped Ollama reusing its work. It moved
   to a stamp on each user message, and replies now start in about 0.15 s instead of 2.7 s.
2. **Trim the history.** Done, as a safety net above 60,000 tokens, cutting in big steps
   before a user message so a tool call never loses its result.
3. **A "new conversation" button** and `POST /reset`. Done. Delete cards also expire after
   5 minutes.
4. **Save the conversation to SQLite.** Considered and deferred. Events and tasks already
   survive restarts; only the chat wording is lost, mostly on `--reload` during development.
   Restoring old chat days later is more likely to confuse than help, and it would mean a
   schema change and more copies of personal text. Deliberate memory (the notes and memory
   tool in Phase 5) covers what is worth keeping. Revisit if restarts become a real problem.

## Phase 5: Features, in order of value

1. **Edit and move events** (`update_event`). *Done: CHANGELOG section 28.* This is the largest gap in the calendar today.
   It needs the same confirmation card as delete, and must handle "this occurrence" versus
   "the whole series". A "this occurrence" change can reuse the exceptions table: add an
   exception for that date and insert a one-off event in its place.
2. **Reminders.** A small scheduler inside the server checks every minute, and the page
   receives reminders through server-sent events, shows them, and speaks them when voice
   mode is on. Store reminders in the database so a restart does not lose them.
3. **Encrypted backups off this Mac.** Before notes. Each daily backup is encrypted with a
   public key (the private key is on paper, never on the Mac), then copied to iCloud Drive.
   A restore script and a test that a restore works. Details in `SECURITY.md` section 5.
   *Done: CHANGELOG sections 32 and 33. Restore drill passed and the first copies are in
   iCloud Drive (copied by hand). Still to try: copying when the server starts from Terminal.*
4. **Notes and memory.** `remember` and `recall` tools backed by a table with SQLite's FTS5
   full-text search. Start with that before reaching for embeddings. Trivial preferences
   only, and the rules in `SECURITY.md` section 5: no secrets, saved only when I ask, `forget`
   through the confirmation card, note text kept out of the log.
   *Done: CHANGELOG section 34. A read-only notes panel on the dashboard: section 40.*
5. **Morning briefing.** Today's events, overdue tasks and open reminders in one reply. Most
   of it can be put together in code, with the model only writing the sentences.
6. **Weather, then news and sports**, as plain read-only tools with a timeout and a cached
   result, so a slow API never blocks a reply.
7. **Sound effects for the dashboard.** The animations are done (CHANGELOG section 42);
   the owner chose to leave sound for later. Quiet, short, and off with voice mode off.

Each new tool gets its own eval cases before it ships.

## Phase 6: Leaving 127.0.0.1 (phone access)

Not before Phases 3 and 4. In this order:

1. **Check that other websites cannot reach the API.** `TrustedHostMiddleware` stops DNS
   rebinding, but a page open in another tab can still send requests to `127.0.0.1:8000`.
   Test whether `/chat` or `/tasks/{id}` accept a cross-site POST, and add a check that rejects
   requests from any other `Origin`. This is worth doing even while the server stays local.
   *Checked in Phase 3:* the JSON endpoints refuse a body sent as `text/plain` (422), which
   is the only kind another site can send without a browser preflight, so they are safe
   today; a test pins this. `/transcribe` takes a form upload, which another site *can*
   send. It only returns text the other site cannot read, but the `Origin` check should
   still cover it.
   *Done: CHANGELOG section 36. Every POST checks `Origin`. Check it again when HTTPS or
   Tailscale changes JARVIS's address.*
2. **A login** (a single user, with the session held in a cookie) on every endpoint.
3. **Tailscale** for the network, with HTTPS from `tailscale serve`. Never port forwarding.
4. **A phone layout** for the page.

## Ongoing upkeep (small, any time)

- **JARVIS can claim a card that was never shown.** When `delete_event` returned an error
  (no date given), the reply still said "confirm on screen" (CHANGELOG section 40).
  *Done: CHANGELOG section 44 ("cancel the dentist" finds the event, and the prompt rule
  about cards is now conditional).* (The clash wording, "cannot move", turned out to be
  true: a clash shows no card.)
- **Check the weekday of fortnightly events too.** *Done: CHANGELOG section 44.*
- **The first week of a fortnightly event.** When the model's date is a day late (a Saturday
  for "every other Friday"), code slides forward to the next Friday, a week later than meant,
  so the series falls on the other set of Fridays (CHANGELOG section 44, 1 eval run in 3).
  One idea: when the model's date is not on the weekday the user said, start from the
  beginning of that week instead. It changes when weekly events start too, so measure first.
- **Whisper may contact the internet when it loads.** *Done: CHANGELOG section 45. It did
  (huggingface.co, on the first transcription after each start); it is offline now.*
- **Split the requirements.** `requirements.txt` is a `pip freeze` dump (it includes `torch`).
  Keep a short `requirements.in` listing what the project uses directly, a
  `requirements-dev.txt` (pytest, ruff, pre-commit), and a generated lock file.
- **Keep backups off this disk.** `backups/` sits next to `jarvis.db`, so a disk failure or
  a lost laptop takes both. Now planned as Phase 5, item 3 (encrypted, to iCloud Drive).
  Time Machine on an external drive is still worth adding for the rest of the Mac.
- **Split up `index.html`.** *Done: CHANGELOG section 40.* The styles are in
  `static/css/jarvis.css` and the scripts in `static/js/`, with no build step.
- **Check model latency.** Measure the time to the first spoken word. Try Ollama's
  `keep_alive` setting so the model stays loaded between requests.
- **Changelog status table:** mark "Streaming replies into speech" as tested, since every
  chat now goes through it.

## What I would not do yet

- **Switch to Google Calendar.** The local calendar is the tested core. Sync can come once
  editing events works and Phase 6 is done.
- **Fine-tune or swap models.** Build the eval suite first, so any switch is measured.
- **Add a frontend framework.** The page works. Splitting it into modules gives most of the
  benefit for little risk.
