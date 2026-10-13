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


def test_delete_matches_when_the_user_says_more_than_the_title():
    """'Cancel my dentist appointment' must find an event titled 'Dentist'."""
    jcal.add_event("Dentist", day(1), "14:00")
    found = jcal.find_for_delete("dentist appointment", day(1))
    assert isinstance(found, dict)
    assert "Dentist" in found["text"]


def test_delete_still_matches_part_of_the_title():
    jcal.add_event("Biological anthropology class", day(1), "10:00")
    assert isinstance(jcal.find_for_delete("anthropology", day(1)), dict)


def test_delete_whole_series_without_a_date():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    found = jcal.find_for_delete("piano lessons", scope="all")
    assert "ALL" in found["text"]
    jcal.apply_delete(found["action"])
    assert dates(0, 60) == []


def test_delete_one_occurrence_needs_a_date():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    assert jcal.find_for_delete("piano", scope="this").startswith("Error")


def test_delete_without_a_date_ignores_events_that_are_over(clock):
    jcal.add_event("Yoga", day(1), "18:00", repeat="weekly", repeat_until=day(8))
    jcal.add_event("Yoga", day(30), "18:00", repeat="weekly")
    clock.set(9, day=20)            # the first series ended on day 8
    found = jcal.find_for_delete("yoga", scope="all")
    assert isinstance(found, dict)
    assert found["action"]["date"] == day(30)


def test_delete_without_a_date_with_two_series_asks_which_one():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    jcal.add_event("Piano practice", day(2), "08:00", repeat="daily")
    found = jcal.find_for_delete("piano", scope="all")
    assert isinstance(found, str) and "several" in found


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


# ---------- changing events (update_event) ----------

from tools import NeedsConfirmation  # noqa: E402


def change(*args, **kwargs):
    """Ask for a change; return the confirmation request (fails the test on an error)."""
    req = jcal.update_event(*args, **kwargs)
    assert isinstance(req, NeedsConfirmation), req
    return req


def times_on(n, title=None):
    return [(e["time"], e["end_time"], e["title"]) for e in occurrences(n, n, title)]


def test_moving_an_event_keeps_its_length_and_waits_for_confirm():
    jcal.add_event("Dentist", day(1), "15:00", "16:30")
    req = change("dentist appointment", day(1), new_start_time="16:00")
    assert req.card == f"Change 'Dentist' on {day(1)} at 15:00-16:30: time to 16:00-17:30?"
    assert times_on(1) == [("15:00", "16:30", "Dentist")]             # nothing changed yet
    assert req.apply() == f"Done. 'Dentist' is now on {day(1)} from 16:00 to 17:30."
    assert times_on(1) == [("16:00", "17:30", "Dentist")]


def test_a_new_end_time_alone_changes_the_length():
    jcal.add_event("Meeting", day(1), "10:00")
    change("meeting", day(1), new_end_time="11:30").apply()
    assert times_on(1) == [("10:00", "11:30", "Meeting")]


def test_moving_a_one_off_event_to_another_day():
    jcal.add_event("Dentist", day(1), "15:00")
    change("dentist", day(1), new_date=day(3)).apply()
    assert times_on(1) == [] and times_on(3) == [("15:00", "16:00", "Dentist")]


def test_renaming_an_event():
    jcal.add_event("Dentist", day(1), "15:00")
    req = change("dentist", day(1), new_title="Orthodontist")
    assert "title to 'Orthodontist'" in req.card
    req.apply()
    assert times_on(1) == [("15:00", "16:00", "Orthodontist")]


def test_changing_one_occurrence_leaves_the_rest_of_the_series():
    jcal.add_event("Piano lesson", day(1), "16:00", "17:00", repeat="weekly")
    req = change("piano", day(8), new_start_time="17:30")
    assert req.card.startswith(f"Change only the {day(8)} occurrence of 'Piano lesson'")
    req.apply()
    assert times_on(1) == [("16:00", "17:00", "Piano lesson")]
    assert times_on(8) == [("17:30", "18:30", "Piano lesson")]           # exactly one, moved
    assert times_on(15) == [("16:00", "17:00", "Piano lesson")]


def test_changing_the_whole_series_without_a_date():
    jcal.add_event("Piano lesson", day(1), "16:00", "17:00", repeat="weekly")
    req = change("piano lessons", scope="all", new_start_time="17:00")
    assert req.card.startswith("Change ALL occurrences of 'Piano lesson'")
    assert req.apply() == "Done. Every 'Piano lesson' is now from 17:00 to 18:00."
    assert {t for d in (1, 8, 15) for t in times_on(d)} == {("17:00", "18:00", "Piano lesson")}


def test_a_whole_series_cannot_move_to_other_days():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    result = jcal.update_event("piano", scope="all", new_date=day(2))
    assert isinstance(result, str) and "cannot be moved to other dates or days" in result


def test_a_move_into_another_event_is_refused():
    jcal.add_event("Dentist", day(1), "15:00")
    jcal.add_event("Team meeting", day(1), "16:00")
    result = jcal.update_event("dentist", day(1), new_start_time="16:30")
    assert result == f"Error: conflicts with 'Team meeting' at 16:00 on {day(1)}."


def test_moving_half_an_hour_does_not_clash_with_itself():
    jcal.add_event("Dentist", day(1), "15:00")
    change("dentist", day(1), new_start_time="15:30").apply()
    assert times_on(1) == [("15:30", "16:30", "Dentist")]


def test_a_series_change_checks_every_upcoming_occurrence():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    jcal.add_event("Recital", day(22), "17:00")                       # clashes in 3 weeks
    result = jcal.update_event("piano", scope="all", new_start_time="17:00")
    assert result == f"Error: conflicts with 'Recital' at 17:00 on {day(22)}."


def test_confirm_checks_again_and_changes_nothing_if_the_slot_was_taken():
    jcal.add_event("Dentist", day(1), "15:00")
    req = change("dentist", day(1), new_start_time="18:00")
    jcal.add_event("Dinner", day(1), "18:00")                          # added meanwhile
    assert req.apply() == f"Nothing was changed. conflicts with 'Dinner' at 18:00 on {day(1)}."
    assert ("15:00", "16:00", "Dentist") in times_on(1)


def test_confirm_after_the_event_was_deleted_changes_nothing():
    jcal.add_event("Dentist", day(1), "15:00")
    req = change("dentist", day(1), new_start_time="17:00")
    jcal.apply_delete(jcal.find_for_delete("dentist", day(1))["action"])
    assert req.apply() == "Nothing was changed. that event no longer exists."
    assert times_on(1) == []


def test_past_times_and_finished_events_cannot_be_changed(clock):
    jcal.add_event("Dentist", day(0), "09:00")
    assert jcal.update_event("dentist", day(0), new_start_time="07:00") == \
        "Error: the new time is in the past."
    clock.set(11)                                                      # it ended at 10:00
    assert jcal.update_event("dentist", day(0), new_start_time="15:00") == \
        "Error: that occurrence has already happened, so it cannot be changed."


@pytest.mark.parametrize("kwargs,error", [
    ({}, "nothing would change"),
    ({"new_start_time": "15:00"}, "nothing would change"),
    ({"new_start_time": "3pm"}, "new_start_time must be HH:MM"),
    ({"new_end_time": "14:00"}, "end time must be after the start"),
    ({"new_date": "Friday"}, "new_date must be YYYY-MM-DD"),
    ({"new_start_time": "23:30"}, "run past midnight"),
    ({"scope": "sometimes"}, "scope must be"),
])
def test_bad_changes_come_back_as_errors(kwargs, error):
    jcal.add_event("Dentist", day(1), "15:00")
    result = jcal.update_event("dentist", day(1), **kwargs)
    assert isinstance(result, str) and result.startswith("Error") and error in result


def test_changing_one_occurrence_needs_its_date():
    jcal.add_event("Piano lesson", day(1), "16:00", repeat="weekly")
    assert jcal.update_event("piano", new_start_time="17:00").startswith(
        "Error: give the date of the occurrence to change")


def test_a_new_length_in_minutes_sets_the_end():
    jcal.add_event("Team meeting", day(3), "10:00", "11:00")
    req = change("team meeting", day(3), new_length_minutes=90)
    assert "time to 10:00-11:30" in req.card
    req.apply()
    assert times_on(3) == [("10:00", "11:30", "Team meeting")]


def test_moving_with_a_new_length_uses_the_new_start():
    jcal.add_event("Team meeting", day(3), "10:00", "11:00")
    change("team meeting", day(3), new_start_time="14:00", new_length_minutes=30).apply()
    assert times_on(3) == [("14:00", "14:30", "Team meeting")]


@pytest.mark.parametrize("kwargs,error", [
    ({"new_length_minutes": 90, "new_end_time": "12:00"}, "not both"),
    ({"new_length_minutes": -5}, "1 to 1440"),
    ({"new_length_minutes": 2000}, "1 to 1440"),
    ({"new_length_minutes": "ninety"}, "1 to 1440"),
])
def test_bad_lengths_come_back_as_errors(kwargs, error):
    jcal.add_event("Team meeting", day(3), "10:00", "11:00")
    result = jcal.update_event("team meeting", day(3), **kwargs)
    assert isinstance(result, str) and error in result


def test_a_length_sent_as_text_is_accepted():
    jcal.add_event("Team meeting", day(3), "10:00", "11:00")
    change("team meeting", day(3), new_length_minutes="90").apply()
    assert times_on(3) == [("10:00", "11:30", "Team meeting")]


def test_the_model_is_told_what_the_card_says():
    jcal.add_event("Dentist", day(1), "15:00")
    req = change("dentist", day(1), new_start_time="16:00")
    assert req.reply.startswith("Confirmation required.")
    assert req.card in req.reply and "NOT been changed" in req.reply
