"""The Work space's figures: free time left today, what's next, and deadlines.

Worked out by code, never by the model (CLAUDE.md: anything that must be right is checked in
code). Plain functions on today's events and the to-do list; `day_summary` gathers them for
GET /day. Spec: docs/specs/2026-10-27-spaces-and-work.md.
"""
from datetime import date, datetime

import config
import jcal
import tasks


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _span(ev: dict) -> tuple:
    start = _mins(ev["time"])
    return start, _mins(ev["end_time"]) if ev.get("end_time") else start + 60


def free_gaps(events: list, now: datetime, day_start: str = config.WORK_DAY_START,
              day_end: str = config.WORK_DAY_END,
              min_gap: int = config.WORK_MIN_GAP_MINUTES) -> list:
    """The free stretches between now and the end of the working day, in time order."""
    begin = max(now.hour * 60 + now.minute, _mins(day_start))
    end = _mins(day_end)
    out = []
    for start, stop in sorted(_span(ev) for ev in events) + [(end, end)]:
        start, stop = max(start, begin), min(stop, end)
        if start - begin >= min_gap:
            out.append({"start": _hhmm(begin), "end": _hhmm(start)})
        begin = max(begin, stop)           # overlapping events just push the start along
        if begin >= end:
            break
    return out


def next_event(events: list, now: datetime) -> dict | None:
    """The first of today's events that has not started yet."""
    minute = now.hour * 60 + now.minute
    later = sorted((ev for ev in events if _mins(ev["time"]) > minute), key=lambda e: e["time"])
    if not later:
        return None
    ev = later[0]
    return {"title": ev["title"], "time": ev["time"], "in_minutes": _mins(ev["time"]) - minute}


def deadlines(task_list: list, today: date) -> list:
    """Open tasks with a due date, soonest first: how many days are left, and their state."""
    out = []
    for t in task_list:
        if t["done"] or not t["due"]:
            continue
        left = (date.fromisoformat(t["due"]) - today).days
        state = "overdue" if left < 0 else "today" if left == 0 else "soon"
        out.append({"id": t["id"], "title": t["title"], "due": t["due"], "days_left": left,
                    "state": state})
    return sorted(out, key=lambda d: (d["due"], d["id"]))


def day_summary(now: datetime | None = None) -> dict:
    """Everything the Work space shows at the top: for GET /day."""
    now = now or jcal.datetime.now()       # the calendar's clock, which the tests freeze
    today = now.date()
    events = jcal.events_between(today, today)
    return {
        "free": free_gaps(events, now),
        "next": next_event(events, now),
        "deadlines": deadlines(tasks.tasks_list(), today),
        "deadline_window_days": config.DEADLINE_WINDOW_DAYS,
    }
