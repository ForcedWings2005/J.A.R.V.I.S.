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
import secrets
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date
from time import monotonic   # its own name, so tests can move the cache's clock

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


# ---------- places, summaries, the cache and the place on screen ----------

# What is asked for (names from Open-Meteo's docs, read 2026-11-05). UV and visibility are
# not listed as "current" values there, so they come from the hourly data at the current hour.
CURRENT = ("temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,is_day,"
           "wind_speed_10m,wind_direction_10m,pressure_msl")
HOURLY = "temperature_2m,precipitation_probability,weather_code,is_day,visibility,uv_index"
DAILY = ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
         "sunrise,sunset")
POLLEN = ("alder", "birch", "grass", "mugwort", "olive", "ragweed")   # Europe only
AIR = "us_aqi,pm2_5,ozone," + ",".join(f"{kind}_pollen" for kind in POLLEN)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# All in memory, never in jarvis.db. One lock guards these three, and is never held while
# a request is out, so a slow Open-Meteo cannot stop anything else.
_lock = threading.Lock()
_cache: OrderedDict = OrderedDict()   # key -> (expires_at, value)
_ids: OrderedDict = OrderedDict()     # match id -> (expires_at, place)
_place = None                         # the place on screen, once confirmed


def forget_everything() -> None:
    """For the tests: no cache, no ids, no place."""
    global _place
    with _lock:
        _cache.clear()
        _ids.clear()
        _place = None


def place_on_screen() -> dict | None:
    with _lock:
        return dict(_place) if _place else None


def clear_place() -> None:
    global _place
    with _lock:
        _place = None


def _keep(store: OrderedDict, key, value) -> None:
    """Store for WEATHER_CACHE_SECONDS, dropping expired entries, then the oldest beyond the cap."""
    now = monotonic()
    for old in [k for k, (expires, _) in store.items() if expires <= now]:
        del store[old]
    store[key] = (now + config.WEATHER_CACHE_SECONDS, value)
    store.move_to_end(key)
    while len(store) > config.WEATHER_CACHE_ENTRIES:
        store.popitem(last=False)


def _cached(key: tuple, make):
    """The value for `key` if fetched in the last 10 minutes, else make() it. Errors are
    not kept, so the next try asks again."""
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] > monotonic():
            return hit[1]
    value = make()                    # outside the lock: this may wait on the network
    with _lock:
        _keep(_cache, key, value)
    return value


def _round(x: float) -> float:
    return round(float(x), config.WEATHER_COORD_DECIMALS)


def find_places(query: str) -> list[dict]:
    """Up to WEATHER_MATCHES places for the words, largest first, each with a short id the
    page sends back to confirm (so neither the page nor the model can invent a place)."""
    q = str(query).strip()
    if not 1 <= len(q) <= config.WEATHER_QUERY_MAX:
        raise ValueError("a place to search for must be 1 to 80 characters")
    results = _cached(("geo", q.lower()), lambda: _get(config.WEATHER_GEOCODE_URL, {
        "name": q, "count": config.WEATHER_MATCHES, "language": "en", "format": "json",
    }).get("results") or [])
    places = []
    for r in sorted(results, key=lambda r: -(r.get("population") or -1)):
        try:
            places.append({"name": clean(r.get("name")), "region": clean(r.get("admin1")),
                           "country": clean(r.get("country")),
                           "lat": _round(r["latitude"]), "lon": _round(r["longitude"])})
        except (KeyError, TypeError, ValueError):
            continue                  # a result without coordinates cannot be shown
    matches = []
    with _lock:
        for place in places[:config.WEATHER_MATCHES]:
            pid = secrets.token_urlsafe(6)
            _keep(_ids, pid, place)
            matches.append({"id": pid, **place})
    return matches


def _at(values, i):
    """values[i], or None when the list is missing, too short or holds null there."""
    try:
        return values[i]
    except (IndexError, TypeError):
        return None


def _summary(place: dict, f: dict, a: dict | None) -> dict:
    """Open-Meteo's replies turned into what the page draws. 'Now' is the forecast's own
    time, already in the place's time zone, never this Mac's clock."""
    current, hourly, daily = f.get("current") or {}, f.get("hourly") or {}, f.get("daily") or {}
    now_time = str(current.get("time") or "")
    words, icon = condition(current.get("weather_code"), bool(current.get("is_day")))
    now = {"time": now_time[11:16], "temp_c": round_half_up(current.get("temperature_2m")),
           "temp_f": to_f(current.get("temperature_2m")),
           "feels_c": round_half_up(current.get("apparent_temperature")),
           "feels_f": to_f(current.get("apparent_temperature")),
           "condition": words, "icon": icon, "is_day": bool(current.get("is_day"))}

    times = hourly.get("time") or []
    this_hour = now_time[:13] + ":00"
    first = next((i for i, t in enumerate(times) if t >= this_hour), len(times))
    hours = []
    for i in range(first, min(first + 24, len(times))):
        is_day = bool(_at(hourly.get("is_day"), i))
        temp = _at(hourly.get("temperature_2m"), i)
        hours.append({"time": times[i][11:16], "temp_c": round_half_up(temp),
                      "temp_f": to_f(temp),
                      "rain_chance": _at(hourly.get("precipitation_probability"), i),
                      "icon": condition(_at(hourly.get("weather_code"), i), is_day)[1],
                      "is_day": is_day})

    days = []
    for i, day in enumerate((daily.get("time") or [])[:7]):
        high, low = _at(daily.get("temperature_2m_max"), i), _at(daily.get("temperature_2m_min"), i)
        d_words, d_icon = condition(_at(daily.get("weather_code"), i), True)
        days.append({"date": day, "weekday": WEEKDAYS[date.fromisoformat(day).weekday()],
                     "condition": d_words, "icon": d_icon,
                     "high_c": round_half_up(high), "high_f": to_f(high),
                     "low_c": round_half_up(low), "low_f": to_f(low),
                     "rain_chance": _at(daily.get("precipitation_probability_max"), i)})

    at_now = first if first < len(times) else None
    uv = _at(hourly.get("uv_index"), at_now) if at_now is not None else None
    seen = _at(hourly.get("visibility"), at_now) if at_now is not None else None
    wind, pressure = current.get("wind_speed_10m"), current.get("pressure_msl")
    details = {"wind_kmh": round_half_up(wind), "wind_mph": kmh_to_mph(wind),
               "wind_dir": current.get("wind_direction_10m"),
               "humidity": current.get("relative_humidity_2m"),
               "uv": uv, "uv_label": uv_label(uv),
               "sunrise": str(_at(daily.get("sunrise"), 0) or "")[11:16] or None,
               "sunset": str(_at(daily.get("sunset"), 0) or "")[11:16] or None,
               "pressure_hpa": round_half_up(pressure), "pressure_inhg": hpa_to_inhg(pressure),
               "visibility_km": m_to_km(seen), "visibility_mi": m_to_mi(seen)}

    air = None
    if a is not None:
        now_air = a.get("current") or {}
        pollen = {kind: now_air[f"{kind}_pollen"] for kind in POLLEN
                  if now_air.get(f"{kind}_pollen") is not None}
        aqi = round_half_up(now_air.get("us_aqi"))
        air = {"aqi": aqi, "aqi_label": aqi_label(aqi), "pm2_5": now_air.get("pm2_5"),
               "ozone": now_air.get("ozone"), "pollen": pollen or None}

    full_place = {**place, "timezone": clean(f.get("timezone")),
                  "utc_offset_seconds": f.get("utc_offset_seconds")}
    return {"place": full_place, "now": now, "hours": hours,
            "rain": rain_windows([(int(h["time"][:2]), h["rain_chance"]) for h in hours]),
            "days": days, "details": details, "air": air}


def forecast_for(place: dict) -> dict:
    """The forecast and air quality for a place (from the cache when recent). A forecast that
    cannot be fetched raises WeatherError; air quality that cannot only leaves `air` empty."""
    where = {"latitude": _round(place["lat"]), "longitude": _round(place["lon"])}
    key = (where["latitude"], where["longitude"])
    f = _cached(("forecast", *key), lambda: _get(config.WEATHER_FORECAST_URL, {
        **where, "current": CURRENT, "hourly": HOURLY, "daily": DAILY,
        "timezone": "auto", "forecast_days": 7}))
    try:
        a = _cached(("air", *key), lambda: _get(config.WEATHER_AIR_URL, {
            **where, "current": AIR, "timezone": "auto"}))
    except WeatherError:
        a = None
    return _summary(place, f, a)


def _show(place: dict) -> dict:
    """Fetch first, and only then make it the place on screen, so a failure changes nothing."""
    global _place
    payload = forecast_for(place)
    payload["spoken"] = spoken_line(place["name"], payload["now"],
                                    payload["days"][0] if payload["days"] else {})
    with _lock:
        _place = payload["place"]
    return payload


def confirm(place_id: str) -> dict:
    """'This one' on the ping: the place behind a match id the server issued, or LookupError."""
    with _lock:
        hit = _ids.get(place_id)
        place = hit[1] if hit and hit[0] > monotonic() else None
    if place is None:
        raise LookupError("unknown or expired place id")
    return _show(place)


def open_home(name: str, lat: float, lon: float) -> dict:
    """The saved home place, sent by the page itself (checked by server.py first)."""
    return _show({"name": clean(name), "region": "", "country": "",
                  "lat": _round(lat), "lon": _round(lon)})
