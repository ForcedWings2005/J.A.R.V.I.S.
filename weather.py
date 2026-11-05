"""Weather: places, forecasts and air quality from Open-Meteo.

This is the first module that reads anything from the internet, so it follows the privacy
rule in SECURITY.md section 5: only three fixed HTTPS addresses (config.py), built here by
code; requests carry only what the service needs (the place, coordinates rounded to about
1 km); the model never chooses an address. Every figure is worked out here, never by the model.
Spec: docs/specs/2026-11-05-weather-space.md.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import config

log = logging.getLogger("jarvis.weather")

ADDRESSES = (config.WEATHER_GEOCODE_URL, config.WEATHER_FORECAST_URL, config.WEATHER_AIR_URL)
UNREACHABLE = "Couldn't reach the weather service."


class WeatherError(Exception):
    """Something went wrong reaching Open-Meteo. The message is safe to show the user."""


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """urllib normally follows a "go over there instead" reply, which could take JARVIS to
    another site. Returning None makes it raise HTTPError instead, so the address stays fixed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirects)


def _fetch(address: str) -> bytes:
    """The one door to the internet. Tests replace it (tests/conftest.py)."""
    with _OPENER.open(address, timeout=config.WEATHER_TIMEOUT_SECONDS) as reply:
        return reply.read(config.WEATHER_MAX_BYTES + 1)


def _get(base: str, params: dict) -> dict:
    """Ask one of the three fixed addresses; any failure becomes one plain WeatherError."""
    if base not in ADDRESSES:
        raise ValueError(f"not a weather address: {base}")
    address = base + "?" + urllib.parse.urlencode(params)
    host = urllib.parse.urlsplit(base).hostname
    start = time.monotonic()
    outcome = "ok"
    try:
        body = _fetch(address)
        if len(body) > config.WEATHER_MAX_BYTES:
            raise ValueError("reply too large")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("reply is not a JSON object")
        return data
    except (OSError, ValueError) as e:   # URLError, HTTPError and timeouts are OSErrors
        outcome = type(e).__name__
        raise WeatherError(UNREACHABLE) from e
    finally:
        # The host and timing only: the address itself holds the place
        log.info("weather request: %s, %s in %d ms", host, outcome,
                 (time.monotonic() - start) * 1000)
