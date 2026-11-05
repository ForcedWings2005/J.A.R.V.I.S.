# Weather, stage 2: the server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** JARVIS can look up places and fetch their forecast and air quality from Open-Meteo,
through three fixed HTTPS addresses, and serve them to the page through three POST endpoints.
Nothing on screen yet, and no tools yet.

**Architecture:** One new module, `weather.py`, owns everything about weather. There is one
door to the internet: `_fetch(address) -> bytes`. `_get(base, params) -> dict` builds every
address from a fixed base, and calls that door. Above it sit pure functions that work out every
figure (units, labels, rain windows), then the summaries, an in-memory cache, the match ids and
the place on screen. `server.py` adds `POST /weather/places`, `/weather/confirm` and
`/weather/home`. The last two add the spoken line to the conversation through a new
`Assistant.add_reply`. `brain.py` imports `weather` last, so `reset()` can forget the place.
`weather` registers no tools, so the prompt does not change.

**Tech Stack:** Python 3.13 standard library (`urllib.request`, `urllib.parse`, `json`,
`secrets`, `threading`, `time.monotonic`, `unicodedata`, `math`), FastAPI/Pydantic for the
endpoints, pytest. No new dependency.

**Spec:** `docs/specs/2026-11-05-weather-space.md`: "The privacy rule", "How it works" (Files,
Settings, Going online, Worked out in code, The cache..., Endpoints, When something goes
wrong), "Security and privacy", "Testing", "Build order" stage 2. Stage 1 (the CSP) is merged:
CHANGELOG section 55.

## Global Constraints

- The three addresses, exactly: `https://geocoding-api.open-meteo.com/v1/search`,
  `https://api.open-meteo.com/v1/forecast`, `https://air-quality-api.open-meteo.com/v1/air-quality`.
- The settings (spec, verbatim values): `WEATHER_TIMEOUT_SECONDS = 5`,
  `WEATHER_MAX_BYTES = 1_000_000`, `WEATHER_CACHE_SECONDS = 600`, `WEATHER_CACHE_ENTRIES = 50`,
  `WEATHER_MATCHES = 5`, `WEATHER_QUERY_MAX = 80`, `WEATHER_NAME_MAX = 60`,
  `WEATHER_COORD_DECIMALS = 2`. One more, decided in this plan: `WEATHER_RAIN_CHANCE = 40` (the
  spec's "40 % or more").
- Redirects are refused. HTTPS only. Every request is logged with its host, time and status,
  **never its address** (the address holds the place).
- Coordinates are rounded to 2 decimal places before any request, and are the cache key.
- Outside names (`name`, `admin1`, `country`) are cleaned: control characters removed, cut to
  60 characters.
- °F is `round_half_up(c * 9 / 5 + 32)`, rounded once at the end. Fetch in °C and km/h.
- All state lives in memory (never `jarvis.db`): no schema change.
- The model chooses nothing in this stage. `weather` registers no `@tool`, so `tools.SCHEMAS`
  and the prompt are unchanged and no eval is needed.
- Tests never go online. An autouse fixture in `tests/conftest.py` makes `weather._fetch` fail
  loudly.
- `JARVIS_DB` is set before any import in a demo or script; the live check never touches the
  real `jarvis.db`, `backups/` or `logs/`. The live check uses made-up places (Paris, and Rome
  as a pretend home), never the owner's real home.
- Commit on `weather-stage-2` after each task. Never on `main`; do not push.

## Decisions this plan makes (the spec is silent)

- **Wind, visibility and pressure in both systems**, like temperature: `wind_mph` and
  `wind_kmh`, `visibility_mi` and `visibility_km` (whole numbers), `pressure_hpa` and
  `pressure_inhg` (2 decimals). The page shows US units first, as for °F.
- **UV and visibility come from the hourly data at the current hour.** Open-Meteo's docs do not
  list them as `current` variables (checked 2026-11-05).
- **"Now" for a place is the forecast's own `current.time`**, already in the place's local time
  (`timezone=auto`), never the Mac's clock. So the tests need no clock, and a place in another
  time zone is right.
- **A missing value stays `None`** all the way to the page (Open-Meteo's arrays can hold
  `null`). Conversions of `None` give `None`, and the spoken line leaves out a missing part.
- **Half rounds up** (`math.floor(x + 0.5)`), not Python's `round()`, which rounds 0.5 to the
  nearest even number. So 0.5 °F is 1, not 0.
- **`README.md`'s first paragraph is corrected in this stage.** It says nothing leaves the Mac
  except the backups, which stops being true here. The spec left README for stage 4, but a false
  privacy claim should not wait.

## Review Focus

1. **Missing values in Open-Meteo's replies** (`null` in an hourly or daily array, pollen
   `null` outside Europe or out of season, no `results` key for no match). Expected: the payload
   holds `None` and nothing crashes. Pinned by `test_missing_values_stay_none` and
   `test_no_match_is_an_empty_list` (Task 3), and `test_spoken_line_leaves_out_missing_parts`
   (Task 2).
2. **Late evening:** `current.time` is `"…T21:45"`, so the next 24 hours run from 21:00 across
   midnight into tomorrow. Pinned by `test_next_24_hours_start_at_the_current_hour_and_cross_midnight`
   (Task 3).
3. **An id used after it expires, or never issued** (the ping left open 10 minutes). Expected: a
   404 saying to search again, and the place on screen unchanged. Pinned by
   `test_an_expired_id_is_refused` (Task 3) and `test_confirm_refuses_an_unknown_id` (Task 4).
4. **Odd numbers sent to `/weather/home`**: `NaN`, `Infinity`, 91, a string. Expected: 422.
   Pinned by `test_home_refuses_bad_coordinates` (Task 4).
5. **Accented names and commas** ("São Paulo", "Paris, Texas") must reach the service intact
   and stay in the query string. Pinned by `test_queries_are_encoded_inside_the_query_string`
   (Task 1).

---

### Task 1: The settings, and the one door to the internet

**Files:**
- Modify: `config.py`: a "Weather" block after the Work block, with the eleven settings above
  and a comment naming the spec.
- Create: `weather.py`: module docstring (why: the first outside data, and the privacy rule),
  `WeatherError`, `_RefuseRedirects`, `_OPENER`, `_fetch`, `_get`.
- Modify: `tests/conftest.py`: an autouse fixture `no_internet(monkeypatch)` that replaces
  `weather._fetch` with a function raising `AssertionError("a test tried to reach the internet: ...")`.
- Create: `tests/test_weather.py`.

**Interfaces:**
- Produces:
  - `class WeatherError(Exception)`: its message is what a user may see.
  - `_fetch(address: str) -> bytes`: the only function that touches the network.
    `_OPENER.open(address, timeout=config.WEATHER_TIMEOUT_SECONDS)`, reading at most
    `WEATHER_MAX_BYTES + 1` bytes.
  - `_get(base: str, params: dict) -> dict`: refuses (`ValueError`, a programming error) any
    `base` that is not one of the three settings. Builds `base + "?" + urllib.parse.urlencode(params)`
    and calls `_fetch`. More than `WEATHER_MAX_BYTES` bytes, invalid JSON, a JSON value that is
    not an object, a timeout, `URLError` or `HTTPError` all become
    `WeatherError("Couldn't reach the weather service.")`. Logs one line per request via
    `logging.getLogger("jarvis.weather")`: the host, the milliseconds, and `ok` or the error's
    class name.
  - `_OPENER = urllib.request.build_opener(_RefuseRedirects)`. `_RefuseRedirects` subclasses
    `urllib.request.HTTPRedirectHandler`, and its `redirect_request` returns `None`, so urllib
    raises `HTTPError` for the 3xx instead of following it.

- [ ] **Step 1: Write the failing tests** in `tests/test_weather.py`. A helper `fake_fetch(monkeypatch, reply: bytes | Exception)`
  replaces `weather._fetch`, records each address in a list it returns, and returns `reply`
  (or raises it).

```python
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
                                   b"not json", b"[1, 2]", b"x" * (1_000_001)])
def test_anything_wrong_becomes_one_clear_error(monkeypatch, reply):
    fake_fetch(monkeypatch, reply)
    with pytest.raises(weather.WeatherError, match="Couldn't reach the weather service."):
        weather._get(config.WEATHER_FORECAST_URL, {"latitude": 1})

def test_redirects_are_refused():
    """A real local server answers 302; the opener must not follow it."""
    # http.server.HTTPServer on 127.0.0.1, port 0, in a thread; its handler sends 302 with
    # Location: /elsewhere and counts requests to /elsewhere.
    with pytest.raises(urllib.error.HTTPError) as caught:
        weather._OPENER.open(f"http://127.0.0.1:{port}/start", timeout=2)
    assert caught.value.code == 302 and elsewhere_hits == 0

def test_each_request_is_logged_without_its_address(monkeypatch, caplog):
    fake_fetch(monkeypatch, b"{}")
    with caplog.at_level(logging.INFO, logger="jarvis.weather"):
        weather._get(config.WEATHER_GEOCODE_URL, {"name": "Paris"})
    assert "geocoding-api.open-meteo.com" in caplog.text and "Paris" not in caplog.text

def test_tests_cannot_reach_the_internet():
    with pytest.raises(AssertionError, match="internet"):
        weather._fetch(config.WEATHER_GEOCODE_URL)
```

The redirect test talks only to `127.0.0.1` through the real `_OPENER`, never through
`_fetch`, so the guard fixture does not block it. Shut the server down in a `finally`.

- [ ] **Step 2: Run them to make sure they fail.** Run: `python -m pytest -q tests/test_weather.py`.
  Expected: errors collecting, because `weather` does not exist (`ModuleNotFoundError`), and
  `conftest.py` fails the same way once its fixture names `weather`.
- [ ] **Step 3: Write the settings and the functions** listed under Interfaces.
- [ ] **Step 4: Run the tests to make sure they pass, then everything.** Run
  `python -m pytest -q tests/test_weather.py`, then `ruff check .` and `python -m pytest -q`.
  Expected: all pass, and ruff is clean.
- [ ] **Step 5: Commit** `config.py weather.py tests/conftest.py tests/test_weather.py`:
  "Weather: one fixed door to Open-Meteo (settings, fetch rules, tests)".

---

### Task 2: The figures, worked out in code

**Files:**
- Modify: `weather.py`: pure functions, no state, no network.
- Test: `tests/test_weather.py`.

**Interfaces:**
- Produces (all take and give `None` for a missing value unless noted):
  - `round_half_up(x: float | None) -> int | None`
  - `to_f(c) -> int | None`, `kmh_to_mph(kmh) -> int | None`, `m_to_km(m) -> int | None`,
    `m_to_mi(m) -> int | None`, `hpa_to_inhg(hpa) -> float | None` (2 decimals, factor
    0.02953).
  - `clean(text: str | None, limit: int = config.WEATHER_NAME_MAX) -> str`: whitespace characters
    (`str.isspace`, so `\n` too) become spaces first, then any other character whose Unicode
    category starts with `C` is removed. Runs of spaces are squeezed to one, and the result is
    stripped and cut to `limit`. `None` gives `""`.
  - `condition(code: int | None, is_day: bool) -> tuple[str, str]`: words and icon name. The
    icons are `sun`, `moon`, `part-cloud`, `cloud`, `fog`, `rain`, `snow`, `thunder`. 0 is
    "clear" (`sun` or `moon`); 1 is "mainly clear" (`sun`/`moon`); 2 "partly cloudy"; 3
    "overcast"; 45, 48 "fog"; 51, 53, 55 "drizzle"; 56, 57 "freezing drizzle"; 61 "light rain";
    63 "rain"; 65 "heavy rain"; 66, 67 "freezing rain"; 71 "light snow"; 73 "snow"; 75 "heavy
    snow"; 77 "snow grains"; 80, 81, 82 "rain showers"; 85, 86 "snow showers"; 95
    "thunderstorm"; 96, 99 "thunderstorm with hail". Unknown or `None` is `("unknown", "cloud")`.
  - `aqi_label(aqi) -> str | None` and `uv_label(uv) -> str | None`, using the spec's bands. UV
    is rounded half up first.
  - `hour_words(hour: int) -> str`: `0` "midnight", `12` "noon", otherwise "2 pm", "9 am".
  - `rain_windows(hours: list[tuple[int, int | None]]) -> str`: `(hour, chance)` in order.
    Consecutive hours at or above `config.WEATHER_RAIN_CHANCE` become "from 2 pm to 6 pm" (the
    end is the hour after the last rainy one). Several windows are joined with " and ". None
    gives `""`.
  - `say_degrees(n: int) -> str`: `"-3"` becomes `"minus 3"`, so speech says it right.
  - `spoken_line(name: str, now: dict, today: dict) -> str` (`now` and `today` as in Task 3's
    payload): `"Paris: 64 degrees, 18 Celsius, and clear. High of 70, 10 percent chance of rain."`.
    It leaves out the high or the rain clause when that value is `None`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("c, f", [(-40, -40), (0, 32), (100, 212), (18.3, 65), (-17.5, 1), (None, None)])
def test_celsius_to_fahrenheit_rounds_once_half_up(c, f):
    assert weather.to_f(c) == f

def test_other_units():
    assert weather.kmh_to_mph(20) == 12 and weather.m_to_km(24140) == 24
    assert weather.m_to_mi(24140) == 15 and weather.hpa_to_inhg(1015.2) == 29.98

def test_outside_names_are_cleaned():
    assert weather.clean("Pa\x00ris\n  ‮France") == "Paris France"
    assert len(weather.clean("x" * 500)) == 60 and weather.clean(None) == ""

def test_every_known_weather_code_has_words():
    for code in (0, 1, 2, 3, 45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
                 80, 81, 82, 85, 86, 95, 96, 99):
        assert weather.condition(code, True)[0] != "unknown"
    assert weather.condition(0, False) == ("clear", "moon")
    assert weather.condition(12345, True) == ("unknown", "cloud")

@pytest.mark.parametrize("aqi, label", [(0, "Good"), (50, "Good"), (51, "Moderate"), (100, "Moderate"),
    (101, "Unhealthy for sensitive groups"), (151, "Unhealthy"), (201, "Very unhealthy"),
    (301, "Hazardous"), (None, None)])
def test_aqi_bands(aqi, label): ...

@pytest.mark.parametrize("uv, label", [(2.4, "Low"), (2.5, "Moderate"), (5, "Moderate"), (6, "High"),
    (8, "Very high"), (11, "Extreme"), (None, None)])
def test_uv_bands(uv, label): ...

def test_rain_windows():
    hours = [(13, 10), (14, 60), (15, 40), (16, 70), (17, 20), (22, 50), (23, 80), (0, 90), (1, None)]
    assert weather.rain_windows(hours) == "from 2 pm to 5 pm and from 10 pm to 1 am"
    assert weather.rain_windows([(11, 50)]) == "from 11 am to noon"
    assert weather.rain_windows([(9, 39)]) == ""

def test_spoken_line():
    now = {"temp_f": 64, "temp_c": 18, "condition": "clear"}
    today = {"high_f": 70, "rain_chance": 10}
    assert weather.spoken_line("Paris", now, today) == \
        "Paris: 64 degrees, 18 Celsius, and clear. High of 70, 10 percent chance of rain."
    cold = {"temp_f": -3, "temp_c": -19, "condition": "light snow"}
    assert weather.spoken_line("Oslo", cold, today).startswith("Oslo: minus 3 degrees, minus 19 Celsius")

def test_spoken_line_leaves_out_missing_parts():
    now = {"temp_f": 64, "temp_c": 18, "condition": "clear"}
    assert weather.spoken_line("Paris", now, {"high_f": 70, "rain_chance": None}) == \
        "Paris: 64 degrees, 18 Celsius, and clear. High of 70."
```

Fill in the two `...` bodies as `assert weather.aqi_label(aqi) == label` and the same for UV.

- [ ] **Step 2: Run them to make sure they fail** with `AttributeError` for each missing function.
  Run: `python -m pytest -q tests/test_weather.py`.
- [ ] **Step 3: Write the functions** listed under Interfaces.
- [ ] **Step 4: Run the tests to make sure they pass, then everything.** Run
  `python -m pytest -q tests/test_weather.py`, `ruff check .` and `python -m pytest -q`.
  Expected: all pass.
- [ ] **Step 5: Commit** `weather.py tests/test_weather.py`: "Weather: units, labels, rain windows
  and the spoken line, worked out in code".

---

### Task 3: Places, summaries, the cache and the place on screen

**Files:**
- Modify: `weather.py`.
- Create: `tests/weather_data.py`: made-up replies shaped like Open-Meteo's (fields as in its
  docs, read 2026-11-05).
  - `geocode(*results)` gives `{"results": [...]}`, or `{}` when there are none.
  - `PARIS_FR`: population 2,138,551, admin1 "Île-de-France", 48.85341, 2.3488.
  - `PARIS_TX`: population 24,171, admin1 "Texas", 33.66094, -95.55551.
  - `NO_POPULATION`: admin1 "Nowhere", no `population` key.
  - `serve(monkeypatch, geo=None, forecast=None, air=None) -> Served`: replaces `weather._fetch`
    with one that answers by host (bytes made with `json.dumps`, or raises an exception it is
    given). It returns `Served`, with `addresses: list[str]` and `count(host_word: str) -> int`.
    It lives here so that Task 4's tests use it too.
  - `forecast(current_time="2026-11-05T21:45", nulls=False)`:
    - `timezone` "Europe/Paris", `utc_offset_seconds` 3600;
    - `current`: temperature_2m 18.3, apparent_temperature 16.0, relative_humidity_2m 70,
      weather_code 0, is_day 0, wind_speed_10m 20.0, wind_direction_10m 225, pressure_msl 1015.2;
    - `hourly` from `2026-11-05T00:00`, 168 hours: temperature_2m = 10 + hour of day / 2;
      precipitation_probability 60 for 14:00–16:00 on 2026-11-06, otherwise 10; weather_code 3;
      is_day 1 from 07:00 to 17:00; visibility 24140; uv_index 2.0;
    - `daily`, 7 days from 2026-11-05: weather_code 3, max 21.5, min 10.0,
      precipitation_probability_max 10, sunrise "…T07:45", sunset "…T17:20", uv_index_max 2.0;
    - `nulls=True` puts `None` in the hourly precipitation_probability at 2026-11-05T21:00 and
      in daily precipitation_probability_max[0].
  - `air(us_aqi=42, pollen=False)`: `current` with us_aqi, pm2_5 8.5, ozone 61.0, and the six
    pollen variables, all `None` unless `pollen=True` (then grass_pollen 12.0, the rest `None`).
- Test: `tests/test_weather.py`.
- Modify: `tests/conftest.py`: the same autouse fixture also calls `weather.forget_everything()`.

**Interfaces:**
- Consumes: `_get`, `WeatherError` (Task 1); every Task 2 function.
- Produces:
  - A **place**: `{"name": str, "region": str, "country": str, "lat": float, "lon": float}`,
    with names cleaned and coordinates rounded to `WEATHER_COORD_DECIMALS`.
  - A **match**: a place plus `"id": str`.
  - `find_places(query: str) -> list[dict]`: the matches.
    - The query is stripped, and must be 1 to `WEATHER_QUERY_MAX` characters (else `ValueError`).
    - The geocoding request is `{"name": q, "count": WEATHER_MATCHES, "language": "en", "format": "json"}`.
    - Matches are sorted by population, largest first; a missing population goes last.
    - Each match gets an id from `secrets.token_urlsafe(6)`, valid `WEATHER_CACHE_SECONDS`.
  - `forecast_for(place: dict) -> dict`: the **payload**, without the spoken line. Its shape:
    - `place`: the place plus `timezone` and `utc_offset_seconds`;
    - `now`: `time` ("HH:MM", the place's own), `temp_c`, `temp_f`, `feels_c`, `feels_f`,
      `condition`, `icon`, `is_day`;
    - `hours`: 24 items of `time`, `temp_c`, `temp_f`, `rain_chance`, `icon`, `is_day`, from
      the current hour;
    - `rain`: `rain_windows` over those 24 hours;
    - `days`: 7 items of `date`, `weekday` (e.g. "Thu"), `condition`, `icon`, `high_c`,
      `high_f`, `low_c`, `low_f`, `rain_chance`;
    - `details`: `wind_kmh`, `wind_mph`, `wind_dir`, `humidity`, `uv`, `uv_label`, `sunrise`,
      `sunset` ("HH:MM"), `pressure_hpa`, `pressure_inhg`, `visibility_km`, `visibility_mi`;
    - `air`: `aqi`, `aqi_label`, `pm2_5`, `ozone`, `pollen` (a dict of only the pollen types
      that have a value, or `None`), or `air: None` when air quality could not be fetched.
    - The forecast request: `latitude`, `longitude`, `current`, `hourly`, `daily` (comma-joined
      variable lists, as named in `tests/weather_data.py`), `timezone="auto"`, `forecast_days=7`.
      The air request: `latitude`, `longitude`, `current`, `timezone="auto"`.
    - A forecast failure raises `WeatherError`. An air failure only sets `air` to `None`.
  - `confirm(place_id: str) -> dict`: the payload plus `"spoken"`. Raises `LookupError` for an
    unknown or expired id. Sets the place on screen only after the fetch succeeded.
  - `open_home(name: str, lat: float, lon: float) -> dict`: the same for a place the page sends:
    `clean(name)`, empty region and country, rounded coordinates.
  - `place_on_screen() -> dict | None`, `clear_place() -> None`, `forget_everything() -> None`
    (for tests: the cache, the ids and the place).
  - The cache:
    - an `OrderedDict` of `key -> (expires_at, value)` with keys `("geo", query.lower())`,
      `("forecast", lat, lon)` and `("air", lat, lon)`;
    - at most `WEATHER_CACHE_ENTRIES`, the oldest dropped first; errors are never cached;
    - the ids live in their own dict, pruned of expired ones whenever one is issued, and capped
      the same way;
    - one `threading.Lock` guards the cache, the ids and the place, and is **never held during
      a request**;
    - time comes from `monotonic`, imported into `weather` so tests can patch `weather.monotonic`.

- [ ] **Step 1: Write the failing tests.** `data` is `tests/weather_data.py`, and `serve` is `data.serve`.

```python
def test_matches_are_sorted_by_population_and_cleaned(monkeypatch):
    serve(monkeypatch, geo=data.geocode(data.PARIS_TX, data.NO_POPULATION, data.PARIS_FR))
    matches = weather.find_places("  Paris ")
    assert [m["region"] for m in matches] == ["Île-de-France", "Texas", "Nowhere"]
    assert matches[0]["lat"] == 48.85 and matches[0]["lon"] == 2.35 and len(matches[0]["id"]) == 8

def test_no_match_is_an_empty_list(monkeypatch):
    serve(monkeypatch, geo=data.geocode())
    assert weather.find_places("Xqzzv") == []

def test_requests_carry_only_rounded_coordinates(monkeypatch):
    seen = serve(monkeypatch, geo=..., forecast=..., air=...)   # records addresses
    weather.confirm(weather.find_places("Paris")[0]["id"])
    for address in seen.addresses[1:]:
        assert "latitude=48.85&" in address and "longitude=2.35&" in address

def test_payload_now_and_details(monkeypatch):
    # payload = weather.confirm(...) for Paris with data.forecast(), data.air()
    assert payload["now"] == {"time": "21:45", "temp_c": 18, "temp_f": 65, "feels_c": 16,
        "feels_f": 61, "condition": "clear", "icon": "moon", "is_day": False}
    assert payload["details"]["wind_mph"] == 12 and payload["details"]["visibility_mi"] == 15
    assert payload["details"]["uv_label"] == "Low" and payload["details"]["sunset"] == "17:20"
    assert payload["spoken"] == "Paris: 65 degrees, 18 Celsius, and clear. High of 71, 10 percent chance of rain."

def test_next_24_hours_start_at_the_current_hour_and_cross_midnight(monkeypatch):
    # payload from data.forecast(current_time="2026-11-05T21:45")
    assert len(payload["hours"]) == 24
    assert payload["hours"][0]["time"] == "21:00" and payload["hours"][3]["time"] == "00:00"
    assert payload["rain"] == "from 2 pm to 5 pm"
    assert [d["weekday"] for d in payload["days"]][:2] == ["Thu", "Fri"] and len(payload["days"]) == 7

def test_missing_values_stay_none(monkeypatch):
    # data.forecast(nulls=True)
    assert payload["hours"][0]["rain_chance"] is None and payload["days"][0]["rain_chance"] is None
    assert payload["spoken"].endswith("High of 71.")

def test_air_quality_failing_leaves_the_forecast(monkeypatch):
    serve(monkeypatch, geo=..., forecast=..., air=urllib.error.URLError("down"))
    payload = weather.confirm(...)
    assert payload["air"] is None and payload["now"]["temp_f"] == 65

def test_pollen_only_where_there_is_some(monkeypatch):
    # data.air() gives pollen None; data.air(pollen=True) gives {"grass": 12.0}, keyed by the
    # pollen type without "_pollen"
    ...

def test_a_failed_forecast_leaves_the_place_on_screen_alone(monkeypatch):
    # confirm Paris, then make the forecast raise and confirm Paris, Texas: WeatherError,
    # and place_on_screen() is still Paris, France

def test_the_cache_avoids_asking_twice_within_10_minutes(monkeypatch):
    # monkeypatch weather.monotonic to a list-backed fake; confirm the same place twice
    # within 599 s: one forecast call; at 601 s: two
    ...

def test_the_cache_holds_at_most_50_entries(monkeypatch):
    # 60 different open_home coordinates: len(weather._cache) <= 50, and the first is gone

def test_an_expired_id_is_refused(monkeypatch):
    # issue ids at t=0, move monotonic to 601: confirm raises LookupError, place_on_screen() is None
    with pytest.raises(LookupError):
        weather.confirm("never-issued")

def test_home_place(monkeypatch):
    serve(monkeypatch, forecast=data.forecast(), air=data.air())
    payload = weather.open_home("Rome\x07", 41.902782, 12.496366)
    assert payload["place"]["name"] == "Rome" and payload["place"]["lat"] == 41.9
    assert weather.place_on_screen()["name"] == "Rome"
```

The high of 71 is `to_f(21.5)` = `round_half_up(70.7)`. Write each commented test in full, with
the assertions its comment states.

- [ ] **Step 2: Run them to make sure they fail** with `AttributeError` (`find_places`,
  `confirm`, ...). Run: `python -m pytest -q tests/test_weather.py`.
- [ ] **Step 3: Write the functions** listed under Interfaces. `weather` imports nothing from the
  project except `config`.
- [ ] **Step 4: Run the tests to make sure they pass, then everything.** Run
  `python -m pytest -q tests/test_weather.py`, `ruff check .` and `python -m pytest -q`.
  Expected: all pass.
- [ ] **Step 5: Commit** `weather.py tests/weather_data.py tests/test_weather.py tests/conftest.py`:
  "Weather: places, forecast summaries, cache and the place on screen".

---

### Task 4: The endpoints, and the conversation

**Files:**
- Modify: `brain.py`:
  - `import weather  # noqa: F401, E402` after `spaces`, with a comment that it registers no
    tools yet, so the prompt is unchanged;
  - `Assistant.add_reply(text: str) -> None`, which appends `{"role": "assistant", "content": text}`
    under `self.lock`, with a docstring saying only the page's buttons call it, like
    `resolve_pending`;
  - `reset()` also calls `weather.clear_place()`.
- Modify: `server.py`:
  - three request models:
    - `PlacesRequest.query`: stripped, 1 to `WEATHER_QUERY_MAX` characters;
    - `PlaceChoice.id`: 1 to 32 characters;
    - `HomePlace.name`: stripped, 1 to `WEATHER_NAME_MAX` characters. `lat` and `lon` are
      floats with `ge`/`le` bounds and `allow_inf_nan=False`. Use Pydantic's
      `StringConstraints` and `Field` in `Annotated` types.
  - three plain `def` endpoints (they block on the network, so FastAPI runs them in its thread
    pool), placed after `/day`:
    - `POST /weather/places` returns `{"matches": weather.find_places(q)}`;
    - `POST /weather/confirm` returns `weather.confirm(id)`, then `assistant.add_reply(payload["spoken"])`;
    - `POST /weather/home` returns `weather.open_home(...)`, then the same.
  - `WeatherError` becomes `HTTPException(502, "Couldn't reach the weather service.")`, and
    `LookupError` becomes `HTTPException(404, "That place has expired. Search again.")`.
- Test: `tests/test_server.py` (a new section "weather endpoints") and `tests/test_brain.py`.

**Interfaces:**
- Consumes: `weather.find_places`, `confirm`, `open_home`, `clear_place`, `place_on_screen`,
  `WeatherError` (Task 3); the `client` and `model` fixtures; `data.serve` and the made-up
  replies from `tests/weather_data.py` (Task 3).
- Produces, for stage 3: the three endpoints and their JSON (Task 3's payload plus `spoken`;
  matches as `{"matches": [...]}`).

- [ ] **Step 1: Write the failing tests**

```python
def test_places_endpoint(client, monkeypatch):
    data.serve(monkeypatch, geo=data.geocode(data.PARIS_FR, data.PARIS_TX))
    r = client.post("/weather/places", json={"query": "Paris"})
    assert r.status_code == 200 and len(r.json()["matches"]) == 2

@pytest.mark.parametrize("query", ["", "   ", "x" * 81])
def test_places_refuses_empty_or_long_queries(client, query):
    assert client.post("/weather/places", json={"query": query}).status_code == 422

def test_confirm_adds_the_spoken_line_to_the_conversation(client, model, monkeypatch):
    model()                                   # a fresh Assistant with a fake model
    # serve geo, forecast, air; find a place via /weather/places; confirm its id
    assert r.status_code == 200 and r.json()["spoken"].startswith("Paris: 65 degrees")
    assert server.assistant.messages[-1] == {"role": "assistant", "content": r.json()["spoken"]}

def test_confirm_refuses_an_unknown_id(client):
    r = client.post("/weather/confirm", json={"id": "nope"})
    assert r.status_code == 404 and r.json()["detail"] == "That place has expired. Search again."

def test_the_service_down_is_a_502(client, monkeypatch):
    data.serve(monkeypatch, geo=urllib.error.URLError("down"))
    r = client.post("/weather/places", json={"query": "Paris"})
    assert r.status_code == 502 and r.json()["detail"] == "Couldn't reach the weather service."

@pytest.mark.parametrize("body", [{"name": "Home", "lat": 91, "lon": 0},
    {"name": "Home", "lat": 0, "lon": 181}, {"name": "x" * 61, "lat": 0, "lon": 0},
    {"name": "", "lat": 0, "lon": 0}, {"name": "Home", "lat": "north", "lon": 0}])
def test_home_refuses_bad_coordinates(client, body):
    assert client.post("/weather/home", json=body).status_code == 422

@pytest.mark.parametrize("number", ["NaN", "Infinity"])
def test_home_refuses_nan_and_infinity(client, number):
    r = client.post("/weather/home", content='{"name": "Home", "lat": %s, "lon": 0}' % number,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422

@pytest.mark.parametrize("path", ["/weather/places", "/weather/confirm", "/weather/home"])
def test_weather_endpoints_refuse_other_websites(client, path):
    r = client.post(path, json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403

@pytest.mark.parametrize("path", ["/weather/places", "/weather/confirm", "/weather/home"])
def test_weather_endpoints_refuse_plain_text(client, path):
    r = client.post(path, content='{"query": "Paris"}', headers={"Content-Type": "text/plain"})
    assert r.status_code == 422

@pytest.mark.parametrize("path", ["/weather/places", "/weather/confirm", "/weather/home"])
def test_weather_endpoints_only_take_post(client, path):
    assert client.get(path).status_code == 405
```

In `tests/test_brain.py`:

```python
def test_reset_forgets_the_place_on_screen(monkeypatch):
    # open_home through data.serve; then Assistant().reset(); weather.place_on_screen() is None

def test_weather_adds_no_tools():
    assert not any(s["function"]["name"].startswith(("find_place", "get_forecast"))
                   for s in tools.SCHEMAS)
    assert [s["function"]["name"] for s in tools.SCHEMAS][-1] == "open_space"
```

- [ ] **Step 2: Run them to make sure they fail.** Expected: 404 for each new endpoint, so most
  fail on their status codes; `test_weather_adds_no_tools` passes before and after, as a guard.
  Write in the ledger that it passed first, and why. Run: `python -m pytest -q tests/test_server.py tests/test_brain.py -k "weather or reset_forgets"`.
- [ ] **Step 3: Write the brain and server changes** listed under Files.
- [ ] **Step 4: Run the tests to make sure they pass, then everything.** Run the same `-k` line,
  then `ruff check .` and `python -m pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit** `brain.py server.py tests/`: "Weather: the three endpoints, and the
  spoken line in the conversation".

---

### Task 5: The privacy rule in the docs, and a live check

**Files:**
- Modify: `SECURITY.md`:
  - **section 4**: new rows. **Control:** "Outside requests go only to three fixed HTTPS
    addresses in `config.py`, built by code, with redirects refused, a 5 s timeout, a 1 MB cap
    and coordinates rounded to 2 decimals (`weather.py`, pinned by tests)". **Protects against:**
    "JARVIS being sent anywhere else, by the model or by a reply". A second row: outside names
    are cleaned and capped before use.
  - **section 5**: a new decision, `### Outside data: Weather (Phase 5, item 6)`. It gives:
    - the rule, verbatim from the spec's "The privacy rule";
    - what goes out (the place name or words; rounded coordinates, the home place's included);
    - what Open-Meteo sees and keeps (the IP address; logs that "may contain ... geographical
      coordinates", deleted after 90 days, read 2026-11-05);
    - why it is accepted;
    - that the log records hosts and times, never addresses;
    - that place names are the first outside text the model will read (stage 4), short and
      cleaned. Anything longer, such as news, needs its own design.
  - **section 7**: the accepted risk in one line.
  - **section 8**: the "Before adding a tool that reads outside content" bullet now says weather
    names are handled, and news and the web still need a prompt-injection design.
- Modify: `CLAUDE.md`:
  - the opening paragraph: "Nothing leaves the machine unencrypted ..." becomes the new rule, in
    its words;
  - the architecture diagram: `weather.py` under `server.py` ("/weather/*: places, forecast, air
    quality from three fixed HTTPS addresses");
  - the file table: a `weather.py` row, and `server.py`'s row gains the three endpoints;
  - Safety boundaries: a bullet that outside requests go only through `weather._get`. The
    addresses are fixed in `config.py`; the model never supplies an address or coordinates;
    redirects are refused; and a new outside service needs the owner's agreement and the same
    rules.
  - Testing: tests never go online (the `no_internet` fixture).
- Modify: `README.md`: the first paragraph (the new rule, in short), and `weather.py` in "How
  the pieces fit".
- Modify: `CHANGELOG.md`:
  - section `## 56. Weather, stage 2: the server`, in the style of section 55: what goes out and
    why, the one door, the figures, the cache, the endpoints, the decisions above, the tests and
    the live check with its real results, and what was not checked;
  - a Status row: "Weather, stage 2 (section 56) | Done; checked live against Open-Meteo; no page
    or tools yet";
  - the "last updated" date.
- Create (scratch, not committed): `demo/run_demo.py` in the session's scratchpad, as in stage 1
  (`JARVIS_DB` first; `BACKUP_DIR`, `BACKUP_ENCRYPTED_DIR` and `LOG_DIR` into the demo folder;
  port 8016). No made-up events are needed.

**Interfaces:**
- Consumes: the three endpoints (Task 4).

- [ ] **Step 1: Live check**, with `curl` against the demo server (these are real requests to
  Open-Meteo, as the agreed rule allows):
  - `POST /weather/places {"query": "Paris"}`: Paris, France first, with 2-decimal coordinates.
  - `POST /weather/places {"query": "Paris, Texas"}`: a match in Texas.
  - `POST /weather/places {"query": "Xqzzv"}`: `{"matches": []}`.
  - Confirm Paris: 24 hours, 7 days, `air` present, and a plausible `spoken` line. Compare
    `now.temp_c` with Open-Meteo's own figure for the same coordinates; read it with `WebFetch`
    on the forecast address with `current=temperature_2m`, which is the same kind of request.
  - `POST /weather/home {"name": "Rome", "lat": 41.902782, "lon": 12.496366}`: Rome's payload.
  - The demo's `logs/jarvis.log` has one line per request, with host, time and status, and no
    "Paris", "Rome" or coordinates in those lines. The message line that `add_reply` records is
    not a request line.
  - The real `jarvis.db`, the newest file in `backups/` and `logs/jarvis.log` keep their times.
  - Stop the demo.
- [ ] **Step 2: Write the docs** as above, with the live check's real results.
- [ ] **Step 3: Check every claim against the code and run the checks.** Run `ruff check .`
  and `python -m pytest -q`. Expected: all pass, and the CHANGELOG states the real count.
- [ ] **Step 4: Commit** `SECURITY.md CLAUDE.md README.md CHANGELOG.md`: "Document the outside-data
  rule and Weather stage 2 (CHANGELOG section 56)".
