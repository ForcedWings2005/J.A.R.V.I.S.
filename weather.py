"""Weather: places, forecasts and air quality from Open-Meteo.

This is the first module that reads anything from the internet, so it follows the privacy
rule in SECURITY.md section 5: only three fixed HTTPS addresses (config.py), built here by
code; requests carry only what the service needs (the place, coordinates rounded to about
1 km); the model never chooses an address. Every figure is worked out here, never by the model.
Spec: docs/specs/2026-11-05-weather-space.md.
"""
import json
import logging
import math
import time
import unicodedata
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


# ---------- figures, worked out in code (the model never does arithmetic) ----------

def round_half_up(x: float | None) -> int | None:
    """Python's round() sends 0.5 to the nearest even number (round(0.5) is 0); people expect 1."""
    return None if x is None else math.floor(x + 0.5)


def to_f(c: float | None) -> int | None:
    """°C to °F, rounded once at the end so °F and °C never disagree by a rounding step."""
    return None if c is None else round_half_up(c * 9 / 5 + 32)


def kmh_to_mph(kmh: float | None) -> int | None:
    return None if kmh is None else round_half_up(kmh / 1.609344)


def m_to_km(m: float | None) -> int | None:
    return None if m is None else round_half_up(m / 1000)


def m_to_mi(m: float | None) -> int | None:
    return None if m is None else round_half_up(m / 1609.344)


def hpa_to_inhg(hpa: float | None) -> float | None:
    return None if hpa is None else round(hpa * 0.02953, 2)


def clean(text: str | None, limit: int = config.WEATHER_NAME_MAX) -> str:
    """Outside text, made safe to show and to give the model: no control or invisible
    formatting characters (such as one that reverses the text), one space between words,
    and no longer than `limit`."""
    if text is None:
        return ""
    kept = []
    for ch in str(text):
        if ch.isspace():
            kept.append(" ")
        elif not unicodedata.category(ch).startswith("C"):
            kept.append(ch)
    return " ".join("".join(kept).split())[:limit].strip()


# WMO weather codes, as Open-Meteo sends them: words, and the icon the page draws.
# Codes 0 and 1 use the sun by day and the moon by night.
CONDITIONS = {
    0: ("clear", None), 1: ("mainly clear", None), 2: ("partly cloudy", "part-cloud"),
    3: ("overcast", "cloud"), 45: ("fog", "fog"), 48: ("fog", "fog"),
    51: ("drizzle", "rain"), 53: ("drizzle", "rain"), 55: ("drizzle", "rain"),
    56: ("freezing drizzle", "rain"), 57: ("freezing drizzle", "rain"),
    61: ("light rain", "rain"), 63: ("rain", "rain"), 65: ("heavy rain", "rain"),
    66: ("freezing rain", "rain"), 67: ("freezing rain", "rain"),
    71: ("light snow", "snow"), 73: ("snow", "snow"), 75: ("heavy snow", "snow"),
    77: ("snow grains", "snow"),
    80: ("rain showers", "rain"), 81: ("rain showers", "rain"), 82: ("rain showers", "rain"),
    85: ("snow showers", "snow"), 86: ("snow showers", "snow"),
    95: ("thunderstorm", "thunder"), 96: ("thunderstorm with hail", "thunder"),
    99: ("thunderstorm with hail", "thunder"),
}


def condition(code: int | None, is_day: bool) -> tuple[str, str]:
    words, icon = CONDITIONS.get(code, ("unknown", "cloud"))
    return words, icon or ("sun" if is_day else "moon")


# US AQI and UV bands: (upper limit, label), checked in order
AQI_BANDS = ((50, "Good"), (100, "Moderate"), (150, "Unhealthy for sensitive groups"),
             (200, "Unhealthy"), (300, "Very unhealthy"))
UV_BANDS = ((2, "Low"), (5, "Moderate"), (7, "High"), (10, "Very high"))


def _band(value: int, bands, top: str) -> str:
    for limit, label in bands:
        if value <= limit:
            return label
    return top


def aqi_label(aqi: float | None) -> str | None:
    return None if aqi is None else _band(round_half_up(aqi), AQI_BANDS, "Hazardous")


def uv_label(uv: float | None) -> str | None:
    return None if uv is None else _band(round_half_up(uv), UV_BANDS, "Extreme")


def hour_words(hour: int) -> str:
    """0 -> 'midnight', 12 -> 'noon', 14 -> '2 pm': how the times are spoken and shown."""
    if hour % 24 == 0:
        return "midnight"
    if hour == 12:
        return "noon"
    return f"{hour % 12} {'am' if hour < 12 else 'pm'}"


def rain_windows(hours: list[tuple[int, int | None]]) -> str:
    """Consecutive hours with at least WEATHER_RAIN_CHANCE percent chance of rain, in words:
    'from 2 pm to 5 pm'. A window ends at the hour after its last rainy hour."""
    windows, start, last = [], None, None
    for hour, chance in hours:
        rainy = chance is not None and chance >= config.WEATHER_RAIN_CHANCE
        if rainy and start is None:
            start = hour
        if not rainy and start is not None:
            windows.append((start, (last + 1) % 24))
            start = None
        last = hour
    if start is not None:
        windows.append((start, (last + 1) % 24))
    return " and ".join(f"from {hour_words(a)} to {hour_words(b)}" for a, b in windows)


def say_degrees(n: int) -> str:
    """'-3' would be read out as 'dash 3' or skipped; 'minus 3' is what people say."""
    return f"minus {-n}" if n < 0 else str(n)


def spoken_line(name: str, now: dict, today: dict) -> str:
    """What JARVIS says after a place is confirmed, written by code so the numbers are right.
    Both units for the current temperature only; anything missing is left out."""
    if now.get("temp_f") is None or now.get("temp_c") is None:
        line = f"{name}: {now['condition']}."
    else:
        line = (f"{name}: {say_degrees(now['temp_f'])} degrees, {say_degrees(now['temp_c'])} "
                f"Celsius, and {now['condition']}.")
    if today.get("high_f") is not None:
        line += f" High of {say_degrees(today['high_f'])}"
        if today.get("rain_chance") is not None:
            line += f", {today['rain_chance']} percent chance of rain"
        line += "."
    return line
