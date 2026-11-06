"""Weather: places, forecasts and air quality from Open-Meteo.

This is the first module that reads anything from the internet, so it follows the privacy
rule in SECURITY.md section 5: only three fixed HTTPS addresses (config.py), built here by
code; requests carry only what the service needs (the place, coordinates rounded to about
1 km); the model never chooses an address. Every figure is worked out here, never by the model.
JARVIS's two tools are at the end: find_place (the page then asks the user to confirm) and
get_forecast (facts for the place the user confirmed). Neither can choose a place itself.
Spec: docs/specs/2026-11-05-weather-space.md.
"""
import json
import logging
import math
import re
import secrets
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date
from time import monotonic   # its own name, so tests can move the cache's clock

import truststore

import config
from tools import ShowPlaces, tool

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


# HTTPS proves it is really Open-Meteo by a certificate, checked against a list of trusted
# signers. python.org's Python ships without such a list, so every request was refused.
# truststore checks against macOS's own list, the one Safari uses (the owner's choice,
# 2026-11-05), and keeps both checks on: the certificate and the host name.
_TLS = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_OPENER = urllib.request.build_opener(_RefuseRedirects, urllib.request.HTTPSHandler(context=_TLS))


def _fetch(address: str) -> bytes:
    """The one door to the internet. Tests replace it (tests/conftest.py)."""
    with _OPENER.open(address, timeout=config.WEATHER_TIMEOUT_SECONDS) as reply:
        return reply.read(config.WEATHER_MAX_BYTES + 1)


def _refuse_constant(name: str):
    """Python's json reads NaN and Infinity, which are not real JSON and not real weather."""
    raise ValueError(f"{name} in a reply")


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
        data = json.loads(body, parse_constant=_refuse_constant)
        if not isinstance(data, dict):
            raise ValueError("reply is not a JSON object")
        return data
    # URLError, HTTPError and timeouts are OSErrors; RecursionError: absurdly nested JSON
    except (OSError, ValueError, RecursionError) as e:
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
_waiting = None                       # (expires_at, place): a search not yet confirmed


def forget_everything() -> None:
    """For the tests: no cache, no ids, no place."""
    global _place, _waiting
    with _lock:
        _cache.clear()
        _ids.clear()
        _place = None
        _waiting = None


def place_on_screen() -> dict | None:
    with _lock:
        return dict(_place) if _place else None


def clear_place() -> None:
    global _place, _waiting
    with _lock:
        _place = None
        _waiting = None


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


# A reply is outside data: it is read only through these, so a value of the wrong type (a
# word where a number belongs, a list where a table belongs) becomes "missing", never a
# crash, and never text that reaches the page or the conversation (final review).

def _num(x) -> int | float | None:
    """x if it is a real, finite number, else None (True counts as a bool, not a 1)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return x if math.isfinite(x) else None


def _text(x) -> str:
    return x if isinstance(x, str) else ""


def _obj(x) -> dict:
    return x if isinstance(x, dict) else {}


def _at(values, i):
    """values[i], or None when the list is missing, too short or holds null there."""
    if not isinstance(values, list) or i is None or not 0 <= i < len(values):
        return None
    return values[i]


def _weekday(day: str) -> str | None:
    try:
        return WEEKDAYS[date.fromisoformat(day).weekday()]
    except ValueError:
        return None


_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d")


def _clock(stamp) -> str | None:
    """'2026-11-05T07:45' -> '07:45'; anything else -> None (final review: a stamp that only
    looked right, such as 'TXX:YY', reached the model)."""
    text = _text(stamp)
    return text[11:16] if _STAMP.match(text) else None


def _iso_date(day) -> str | None:
    """A real 'YYYY-MM-DD' date, or None: dates from a reply reach the model (get_forecast)."""
    text = _text(day)[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text if re.fullmatch(r"\d{4}-\d\d-\d\d", text) else None


def find_places(query: str) -> list[dict]:
    """Up to WEATHER_MATCHES places for the words, largest first, each with a short id the
    page sends back to confirm (so neither the page nor the model can invent a place)."""
    q = str(query).strip()
    if not 1 <= len(q) <= config.WEATHER_QUERY_MAX:
        raise ValueError("a place to search for must be 1 to 80 characters")
    results = _cached(("geo", q.lower()), lambda: _get(config.WEATHER_GEOCODE_URL, {
        "name": q, "count": config.WEATHER_MATCHES, "language": "en", "format": "json",
    }).get("results"))
    found = [r for r in (results if isinstance(results, list) else []) if isinstance(r, dict)]
    places = []
    for r in sorted(found, key=lambda r: -(_num(r.get("population")) or -1)):
        lat, lon = _num(r.get("latitude")), _num(r.get("longitude"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue                  # a result without real coordinates cannot be shown
        places.append({"name": clean(_text(r.get("name"))), "region": clean(_text(r.get("admin1"))),
                       "country": clean(_text(r.get("country"))),
                       "lat": _round(lat), "lon": _round(lon)})
    global _waiting
    matches = []
    with _lock:
        for place in places[:config.WEATHER_MATCHES]:
            pid = secrets.token_urlsafe(6)
            _keep(_ids, pid, place)
            matches.append({"id": pid, **place})
        # Until one of these is confirmed, "there" is not the old place any more (final review)
        if matches:
            _waiting = (monotonic() + config.WEATHER_CACHE_SECONDS, places[0])
    return matches


def _summary(place: dict, f: dict, a: dict | None) -> dict:
    """Open-Meteo's replies turned into what the page draws. 'Now' is the forecast's own
    time, already in the place's time zone, never this Mac's clock. Every number is read
    through _num, every text through _text or clean."""
    current, hourly, daily = _obj(f.get("current")), _obj(f.get("hourly")), _obj(f.get("daily"))
    now_time = _text(current.get("time"))
    temp, feels = _num(current.get("temperature_2m")), _num(current.get("apparent_temperature"))
    words, icon = condition(_num(current.get("weather_code")), _num(current.get("is_day")) == 1)
    now = {"time": _clock(now_time), "temp_c": round_half_up(temp), "temp_f": to_f(temp),
           "feels_c": round_half_up(feels), "feels_f": to_f(feels),
           "condition": words, "icon": icon, "is_day": _num(current.get("is_day")) == 1}

    times = [_text(t) for t in hourly.get("time")] if isinstance(hourly.get("time"), list) else []
    this_hour = now_time[:13] + ":00"
    first = next((i for i, t in enumerate(times) if t and t >= this_hour), None)
    hours = []
    for i in range(first, min(first + 24, len(times))) if first is not None else ():
        if _clock(times[i]) is None:
            continue
        is_day = _num(_at(hourly.get("is_day"), i)) == 1
        h_temp = _num(_at(hourly.get("temperature_2m"), i))
        hours.append({"time": _clock(times[i]), "temp_c": round_half_up(h_temp),
                      "temp_f": to_f(h_temp),
                      "rain_chance": _num(_at(hourly.get("precipitation_probability"), i)),
                      "icon": condition(_num(_at(hourly.get("weather_code"), i)), is_day)[1],
                      "is_day": is_day})

    days = []
    day_list = daily.get("time") if isinstance(daily.get("time"), list) else []
    for i, day in enumerate(day_list[:7]):
        high = _num(_at(daily.get("temperature_2m_max"), i))
        low = _num(_at(daily.get("temperature_2m_min"), i))
        d_words, d_icon = condition(_num(_at(daily.get("weather_code"), i)), True)
        days.append({"date": _iso_date(day), "weekday": _weekday(_text(day)[:10]),
                     "condition": d_words, "icon": d_icon,
                     "high_c": round_half_up(high), "high_f": to_f(high),
                     "low_c": round_half_up(low), "low_f": to_f(low),
                     "rain_chance": _num(_at(daily.get("precipitation_probability_max"), i))})

    uv = _num(_at(hourly.get("uv_index"), first))
    seen = _num(_at(hourly.get("visibility"), first))
    wind, pressure = _num(current.get("wind_speed_10m")), _num(current.get("pressure_msl"))
    details = {"wind_kmh": round_half_up(wind), "wind_mph": kmh_to_mph(wind),
               "wind_dir": _num(current.get("wind_direction_10m")),
               "humidity": _num(current.get("relative_humidity_2m")),
               "uv": uv, "uv_label": uv_label(uv),
               "sunrise": _clock(_at(daily.get("sunrise"), 0)),
               "sunset": _clock(_at(daily.get("sunset"), 0)),
               "pressure_hpa": round_half_up(pressure), "pressure_inhg": hpa_to_inhg(pressure),
               "visibility_km": m_to_km(seen), "visibility_mi": m_to_mi(seen)}

    air = None
    if a is not None:
        now_air = _obj(a.get("current"))
        pollen = {kind: _num(now_air.get(f"{kind}_pollen")) for kind in POLLEN
                  if _num(now_air.get(f"{kind}_pollen")) is not None}
        aqi = round_half_up(_num(now_air.get("us_aqi")))
        air = {"aqi": aqi, "aqi_label": aqi_label(aqi), "pm2_5": _num(now_air.get("pm2_5")),
               "ozone": _num(now_air.get("ozone")), "pollen": pollen or None}

    full_place = {**place, "timezone": clean(_text(f.get("timezone"))),
                  "utc_offset_seconds": _num(f.get("utc_offset_seconds"))}
    return {"place": full_place, "now": now, "hours": hours,
            "rain": rain_windows([(int(h["time"][:2]), h["rain_chance"]) for h in hours]),
            "days": days, "details": details, "air": air}


def _replies(place: dict) -> tuple[dict, dict | None]:
    """The forecast and air quality replies for a place (from the cache when recent). A
    forecast that cannot be fetched raises WeatherError; air quality that cannot is None."""
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
    return f, a


def forecast_for(place: dict) -> dict:
    """What the page draws for a place. A reply this code cannot read becomes WeatherError."""
    f, a = _replies(place)
    key = (_round(place["lat"]), _round(place["lon"]))
    try:
        return _summary(place, f, a)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError) as e:
        # Belt and braces: a reply this code still cannot read is not kept for 10 minutes,
        # and the user gets the same plain message as for any other failure
        with _lock:
            _cache.pop(("forecast", *key), None)
            _cache.pop(("air", *key), None)
        log.warning("weather reply could not be read: %s", type(e).__name__)
        raise WeatherError(UNREACHABLE) from e


def _show(place: dict) -> dict:
    """Fetch first, and only then make it the place on screen, so a failure changes nothing."""
    global _place, _waiting
    payload = forecast_for(place)
    payload["spoken"] = spoken_line(place["name"], payload["now"],
                                    payload["days"][0] if payload["days"] else {})
    with _lock:
        _place = payload["place"]
        _waiting = None
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


# ---------- JARVIS's tools (registered last: brain.py imports this module last) ----------
NO_PLACE = "Error: no place is confirmed yet. Ask which place, or call find_place."
FULL_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _place_words(place: dict) -> str:
    """'Paris, France'; 'Rome, Lazio' with no country; 'Home' for a home place."""
    second = place.get("country") or place.get("region")
    return f"{place['name']}, {second}" if second else place["name"]


def _match_words(match: dict) -> str:
    """'Paris, Texas, United States': enough for the model to tell the matches apart."""
    return ", ".join(p for p in (match["name"], match["region"], match["country"]) if p)


def _both(f, c, unit_f: str = "°F", unit_c: str = "°C") -> str | None:
    return None if f is None or c is None else f"{f}{unit_f} ({c}{unit_c})"


def _day_words(d: dict) -> list[str]:
    """'overcast, high 71°F (22°C), low 50°F (10°C), 60% chance of rain', missing parts left out."""
    high, low = _both(d["high_f"], d["high_c"]), _both(d["low_f"], d["low_c"])
    parts = [d["condition"], high and f"high {high}", low and f"low {low}",
             d["rain_chance"] is not None and f"{d['rain_chance']}% chance of rain"]
    return [p for p in parts if p]


def _full_weekday(day: str) -> str:
    try:
        return FULL_WEEKDAYS[date.fromisoformat(day).weekday()] + " "
    except ValueError:
        return ""


def forecast_facts(day: str = "") -> str:
    """The facts get_forecast gives the model, all worked out here (both units)."""
    with _lock:
        waiting = _waiting[1] if _waiting and _waiting[0] > monotonic() else None
    if waiting:
        return (f"Error: the user has not confirmed {_place_words(waiting)} on the globe yet. "
                "Ask them to confirm it first.")
    place = place_on_screen()
    if place is None:
        return NO_PLACE
    try:
        payload = forecast_for(place)
        f, _ = _replies(place)
    except WeatherError:
        return "Error: couldn't reach the weather service."
    name = _place_words(place)
    days = payload["days"]
    dates = [d["date"] for d in days if d["date"]]
    if day:
        wanted = next((d for d in days if d["date"] == str(day).strip()), None)
        if wanted is None:
            if not dates:
                return "Error: the forecast has no days. Ask again in a moment."
            return (f"Error: the forecast covers {dates[0]} to {dates[-1]}. "
                    "Give a date in that range as YYYY-MM-DD.")
        hourly = _obj(f.get("hourly"))
        times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
        hours = [(int(_clock(t)[:2]), _num(_at(hourly.get("precipitation_probability"), i)))
                 for i, t in enumerate(times)
                 if _clock(t) and _text(t).startswith(wanted["date"])]
        text = f"{name}, {_full_weekday(wanted['date'])}{wanted['date']}: " + \
            ", ".join(_day_words(wanted)) + "."
        rain = rain_windows(hours)
        return text + (f" Rain likely {rain}." if rain else "")

    now, details = payload["now"], payload["details"]
    feels = _both(now["feels_f"], now["feels_c"])
    wind = _both(details["wind_mph"], details["wind_kmh"], " mph", " km/h")
    first = [_both(now["temp_f"], now["temp_c"]), now["condition"], feels and f"feels like {feels}"]
    groups = [", ".join(p for p in first if p), wind and f"wind {wind}",
              details["humidity"] is not None and f"humidity {details['humidity']}%"]
    when = f" ({now['time']} there)" if now["time"] else ""
    text = f"{name}. Now{when}: " + "; ".join(g for g in groups if g) + "."
    if days:
        text += " Today: " + ", ".join(_day_words(days[0])) + "."
    if payload["rain"]:
        text += f" Rain likely {payload['rain']}."
    air = payload["air"]
    if air and air["aqi"] is not None:
        text += f" Air quality: US AQI {air['aqi']}" + (f", {air['aqi_label']}" if air["aqi_label"] else "") + "."
    return text


@tool("Find a place to show its weather, temperature, rain or air quality. Call it when the "
      "user asks about the weather somewhere, with the place as they said it, adding the "
      "country or state if they gave one, such as 'Paris, Texas'. The globe then asks the user "
      "to confirm the place on screen: give no weather until they do.",
      query={"type": "string",
             "description": "the place as the user said it, such as 'Paris' or 'Paris, Texas'"})
def find_place(query: str) -> ShowPlaces | str:
    try:
        matches = find_places(str(query))
    except ValueError:
        return f"Error: say the place in 1 to {config.WEATHER_QUERY_MAX} characters."
    except WeatherError:
        return "Error: couldn't reach the weather service."
    if not matches:
        return f"I couldn't find a place called {clean(str(query))}."
    # The second sentence is read when it matters: after Esc or a reload the ping is gone, and
    # without it the model kept saying "please confirm" with nothing on screen (stage 4 demo)
    reply = (f"Asked the user to confirm {_place_words(matches[0])} on the globe. "
             "Give no weather until they confirm. If they ask again before confirming, "
             "call find_place again: the ping may have been closed.")
    others = [_match_words(m) for m in matches[1:3]]
    if others:
        reply += " Other matches: " + "; ".join(others) + "."
    return ShowPlaces(matches, reply)


@tool("The weather for the place the user confirmed on the globe: now and today when day is "
      "empty, or one day of the next 7 as YYYY-MM-DD. Call it for questions about the place on "
      "screen, such as 'will it rain there tomorrow?'. Use only the figures it returns.",
      day={"type": "string", "description": "YYYY-MM-DD, or empty for now and today"})
def get_forecast(day: str = "") -> str:
    return forecast_facts(str(day or ""))
