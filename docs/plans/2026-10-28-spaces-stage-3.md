# Spaces, stage 3: switching by voice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Saying or typing "let's get some work done" (in any words) switches JARVIS to the
Work space, and JARVIS knows which space you are in when you talk to him.

**Architecture:** A new tool, `open_space`, in a new `spaces.py`, returns `tools.ShowSpace`
(like `NeedsConfirmation`, but needing no click). `Assistant.run_tool` notes it, and the turn
streams a `space` event straight after the tool's step; the page switches on that event with
the existing `switchSpace`. The page sends the current space with each message; the server
checks it and adds it to the message's time stamp (`[Monday 2030-01-07 09:01 · Work] `), never
to the system prompt. Home adds nothing, so Home's messages are exactly as today.

**Tech Stack:** Python 3.13, FastAPI and pydantic (as now), plain scripts sharing globals.
No new dependency.

**Spec:** `docs/specs/2026-10-27-spaces-and-work.md` (stage 3 of its Build order; the
sections "Switching is open-ended", "Switching by voice, step by step", "How JARVIS knows where
you are", "Security and privacy" and "Testing").

## Global Constraints

- `config.SPACES = ("home", "work")`: the one list of space names in Python. The tool schema's
  `enum`, the tool's check and the `/chat` check all read it.
- `open_space` changes only the view. It is **not** in `tools.ASKS_FIRST` and never returns
  `NeedsConfirmation` (spec, Security and privacy).
- Tools are imported in `brain.py` in the order `jcal`, `tasks`, `calc`, `notes`, **then**
  `spaces`, so the existing tools keep their order and `open_space` is last.
- The system prompt must stay identical all day: the current space goes only into the time
  stamp on each user message (CHANGELOG section 27).
- The `space` value from the page is checked against `config.SPACES` before use (422
  otherwise) and never reaches SQL. A body without `space` means Home, so an old cached page
  or `curl` keeps working.
- The host, Origin and JSON-only checks are unchanged; no new address.
- Prompt change rule (CLAUDE.md): full eval before (on the code as on `main`) and after, both
  scores and both prompt hashes in the commit message of Task 4.

## Review Focus

1. A `space` event arriving while a Home panel's opening animation runs (`seq` set): the
   switch must still happen once the animation ends, not be dropped (Task 3).
2. "Let's get some work done" while already in Work: the page stays put with no error, and
   the reply still makes sense (Task 3, browser check).
3. The model passing `"Work"` or `" work "`: accepted as `work`; `"gym"` gives the error
   result and no `space` event (Task 1).
4. A confirmation card waiting when a voice switch happens: the card stays docked and Confirm
   still works (Task 3, browser check).
5. A `/chat` body without `space`: treated as Home, never 422 (Task 2).

---

### Task 1: `open_space`, `ShowSpace` and the `space` event

**Files:**
- Modify: `config.py` (`SPACES` at the top of the `# Work space` block, the spec named)
- Modify: `tools.py` (`ShowSpace` dataclass after `NeedsConfirmation`)
- Create: `spaces.py`
- Modify: `brain.py` (import `spaces` after `notes`; `run_tool`; `chat_stream` yields the
  event; `_STEP_WORDS["open_space"]`; the module docstring names `spaces.py`)
- Test: `tests/test_spaces.py` (new), `tests/test_brain.py`,
  `tests/test_tasks_calc_tools.py` (the order test gains `"open_space"` last)

**Interfaces:**
- Produces:
  - `tools.ShowSpace(name: str, reply: str)`: a dataclass. `name` is a value from
    `config.SPACES`; `reply` is the tool result the model sees.
  - `spaces.open_space(name: str) -> ShowSpace | str`, registered with `@tool`, schema
    `name={"type": "string", "enum": list(config.SPACES)}`.
  - `Assistant.run_tool` returns `ShowSpace.reply` (a string) and sets
    `self.show_space = result.name`; `chat_stream` resets `self.show_space = None` at the
    start of each turn and, after yielding a tool's `step`, yields
    `{"type": "space", "name": <name>}` if that tool set it (then clears it).
  - Ticker words: `open_space` → `"Showed the Work space"` (the name with a capital).

- [ ] **Step 0: Baseline eval, before any code changes.** With Ollama running:

Run: `python -m evals > .superpowers/sdd/2026-10-28-spaces-stage-3/eval-before.txt 2>&1`
(in the background, about 11 minutes; the steps below can go on meanwhile, since the eval
imports the code once at its start)
Expected: the last lines give a score out of 168 (56 cases x 3) and `prompt 851b5394ed77`.
Record both in the ledger.

- [ ] **Step 1: Write the failing tests** in `tests/test_spaces.py`:

```python
def test_a_known_space_is_shown():
    r = spaces.open_space("work")
    assert r == tools.ShowSpace("work", "Showing the Work space.")

def test_the_name_is_read_loosely():          # Review Focus 3
    assert spaces.open_space(" Work ").name == "work"

def test_an_unknown_space_is_an_error():
    assert spaces.open_space("gym") == "Error: no space called 'gym'. Spaces: home, work."

def test_the_schema_lists_the_spaces():
    schema = next(s for s in tools.SCHEMAS if s["function"]["name"] == "open_space")
    assert schema["function"]["parameters"]["properties"]["name"]["enum"] == list(config.SPACES)
    assert "open_space" not in tools.ASKS_FIRST
```

and in `tests/test_brain.py` (tool rounds section):

```python
def test_opening_a_space_streams_a_space_event_after_its_step():
    model = FakeModel(use(call("open_space", name="work")), say("Work it is, sir."))
    events, reply = run(brain.Assistant(chat=model), "Let's get some work done")
    types = [e["type"] for e in events]
    assert types.index("space") == types.index("step") + 1
    assert next(e for e in events if e["type"] == "space") == {"type": "space", "name": "work"}
    assert next(e["step"] for e in events if e["type"] == "step") == \
        {"text": "Showed the Work space", "status": "done"}
    assert model.seen[1][-1]["content"] == "Showing the Work space."
    assert reply == "Work it is, sir."

def test_an_unknown_space_streams_no_space_event():
    model = FakeModel(use(call("open_space", name="gym")), say("There is no gym, sir."))
    events, _ = run(brain.Assistant(chat=model), "Open the gym")
    assert "space" not in [e["type"] for e in events]
    assert model.seen[1][-1]["content"].endswith("Spaces: home, work.")   # no NO_CARD note

def test_a_space_is_shown_only_on_its_own_turn():
    model = FakeModel(use(call("open_space", name="work")), say("Done."), say("Hello."))
    a = brain.Assistant(chat=model)
    run(a, "Work time")
    events, _ = run(a, "Hello")
    assert "space" not in [e["type"] for e in events]
```

Add `"open_space"` at the end of the list in `test_every_tool_is_registered_in_order`.

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_spaces.py tests/test_brain.py tests/test_tasks_calc_tools.py`
Expected: FAIL: `ModuleNotFoundError: spaces` (collection error) and the order test.

- [ ] **Step 3: Implement.** `config.SPACES`, `tools.ShowSpace` (docstring: returned by a tool
that changes only what is on screen; no click needed, unlike `NeedsConfirmation`), `spaces.py`
(module docstring pointing to the spec; `name.strip().lower()`, checked against
`config.SPACES`), the `brain.py` changes from the Interfaces block. The tool's description,
exact copy (this is the prompt change the evals measure):

> "Show one of the dashboard's spaces on screen. home is the welcome dashboard; work has the
> calendar, the to-do list and deadlines, for work, study and projects. Call it when the user
> wants to start working or studying, or asks for a space, in any words, such as 'let's get
> some work done' or 'time to study', and still answer the rest of their message. Do not call
> it when work is only mentioned, such as 'I had a long day at work'."

- [ ] **Step 4: Run the tests to see them pass, then the whole suite and ruff**

Run: `python -m pytest -q && ruff check .`
Expected: all passed (496 + 7 = 503), `All checks passed!`

- [ ] **Step 5: Commit** (`config.py tools.py spaces.py brain.py` and the three test files):
"Add the open_space tool: JARVIS can show a space". The message says the prompt changed and
the evals are in the Task 4 commit.

### Task 2: the current space in the time stamp, and `/chat` taking it

**Files:**
- Modify: `brain.py` (`time_stamp`, `chat_stream`, one sentence in `build_system_prompt`)
- Modify: `server.py` (`ChatRequest.space`, `chat_endpoint` passes it)
- Test: `tests/test_brain.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `config.SPACES` (Task 1).
- Produces:
  - `brain.time_stamp(space: str = "home") -> str`: `"[Monday 2030-01-07 09:01] "` for Home,
    `"[Monday 2030-01-07 09:01 · Work] "` otherwise (`space.title()`, a middle dot U+00B7).
  - `Assistant.chat_stream(user_text: str, space: str = "home")`.
  - `ChatRequest.space: Literal[config.SPACES] = "home"` (pydantic refuses anything else with
    422). If ruff or pydantic object to `Literal` built from the tuple, a `field_validator`
    against `config.SPACES` with the same 422 result is the fallback.
  - The system prompt gains, straight after "...and never mention the stamps. ":
    `"When a stamp also names a space, such as '· Work', that is the part of the dashboard "
    "on the user's screen. "`

- [ ] **Step 1: Write the failing tests.** In `tests/test_brain.py`, beside the stamp test:

```python
def test_the_stamp_names_the_space_except_home(brain_clock):
    a = brain.Assistant(chat=FakeModel(say("A."), say("B.")))
    list(a.chat_stream("In work", space="work"))
    list(a.chat_stream("At home"))
    users = [m["content"] for m in a.messages if isinstance(m, dict) and m["role"] == "user"]
    assert users == ["[Monday 2030-01-07 09:00 · Work] In work",
                     "[Monday 2030-01-07 09:00] At home"]

def test_the_system_prompt_does_not_change_with_the_space(brain_clock):
    model = FakeModel(say("A."), say("B."))
    a = brain.Assistant(chat=model)
    list(a.chat_stream("x", space="work"))
    list(a.chat_stream("y"))
    assert model.seen[0][0]["content"] == model.seen[1][0]["content"]
```

In `tests/test_server.py`, in the chat section:

```python
def test_chat_passes_the_space_on(client, model):
    fake = model(say("Yes, sir."))
    client.post("/chat", json={"message": "hi", "space": "work"})
    assert fake.seen[0][-1]["content"].endswith(" · Work] hi")

def test_chat_without_a_space_is_home(client, model):        # Review Focus 5
    fake = model(say("Yes, sir."))
    assert chat(client, "hi")[-1]["type"] == "done"
    assert "·" not in fake.seen[0][-1]["content"]

def test_chat_refuses_an_unknown_space(client, model):
    model()
    assert client.post("/chat", json={"message": "hi", "space": "gym"}).status_code == 422
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_brain.py tests/test_server.py`
Expected: FAIL: `chat_stream() got an unexpected keyword argument 'space'`; the server tests
see no stamp and a 200 for "gym".

- [ ] **Step 3: Implement** the Interfaces block. `chat_stream` uses
`time_stamp(space)`; the log line `user: ...` stays as it is.

- [ ] **Step 4: Run the suite and ruff**

Run: `python -m pytest -q && ruff check .`
Expected: all passed (503 + 5 = 508), `All checks passed!`

- [ ] **Step 5: Commit** (`brain.py server.py` and the two test files): "Tell JARVIS which
space you are in", noting the prompt sentence and that the evals are in the Task 4 commit.

### Task 3: the page sends the space and follows the `space` event

**Files:**
- Modify: `static/js/spaces.js` (`switchSpaceWhenFree`)
- Modify: `static/js/chat.js` (the body of `/chat`; the `space` event)

**Interfaces:**
- Consumes: the `space` event (Task 1); `/chat` accepting `space` (Task 2); `switchSpace`,
  `currentSpace`, `seq` (stage 1, motion.js).
- Produces: `switchSpaceWhenFree(name: string)` in `spaces.js`: calls `switchSpace(name)` now,
  or, while `seq` is set, every 100 ms until it is not (the same wait as `followAddress`).
  `chat.js` sends `{ message: text, space: currentSpace }` and, on
  `msg.type === 'space'`, calls `switchSpaceWhenFree(msg.name)`. `chat.js` loads before
  `spaces.js`, but both names are read only when a message is sent, after every script ran.

There is no JavaScript test runner, so this task is checked in a browser (as stages 1 and 2).

- [ ] **Step 1: Implement** the Interfaces block.

- [ ] **Step 2: Browser check** in a demo server with made-up data (scratch `JARVIS_DB`,
backups and logs redirected, a port not used before, `?fresh=` in the address), with the real
model through Ollama:
  - On Home, type "Let's get some work done": the ticker shows "Showed the Work space", Work
    opens, the address is `#work`, the reply streams and is spoken.
  - In Work, "Take me back home": Home opens.
  - In Work, "Let's get some work done" (Review Focus 2): stays in Work, no console error.
  - Expand a Home panel and send "time to study" while it opens (Review Focus 1); a scripted
    check may call `switchSpaceWhenFree('work')` with `seq` set instead: Work opens after.
  - Ask to delete a demo event, leave the card waiting, then "let's work" (Review Focus 4):
    the card stays in the dock and Confirm still works.
  - The request body (network panel or a wrapped `fetch`) carries `"space":"work"` in Work
    and `"space":"home"` on Home.
  - Phone width (375 px): a voice switch shows the dock first, the panels below.
  - No console errors.
Expected: each as described. Record what was and was not checked.

- [ ] **Step 3: Run the suite and ruff** (no Python changed, but the pre-commit hook runs
them only for Python files)

Run: `python -m pytest -q && ruff check .`
Expected: 508 passed, `All checks passed!`

- [ ] **Step 4: Commit** (`static/js/spaces.js static/js/chat.js`): "Switch spaces when JARVIS
opens one, and send him the current space".

### Task 4: the eval cases, and the eval after

**Files:**
- Modify: `evals/check.py` (`Case.space: str = "home"`, the space the message is sent from)
- Modify: `evals/__main__.py` (`run_once` passes `case.space` to both `chat_stream` calls)
- Modify: `evals/cases.py` (a `# --- Spaces` section at the end)
- Test: `tests/test_evals.py` (`test_case_refers_to_real_tools_and_arguments` also checks
  `case.space in config.SPACES`)

**Interfaces:**
- Consumes: `open_space` (Task 1), `chat_stream(..., space=)` (Task 2).
- Produces: six cases (62 in all):

| name | space | message | check |
|---|---|---|---|
| `space_lets_work` | home | "Let's get some work done." | `expect=[("open_space", {"name": "work"})]`, `no_card_claims=True` |
| `space_study` | home | "Time to study." | `expect=[("open_space", {"name": "work"})]` |
| `space_switch_and_answer` | home | "Let's get some work done. What's due this week?" | `expect=[("open_space", {"name": "work"}), ("list_tasks", {})]`, `tasks=["Submit essay"]`, `includes=["essay"]` |
| `space_long_day_no_switch` | home | "I had a long day at work." | `forbid=["open_space"]` |
| `space_calendar_no_switch` | home | "What's on my calendar today?" | `forbid=["open_space"]`, `expect=[("get_events", {"date": TODAY})]` |
| `space_back_home` | work | "Take me back to the home screen." | `expect=[("open_space", {"name": "home"})]` |

`space_already_there` (Review Focus 2) is checked in the browser in Task 3, not as a case: from
Work, either calling `open_space("work")` again or not is correct, so there is nothing to score.

- [ ] **Step 1: Write the failing test**: the `case.space` assertion in
`test_case_refers_to_real_tools_and_arguments`.

Run: `python -m pytest -q tests/test_evals.py`
Expected: FAIL: `AttributeError: 'Case' object has no attribute 'space'`.

- [ ] **Step 2: Implement** `Case.space`, `run_once`, the six cases.

Run: `python -m pytest -q && ruff check .`
Expected: all passed (508 + 6 parametrised cases = 514), `All checks passed!`

- [ ] **Step 3: Quick live check of the new cases**

Run: `python -m evals --runs 1 -k space -v`
Expected: 6 cases ran. Read every reply before calling a failure a model problem (CLAUDE.md).

- [ ] **Step 4: Full eval after**

Run: `python -m evals > .superpowers/sdd/2026-10-28-spaces-stage-3/eval-after.txt 2>&1`
(about 12 minutes)
Expected: a score out of 186 (62 x 3) and a new prompt hash. Compare the 56 old cases with the
baseline from Task 1 Step 0. If an old case drops by more than run-to-run variation (section
47: `task_complete` fell to 7/10), reword the tool description, run again, and say so. If a new
case fails, read its reply first; fix a check only when the reply was right.

- [ ] **Step 5: Commit** (`evals/check.py evals/__main__.py evals/cases.py
tests/test_evals.py`): "Evals for switching spaces", with both scores, both prompt hashes and
the speed lines in the message.

### Task 5: the docs

**Files:**
- Modify: `CHANGELOG.md` (section 52 and the Status table), `README.md` (switching by voice in
  the spaces part), `CLAUDE.md` (architecture diagram and file table: `spaces.py`,
  `open_space`; the `space` event in "How a chat turn works"; the tool import order),
  `docs/specs/2026-10-27-spaces-and-work.md` (any detail settled while building, as done for
  `/day`), `plan.md` (stage 3 done, if it lists the stages)

- [ ] **Step 1: Write them.** CHANGELOG section 52 says, in plain language: what changed, the
eval scores before and after with the hashes, what was checked in the browser and what was
not (Safari not yet), and anything found while building.

- [ ] **Step 2: Run the suite and ruff**

Run: `python -m pytest -q && ruff check .`
Expected: 514 passed, `All checks passed!`

- [ ] **Step 3: Commit**: "Document spaces, stage 3".
