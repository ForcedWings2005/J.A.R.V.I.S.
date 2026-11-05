"""Tests for weather.py: the one door to Open-Meteo, the figures, the places and the cache.

Nothing here goes online: conftest.py makes weather._fetch fail loudly, and each test that
needs a reply puts a made-up one in its place (spec: docs/specs/2026-11-05-weather-space.md).
"""
import http.server
import logging
import threading
import urllib.error

import pytest

import config
import weather


def fake_fetch(monkeypatch, reply):
    """Replace the door with one that records each address and gives `reply` (or raises it)."""
    seen = []

    def fetch(address):
        seen.append(address)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(weather, "_fetch", fetch)
    return seen


# ---------- the one door to the internet ----------

def test_the_three_addresses_are_fixed_https():
    for url in (config.WEATHER_GEOCODE_URL, config.WEATHER_FORECAST_URL, config.WEATHER_AIR_URL):
        assert url.startswith("https://") and "open-meteo.com/" in url


def test_only_the_fixed_addresses_are_used(monkeypatch):
    fake_fetch(monkeypatch, b"{}")
    with pytest.raises(ValueError):
        weather._get("https://example.com/v1/search", {"name": "Paris"})


def test_queries_are_encoded_inside_the_query_string(monkeypatch):
    seen = fake_fetch(monkeypatch, b"{}")
    for words in ("Paris&count=100", "../../x", "São Paulo", "Paris, Texas"):
        weather._get(config.WEATHER_GEOCODE_URL, {"name": words})
    assert all(a.startswith(config.WEATHER_GEOCODE_URL + "?name=") for a in seen)
    assert "Paris%26count%3D100" in seen[0] and "count=100" not in seen[0]
    assert "S%C3%A3o+Paulo" in seen[2] and "Paris%2C+Texas" in seen[3]


@pytest.mark.parametrize("reply", [TimeoutError(), urllib.error.URLError("down"),
                                   b"not json", b"[1, 2]", b"x" * 1_000_001])
def test_anything_wrong_becomes_one_clear_error(monkeypatch, reply):
    fake_fetch(monkeypatch, reply)
    with pytest.raises(weather.WeatherError, match="Couldn't reach the weather service."):
        weather._get(config.WEATHER_FORECAST_URL, {"latitude": 1})


def test_redirects_are_refused():
    """A real server on this Mac answers 302; the opener must not follow it."""
    hits = {"elsewhere": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/elsewhere":
                hits["elsewhere"] += 1
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")
                return
            self.send_response(302)
            self.send_header("Location", "/elsewhere")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    # A short poll, so shutdown() returns at once instead of after half a second
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            weather._OPENER.open(f"http://127.0.0.1:{server.server_port}/start", timeout=2)
        assert caught.value.code == 302
        caught.value.close()
        assert hits["elsewhere"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_each_request_is_logged_without_its_address(monkeypatch, caplog):
    fake_fetch(monkeypatch, b"{}")
    with caplog.at_level(logging.INFO, logger="jarvis.weather"):
        weather._get(config.WEATHER_GEOCODE_URL, {"name": "Paris"})
    assert "geocoding-api.open-meteo.com" in caplog.text and "Paris" not in caplog.text


def test_tests_cannot_reach_the_internet():
    with pytest.raises(AssertionError, match="internet"):
        weather._fetch(config.WEATHER_GEOCODE_URL)


# ---------- the figures, worked out in code ----------

@pytest.mark.parametrize("c, f", [(-40, -40), (0, 32), (100, 212), (18.3, 65), (-17.5, 1),
                                  (None, None)])
def test_celsius_to_fahrenheit_rounds_once_half_up(c, f):
    assert weather.to_f(c) == f


def test_other_units():
    assert weather.kmh_to_mph(20) == 12 and weather.m_to_km(24140) == 24
    assert weather.m_to_mi(24140) == 15 and weather.hpa_to_inhg(1015.2) == 29.98
    assert weather.kmh_to_mph(None) is None and weather.hpa_to_inhg(None) is None


def test_outside_names_are_cleaned():
    assert weather.clean("Pa\x00ris\n  \u202eFrance") == "Paris France"
    assert len(weather.clean("x" * 500)) == 60 and weather.clean(None) == ""


def test_every_known_weather_code_has_words():
    for code in (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
                 80, 81, 82, 85, 86, 95, 96, 99):
        assert weather.condition(code, True)[0] != "unknown", code
    assert weather.condition(0, True) == ("clear", "sun")
    assert weather.condition(0, False) == ("clear", "moon")
    assert weather.condition(12345, True) == ("unknown", "cloud")
    assert weather.condition(None, True) == ("unknown", "cloud")


@pytest.mark.parametrize("aqi, label", [
    (0, "Good"), (50, "Good"), (51, "Moderate"), (100, "Moderate"),
    (101, "Unhealthy for sensitive groups"), (150, "Unhealthy for sensitive groups"),
    (151, "Unhealthy"), (201, "Very unhealthy"), (300, "Very unhealthy"), (301, "Hazardous"),
    (None, None)])
def test_aqi_bands(aqi, label):
    assert weather.aqi_label(aqi) == label


@pytest.mark.parametrize("uv, label", [(2.4, "Low"), (2.5, "Moderate"), (5, "Moderate"),
                                       (6, "High"), (8, "Very high"), (11, "Extreme"),
                                       (None, None)])
def test_uv_bands(uv, label):
    assert weather.uv_label(uv) == label


def test_hour_words():
    assert [weather.hour_words(h) for h in (0, 9, 12, 14, 23)] == \
        ["midnight", "9 am", "noon", "2 pm", "11 pm"]


def test_rain_windows():
    hours = [(13, 10), (14, 60), (15, 40), (16, 70), (17, 20), (22, 50), (23, 80), (0, 90),
             (1, None)]
    assert weather.rain_windows(hours) == "from 2 pm to 5 pm and from 10 pm to 1 am"
    assert weather.rain_windows([(11, 50)]) == "from 11 am to noon"
    assert weather.rain_windows([(9, 39)]) == ""


def test_spoken_line():
    now = {"temp_f": 64, "temp_c": 18, "condition": "clear"}
    today = {"high_f": 70, "rain_chance": 10}
    assert weather.spoken_line("Paris", now, today) == \
        "Paris: 64 degrees, 18 Celsius, and clear. High of 70, 10 percent chance of rain."
    cold = {"temp_f": -3, "temp_c": -19, "condition": "light snow"}
    assert weather.spoken_line("Oslo", cold, today).startswith(
        "Oslo: minus 3 degrees, minus 19 Celsius, and light snow.")


def test_spoken_line_leaves_out_missing_parts():
    now = {"temp_f": 64, "temp_c": 18, "condition": "clear"}
    assert weather.spoken_line("Paris", now, {"high_f": 70, "rain_chance": None}) == \
        "Paris: 64 degrees, 18 Celsius, and clear. High of 70."
    assert weather.spoken_line("Paris", now, {"high_f": None, "rain_chance": None}) == \
        "Paris: 64 degrees, 18 Celsius, and clear."


def test_spoken_line_without_a_current_temperature():
    now = {"temp_f": None, "temp_c": None, "condition": "clear"}
    assert weather.spoken_line("Paris", now, {"high_f": 70, "rain_chance": 10}) == \
        "Paris: clear. High of 70, 10 percent chance of rain."
