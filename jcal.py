"""Calendar logic for JARVIS: durations, repeating events, per-date exceptions."""
import sqlite3
import threading
from datetime import datetime, timedelta

db = sqlite3.connect("jarvis.db", check_same_thread=False)
lock = threading.Lock()

db.execute(
    "CREATE TABLE IF NOT EXISTS events ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "title TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL)"
)
db.execute(
    "CREATE TABLE IF NOT EXISTS event_exceptions ("
    "event_id INTEGER NOT NULL, date TEXT NOT NULL, "
    "PRIMARY KEY (event_id, date))"
)
# Upgrade an existing events table in place (keeps your current events)
_cols = {r[1] for r in db.execute("PRAGMA table_info(events)")}
for _name, _ddl in (
    ("end_time", "TEXT"),
    ("repeat_rule", "TEXT NOT NULL DEFAULT 'none'"),
    ("repeat_until", "TEXT"),
    ("repeat_days", "TEXT"),  # NEW: e.g. "2,4" for Wed and Fri
):
    if _name not in _cols:
        db.execute(f"ALTER TABLE events ADD COLUMN {_name} {_ddl}")
db.commit()

REPEATS = ("none", "daily", "weekdays", "weekly", "biweekly", "monthly")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
REPEAT_WORDS = {
    "daily": "daily", "weekdays": "every weekday (Mon-Fri)", "weekly": "weekly",
    "biweekly": "every 2 weeks", "monthly": "monthly",
}


def _parse_days(s: str):
    """'wed, Friday' -> [2, 4]. Returns None if any word isn't a weekday."""
    out = set()
    for part in (s or "").replace(";", ",").replace(" ", ",").split(","):
        part = part.strip().lower()[:3]
        if not part:
            continue
        if part not in DAYS:
            return None
        out.add(DAYS[part])
    return sorted(out)


def _rep_label(rule: str, rd) -> str:
    if rd:
        return "weekly on " + ", ".join(DAY_NAMES[int(x)] for x in rd.split(","))
    return REPEAT_WORDS.get(rule, rule)


def _d(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _hhmm(m: int) -> str:
    m = min(m, 23 * 60 + 59)
    return f"{m // 60:02d}:{m % 60:02d}"


def _matches(rule: str, base, d, days=None) -> bool:
    if d < base:
        return False
    if rule == "none":
        return d == base
    if days:
        return d.weekday() in days
    if rule == "daily":
        return True
    if rule == "weekdays":
        return d.weekday() < 5
    delta = (d - base).days
    if rule == "weekly":
        return delta % 7 == 0
    if rule == "biweekly":
        return delta % 14 == 0
    if rule == "monthly":
        return d.day == base.day
    return False


def events_between(start, end) -> list:
    """Every occurrence (repeats expanded) from start to end, inclusive."""
    with lock:
        rows = db.execute(
            "SELECT id, title, date, time, end_time, repeat_rule, repeat_until, repeat_days "
            "FROM events WHERE date <= ? AND (repeat_rule != 'none' OR date >= ?)",
            (end.isoformat(), start.isoformat()),
        ).fetchall()
        skips = set(
            db.execute(
                "SELECT event_id, date FROM event_exceptions WHERE date BETWEEN ? AND ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        )
    out = []
    for id_, title, ds, t, et, rule, until, rd in rows:
        base = _d(ds)
        day_list = [int(x) for x in rd.split(",")] if rd else None
        if rule == "none":
            days = [base] if start <= base <= end else []
        else:
            days = []
            stop = min(end, _d(until)) if until else end
            d = max(start, base)
            while d <= stop:
                if _matches(rule, base, d, day_list):
                    days.append(d)
                d += timedelta(days=1)
        for d in days:
            if (id_, d.isoformat()) in skips:
                continue
            out.append({
                "id": id_, "title": title, "date": d.isoformat(),
                "time": t, "end_time": et, "repeat": rule,
                "repeat_label": _rep_label(rule, rd),
            })
    out.sort(key=lambda e: (e["date"], e["time"]))
    return out


def _find_clash(d, s: int, e: int):
    for ev in events_between(d, d):
        es = _mins(ev["time"])
        ee = _mins(ev["end_time"]) if ev["end_time"] else es + 60
        if s < ee and es < e:
            return ev
    return None

def _status(ev: dict, now) -> str:
    """'finished', 'in progress', 'upcoming', or '' for a day that is still ahead."""
    today = now.date().isoformat()
    if ev["date"] < today:
        return "finished"
    if ev["date"] > today:
        return ""
    s = _mins(ev["time"])
    e = _mins(ev["end_time"]) if ev["end_time"] else s + 60
    cur = now.hour * 60 + now.minute
    if cur >= e:
        return "finished"
    if cur >= s:
        return "in progress"
    return "upcoming"

def get_events(date: str, end_date: str = "") -> str:
    try:
        start = _d(date)
        end = _d(end_date) if end_date else start
    except ValueError:
        return "Error: dates must be YYYY-MM-DD."
    if end < start or (end - start).days > 62:
        return "Error: end_date must be on or after date, within 62 days."
    label = date if start == end else f"{date} to {end_date}"
    now = datetime.now()
    clock = f"it is now {now.strftime('%A %H:%M')}"
    evs = events_between(start, end)
    if not evs:
        return f"No events on {label} ({clock})."
    parts = []
    for ev in evs:
        when = ev["time"] + (f"-{ev['end_time']}" if ev["end_time"] else "")
        rep = f" (repeats {ev['repeat_label']})" if ev["repeat"] != "none" else ""
        day = f"{ev['date']} " if start != end else ""
        status = _status(ev, now)
        tag = f" [{status}]" if status else ""
        parts.append(f"{day}{when} {ev['title']}{rep}{tag}")
    text = f"Events on {label} ({clock}): " + "; ".join(parts) + "."
    today_evs = [e for e in evs if e["date"] == now.date().isoformat()]
    if today_evs and all(_status(e, now) == "finished" for e in today_evs):
        text += " Nothing further is left today."
    return text


def add_event(title: str, date: str, start_time: str, end_time: str = "",
              repeat: str = "none", repeat_until: str = "",
              repeat_days: str = "") -> str:
    title = title.strip()
    if not title:
        return "Error: the event needs a title."
    repeat = (repeat or "none").lower().strip()
    if repeat not in REPEATS:
        return "Error: repeat must be one of " + ", ".join(REPEATS) + "."

    day_list = None
    if repeat_days:
        day_list = _parse_days(repeat_days)
        if not day_list:
            return "Error: repeat_days must be weekday names such as 'wed,fri'."
        if repeat not in ("none", "weekly"):
            return "Error: repeat_days only works with a weekly repeat."
        repeat = "weekly"

    try:
        when = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Error: use date YYYY-MM-DD and start_time HH:MM (24-hour)."

    if day_list:
        # Slide forward to the first listed weekday that is still in the future
        while when.weekday() not in day_list or when < datetime.now():
            when += timedelta(days=1)
        date = when.strftime("%Y-%m-%d")
    if when < datetime.now():
        return "Error: that time is in the past."

    start_t = when.strftime("%H:%M")
    s = _mins(start_t)

    defaulted = False
    if end_time:
        try:
            et = datetime.strptime(end_time, "%H:%M")
        except ValueError:
            return "Error: end_time must be HH:MM (24-hour)."
        e = et.hour * 60 + et.minute
        if e <= s:
            return "Error: the end time must be after the start time on the same day."
    else:
        e = min(s + 60, 23 * 60 + 59)
        defaulted = True
        if e <= s:
            return "Error: please give an end time for an event this late."
    end_t = _hhmm(e)

    start_d = _d(date)
    until = None
    if repeat != "none" and repeat_until:
        try:
            until_d = _d(repeat_until)
        except ValueError:
            return "Error: repeat_until must be YYYY-MM-DD."
        if until_d < start_d:
            return "Error: repeat_until is before the start date."
        until = repeat_until

    horizon = start_d
    if repeat != "none":
        horizon = start_d + timedelta(days=90)
        if until and _d(until) < horizon:
            horizon = _d(until)
    d = start_d
    while d <= horizon:
        if _matches(repeat, start_d, d, day_list):
            clash = _find_clash(d, s, e)
            if clash:
                return (f"Error: conflicts with '{clash['title']}' at "
                        f"{clash['time']} on {d.isoformat()}.")
        d += timedelta(days=1)

    stored_days = ",".join(str(x) for x in day_list) if day_list else None
    with lock:
        db.execute(
            "INSERT INTO events (title, date, time, end_time, repeat_rule, repeat_until, repeat_days) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, date, start_t, end_t, repeat, until, stored_days),
        )
        db.commit()
    msg = f"Added '{title}' starting {date} from {start_t} to {end_t}"
    if defaulted:
        msg += " (one hour by default)"
    if repeat != "none":
        msg += f", repeating {_rep_label(repeat, stored_days)}"
        msg += f" until {until}" if until else " with no end date"
    return msg + "."


def apply_delete(action: dict) -> None:
    with lock:
        if action["scope"] == "all":
            db.execute("DELETE FROM events WHERE id = ?", (action["event_id"],))
            db.execute("DELETE FROM event_exceptions WHERE event_id = ?", (action["event_id"],))
        else:
            db.execute(
                "INSERT OR IGNORE INTO event_exceptions (event_id, date) VALUES (?, ?)",
                (action["event_id"], action["date"]),
            )
        db.commit()


EVENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_events",
            "description": "List calendar events for a date (YYYY-MM-DD), or for a range of dates by also giving end_date. Use a range for questions like 'what's my week look like'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "Optional last date of a range, YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_event",
            "description": "Add a calendar event. Only call when the user has given a title, a date and a start time. If they give an end time or a duration, set end_time (start_time plus the duration). If not, omit end_time and it defaults to one hour. For recurring events like 'every Tuesday', set repeat and use the first occurrence as date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD, the first occurrence"},
                    "start_time": {"type": "string", "description": "HH:MM, 24-hour"},
                    "end_time": {"type": "string", "description": "Optional, HH:MM, 24-hour"},
                    "repeat": {"type": "string", "enum": list(REPEATS), "description": "How often it repeats. Default none. 'weekdays' means every Monday through Friday ONLY. For specific days like Wednesday and Friday, use repeat_days instead."},
                    "repeat_until": {"type": "string", "description": "Optional last date of a repeating event, YYYY-MM-DD"},
                    "repeat_days": {"type": "string", "description": "Comma-separated weekdays for a weekly repeat, e.g. 'wed,fri'. Use this whenever the user names specific days of the week."},
                },
                "required": ["title", "date", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_event",
            "description": "Request deletion of the calendar event whose title matches, on a date. This only asks the user to confirm on screen; nothing is deleted until they click Confirm. For a repeating event, scope 'this' removes only that date's occurrence, and scope 'all' removes the whole series. Use 'all' only if the user says every occurrence or the whole series.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD, the occurrence to delete"},
                    "scope": {"type": "string", "enum": ["this", "all"]},
                },
                "required": ["title", "date"],
            },
        },
    },
]