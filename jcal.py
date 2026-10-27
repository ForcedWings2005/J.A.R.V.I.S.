"""Calendar logic for JARVIS: durations, repeating events, per-date exceptions."""
from datetime import datetime, timedelta

from database import conn as db, lock
from tools import ASKS_FIRST, NeedsConfirmation, tool

REPEATS = ("none", "daily", "weekdays", "weekly", "biweekly", "monthly")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FULL_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
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
        every = "every 2 weeks on " if rule == "biweekly" else "weekly on "
        return every + ", ".join(DAY_NAMES[int(x)] for x in rd.split(","))
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
        if rule == "biweekly":
            # Count whole calendar weeks (Monday to Sunday) from the first one, and keep
            # every other week, so "Tuesday and Thursday" stay together in the same week
            first_monday = base - timedelta(days=base.weekday())
            if (d - first_monday).days // 7 % 2:
                return False
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


def _find_clash(d, s: int, e: int, ignore_id=None):
    """The first event on date d overlapping minutes s..e (ignore_id: the event being moved)."""
    for ev in events_between(d, d):
        if ev["id"] == ignore_id:
            continue
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

@tool("List calendar events for a date (YYYY-MM-DD), or for a range of dates by also giving end_date. Use a range for questions like 'what's my week look like'.",
      date={"type": "string", "description": "YYYY-MM-DD"},
      end_date={"type": "string", "description": "Optional last date of a range, YYYY-MM-DD"})
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


@tool("Add a calendar event. Only call when the user has given a title, a date and a start time. If they give an end time or a duration, set end_time (start_time plus the duration). If not, omit end_time and it defaults to one hour. For recurring events like 'every Tuesday', set repeat and use the first occurrence as date.",
      title={"type": "string"},
      date={"type": "string", "description": "YYYY-MM-DD, the first occurrence"},
      start_time={"type": "string", "description": "HH:MM, 24-hour"},
      end_time={"type": "string", "description": "Optional, HH:MM, 24-hour"},
      repeat={"type": "string", "enum": list(REPEATS), "description": "How often it repeats. Default none. 'weekdays' means every Monday through Friday ONLY. For specific days like Wednesday and Friday, use repeat_days instead."},
      repeat_until={"type": "string", "description": "Optional last date of a repeating event, YYYY-MM-DD"},
      repeat_days={"type": "string", "description": "Comma-separated weekdays for a weekly repeat, e.g. 'wed,fri'. Use this whenever the user names specific days of the week."})
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
        if repeat not in ("none", "weekly", "biweekly"):
            return "Error: repeat_days only works with a weekly or fortnightly repeat."
        if repeat == "none":
            repeat = "weekly"
    elif repeat == "weekly":
        # The weekday must come from the user's words, and the code works out the date from
        # it: the model once gave a Sunday date for "every Monday" (CHANGELOG section 39).
        return ("Error: a weekly event needs repeat_days: the weekday or weekdays the user "
                "said, such as 'mon' or 'tue,thu'. The first date is worked out from them.")
    elif repeat == "biweekly":
        # The same for every other week (CHANGELOG section 44)
        return ("Error: a fortnightly event needs repeat_days: the weekday or weekdays the "
                "user said, such as 'fri'. The first date is worked out from them.")

    try:
        when = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "Error: use date YYYY-MM-DD and start_time HH:MM (24-hour)."

    if day_list:
        if when.weekday() not in day_list:
            # The model's date can be a day off either way ("every other Friday" given as a
            # Saturday). Move to the nearest weekday the user named, trying 1 day back, 1 day
            # on, 2 back and so on, so a tie picks the earlier day. Only sliding forward
            # started such a series a week late, on the other Fridays (CHANGELOG section 46).
            shifts = [n for n in (-1, 1, -2, 2, -3, 3) if (when.weekday() + n) % 7 in day_list]
            when += timedelta(days=shifts[0])
        # Then slide forward to the first listed weekday that is still in the future
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
    # The weekday by name, so a wrong date is visible to the model and to the user
    msg = (f"Added '{title}' starting {date} (a {FULL_DAY_NAMES[start_d.weekday()]}) "
           f"from {start_t} to {end_t}")
    if defaulted:
        msg += " (one hour by default)"
    if repeat != "none":
        msg += f", repeating {_rep_label(repeat, stored_days)}"
        msg += f" until {until}" if until else " with no end date"
    return msg + "."

def _title_matches(said: str, title: str) -> bool:
    """'dentist' finds 'Dentist appointment', and 'dentist appointment' finds 'Dentist'."""
    a, b = said.lower().strip(), title.lower().strip()
    return bool(a) and (a in b or b in a)


def _locate(title: str, date: str, scope: str, verb: str):
    """Find the one event the user means. Returns an error string, or (event, date, scope).

    Shared by delete_event and update_event. The date can be left out only with
    scope 'all' (the user rarely knows a date when they say "all my piano lessons").
    """
    scope = (scope or "this").lower().strip()
    if scope not in ("this", "all"):
        return "Error: scope must be 'this' or 'all'."
    if not date:
        if scope != "all":
            # Say what is really wrong: no such event, several, or one that repeats. The
            # old message mentioned a "repeating series" even for a one-off event, and
            # JARVIS then asked "just this one or the whole series?" (CHANGELOG section 44)
            only = _find_series(title)
            if isinstance(only, str):
                return only
            msg = (f"Error: give the date of the occurrence to {verb}, "
                   f"or use scope 'all' to {verb} a whole repeating series.")
            if verb == "change":
                msg += (" date is the event's CURRENT date; new_date is only for "
                        "moving it to a different day.")
            return msg
        found = _find_series(title)
        return found if isinstance(found, str) else (found, found["date"], "all")
    try:
        d = _d(date)
    except ValueError:
        return "Error: use date YYYY-MM-DD."
    matches = [ev for ev in events_between(d, d) if _title_matches(title, ev["title"])]
    if not matches:
        return f"Error: no event matching '{title}' on {date}."
    if len(matches) > 1:
        names = "; ".join(f"{m['time']} {m['title']}" for m in matches)
        return f"Error: several events match ({names}). Ask the user which one."
    return matches[0], date, scope


def _only_one_off(title: str) -> str:
    """The date of the one upcoming event with this title, if it does not repeat; else "".

    Lets "cancel the dentist" or "move the dentist" work without a date. The card shows
    the date that was found, so the user sees which event it is before anything happens.
    """
    only = _find_series(title)
    if isinstance(only, dict) and only["repeat"] == "none":
        return only["date"]
    return ""


def find_for_delete(title: str, date: str = "", scope: str = "this"):
    """Returns an error string, or {'action': ..., 'text': ...} to confirm."""
    found = _locate(title, date, scope, "delete")
    if isinstance(found, str):
        return found
    return _delete_request(*found)


def _find_series(title: str):
    """Without a date: the one event matching the title that still has something ahead."""
    today = datetime.now().date().isoformat()
    with lock:
        rows = db.execute(
            "SELECT id, title, date, time, end_time, repeat_rule, repeat_until, repeat_days "
            "FROM events"
        ).fetchall()
    matches = []
    for id_, t, ds, tm, et, rule, until, rd in rows:
        ahead = ds >= today if rule == "none" else (until is None or until >= today)
        if ahead and _title_matches(title, t):
            matches.append({"id": id_, "title": t, "date": ds, "time": tm, "end_time": et,
                            "repeat": rule, "repeat_label": _rep_label(rule, rd)})
    if not matches:
        return f"Error: no upcoming event matching '{title}'."
    if len(matches) > 1:
        names = "; ".join(f"{m['title']} ({m['repeat_label'] if m['repeat'] != 'none' else m['date']})"
                          for m in matches)
        return f"Error: several events match ({names}). Ask the user which one."
    return matches[0]


def _delete_request(ev: dict, date: str, scope: str) -> dict:
    if ev["repeat"] == "none":
        action = {"event_id": ev["id"], "date": date, "scope": "all"}
        text = f"Delete '{ev['title']}' on {date} at {ev['time']}?"
    elif scope == "all":
        action = {"event_id": ev["id"], "date": date, "scope": "all"}
        text = f"Delete ALL occurrences of '{ev['title']}' (repeats {ev['repeat_label']})?"
    else:
        action = {"event_id": ev["id"], "date": date, "scope": "this"}
        text = (f"Delete only the {date} occurrence of '{ev['title']}' "
                f"(it repeats {ev['repeat_label']})?")
    return {"action": action, "text": text}

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


# Deleting and changing only ask: the card does it (see tools.ASKS_FIRST)
ASKS_FIRST.update({"delete_event", "update_event"})


@tool("Request deletion of the calendar event whose title matches. This only asks the user to confirm on screen; nothing is deleted until they click Confirm. For a repeating event, scope 'this' removes only that date's occurrence, and scope 'all' removes the whole series. Use 'all' only if the user says every occurrence or the whole series. With scope 'all' the date can be left out, so never ask the user for a date just to delete a whole series.",
      title={"type": "string"},
      date={"type": "string", "description": "YYYY-MM-DD, the occurrence to delete. Optional when scope is 'all'."},
      scope={"type": "string", "enum": ["this", "all"]})
def delete_event(title: str, date: str = "", scope: str = "this"):
    """Never deletes anything itself: returns a request the user must confirm."""
    if not date and (scope or "this").lower().strip() != "all":
        date = _only_one_off(title)
    found = find_for_delete(title, date, scope)
    if isinstance(found, str):
        return found
    action = found["action"]

    def apply() -> str:
        apply_delete(action)
        return "Done. The event has been deleted."

    return NeedsConfirmation(
        card=found["text"], apply=apply,
        # Facts for the model to put in its own words; an order such as "tell the user to
        # confirm" was read out word for word (CHANGELOG section 38)
        reply=f"Confirmation required. The event has NOT been deleted yet. The card on "
              f"screen asks: \"{found['text']}\" It is deleted only if the user taps "
              "Confirm. Make sure the user knows it needs their Confirm on the card; say "
              "that in your own words.",
    )


# ---------- changing an event (update_event) ----------

def _event_row(event_id: int):
    with lock:
        r = db.execute(
            "SELECT id, title, date, time, end_time, repeat_rule, repeat_until, repeat_days "
            "FROM events WHERE id = ?", (event_id,)
        ).fetchone()
    if r is None:
        return None
    id_, t, ds, tm, et, rule, until, rd = r
    return {"id": id_, "title": t, "date": ds, "time": tm, "end_time": et, "repeat": rule,
            "repeat_until": until, "repeat_days": rd, "repeat_label": _rep_label(rule, rd)}


def _parse_hhmm(value: str):
    try:
        t = datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
    return t.hour * 60 + t.minute


def _work_out_update(event_id: int, date: str, scope: str, new_title: str, new_date: str,
                     new_start_time: str, new_end_time: str, new_length_minutes: int = 0):
    """Check a change and work out exactly what it would do.

    Returns an error string, or a plan dict. It runs twice: once to build the
    confirmation card, and again when the user clicks Confirm, in case the
    calendar changed in between (for example, something now in that slot).
    """
    ev = _event_row(event_id)
    if ev is None:
        return "Error: that event no longer exists."
    one_off = ev["repeat"] == "none"
    whole = scope == "all" and not one_off            # change every occurrence of a series
    if not one_off and not whole:
        occurrences = events_between(_d(date), _d(date))
        if not any(o["id"] == event_id for o in occurrences):
            return f"Error: '{ev['title']}' is no longer on {date}."

    old_s = _mins(ev["time"])
    old_e = _mins(ev["end_time"]) if ev["end_time"] else old_s + 60
    title = (new_title or "").strip() or ev["title"]

    if whole and new_date:
        return ("Error: a whole repeating series cannot be moved to other dates or days. "
                "Delete it and add it again with the new days, or move one occurrence.")
    target = new_date or (ev["date"] if whole else date)
    try:
        _d(target)
    except ValueError:
        return "Error: new_date must be YYYY-MM-DD."

    s, e = old_s, old_e
    if new_start_time:
        s = _parse_hhmm(new_start_time)
        if s is None:
            return "Error: new_start_time must be HH:MM (24-hour)."
        e = s + (old_e - old_s)                       # moving keeps the length
    if new_end_time and new_length_minutes:
        return "Error: give new_end_time or new_length_minutes, not both."
    if new_end_time:
        e = _parse_hhmm(new_end_time)
        if e is None:
            return "Error: new_end_time must be HH:MM (24-hour)."
    if new_length_minutes:
        # The code works out the end, so the model never adds up times itself
        # The model sometimes sends numbers as text ("90"), so accept digit strings too
        minutes = str(new_length_minutes).strip()
        if not minutes.isdigit() or not 0 < int(minutes) <= 24 * 60:
            return "Error: new_length_minutes must be a whole number of minutes, 1 to 1440."
        e = s + int(minutes)
    if e > 23 * 60 + 59:
        return "Error: the event would run past midnight. Give an end time on the same day."
    if e <= s:
        return "Error: the end time must be after the start time on the same day."
    if (title, target, s, e) == (ev["title"], date if not whole else ev["date"], old_s, old_e):
        return "Error: nothing would change. Ask the user what they want to change."

    now = datetime.now()
    if not whole:
        if datetime.strptime(f"{date} {_hhmm(old_e)}", "%Y-%m-%d %H:%M") <= now:
            return "Error: that occurrence has already happened, so it cannot be changed."
        if datetime.strptime(f"{target} {_hhmm(s)}", "%Y-%m-%d %H:%M") < now:
            return "Error: the new time is in the past."
        clash = _find_clash(_d(target), s, e, ignore_id=event_id)
        if clash:
            return f"Error: conflicts with '{clash['title']}' at {clash['time']} on {target}."
    else:
        # Every upcoming occurrence of the series, 90 days ahead (as add_event checks)
        start = max(now.date(), _d(ev["date"]))
        for occ in events_between(start, start + timedelta(days=90)):
            if occ["id"] != event_id:
                continue
            clash = _find_clash(_d(occ["date"]), s, e, ignore_id=event_id)
            if clash:
                return (f"Error: conflicts with '{clash['title']}' at "
                        f"{clash['time']} on {occ['date']}.")

    changes = []
    if title != ev["title"]:
        changes.append(f"title to '{title}'")
    if target != (ev["date"] if whole else date):
        changes.append(f"date to {target}")
    if (s, e) != (old_s, old_e):
        changes.append(f"time to {_hhmm(s)}-{_hhmm(e)}")
    was = f"{_hhmm(old_s)}-{_hhmm(old_e)}"
    if one_off:
        card = f"Change '{ev['title']}' on {date} at {was}: {', '.join(changes)}?"
    elif whole:
        card = (f"Change ALL occurrences of '{ev['title']}' (repeats {ev['repeat_label']}, "
                f"{was}): {', '.join(changes)}?")
    else:
        card = (f"Change only the {date} occurrence of '{ev['title']}' "
                f"(it repeats {ev['repeat_label']}, {was}): {', '.join(changes)}?")
    return {"card": card, "event_id": event_id, "kind": "one_off" if one_off else
            ("series" if whole else "occurrence"), "date": date, "target": target,
            "title": title, "start": _hhmm(s), "end": _hhmm(e)}


def apply_update(plan: dict) -> str:
    """Write a confirmed change. Only ever called from the Confirm button."""
    with lock:
        if plan["kind"] == "one_off":
            db.execute("UPDATE events SET title = ?, date = ?, time = ?, end_time = ? WHERE id = ?",
                       (plan["title"], plan["target"], plan["start"], plan["end"], plan["event_id"]))
        elif plan["kind"] == "series":
            db.execute("UPDATE events SET title = ?, time = ?, end_time = ? WHERE id = ?",
                       (plan["title"], plan["start"], plan["end"], plan["event_id"]))
        else:
            # One occurrence of a series: skip that date, add a one-off in its place
            db.execute("INSERT OR IGNORE INTO event_exceptions (event_id, date) VALUES (?, ?)",
                       (plan["event_id"], plan["date"]))
            db.execute(
                "INSERT INTO events (title, date, time, end_time, repeat_rule) "
                "VALUES (?, ?, ?, ?, 'none')",
                (plan["title"], plan["target"], plan["start"], plan["end"]),
            )
        db.commit()
    if plan["kind"] == "series":
        return f"Done. Every '{plan['title']}' is now from {plan['start']} to {plan['end']}."
    return f"Done. '{plan['title']}' is now on {plan['target']} from {plan['start']} to {plan['end']}."


def _date_for_change(title: str, new_date: str):
    """update_event was called without the event's current date. Work it out if that is safe.

    1. Exactly one upcoming event has this title and it does not repeat: use its date
       (so "move the dentist to Thursday" works without one).
    2. Otherwise, if the event really is on new_date, the model put the current date in
       the wrong field: use it as the date, and move nothing to another day.
    Returns (date, new_date); date stays "" if neither applies. Whatever is worked out
    here is shown on the confirmation card before anything changes.
    """
    only = _only_one_off(title)
    if only:
        return only, new_date
    if new_date:
        try:
            d = _d(new_date)
        except ValueError:
            return "", new_date
        if any(_title_matches(title, ev["title"]) for ev in events_between(d, d)):
            return new_date, ""
    return "", new_date


@tool("Request a change to a calendar event: its time, length, date or title. This only asks the user to confirm on screen; nothing changes until they click Confirm. Find the event by its title and date, as for delete_event. For a repeating event, scope 'this' changes only that date's occurrence and scope 'all' changes the whole series. With scope 'all' only the title is needed: the tool finds the series itself, so never ask the user for its date, days or current time. For 'all my piano lessons' or 'from now on', call this straight away with scope 'all' and the title. Give only what changes: new_start_time alone moves the event and keeps its length; new_length_minutes sets its length (for 'make it last 90 minutes' pass 90, without needing the start time); new_end_time sets an exact end. A whole series cannot be moved to other days.",
      title={"type": "string"},
      date={"type": "string", "description": "The event's CURRENT date, YYYY-MM-DD (the occurrence to change). Optional when scope is 'all', and when only one upcoming event has this title, so never ask the user for it."},
      scope={"type": "string", "enum": ["this", "all"]},
      new_title={"type": "string", "description": "Optional new title"},
      new_date={"type": "string", "description": "Optional new date, YYYY-MM-DD"},
      new_start_time={"type": "string", "description": "Optional new start, HH:MM 24-hour"},
      new_end_time={"type": "string", "description": "Optional new end, HH:MM 24-hour"},
      new_length_minutes={"type": "integer", "description": "Optional new length in minutes, e.g. 90"})
def update_event(title: str, date: str = "", scope: str = "this", new_title: str = "",
                 new_date: str = "", new_start_time: str = "", new_end_time: str = "",
                 new_length_minutes: int = 0):
    """Never changes anything itself: returns a request the user must confirm."""
    if not date and (scope or "this").lower().strip() != "all":
        date, new_date = _date_for_change(title, new_date)
    found = _locate(title, date, scope, "change")
    if isinstance(found, str):
        return found
    ev, occ_date, scope = found
    args = (ev["id"], occ_date, scope, new_title, new_date, new_start_time, new_end_time,
            new_length_minutes)
    plan = _work_out_update(*args)
    if isinstance(plan, str):
        return plan

    def apply() -> str:
        fresh = _work_out_update(*args)           # check again: the calendar may have changed
        if isinstance(fresh, str):
            return "Nothing was changed. " + fresh.removeprefix("Error: ")
        return apply_update(fresh)

    return NeedsConfirmation(
        card=plan["card"], apply=apply,
        # The model sees what the card says, so it can describe the change accurately
        reply=f"Confirmation required. The card on screen asks: \"{plan['card']}\" "
              "The event has NOT been changed yet; it changes only if the user taps "
              "Confirm. Make sure the user knows it needs their Confirm on the card; say "
              "that in your own words.",
    )
