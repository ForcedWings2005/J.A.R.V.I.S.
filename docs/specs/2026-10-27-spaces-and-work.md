# Spaces, and the Work space (version 1)

Status: design, agreed with the owner in conversation on 2026-10-27. To be approved as
written before the implementation plan.

## Why

Every new feature so far has become a panel on one dashboard. With sports, games and more to
come, that page would get cluttered. Instead, JARVIS gets **spaces**: a welcome screen (today's
dashboard) and separate screens for different activities, each with its own panels. Work is
the first; Sports is the second, built on the same structure.

Work is for a mix: school now (a year left), then a job and personal projects. It should help
run the day, not only show it.

## What the owner asked for

- A welcome dashboard that stays as it is today: **Home**.
- Separate spaces for activities, each with its own panels: Work first, then Sports, Games and
  others later. New spaces are additions; no single page gets cluttered.
- Switching by talking: "JARVIS, let's get some work done".
- JARVIS himself (orb, chat, voice) is present in **every** space.

## Decisions

| Question | Decision | Why |
|---|---|---|
| How spaces are built | **One page that swaps its middle** | The conversation, voice and a waiting confirmation card survive a switch; the transition can run between spaces. Separate pages would reload everything. A frontend framework would bring a build step and many dependencies (plan.md: not yet). |
| How a spoken request switches | **A new tool, `open_space`, that the model calls** | Open-ended wording (below). Trigger words in code would be brittle ("I have work to do" would switch). |
| Where JARVIS is in a space | **Docked on the right**: smaller orb, the conversation, the activity line, the confirmation card, the command bar and microphone | The same elements as on Home, placed by layout rules, not moved in the page, so nothing they do changes. |
| First space | **Work** | It reuses the calendar and to-do list that already work, so it proves the structure on solid ground. |

### Switching is open-ended

There are no fixed words. The model judges what is meant, so "let's get some work done", "time
to study", "open my work space" and "I need to work on my essay" all switch, and "let's get
some work done, what's due this week?" switches and answers. It can misjudge an unusual
phrasing, or switch when work is only mentioned ("I had a long day at work"); the evals measure
both before this ships. Clicking a space name or pressing its number always works, whatever the
model does.

## Version 1: what is in it

### Moving between spaces

- **Header**: a row of space names after the readouts, `1 Home · 2 Work`, the current one
  highlighted. Clicking one switches.
- **Number keys**: `1` Home, `2` Work. Ignored while typing (like `/` today).
- **Address**: the space is in the address (`127.0.0.1:8000/#work`), so a reload or the Back
  button keeps it. No address part means Home.
- **Voice or chat**: the `open_space` tool.
- **Transition**: the access sequence (section 42) for a whole space: "ACCESSING WORK", the bar,
  "ACCESS GRANTED", the panels beam in, and the orb glides into the dock. Back to Home reverses
  it. A click or Escape skips it; Reduce motion makes it instant.
- **Phone width** (under 900 px): one column, as today; in a space, JARVIS's dock comes first and
  the space's panels below.
- **Unchanged everywhere**: the header readouts and switches, the boot sequence, the lights and
  glass, the motion layer, and every security rule.

### Home

Exactly as today, plus the space names in the header.

### Work

Four panels, with JARVIS docked on the right:

1. **"Your day, worked out"**, a strip across the top, worked out by code from the calendar and
   the to-do list (never by the model):
   - the **free time left today**: gaps of at least `WORK_MIN_GAP_MINUTES` (30) between now,
     today's events and the end of the day, within `WORK_DAY_START`-`WORK_DAY_END`
     (08:00-22:00), for example "Free 13:00-15:00 and after 17:30";
   - **what's next**, for example "Dentist at 15:00, in 2 hours";
   - the **nearest deadline**, for example "Essay due in 2 days".
2. **Deadlines**: open tasks that have a due date, soonest first. Each has a countdown bar
   that fills as the date comes closer, over 14 days. Overdue in red, due today in amber; the
   soonest is marked "next up". Uses the due dates the to-do list already stores.
3. **To-do**: the same list as on Home, with more room. Ticking works as on Home and shows
   everywhere.
4. **Calendar, always open**: the full calendar (year, month, week, day) in the middle,
   starting in week view.

## Later versions (not in version 1)

- **v2: focus mode** ("focus for 25 minutes": a countdown, the rest dimmed, JARVIS speaks when
  time is up), built together with **reminders**, because both need the server to speak up by
  itself.
- **v3: "Plan my afternoon"**: JARVIS proposes time blocks for open tasks in the free gaps, as
  **one confirmation card** for the whole plan; nothing is added until Confirm.
- **v4: quick capture** ("JARVIS, note that ...") into a scratchpad, growing into a
  **brainstorm board** (its own design, with a database change), and an **end-of-day review**.
- **A tool for free time** ("when am I free this afternoon?"): easy once `workday.py` exists,
  but a new tool is a prompt change with its own evals.
- Other ideas kept for later: a colour per space, each space remembering its state, a greeting
  on arrival, fewer tools per space, JARVIS suggesting a space, spaces notifying each other.

## How it works

### Files

| File | New or changed | What |
|---|---|---|
| `workday.py` | new | Free-time gaps, what's next and deadline states, as plain functions on events, tasks and "now". |
| `spaces.py` | new | The `open_space` tool. |
| `config.py` | changed | `SPACES = ("home", "work")`, `WORK_DAY_START = "08:00"`, `WORK_DAY_END = "22:00"`, `WORK_MIN_GAP_MINUTES = 30`, `DEADLINE_WINDOW_DAYS = 14`. |
| `tools.py` | changed | `ShowSpace(name, reply)`: what a tool returns to change the view, like `NeedsConfirmation` but needing no click. |
| `brain.py` | changed | `run_tool` handles `ShowSpace` and the turn streams a `space` event; the time stamp names the space when it is not Home; `spaces` is imported after `notes`, so the existing tools keep their order. |
| `server.py` | changed | `ChatRequest` gains an optional `space`; new read-only `GET /day`. |
| `static/index.html` | changed | The space names in the header; a `<section>` for Work. |
| `static/js/spaces.js` | new | The registry of spaces, the header names, number keys, the address, switching. |
| `static/js/space-work.js`, `static/css/space-work.css` | new | Everything that belongs only to Work. |
| `static/js/calendar.js` | changed | Able to draw into a given element, not only Home's Schedule panel (see Risks). |
| `static/js/chat.js` | changed | Sends the current space with each message; switches on a `space` event. |
| `static/css/jarvis.css`, `static/css/motion.css`, `static/js/motion.js` | changed | The dock layout; the space transition. |

Each space registers itself in `spaces.js` (its name, its title and what to do on entering
and leaving), much as a tool registers with `@tool`. Adding Sports later means a new section,
a new script and a new stylesheet, without editing Work.

### Switching by voice, step by step

1. The model calls `open_space(name)`. Its schema lists the names in `config.SPACES`.
2. The tool checks the name; an unknown one is an error ("Error: no space called 'gym'.
   Spaces: home, work."). It is not in `ASKS_FIRST` (section 44): it never shows a card, so no
   "No card was shown" note is added.
3. It returns `ShowSpace("work", "Showing the Work space.")`. `run_tool` records it, the turn
   streams `{"type": "space", "name": "work"}` at once, and the result text goes to the model,
   which answers in its own words.
4. The page plays the transition while the reply streams in.

### How JARVIS knows where you are

The page sends the current space with every message (`{"message": ..., "space": "work"}`). An
unknown value is refused (422), like any other bad body. The server adds it to the time stamp:
`[Monday 2030-01-07 09:01 · Work] `. On Home nothing is added, so Home's messages are exactly
as today. The space is never put in the system prompt, which must stay the same all day
(CHANGELOG section 27). The prompt gained one fixed sentence, while building stage 3, saying
what a space in the stamp means; placed beside the time-stamp instructions it hurt the AM/PM
question, so it sits before the general-knowledge part (CHANGELOG section 52).

### `GET /day`

Read-only, like `/calendar` and `/tasks`; it changes nothing and, being a GET, the Origin check
does not apply (as for the other reads). It returns, for now:

```json
{
  "free": [{"start": "13:00", "end": "15:00"}, {"start": "17:30", "end": "22:00"}],
  "next": {"title": "Dentist", "time": "15:00", "in_minutes": 120},
  "deadlines": [
    {"id": 3, "title": "Submit essay", "due": "2030-01-09", "days_left": 2, "state": "soon"}
  ],
  "deadline_window_days": 14,
  "day_end": "22:00"
}
```

(The last two were added while building stage 2, so the page reads the settings from
`config.py` instead of repeating them; CHANGELOG section 51.)

`next` is `null` when nothing else is on today. `deadlines` lists every open task that has a
due date; `state` is `overdue`, `today` or `soon` (any later day). The countdown bar starts to
fill `DEADLINE_WINDOW_DAYS` (14) before the due date, so a task due further away shows an empty
bar. Gaps come from today's events with repeats expanded
(`jcal.events_between`), starting from now (or `WORK_DAY_START` if now is earlier) and ending at
`WORK_DAY_END`, so after `WORK_DAY_END` the list is empty; overlapping events merge; gaps shorter than `WORK_MIN_GAP_MINUTES` are left out.

### When something goes wrong

- An unknown space name: an error result to the model; the view stays where it is.
- `/day` fails: its panels say "Couldn't load your day" and the rest of Work works.
- An unknown space in the address: Home.
- A space's script failing must not stop Home.

## Security and privacy

- Nothing leaves the Mac: no new outside connection, no new dependency.
- `GET /day` is read-only. `open_space` changes only the view: it never deletes, overwrites or
  sends anything, so it does not need the confirmation path and is not in `ASKS_FIRST`.
- The new `space` field is checked against `config.SPACES` before use; it never reaches SQL.
- The server stays on 127.0.0.1; the host, Origin and JSON-only checks are unchanged.

## Testing

- **Python tests**, each written first and seen failing:
  - `workday.py`: gaps between events, overlapping events, a repeating event, events already
    over, now before `WORK_DAY_START`, now after `WORK_DAY_END`, the 30-minute minimum, no
    events at all; deadline states (overdue, today, days left), tasks without a due date left
    out, done tasks left out.
  - `GET /day` with made-up data.
  - `open_space`: a known name gives `ShowSpace`, an unknown one an error; the turn streams the
    `space` event; the schema lists `config.SPACES`.
  - `/chat` with a `space`: the time stamp names it; Home adds nothing; an unknown space is 422.
- **Evals**: new cases that should switch ("let's get some work done", "time to study") and
  that should not ("I had a long day at work", "what's on my calendar today?"), plus "let's
  get some work done, what's due this week?" (switch and answer). A new tool is a prompt
  change: full eval before and after, with both prompt hashes.
- **In a browser**: a demo with made-up data at desktop and phone width (the calendar in all
  four views, in Work and on Home; switching by click, key, address and voice; Reduce motion),
  then the owner in Safari.

## Build order

Each stage is its own commit and leaves JARVIS working:

1. **The structure**: spaces, the header names, number keys, the address, the dock layout and
   an empty Work space, switching by click and key.
2. **The Work panels**: `workday.py`, `GET /day`, the four panels, the calendar drawing into
   Work.
3. **Switching by voice**: `open_space`, `ShowSpace`, the `space` event and the time stamp,
   with the evals before and after.
4. **The transition** and the docs (CHANGELOG, README, CLAUDE.md, plan.md).

## Risks

- **The calendar** draws only into Home's Schedule panel today (`calBox`, one shared state).
  Making it draw into Work's panel too is the riskiest change: checked in all four views in
  both places.
- **A new tool changes what the model sees.** Section 39 and section 47 showed that a
  description change can unsettle unrelated cases (`task_complete`). The full eval decides;
  if a case suffers, the tool's description is reworded and measured again.
- **The dock** reuses Home's chat elements through layout rules; the confirmation card, voice
  and the transcript must keep working while docked: checked by hand in the demo.
