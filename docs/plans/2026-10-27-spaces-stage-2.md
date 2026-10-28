# Spaces, stage 2: the Work panels — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Work space gets its four panels: "Your day, worked out", Deadlines, To-do and
the calendar always open in week view.

**Architecture:** A new `workday.py` works out free time, what's next and deadline states as
plain functions, tested in Python; a read-only `GET /day` serves them. On the page, the one
existing calendar learns to draw into a given element, so it moves between Home's Schedule
panel and Work (only one space is shown at a time, so it never needs to be in both). The
to-do list draws the same tasks into Home's box and Work's. `space-work.js` draws the strip
and the deadlines from `/day`.

**Tech Stack:** Python 3.13 and FastAPI (as now), plain scripts sharing globals, CSS grid.
No new dependency.

**Spec:** `docs/specs/2026-10-27-spaces-and-work.md` (stage 2 of its Build order; the
sections "Work", "`GET /day`" and "When something goes wrong").

## Global Constraints

- Settings in `config.py`: `WORK_DAY_START = "08:00"`, `WORK_DAY_END = "22:00"`,
  `WORK_MIN_GAP_MINUTES = 30`, `DEADLINE_WINDOW_DAYS = 14` (agreed with the owner).
- `GET /day` is read-only and changes nothing; it is the only new address.
- Times are 24-hour `"HH:MM"` strings and dates `"YYYY-MM-DD"` in Python and JSON. On the page,
  times are shown with the dashboard's existing `fmtTime` (12-hour, like the calendar), so the
  spec's examples ("Dentist at 15:00") appear as "Dentist at 3 PM".
- Every database access goes through `jcal` and `tasks`, which hold the lock; `workday.py`
  never touches the database itself.
- Tests run with the frozen clock (Monday 2030-01-07 08:00, `jcal.datetime`) and the
  in-memory database; `workday.day_summary()` reads "now" from `jcal.datetime` so the tests
  control it.
- Home must look and behave as before: its Schedule panel still opens the calendar in year
  view; its to-do list and count as today.
- No new dependency; no build step; page classes must not reuse existing names.

## Review Focus

1. Ticking a task in Work updates everything at once: Work's to-do, Work's deadlines and the
   strip, and Home's list and count (Task 3).
2. The one calendar moving between spaces: Work shows week view; going Home and opening
   Schedule shows year view in Home's panel; back in Work it is week view again, with no
   calendar left drawn in the hidden place (Task 2).
3. Late in the evening (after 22:00) the strip says there is no free time left, with no
   error; an event running past 22:00 ends the free time at its start (Task 1, Task 3).
4. A task due more than 14 days away shows an empty bar; an overdue one is red and first;
   a task without a due date is not in Deadlines (Task 1, Task 3).
5. If `/day` fails, the strip and Deadlines say "Couldn't load your day" and the to-do list
   and calendar still work (Task 3).

---

### Task 1: `workday.py`, the settings and `GET /day`

**Files:**
- Create: `workday.py`
- Modify: `config.py` (the four settings, under a `# Work space` comment, with the spec
  section named)
- Modify: `server.py` (`import workday` beside the other modules; `@app.get("/day")`)
- Test: `tests/test_workday.py` (new), `tests/test_server.py`

**Interfaces:**
- Produces (Python):
  - `free_gaps(events: list[dict], now: datetime, day_start: str = config.WORK_DAY_START,
    day_end: str = config.WORK_DAY_END, min_gap: int = config.WORK_MIN_GAP_MINUTES)
    -> list[dict]`: `[{"start": "HH:MM", "end": "HH:MM"}, ...]` in time order. `events` are
    today's events as `jcal.events_between` returns them (`time`, `end_time` or `None`); an
    event without an end lasts 60 minutes. The window starts at the later of `now` (whole
    minutes) and `day_start`, and ends at `day_end`; overlapping events merge; gaps shorter
    than `min_gap` are left out.
  - `next_event(events: list[dict], now: datetime) -> dict | None`: the first of today's
    events that starts after `now`: `{"title", "time", "in_minutes"}`, or `None`.
  - `deadlines(task_list: list[dict], today: date) -> list[dict]`: every task with a `due`
    that is not `done`, soonest first (then by `id`):
    `{"id", "title", "due", "days_left", "state"}`, `state` `"overdue"` (days_left < 0),
    `"today"` (0) or `"soon"` (> 0).
  - `day_summary(now: datetime | None = None) -> dict`: `now` defaults to
    `jcal.datetime.now()`; reads today's events (`jcal.events_between(today, today)`) and
    `tasks.tasks_list()`; returns `{"free": [...], "next": ... or None, "deadlines": [...],
    "deadline_window_days": config.DEADLINE_WINDOW_DAYS}`.
- Produces (HTTP): `GET /day` → `day_summary()` as JSON. Ruling for the record: the spec's
  example has no `deadline_window_days`; it is added so the page reads the setting from
  `config.py` instead of repeating 14.

- [ ] **Step 1: Write the failing tests in `tests/test_workday.py`**

  Helper: `ev(start, end=None, title="X")` returns `{"title": title, "time": start,
  "end_time": end}`; `at(hhmm)` returns `datetime(2030, 1, 7, h, m)`.

  ```python
  def test_free_time_between_events():
      assert workday.free_gaps([ev("09:00", "10:00"), ev("13:00", "14:30")], at("08:00")) == [
          {"start": "08:00", "end": "09:00"}, {"start": "10:00", "end": "13:00"},
          {"start": "14:30", "end": "22:00"}]

  def test_free_time_starts_now():                 # at("11:10") -> 11:10-13:00, 14:30-22:00
  def test_overlapping_events_merge():             # 09-11 and 10:30-12 -> 08-09, 12-22
  def test_gaps_under_30_minutes_are_left_out():   # 09-10, 10:20-11 -> no 10:00-10:20
  def test_an_event_without_an_end_lasts_an_hour():  # ev("09:00") -> 08-09, 10-22
  def test_before_the_day_starts():                # at("06:00"), no events -> 08:00-22:00
  def test_after_the_day_ends():                   # at("22:30") -> []
  def test_an_event_past_the_end_of_the_day():     # ev("21:00","23:00"), at("20:00") -> 20-21
  def test_events_already_over_are_ignored():      # ev("08:00","09:00"), at("10:00") -> 10-22
  def test_a_gap_exactly_30_minutes_is_kept():     # 09-10, 10:30-11 -> 10:00-10:30 kept

  def test_next_is_the_first_event_still_to_start():
      evs = [ev("09:00", "09:30", "Stand-up"), ev("15:00", "16:00", "Dentist")]
      assert workday.next_event(evs, at("10:00")) == {"title": "Dentist", "time": "15:00",
                                                        "in_minutes": 300}

  def test_nothing_next_when_the_day_is_done():    # at("16:00") -> None

  def test_deadline_states():
      ts = [{"id": 1, "title": "Soon", "due": "2030-01-09", "done": False},
            {"id": 2, "title": "Late", "due": "2030-01-05", "done": False},
            {"id": 3, "title": "Today", "due": "2030-01-07", "done": False},
            {"id": 4, "title": "No date", "due": None, "done": False},
            {"id": 5, "title": "Done", "due": "2030-01-08", "done": True}]
      out = workday.deadlines(ts, date(2030, 1, 7))
      assert [(d["title"], d["days_left"], d["state"]) for d in out] == [
          ("Late", -2, "overdue"), ("Today", 0, "today"), ("Soon", 2, "soon")]

  def test_day_summary_reads_the_calendar_and_the_tasks():   # frozen Mon 2030-01-07 08:00
      jcal.add_event("Dentist", "2030-01-07", "15:00", "16:00")
      jcal.add_event("Gym", "2030-01-07", "18:00", "19:00", repeat="weekly", repeat_days="mon")
      tasks.add_task("Essay", "2030-01-09")
      s = workday.day_summary()
      assert s["free"] == [{"start": "08:00", "end": "15:00"}, {"start": "16:00", "end": "18:00"},
                           {"start": "19:00", "end": "22:00"}]
      assert s["next"]["title"] == "Dentist" and s["deadline_window_days"] == 14
      assert [d["title"] for d in s["deadlines"]] == ["Essay"]
  ```
  In `tests/test_server.py`:
  ```python
  def test_day_gives_the_work_summary(client):
      r = client.get("/day")
      assert r.status_code == 200
      assert set(r.json()) == {"free", "next", "deadlines", "deadline_window_days"}

  def test_day_is_read_only(client):
      assert client.post("/day", json={}).status_code == 405
  ```

- [ ] **Step 2: Run the tests to see them fail**

  Run: `python -m pytest -q tests/test_workday.py tests/test_server.py -k "day or free or next or deadline or gap or event"`
  Expected: errors on `import workday` (no such module) and 404 for `/day`.

- [ ] **Step 3: Implement `workday.py`, the settings and the endpoint**

  Work in minutes from midnight; merge the event intervals clipped to the window, then walk
  them. `day_summary` uses `jcal.datetime.now()` when `now` is `None` (comment: the
  calendar's clock, frozen in tests). The endpoint is one line, beside `/calendar` and
  `/tasks`, with a one-line comment that it is read-only.

- [ ] **Step 4: Run the tests to see them pass, and the whole suite**

  Run: `ruff check . && python -m pytest -q`
  Expected: `All checks passed!` and `493 passed` (477 + 16 new).

- [ ] **Step 5: Commit**

  ```bash
  git add workday.py config.py server.py tests/test_workday.py tests/test_server.py
  git commit -m "Work out free time, what's next and deadlines, served by GET /day"
  ```

### Task 2: The calendar and the to-do list in Work

**Files:**
- Modify: `static/js/calendar.js` (`openCal`, `closeCal`, `renderCal` draw into `cal.box`)
- Modify: `static/js/tasks.js` (`loadTasks` draws into every to-do box)
- Modify: `static/js/space-work.js` (`enter` opens the calendar in Work, `leave` closes it)
- Modify: `static/index.html` (Work's panels replace the stage-1 placeholder)
- Modify: `static/css/space-work.css` (Work's layout)
- Create (scratch, not committed): a demo launcher in this session's scratchpad, as in stage 1
  (`run_demo.py`: made-up data, its own `demo.db`, backups and logs in its own folder, port
  `8016`)

**Interfaces:**
- Consumes: `registerSpace`, `switchSpace`, `currentSpace` (stage 1).
- Produces (page):
  - `openCal(box: Element = document.getElementById('cal'), view: string = 'year')`: shows the
    calendar in `box`, starting in `view` on today; sets `cal.box`. `closeCal()` empties
    `cal.box` and sets `cal.open = false`. `renderCal` draws into `cal.box` only.
  - Markup in `#space-work`, in this order: `<div class="panel" id="work-day">` (the strip,
    header `YOUR DAY`), `<div class="panel" id="work-deadlines-panel">` (header `DEADLINES`,
    body `<div id="work-deadlines">`), `<div class="panel" id="work-tasks-panel">` (header
    `TO-DO`, body `<div id="work-tasks" class="task-list">`), `<div class="panel"
    id="work-cal-panel">` (header `CALENDAR`, body `<div id="work-cal">`). Home's `#tasks`
    also gets `class="task-list"`.
  - `loadTasks()` draws the same tasks into every `.task-list`; the count stays Home's.
  - Layout (`space-work.css`): the strip across the top; below it two columns, Deadlines and
    To-do on the left (`minmax(260px, 320px)`), the calendar filling the rest.

- [ ] **Step 1: Write the browser checks (they fail now)**

  In the demo at 1440x900, in Work:
  ```js
  ({ calInWork: !!document.querySelector('#work-cal .cbody'), view: cal.view,
     homeCalEmpty: document.getElementById('cal').childElementCount === 0,
     workTasks: document.querySelectorAll('#work-tasks .task').length,
     homeTasks: document.querySelectorAll('#tasks .task').length })
  ```
  Expected after Task 2: `{ calInWork: true, view: 'week', homeCalEmpty: true, workTasks: 4,
  homeTasks: 4 }` (the demo has 4 tasks). Now: `calInWork: false`, `workTasks: 0`.

- [ ] **Step 2: Implement**

  - `calendar.js`: `cal.box` replaces the fixed `calBox` in `renderCal` and `closeCal`;
    `openCal(box, view)` as in Interfaces. Home's `focusPanel` keeps calling `openCal()`.
  - `space-work.js`: `enter() { openCal(document.getElementById('work-cal'), 'week'); }`,
    `leave() { closeCal(); }`.
  - `tasks.js`: the drawing part of `loadTasks` becomes `drawTasks(box, tasks)`, called for each
    `.task-list`; the empty message and the count unchanged.

- [ ] **Step 3: Run the browser checks**

  - Step 1's check → as expected.
  - Review Focus 2: `switchSpace('home')`, click Schedule, wait 3 s → `cal.view === 'year'`,
    `#cal .cbody` present, `#work-cal` empty; Escape, wait 1 s, `switchSpace('work')` →
    `cal.view === 'week'`, `#work-cal .cbody` present, `#cal` empty.
  - All four views in Work: click Year, Month, Week, Day with real clicks → each draws (`.cbody`
    has children) and the title changes.
  - Ticking a task in `#work-tasks` (real click) → the same task is ticked in `#tasks`, and
    `#tasks-count` drops by one; untick it again.
  - Home looks as before (screenshot compared with one taken before the task); its Schedule
    and To-do panels open as before.
  - `read_console_messages` with `onlyErrors` → none.

- [ ] **Step 4: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `493 passed`.

  ```bash
  git add static/js/calendar.js static/js/tasks.js static/js/space-work.js static/index.html static/css/space-work.css
  git commit -m "Show the calendar and the to-do list in the Work space"
  ```

### Task 3: "Your day, worked out" and Deadlines

**Files:**
- Modify: `static/js/space-work.js` (`loadDay()` and the drawing)
- Modify: `static/css/space-work.css` (the strip, the deadline rows and bars)

**Interfaces:**
- Consumes: `GET /day` (Task 1); `fmtTime`, `inWords` (`calendar.js`); `friendlyDue`
  (`tasks.js`); the markup from Task 2.
- Produces: `loadDay(): Promise<void>` (fetches `/day`, then calls `drawDay`), and
  `drawDay(summary: object): void` (draws `#work-day` and `#work-deadlines` from one `/day`
  answer, so it can be checked with made-up answers).

- [ ] **Step 1: Write the browser checks (they fail now)**

  With the demo's made-up data, in Work:
  ```js
  if (typeof loadDay === 'function') await loadDay();   // not defined before this task
  ({ defined: typeof loadDay, strip: document.getElementById('work-day').textContent,
     rows: [...document.querySelectorAll('#work-deadlines .deadline')].map(r => r.dataset.state) })
  ```
  Expected after Task 3: the strip contains `Free`, the demo's next event's title and the
  nearest deadline's title; `rows` lists one state per open task with a due date, overdue
  ones first. Now: `defined: 'undefined'` and `rows` is `[]`.

- [ ] **Step 2: Implement `loadDay()` and its drawing**

  Exact wording on the strip (three lines, each its own element):
  - Free time: `Free ` + the gaps joined with `, ` and a final ` and `; a gap that ends at
    `WORK_DAY_END` reads `after <start>`; each time through `fmtTime`. No gaps: `No free time
    left today`.
  - Next: `<title> at <fmtTime(time)>, <inWords(in_minutes)>`. None: `Nothing else on today`.
  - Deadline: the first deadline: `<title> is overdue` (overdue), `<title> due today` (0
    days), `<title> due tomorrow` (1 day), otherwise `<title> due <friendlyDue text>` (for
    example `Essay due Thu 29 Oct`). None: `No deadlines`.

  Deadlines panel: one row per deadline (`class="deadline"`, `data-state`), the title, the
  `friendlyDue` text, and a bar whose fill is `max(0, min(1, (window - days_left) / window))`
  of its width, full for overdue; overdue rows red, today amber, the first row marked
  `NEXT UP`. Empty list: `No deadlines`.

  When it runs: on `enter`; after every `loadTasks()` and `loadEvents()` while Work is shown
  (wrap them in `space-work.js` the way `motion.js` wraps functions: keep the original, call
  it, then `loadDay()` if `currentSpace === 'work'`); and once a minute while Work is shown.
  If the fetch fails or the answer is not OK: the strip and Deadlines both say `Couldn't load
  your day`.

- [ ] **Step 3: Run the browser checks**

  - Step 1's check → as expected; a screenshot shows the strip, the bars, the to-do list and
    the week calendar beside JARVIS's dock.
  - Review Focus 1: tick an open task with a due date in `#work-tasks` (real click) → after
    0.5 s it is gone from `#work-deadlines`, and `#tasks` shows it ticked; untick → back.
  - Review Focus 4: through the demo database, add a task due in 20 days and one due 3 days
    ago (a scratch Python one-off with `JARVIS_DB` pointing at the demo's `demo.db`), reload →
    the far one's bar fill is 0 %, the overdue one is the first row, red, `data-state` overdue.
  - Review Focus 3: in the page, call `drawDay` with
    `{"free": [], "next": null, "deadlines": [], "deadline_window_days": 14}` → `No free time
    left today`, `Nothing else on today`, `No deadlines`, no error.
  - Review Focus 5: stop answering `/day` (in the page, wrap `fetch` so `/day` returns a 500
    once) and call `loadDay()` → both say `Couldn't load your day`; the to-do list and the
    calendar still work.
  - Phone width (375x812): Work's panels in one column under JARVIS, no sideways scrolling.
  - `read_console_messages` with `onlyErrors` → none.

- [ ] **Step 4: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `493 passed`.

  ```bash
  git add static/js/space-work.js static/css/space-work.css
  git commit -m "Show your day, worked out, and the deadlines in the Work space"
  ```

### Task 4: Docs, then the owner's check

**Files:**
- Modify: `CHANGELOG.md` (section 51, "Spaces, stage 2"; the file layout adds `workday.py`;
  a Status row)
- Modify: `README.md` (Work's panels in one short paragraph)
- Modify: `CLAUDE.md` (the file table: `workday.py`; `server.py`'s endpoint list adds `/day`)
- Modify: `plan.md` (the spaces line: stage 2 done)

- [ ] **Step 1: Write the docs**

  Section 51: what changed and why, the settings, what was checked (each Review Focus line
  with its real result), what was not (Safari, the real data). Only checks that ran.

- [ ] **Step 2: Run the Python checks and commit**

  Run: `ruff check . && python -m pytest -q` → `All checks passed!` and `493 passed`.

  ```bash
  git add CHANGELOG.md README.md CLAUDE.md plan.md
  git commit -m "Document spaces, stage 2"
  ```

- [ ] **Step 3: The owner checks it in Safari**

  Stop the demo server. The owner looks at Work in Safari (on the demo or their own server).
  Push only when they say so.
