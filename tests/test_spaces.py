"""Tests for spaces.py: the open_space tool, which shows a space on screen.

Spec: docs/specs/2026-10-27-spaces-and-work.md ("Switching by voice, step by step").
"""
import config
import spaces
import tools


def test_a_known_space_is_shown():
    assert spaces.open_space("work") == tools.ShowSpace("work", "Showing the Work space.")


def test_the_name_is_read_loosely():
    assert spaces.open_space(" Work ").name == "work"


def test_an_unknown_space_is_an_error():
    assert spaces.open_space("gym") == "Error: no space called 'gym'. Spaces: home, work, weather."


def test_the_schema_lists_the_spaces():
    schema = next(s for s in tools.SCHEMAS if s["function"]["name"] == "open_space")
    assert schema["function"]["parameters"]["properties"]["name"]["enum"] == list(config.SPACES)
    assert "open_space" not in tools.ASKS_FIRST


def test_weather_is_a_space():
    """Weather stage 3 (docs/specs/2026-11-05-weather-space.md)."""
    assert spaces.open_space("Weather") == tools.ShowSpace("weather", "Showing the Weather space.")
