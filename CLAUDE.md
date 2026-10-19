# CLAUDE.md: working on JARVIS

JARVIS is a private assistant that runs entirely on one Mac: a FastAPI server, a single-page
dashboard (calendar, to-do list, chat, voice), a local language model through Ollama, and
SQLite. Nothing leaves the machine unencrypted, and only the owner holds the key (today the
only thing that leaves is the encrypted backup copy). The owner is learning Python and software
engineering, so explanations matter as much as the code.

Read `README.md` (setup, running), `CHANGELOG.md` (history, incidents, status), `plan.md`
(the roadmap, by phase) and `SECURITY.md` (the threat model and security decisions) when you
need context. Do not duplicate them here.

## Architecture

```
static/index.html ──HTTP, 127.0.0.1 only──> server.py (FastAPI)
                                              ├─ brain.Assistant ── ollama.chat(stream=True, tools=tools.SCHEMAS)
                                              │     └─ runs tools from tools.FUNCTIONS
                                              │          ├─ jcal.py   get_events, add_event, delete_event, update_event
                                              │          ├─ tasks.py  add_task, list_tasks, complete_task
                                              │          ├─ calc.py   calculate
                                              │          └─ notes.py  remember, recall, forget
                                              ├─ speech.py (Kokoro, loaded on first use) + speech_text.py
                                              ├─ mlx_whisper (imported on first /transcribe)
                                              └─ backup_db.py (runs at import, before the database opens)
            jcal.py, tasks.py, notes.py ──> database.py (one connection + one lock) ──> jarvis.db
```

The core rule: **anything that must be right (dates, times, conflicts, deletes, arithmetic)
is checked in code, never left to the model.** The model chooses tools; code validates and acts.

| File | Responsibility |
|---|---|
| `config.py` | Every setting: model name, paths (built from the project folder), limits, voice. `JARVIS_DB` env var overrides the database path. |
| `database.py` | The shared `conn` and `lock`, and `MIGRATIONS` (schema version in `PRAGMA user_version`). |
| `tools.py` | The `@tool` registry (`FUNCTIONS`, `SCHEMAS`) and `NeedsConfirmation`. |
| `brain.py` | `build_system_prompt()` and `Assistant`: the conversation, the tool loop (capped at `MAX_ROUNDS`), the pending confirmation. |
| `jcal.py` | Calendar logic: durations, repeats (stored as one row, expanded on read), exceptions, conflicts, finished/upcoming labels. |
| `tasks.py`, `calc.py` | To-do list; safe arithmetic (parses the expression with `ast`, never `eval`). |
| `notes.py` | Notes and memory (FTS5 search). Trivial preferences only; secrets refused; saving and forgetting go through the confirmation card. |
| `server.py` | Endpoints `/`, `/chat` (NDJSON stream), `/confirm`, `/calendar`, `/tasks`, `/tasks/{id}`, `/transcribe`, `/speak`; logging setup at start-up. |
| `speech.py`, `speech_text.py` | Kokoro synthesis; text clean-up before speaking (numbers, pronunciations). |
| `backup_db.py` | Daily SQLite backup via the backup API, integrity-checked, 7 kept; the nightly run (`main()`) then makes an encrypted copy, 30 kept. |
| `backup_crypto.py`, `backup_keys.py`, `restore_backup.py` | Encrypted backups: lock/unlock and the file format; making the key pair (owner only); restoring (owner only). |
| `evals/` | Model evaluation suite (`python -m evals`). Cases in `cases.py`, scoring in `check.py`. |
| `tests/` | pytest. `conftest.py` sets up the in-memory database and frozen clock; `fakes.py` has `FakeModel`. |
| `experiments/` | Old scripts, not part of the app, excluded from ruff. Do not run `agent.py` from the project root (it opens `jarvis.db`). |

### How a chat turn works
`/chat` → `Assistant.chat_stream()` rebuilds the system prompt (today's date only, so it stays
identical all day and Ollama can reuse its work), appends the user message with a
`[Monday 2030-01-07 09:01]` time stamp, and streams the model's reply. If the model asks for tools, `run_tool()` runs
each one, appends the result as a `tool` message, and the model is called again, up to
`MAX_ROUNDS` tool rounds. Events streamed to the page: `delta`, `step`, `break`, `done`, `error`.

### Destructive actions: the confirmation path
`delete_event` never deletes, `update_event` never changes anything, and `remember` and
`forget` never save or delete a note. Each returns
`NeedsConfirmation(card, apply, reply)`. `Assistant`
stores it under a random id and shows a card; only `POST /confirm` (the on-screen buttons)
calls `apply()`. **The model must never be able to confirm, skip or trigger `apply()` itself.**
Any new tool that deletes, overwrites or sends something must use this same path.

## Coding conventions (taken from the existing code)

- Python 3.13 (`ruff.toml` target `py313`, CI `python-version: "3.13"`, venv 3.13.7).
- Ruff rule sets E, F, B; long lines allowed (E501 ignored); `line-length = 100`.
- Plain functions and small modules. One class where it holds state (`Assistant`).
- Type hints on function signatures; short docstrings that say *why*, not *what*.
- Dates are `YYYY-MM-DD` strings, times are 24-hour `HH:MM` strings. Datetimes are naive local time.
- Tool functions return a string for the model. Errors start with `"Error: "` (the ticker
  marks them by that prefix); a confirmation result starts with `"Confirmation required"`.
  Tools validate their own input and return an error string rather than raising.
- Every SQL value goes through `?` parameters. Never put user or model text into SQL with
  f-strings. (The two f-strings in `database.py` use only fixed column definitions and an int.)
- Every database access holds `database.lock` (imported as `lock`).
- A new tool: write the function with `@tool(description, arg=schema, ...)` in the module that
  owns it. Arguments without a default become required. The import order in `brain.py`
  (`jcal`, `tasks`, `calc`, `notes`) is the order the model sees the tools; changing it changes
  the prompt. A tool that handles private text adds its name to `tools.PRIVATE` (the log then
  records only lengths) and sets `private=True` on its `NeedsConfirmation`.
- Replies are spoken aloud: the system prompt asks for plain speech, no markdown.
- Match the style of the file you are in. Comments and docs are plain English, short sentences.

## Safety and security boundaries (do not weaken silently)

These are the real controls, verified in the code. Changing any of them needs an explanation
of the risk and the owner's agreement first.

- The server listens on `127.0.0.1` only (uvicorn's default; README runs it without `--host`).
- `TrustedHostMiddleware` allows only `127.0.0.1` and `localhost` (stops DNS rebinding).
- There is **no login and no HTTPS**. This is only acceptable while the server stays local.
  Never add `--host 0.0.0.0`, port forwarding or remote access without Phase 6 of `plan.md`.
- JSON endpoints reject `text/plain` bodies (422), so other websites cannot drive `/chat`,
  `/confirm` or `/tasks`; `tests/test_server.py` pins this. `/transcribe` accepts a form upload
  and is not yet protected by an `Origin` check (noted in `plan.md`).
- Input limits: uploads 10 MB (unknown file extensions are saved as `.webm`), the temporary
  audio file is always deleted;
  `/speak` text capped at 2000 characters; `/calendar` range at most 400 days; `get_events` at
  most 62 days; calculator exponents ≤ 1000 and results ≤ 10^300.
- Deletes and changes to events go only through `NeedsConfirmation` and `/confirm` (see above).
  `update_event` checks everything again inside `apply()`, in case the calendar changed
  while the card was waiting; a new destructive tool should do the same.
- Personal data: `jarvis.db`, `backups/`, `logs/` (the log holds what was said to JARVIS) and
  `evals/results/` are in `.gitignore`. Never commit them, paste their contents into docs or
  commit messages, or log secrets. There are no API keys today; if one is ever needed it goes
  in `.env` (already ignored), never in code.
- Encrypted backups: the private key exists only on paper. **Never run `backup_keys.py` or
  `restore_backup.py`, and never ask for, read or handle the private key:** anything a tool
  run prints is sent off this Mac. The owner runs both in their own Terminal.
  `backup_public_key.txt` is meant to be in git (it can only lock); never replace it.

## Database changes

- **Never edit or reorder an existing step in `database.MIGRATIONS`.** Add a new function at
  the end. Each step runs once, inside a transaction, and the version is bumped with it.
- A new step needs a test in `tests/test_database.py`, including a database that already has data.
- **Importing `config` or `database` opens the real `jarvis.db`** unless `JARVIS_DB` is set
  first. When running ad-hoc scripts, set `JARVIS_DB=:memory:` or point it at a copy (this has
  already caused one accidental migration of the real file, see CHANGELOG section 23).
- `server.py` runs `backup_db.backup()` *before* importing `brain`, so the daily snapshot is
  taken before any migration. Keep that order, and keep `backup_db.py` free of `database` imports.
- Do not touch the real `jarvis.db` or `backups/` without asking. To test against real data,
  copy it with SQLite's backup API (a plain file copy is not safe while the server runs).

## Testing, linting and CI

Run from the project folder with the venv active (`source .venv/bin/activate`):

```bash
ruff check .            # lint
python -m pytest -q     # all tests, under a second; never touches jarvis.db or a model
python -m evals --runs 1 -k <name>   # quick live check of some model cases (needs Ollama)
python -m evals         # full suite, 51 cases x 3 runs, about 18 minutes
```

- The pre-commit hook (installed) runs ruff and pytest on every commit with Python files.
- CI (`.github/workflows/tests.yml`) installs only `requirements-dev.txt` and runs ruff and
  pytest on every push. CI has no Ollama, Whisper or Kokoro, so tests must never need them.
- Tests run with a frozen clock (Monday 2030-01-07 08:00, `jcal.datetime` is patched) and an
  in-memory database emptied before each test. Use `fakes.FakeModel` instead of a real model,
  and `TestClient(server.app, base_url="http://127.0.0.1")` (other hosts are refused).
- **Prompt or tool-description changes:** run the full eval before and after, and put both
  scores and the prompt hash in the commit message. The eval prints the hash; if it is
  unchanged, the model saw identical input and score differences are run-to-run variation.
- Eval reply checks are phrase lists and can be too strict. Before calling a failure a model
  problem, read the actual reply (`-v`). Fix a check only when the reply really was correct,
  and say so.
- A bug fix gets a test that fails without the fix.

## Dependencies and configuration

- `requirements.txt` is a `pip freeze` of the Mac's venv; `requirements-dev.txt` is what CI
  needs. Pin versions to what is installed. Avoid new dependencies; ask first if one seems needed.
- Settings belong in `config.py`, not as constants scattered through modules.
- Ollama: model `config.MODEL` (`gemma4:latest`), called through the `ollama` client's default
  address. The pinned model ID is in README; if behaviour changes, check `ollama list` first.
- Keep `config.MODEL_THINK = True`. Turning gemma4's thinking off made replies 7x faster but
  dropped the evals from 102/102 to 73/102 (wrong arithmetic, actions claimed without tools).
- Never put anything that changes more than once a day (like the time) into the system prompt:
  it stops Ollama reusing its work and slows every reply (CHANGELOG section 27).
- Large model files live in `models/` (not in git). Kokoro and Whisper must stay lazily loaded
  so the server and tests can start without them.
- A launchd job (`~/Library/LaunchAgents/com.jarvis.backup.plist`) runs
  `.venv/bin/python backup_db.py` at 03:00 using absolute paths. Moving or renaming the project,
  the venv or `backup_db.py` breaks it. Do not change system configuration without asking.

## Errors, logging and documentation

- Errors a user or the model should see become plain text (`"Error: ..."` from tools, the
  `error` event in the stream, `HTTPException` with a clear `detail`). A crashing tool must not
  end the turn: `run_tool` turns it into an error result and logs the traceback.
- Use `logging.getLogger("jarvis.<module>")`, not `print`. Logging is configured only in the
  server's start-up (`lifespan`), so tests never write a log file. The log records turns and
  tool calls with timings; when JARVIS misbehaves, read `logs/jarvis.log`. The model's own
  explanation of a mistake is a guess, not a diagnosis.
- Every commit that changes behaviour also updates `CHANGELOG.md` (a numbered section, plain
  language, what was checked and what was not) and, when relevant, the file layout and the
  Status table. Update `README.md` for setup or usage changes, and `plan.md` when the plan changes.

## Working rules

- Read the relevant code before editing it. Follow existing conventions unless there is a
  concrete reason not to, and say what the reason is.
- Keep changes minimal and on-task. No unrelated refactors, speculative features or new
  dependencies. Note other problems you notice instead of fixing them unasked.
- **Before** a change that touches security controls, the database schema, tool execution or
  anything destructive, explain the risk and the planned approach, and wait for agreement.
- Work on a branch per phase or feature; commit after each step that works. Commit, push,
  merge or delete branches only when asked. The usual flow: branch, commits, push, CI green,
  fast-forward merge into `main`, delete the branch.
- Write or update tests for every meaningful behaviour change and bug fix.
- Explain important changes so the owner can learn from them: what changed, why, and how the
  new code works, in plain language. Point to the exact file and line.

## Reporting work

When finishing a task, report:

1. What changed and why (files, with links).
2. The exact commands run and their real results (for example `191 passed`). **Never claim a
   check passed unless it ran and passed.** If it was not run, say so.
3. What could not be verified (for example: "the decimal fix is checked against Kokoro's
   phonemes but not heard in the real app", or "CI result not visible: the repo is private").
4. Assumptions made, and unresolved issues or follow-ups.
5. Anything done by mistake, and its effect, plainly.
