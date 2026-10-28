"""Tests for workday.py: free time, what's next and deadlines, for the Work space.

Spec: docs/specs/2026-10-27-spaces-and-work.md (the "Your day, worked out" strip and
Deadlines). The day runs 08:00-22:00 and gaps under 30 minutes are left out.
"""
from datetime import date, datetime

import jcal
import tasks
import workday


def ev(start, end=None, title="X"):
    return {"title": title, "time": start, "end_time": end}


def at(hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(2030, 1, 7, h, m)


def gaps(*pairs):
    return [{"start": a, "end": b} for a, b in pairs]


# ---------- free time ----------

def test_free_time_between_events():
    assert workday.free_gaps([ev("09:00", "10:00"), ev("13:00", "14:30")], at("08:00")) == \
        gaps(("08:00", "09:00"), ("10:00", "13:00"), ("14:30", "22:00"))


def test_free_time_starts_now():
    assert workday.free_gaps([ev("09:00", "10:00"), ev("13:00", "14:30")], at("11:10")) == \
        gaps(("11:10", "13:00"), ("14:30", "22:00"))


def test_overlapping_events_merge():
    assert workday.free_gaps([ev("09:00", "11:00"), ev("10:30", "12:00")], at("08:00")) == \
        gaps(("08:00", "09:00"), ("12:00", "22:00"))


def test_gaps_under_30_minutes_are_left_out():
    assert workday.free_gaps([ev("09:00", "10:00"), ev("10:20", "11:00")], at("08:00")) == \
        gaps(("08:00", "09:00"), ("11:00", "22:00"))


def test_a_gap_of_exactly_30_minutes_is_kept():
    assert workday.free_gaps([ev("09:00", "10:00"), ev("10:30", "11:00")], at("08:00")) == \
        gaps(("08:00", "09:00"), ("10:00", "10:30"), ("11:00", "22:00"))


def test_an_event_without_an_end_lasts_an_hour():
    assert workday.free_gaps([ev("09:00")], at("08:00")) == \
        gaps(("08:00", "09:00"), ("10:00", "22:00"))


def test_before_the_day_starts():
    assert workday.free_gaps([], at("06:00")) == gaps(("08:00", "22:00"))


def test_after_the_day_ends():
    assert workday.free_gaps([], at("22:30")) == []


def test_an_event_past_the_end_of_the_day():
    assert workday.free_gaps([ev("21:00", "23:00")], at("20:00")) == gaps(("20:00", "21:00"))


def test_an_event_after_the_end_of_the_day():
    """Found in the stage 2 demo: a 23:00 event made the free time run on to 23:00."""
    assert workday.free_gaps([ev("23:00", "23:45")], at("20:00")) == gaps(("20:00", "22:00"))


def test_events_already_over_are_ignored():
    assert workday.free_gaps([ev("08:00", "09:00")], at("10:00")) == gaps(("10:00", "22:00"))


# ---------- what's next ----------

def test_next_is_the_first_event_still_to_start():
    evs = [ev("09:00", "09:30", "Stand-up"), ev("15:00", "16:00", "Dentist")]
    assert workday.next_event(evs, at("10:00")) == \
        {"title": "Dentist", "time": "15:00", "in_minutes": 300}


def test_nothing_next_when_the_day_is_done():
    assert workday.next_event([ev("09:00", "09:30"), ev("15:00", "16:00")], at("16:00")) is None


# ---------- deadlines ----------

def test_deadline_states():
    ts = [{"id": 1, "title": "Soon", "due": "2030-01-09", "done": False},
          {"id": 2, "title": "Late", "due": "2030-01-05", "done": False},
          {"id": 3, "title": "Today", "due": "2030-01-07", "done": False},
          {"id": 4, "title": "No date", "due": None, "done": False},
          {"id": 5, "title": "Done", "due": "2030-01-08", "done": True}]
    out = workday.deadlines(ts, date(2030, 1, 7))
    assert [(d["title"], d["days_left"], d["state"]) for d in out] == [
        ("Late", -2, "overdue"), ("Today", 0, "today"), ("Soon", 2, "soon")]


# ---------- the whole summary, from the real calendar and to-do list ----------

def test_day_summary_reads_the_calendar_and_the_tasks():
    """Frozen clock: Monday 2030-01-07 08:00 (conftest.py). The weekly gym counts today."""
    jcal.add_event("Dentist", "2030-01-07", "15:00", "16:00")
    jcal.add_event("Gym", "2030-01-07", "18:00", "19:00", repeat="weekly", repeat_days="mon")
    tasks.add_task("Essay", "2030-01-09")
    s = workday.day_summary()
    assert s["free"] == gaps(("08:00", "15:00"), ("16:00", "18:00"), ("19:00", "22:00"))
    assert s["next"]["title"] == "Dentist" and s["deadline_window_days"] == 14
    assert [d["title"] for d in s["deadlines"]] == ["Essay"]
