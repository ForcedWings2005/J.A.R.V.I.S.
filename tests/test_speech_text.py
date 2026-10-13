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
