"""Made-up Open-Meteo replies for the weather tests, shaped like the real ones (field names
from Open-Meteo's docs, read 2026-11-05), and `serve`, which answers weather._fetch with them."""
import json
from datetime import date, datetime, timedelta

import weather

PARIS_FR = {"id": 2988507, "name": "Paris", "latitude": 48.85341, "longitude": 2.3488,
            "country_code": "FR", "country": "France", "admin1": "Île-de-France",
            "timezone": "Europe/Paris", "population": 2138551}
PARIS_TX = {"id": 4717560, "name": "Paris", "latitude": 33.66094, "longitude": -95.55551,
            "country_code": "US", "country": "United States", "admin1": "Texas",
            "timezone": "America/Chicago", "population": 24171}
NO_POPULATION = {"id": 1, "name": "Paris", "latitude": 10.0, "longitude": 10.0,
                 "country": "Nowhereland", "admin1": "Nowhere", "timezone": "UTC"}


def geocode(*results) -> dict:
    """No results means no `results` key at all, as Open-Meteo leaves out empty fields."""
    return {"results": list(results), "generationtime_ms": 0.5} if results else \
        {"generationtime_ms": 0.5}


def forecast(current_time: str = "2026-11-05T21:45", nulls: bool = False) -> dict:
    """Seven days from current_time's date. Day 2 has rain from 14:00 to 16:00 (60 %)."""
    first = date.fromisoformat(current_time[:10])
    days = [(first + timedelta(days=i)).isoformat() for i in range(7)]
    times = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    hours = [int(t[11:13]) for t in times]
    rain = [60 if t.startswith(days[1]) and 14 <= h <= 16 else 10
            for t, h in zip(times, hours, strict=True)]
    if nulls:
        rain[times.index(days[0] + "T21:00")] = None
    data = {
        "latitude": 48.86, "longitude": 2.36, "utc_offset_seconds": 3600,
        "timezone": "Europe/Paris", "timezone_abbreviation": "GMT+1",
        "current": {"time": current_time, "interval": 900, "temperature_2m": 18.3,
                    "apparent_temperature": 16.0, "relative_humidity_2m": 70,
                    "weather_code": 0, "is_day": 0, "wind_speed_10m": 20.0,
                    "wind_direction_10m": 225, "pressure_msl": 1015.2},
        "hourly": {"time": times,
                   "temperature_2m": [10 + h / 2 for h in hours],
                   "precipitation_probability": rain,
                   "weather_code": [3] * len(times),
                   "is_day": [1 if 7 <= h <= 17 else 0 for h in hours],
                   "visibility": [24140.0] * len(times),
                   "uv_index": [2.0] * len(times)},
        "daily": {"time": days, "weather_code": [3] * 7, "temperature_2m_max": [21.5] * 7,
                  "temperature_2m_min": [10.0] * 7,
                  "precipitation_probability_max": [10, 60, 10, 10, 10, 10, 10],
                  "sunrise": [f"{d}T07:45" for d in days],
                  "sunset": [f"{d}T17:20" for d in days],
                  "uv_index_max": [2.0] * 7},
    }
    if nulls:
        data["daily"]["precipitation_probability_max"][0] = None
    return data


POLLEN = ("alder", "birch", "grass", "mugwort", "olive", "ragweed")


def air(us_aqi: int = 42, pollen: bool = False) -> dict:
    current = {"time": "2026-11-05T21:00", "interval": 3600, "us_aqi": us_aqi,
               "pm2_5": 8.5, "ozone": 61.0}
    for kind in POLLEN:
        current[f"{kind}_pollen"] = 12.0 if pollen and kind == "grass" else None
    return {"latitude": 48.86, "longitude": 2.36, "utc_offset_seconds": 3600,
            "timezone": "Europe/Paris", "current": current}


class Served:
    def __init__(self):
        self.addresses: list[str] = []

    def count(self, host_word: str) -> int:
        return sum(host_word in a for a in self.addresses)


def serve(monkeypatch, geo=None, forecast=None, air=None) -> Served:
    """Answer weather._fetch by host: a dict becomes its JSON bytes, an exception is raised,
    and a request nobody prepared for fails the test."""
    served = Served()
    answers = (("geocoding-api.", geo), ("air-quality-api.", air), ("api.open-meteo.com/", forecast))

    def fetch(address):
        served.addresses.append(address)
        for host, answer in answers:
            if host in address:
                if answer is None:
                    raise AssertionError(f"no made-up reply for {address}")
                if isinstance(answer, BaseException):
                    raise answer
                return json.dumps(answer).encode()
        raise AssertionError(f"unexpected address {address}")

    monkeypatch.setattr(weather, "_fetch", fetch)
    return served


def canned_fetch(address: str, now: datetime) -> bytes:
    """Offline replies for the evals (evals/__main__.py): Paris and Paris, Texas, with a
    forecast that starts at `now`. Any other search finds nothing."""
    if "geocoding-api." in address:
        if "Texas" in address:
            reply = geocode(PARIS_TX)
        elif "Paris" in address:
            reply = geocode(PARIS_FR, PARIS_TX)
        else:
            reply = geocode()
    elif "air-quality-api." in address:
        reply = air()
    else:
        reply = forecast(current_time=now.strftime("%Y-%m-%dT%H:%M"))
    return json.dumps(reply).encode()
