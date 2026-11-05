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
