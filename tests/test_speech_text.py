"""Tests for the text clean-up done before JARVIS speaks."""
import pytest

from speech_text import prepare, speak_numbers


@pytest.mark.parametrize("text,spoken", [
    # The bug: with a full stop at the end, espeak read "38.4444444444." as
    # "thirty-eight. four billion four hundred and forty-four million ..."
    ("The result is 38.4444444444.", "The result is 38 point 4 4 4 4."),
    ("346 / 9 = 38.4444444444", "346 / 9 = 38 point 4 4 4 4"),
    ("It is 38.4444444444, sir.", "It is 38 point 4 4 4 4, sir."),
    ("That is 409.5.", "That is 409 point 5."),
    ("Pi is 3.14159265", "Pi is 3 point 1 4 1 6"),          # rounded, not cut off
    ("about 2.99999999", "about 3"),                         # rounding carries over
    ("0.05 of it", "0 point 0 5 of it"),
    ("7,006,652 exactly", "7006652 exactly"),
    ("1,234.56789", "1234 point 5 6 7 9"),
    ("Version 1.2.3 stays", "Version 1.2.3 stays"),
    ("In 2030, 15 people came.", "In 2030, 15 people came."),  # a real comma stays
    ("At 10:30 and 18:00", "At 10:30 and 18:00"),
])
def test_speak_numbers(text, spoken):
    assert speak_numbers(text) == spoken


def test_sentence_end_after_a_whole_number_is_untouched():
    assert speak_numbers("You have 3. Shall I list them?") == "You have 3. Shall I list them?"


def test_prepare_strips_markdown_and_fixes_pronunciation():
    assert prepare("**Trastevere** is 2.5 km away") == "Trah-stay-veh-reh is 2 point 5 km away"


# ---------- dates ----------

from datetime import date  # noqa: E402

from speech_text import speak_dates  # noqa: E402

THIS_YEAR = date(2026, 10, 14)


@pytest.mark.parametrize("text,spoken", [
    # The bug: read as "two thousand and twenty-six dash ten dash sixteen"
    ("Your dentist is on 2026-10-16 at 15:00.", "Your dentist is on October the 16th at 15:00."),
    ("2026-10-01", "October the 1st"),
    ("2026-11-02", "November the 2nd"),
    ("2026-12-03", "December the 3rd"),
    ("2026-01-11", "January the 11th"),
    ("2026-02-12", "February the 12th"),
    ("2026-03-13", "March the 13th"),
    ("2026-05-21", "May the 21st"),
    ("2026-07-22", "July the 22nd"),
    ("2026-08-23", "August the 23rd"),
    ("2026-12-31", "December the 31st"),
    ("2027-03-03", "March the 3rd, 2027"),               # another year: say which
    ("from 2026-10-16 to 2026-10-23", "from October the 16th to October the 23rd"),
    ("2026-13-45 is not a date", "2026-13-45 is not a date"),
    ("2026-02-30", "2026-02-30"),
    ("serial 12026-10-16-7", "serial 12026-10-16-7"),
])
def test_speak_dates(text, spoken):
    assert speak_dates(text, today=THIS_YEAR) == spoken


def test_prepare_speaks_dates_before_numbers():
    assert prepare("On 2027-03-03 it costs 9.99.", today=THIS_YEAR) == \
        "On March the 3rd, 2027 it costs 9 point 9 9."
