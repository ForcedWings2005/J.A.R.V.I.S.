"""Tests for jcal.py: durations, repeats, conflicts, deletes and finished/upcoming labels."""
from datetime import date, timedelta

import pytest

import jcal

MON = date(2030, 1, 7)      # the frozen "today" (see conftest.py)


def day(n):
    """ISO date string for n days after the frozen today."""
    return (MON + timedelta(days=n)).isoformat()


def occurrences(first, last, title=None):
    """Expanded events between day(first) and day(last), optionally by title."""
    evs = jcal.events_between(MON + timedelta(days=first), MON + timedelta(days=last))
    return [e for e in evs if title is None or e["title"] == title]


def dates(first, last):
    return [e["date"] for e in occurrences(first, last)]


# ---------- adding events ----------

def test_add_event_defaults_to_one_hour():
    msg = jcal.add_event("Dentist", day(1), "14:00")
    assert msg.startswith("Added")
    assert "from 14:00 to 15:00" in msg
    assert "one hour by default" in msg
    assert "Dentist" in jcal.get_events(day(1))


def test_add_event_with_end_time():
    msg = jcal.add_event("Class", day(1), "10:00", end_time="11:15")
    assert "from 10:00 to 11:15" in msg
    assert "default" not in msg


def test_end_must_be_after_start():
    assert jcal.add_event("Bad", day(1), "10:00", end_time="09:00").startswith("Error")
    assert jcal.add_event("Bad", day(1), "10:00", end_time="10:00").startswith("Error")


def test_event_starting_at_the_very_end_of_the_day_needs_an_end_time():
    assert jcal.add_event("Late", day(1), "23:59").startswith("Error")


@pytest.mark.parametrize("date_text, time_text", [
    ("2030-13-01", "10:00"),
    ("not a date", "10:00"),
    (day(1), "25:99"),
    (day(1), "10am"),
])
def test_bad_formats_are_rejected(date_text, time_text):
    assert jcal.add_event("X", date_text, time_text).startswith("Error")


def test_past_times_are_rejected():
    # The frozen clock says it is Monday 08:00
    assert "past" in jcal.add_event("Too early", day(0), "07:00")
    assert jcal.add_event("Later today", day(0), "09:00").startswith("Added")


def test_empty_title_is_rejected():
    assert jcal.add_event("   ", day(1), "10:00").startswith("Error")


# ---------- conflicts ----------

def test_overlapping_events_are_rejected():
    jcal.add_event("A", day(1), "10:00", end_time="11:00")
    msg = jcal.add_event("B", day(1), "10:30", end_time="11:30")
    assert msg.startswith("Error")
    assert "conflicts with 'A'" in msg


def test_back_to_back_events_are_allowed():
    jcal.add_event("A", day(1), "10:00", end_time="11:00")
    assert jcal.add_event("B", day(1), "11:00", end_time="12:00").startswith("Added")


def test_default_one_hour_still_blocks_overlaps():
    jcal.add_event("A", day(1), "10:00")                    # 10:00 to 11:00
    assert jcal.add_event("B", day(1), "10:30").startswith("Error")


def test_legacy_event_without_end_time_counts_as_one_hour():
    with jcal.lock:
        jcal.db.execute(
            "INSERT INTO events (title, date, time, end_time, repeat_rule) "
            "VALUES ('Legacy', ?, '10:00', NULL, 'none')", (day(1),))
        jcal.db.commit()
    assert jcal.add_event("New", day(1), "10:30").startswith("Error")
    assert jcal.add_event("New", day(1), "11:00").startswith("Added")


# ---------- repeating events ----------

def test_weekly_repeat_expands_each_week():
    jcal.add_event("Gym", day(1), "18:00", repeat="weekly")
    assert dates(0, 21) == [day(1), day(8), day(15)]


def test_biweekly_repeat_skips_every_other_week():
    jcal.add_event("Review", day(1), "18:00", repeat="biweekly")
    assert dates(0, 30) == [day(1), day(15), day(29)]


def test_daily_repeat_fills_every_day():
    jcal.add_event("Walk", day(1), "07:00", repeat="daily")
    assert dates(0, 4) == [day(1), day(2), day(3), day(4)]


def test_weekdays_rule_skips_the_weekend():
    jcal.add_event("Standup", day(0), "09:00", repeat="weekdays")     # starts Monday
    assert dates(0, 6) == [day(i) for i in range(5)]                    # Mon to Fri only


def test_repeat_until_stops_the_series():
    jcal.add_event("Gym", day(1), "18:00", repeat="weekly", repeat_until=day(9))
    assert dates(0, 60) == [day(1), day(8)]


def test_repeat_until_before_the_start_is_rejected():
    msg = jcal.add_event("Gym", day(5), "18:00", repeat="weekly", repeat_until=day(1))
    assert msg.startswith("Error")


def test_unknown_repeat_rule_is_rejected():
    assert jcal.add_event("Gym", day(1), "18:00", repeat="hourly").startswith("Error")


def test_monthly_repeat_on_the_31st_skips_short_months():
    # Known limit, recorded in CHANGELOG.md: February has no 31st.
    with jcal.lock:
        jcal.db.execute(
            "INSERT INTO events (title, date, time, end_time, repeat_rule) "
            "VALUES ('Rent', '2030-01-31', '10:00', '11:00', 'monthly')")
        jcal.db.commit()
    evs = jcal.events_between(date(2030, 1, 31), date(2030, 3, 31))
    assert [e["date"] for e in evs] == ["2030-01-31", "2030-03-31"]


def test_repeating_event_checks_conflicts_in_the_future():
    jcal.add_event("Dentist", day(15), "18:30", end_time="19:30")       # two weeks out
    msg = jcal.add_event("Gym", day(1), "18:00", end_time="19:00", repeat="weekly")
    assert msg.startswith("Error")
    assert "conflicts with 'Dentist'" in msg


# ---------- repeating on specific weekdays (the Wednesday and Friday bug) ----------

def test_repeat_days_wednesday_and_friday():
    jcal.add_event("Class", day(0), "10:00", end_time="11:15", repeat_days="wed,fri")
    assert dates(0, 13) == [day(2), day(4), day(9), day(11)]            # Wed, Fri, Wed, Fri


def test_repeat_days_start_slides_to_the_first_matching_day():
    msg = jcal.add_event("Class", day(0), "10:00", repeat_days="wed,fri")   # Monday start
    assert f"starting {day(2)}" in msg
    assert "weekly on Wed, Fri" in msg


def test_repeat_days_skips_a_time_that_has_already_passed_today():
    # Monday 07:00 has passed (it is 08:00), so Monday is skipped
    msg = jcal.add_event("Early", day(0), "07:00", repeat_days="mon,wed")
    assert f"starting {day(2)}" in msg


def test_repeat_days_accepts_full_names_and_mixed_case():
    jcal.add_event("Class", day(0), "10:00", repeat_days="Wednesday, FRIDAY")
    assert dates(0, 6) == [day(2), day(4)]


def test_repeat_days_with_an_end_date_includes_that_day():
    jcal.add_event("Class", day(0), "10:00", repeat_days="wed,fri", repeat_until=day(9))
    assert dates(0, 30) == [day(2), day(4), day(9)]


def test_repeat_days_rejects_nonsense_words():
    assert jcal.add_event("X", day(1), "10:00", repeat_days="blursday").startswith("Error")


def test_repeat_days_cannot_combine_with_a_daily_repeat():
    msg = jcal.add_event("X", day(1), "10:00", repeat="daily", repeat_days="wed")
    assert msg.startswith("Error")


def test_parse_days():
    assert jcal._parse_days("Wed, Friday") == [2, 4]
    assert jcal._parse_days("fri;mon") == [0, 4]
    assert jcal._parse_days("funday") is None
    assert jcal._parse_days("") == []


# ---------- deleting ----------

def test_delete_a_single_event():
    jcal.add_event("Dentist", day(1), "14:00")
    found = jcal.find_for_delete("dentist", day(1))
    assert isinstance(found, dict)
    jcal.apply_delete(found["action"])
    assert jcal.get_events(day(1)).startswith("No events")


def test_delete_one_occurrence_keeps_the_rest_of_the_series():
    jcal.add_event("Gym", day(1), "18:00", repeat="weekly")
    found = jcal.find_for_delete("Gym", day(8), scope="this")
    assert "only" in found["text"]
    jcal.apply_delete(found["action"])
    assert dates(0, 21) == [day(1), day(15)]


def test_delete_the_whole_series():
    jcal.add_event("Gym", day(1), "18:00", repeat="weekly")
    found = jcal.find_for_delete("Gym", day(8), scope="all")
    assert "ALL" in found["text"]
    jcal.apply_delete(found["action"])
    assert dates(0, 60) == []


def test_delete_errors_come_back_as_text():
    jcal.add_event("Gym", day(1), "18:00")
    assert jcal.find_for_delete("Nothing", day(1)).startswith("Error")
    assert jcal.find_for_delete("Gym", "bad date").startswith("Error")
    assert jcal.find_for_delete("Gym", day(1), scope="sometimes").startswith("Error")


def test_delete_with_two_matches_asks_which_one():
    jcal.add_event("Study group", day(1), "10:00")
    jcal.add_event("Study hall", day(1), "14:00")
    found = jcal.find_for_delete("study", day(1))
    assert isinstance(found, str)
    assert "several" in found


# ---------- reading events ----------

def test_no_events_message():
    assert jcal.get_events(day(3)).startswith("No events")


def test_results_are_sorted_by_date_then_time():
    jcal.add_event("Late", day(1), "15:00")
    jcal.add_event("Early", day(1), "09:00")
    jcal.add_event("Next day", day(2), "08:00")
    assert [e["title"] for e in occurrences(0, 3)] == ["Early", "Late", "Next day"]


def test_range_lists_several_days_with_dates():
    jcal.add_event("A", day(1), "10:00")
    jcal.add_event("B", day(3), "10:00")
    text = jcal.get_events(day(0), day(6))
    assert day(1) in text and day(3) in text


def test_range_validation():
    assert jcal.get_events(day(5), day(1)).startswith("Error")
    assert jcal.get_events(day(0), day(100)).startswith("Error")
    assert jcal.get_events("not a date").startswith("Error")


def test_result_states_the_current_time():
    assert "it is now Monday 08:00" in jcal.get_events(day(1))


# ---------- finished, in progress and upcoming (the "how are we tonight" bug) ----------

@pytest.mark.parametrize("hour, minute, label", [
    (9, 0, "[upcoming]"),
    (10, 0, "[in progress]"),
    (11, 14, "[in progress]"),
    (11, 15, "[finished]"),
    (12, 0, "[finished]"),
])
def test_status_labels_for_todays_class(clock, hour, minute, label):
    jcal.add_event("Class", day(0), "10:00", end_time="11:15")
    clock.set(hour, minute)
    assert label in jcal.get_events(day(0))


def test_everything_finished_says_nothing_is_left(clock):
    jcal.add_event("Class", day(0), "10:00", end_time="11:15")
    clock.set(21)
    assert "Nothing further is left today." in jcal.get_events(day(0))


def test_an_upcoming_event_means_something_is_left(clock):
    jcal.add_event("Class", day(0), "10:00", end_time="11:15")
    jcal.add_event("Dinner", day(0), "19:00", end_time="20:00")
    clock.set(12)
    text = jcal.get_events(day(0))
    assert "[finished]" in text and "[upcoming]" in text
    assert "Nothing further" not in text


def test_future_days_get_no_label_and_no_note(clock):
    jcal.add_event("Dentist", day(1), "10:00")
    clock.set(21)
    text = jcal.get_events(day(1))
    assert "[" not in text
    assert "Nothing further" not in text


def test_past_days_are_all_finished(clock):
    jcal.add_event("Class", day(0), "10:00")
    clock.set(8, day=15)                                   # a week later
    assert "[finished]" in jcal.get_events(day(0))


def test_legacy_event_without_end_time_is_labelled_as_one_hour(clock):
    with jcal.lock:
        jcal.db.execute(
            "INSERT INTO events (title, date, time, end_time, repeat_rule) "
            "VALUES ('Legacy', ?, '10:00', NULL, 'none')", (day(0),))
        jcal.db.commit()
    clock.set(10, 30)
    assert "[in progress]" in jcal.get_events(day(0))
    clock.set(11, 0)
    assert "[finished]" in jcal.get_events(day(0))
