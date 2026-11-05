# Weather, stage 3: the page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Weather space, key 3, opens on a slowly turning wireframe globe. A search spins it
to the place, a ping asks "Paris?", and confirming zooms in and fades into the weather page.
JARVIS can open the space by name (`open_space("weather")`).

**Architecture:** Two new plain scripts, following Work:
- `globe.js` only draws: an orthographic projection on a canvas, plus turning, spinning,
  zooming and the ping. It never fetches.
- `space-weather.js` registers the space and runs everything else: the search box, the ping
  card, the panels and the home settings. It talks only to stage 2's `/weather/...` endpoints.

The coastlines are a small JSON file made from Natural Earth by a standard-library script. On
the Python side the only change is `"weather"` in `config.SPACES` and a short mention in
`open_space`'s description. That is a prompt change, so a full eval runs before and after.

**Tech Stack:** Plain JavaScript (no library, no build step), canvas 2D, SVG made with
`createElementNS`, CSS. Python standard library for the coastline script. pytest for the
script, the data file and the spaces list. The page itself is checked in a demo in the
browser (there is no JavaScript test runner), then by the owner in Safari.

**Spec:** `docs/specs/2026-11-05-weather-space.md`: "How it works, end to end", "The page",
"Files", "When something goes wrong", "The Content Security Policy" (its rules for new code),
"Evals", and "Build order" stage 3. Stages 1 and 2: CHANGELOG sections 55 and 56.

## Global Constraints

- The page talks only to `127.0.0.1`: `fetch` goes to `/weather/places`, `/weather/confirm`,
  `/weather/home` and `/static/data/coastlines.json`, nothing else (CSP `connect-src 'self'`).
- No inline scripts or styles, no `style=` attributes, no `on...=` attributes, no `eval`, no
  `innerHTML` with markup, and no `setAttribute('style', ...)`. Styles that change at run time
  go through the style object (`el.style.left = ...`). The SVG helper refuses `style` and
  `on...` attribute names (stage 1's review: the scans cannot see attributes set at run time).
- Text from the server goes into the page only through `textContent` or `h()`.
- Units: °F large, °C smaller; mph before km/h; miles before km; inHg before hPa. A missing
  value (`null`) shows as `–`, never as "null", "NaN" or "undefined".
- The globe (spec values): a grid every 30°; one turn a minute at rest; to a place in about
  1.5 s, the short way round, easing in and out; zoom about 4× in 0.8 s; Reduce motion means
  no turning at rest, a jump instead of a spin, and a plain fade instead of a zoom. Drawing
  stops when Weather is left, when the tab is hidden, and while the page is dimmed after
  3 minutes idle (`body.fx-ambient`).
- Ping: focus moves to **This one**, so Enter confirms with no extra key handling. **Not this
  one** goes to the next match, and **Esc** cancels.
- Home settings live in `localStorage` (`weatherHome`, `weatherOpenOnHome`). Every read and
  write is wrapped in `try`. **Open on home** is off by default.
- JavaScript conventions (CLAUDE.md, existing files): plain scripts sharing globals, loaded in
  order; `h(tag, cls, text)` from `calendar.js`; `fmtTime` for times; `say` and `speak` for
  JARVIS's line; `showSteps` for the ticker.
- Downloading Natural Earth's file needs the owner's permission (spec). Approving this plan
  gives it for exactly this file: `ne_110m_coastline.geojson`, Natural Earth v4.1.0, from
  `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/693f11422f4e08d2da4566b854dda53eb7c39fb3/geojson/ne_110m_coastline.geojson`,
  139,907 bytes (size from the server's headers, 2026-11-05), public domain. It goes into its
  own new folder in the session's scratchpad. The script reads it as data and is run with
  `python -I`.
- Demos: their own database, backups and log; port 8016. Check `lsof -iTCP:8000 -sTCP:LISTEN`
  first. The owner's own JARVIS reloads on file changes; say so in the report.
- Commit on `weather-stage-3` after each task. Never on `main`; do not push.

## Decisions this plan makes (the spec is silent)

- **After the last match, "Not this one" cancels.** The note says "No other matches. Try
  adding the country, like "Paris, Texas"."
- **The page shows times as the rest of the page does** (`fmtTime`), and the place's local
  time from `utc_offset_seconds`, refreshed every 30 s while the page is shown.
- **The wind arrow points where the wind blows to** (`wind_dir + 180`), drawn with an SVG
  `transform` attribute.
- **Space states** are a `data-view` attribute on the section: `globe`, `ping` or `page`, and
  CSS shows each view.
- **One confirm at a time.** The buttons are disabled while a request is out, so a
  double-click sends one request.
- **Stage 4 will feed the globe from the chat** through `weatherShowMatches(matches)`, so the
  search box uses that same function today.
- **Two eval cases** for the spaces list: "Open the weather." opens it, and "I love rainy
  weather." does not.

## Review Focus

1. **Escape while typing in the search box** should only leave the box (as everywhere,
   `spaces.js`). A second Escape cancels the ping or goes back to the globe. Pinned by
   Task 4's demo step "Escape".
2. **Leaving Weather in the middle of a spin, a ping or a zoom** (key 1, or JARVIS switching)
   stops the animation with no console errors. Coming back shows the turning globe, or the page
   if it was shown. Pinned by Task 4's demo step "Leaving mid-way".
3. **A payload with missing values** must show `–` everywhere: no "null", "NaN" or
   "undefined", and no broken chart line. Pinned by Task 5's demo step "Missing values".
4. **A double click on This one, or a search while a ping is open,** sends exactly one confirm,
   and the newest search wins. Pinned by Task 4's demo step "One at a time".
5. **Storage that throws** (a private window): the page still works, and the home settings do
   nothing. Pinned by Task 6's demo step "No storage".

---

### Task 1: The coastline data

**Files:**
- Create: `scripts/make_coastlines.py`. Its docstring gives the source URL, the version and
  "public domain". `convert(geojson: dict) -> dict` takes each `LineString` and
  `MultiLineString` and returns `{"source": "Natural Earth 1:110m coastlines, v4.1.0, public domain", "lines": [[[lon, lat], ...], ...]}`.
  Coordinates are rounded to 1 decimal place, consecutive duplicates are dropped, and lines
  shorter than 2 points are dropped. Anything that is not a pair of finite numbers in range is
  skipped. `main(argv)` reads the path in `argv[1]` and writes `static/data/coastlines.json`
  with `json.dump(..., separators=(",", ":"))`.
- Create: `static/data/coastlines.json` (generated, committed).
- Test: `tests/test_coastlines.py`.

**Interfaces:**
- Produces: `/static/data/coastlines.json` = `{"source": str, "lines": [[[lon, lat], ...]]}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_lines_are_rounded_and_cleaned():
    geo = {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "LineString", "coordinates": [[1.04, 2.06], [1.01, 2.09], [3.5, 4.5]]}},
        {"geometry": {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[5, 5]]]}},
        {"geometry": {"type": "Point", "coordinates": [9, 9]}},
        {"geometry": {"type": "LineString", "coordinates": [[1, "x"], [200, 0], [2, 2], [3, 3]]}},
    ]}
    out = make_coastlines.convert(geo)
    assert out["lines"] == [[[1.0, 2.1], [3.5, 4.5]], [[0, 0], [1, 1]], [[2, 2], [3, 3]]]
    assert "public domain" in out["source"]

def test_the_committed_file_is_small_and_sane():
    data = json.loads((config.STATIC_DIR / "data" / "coastlines.json").read_text())
    size = (config.STATIC_DIR / "data" / "coastlines.json").stat().st_size
    assert 10_000 < size < 100_000
    assert len(data["lines"]) > 50
    for line in data["lines"]:
        assert len(line) >= 2
        assert all(-180 <= lon <= 180 and -90 <= lat <= 90 for lon, lat in line)
```

Import the script with `importlib.util.spec_from_file_location` (`scripts/` is not a package).

- [ ] **Step 2: Run them to make sure they fail.** Run: `python -m pytest -q tests/test_coastlines.py`.
  Expected: the first errors because the script does not exist, the second because the file
  does not exist.
- [ ] **Step 3: Write the script**, then **download the file** (the permission is above) with
  `curl -sL -o <scratchpad>/ne/ne_110m_coastline.geojson <url>`. Record its size and SHA-256
  in the ledger and in the script's docstring. Then run
  `python -I scripts/make_coastlines.py <scratchpad>/ne/ne_110m_coastline.geojson` from the
  project folder.
- [ ] **Step 4: Run the tests and everything.** Run `python -m pytest -q tests/test_coastlines.py`,
  `ruff check .` and `python -m pytest -q`. Expected: all pass. Write the output file's size in
  the ledger. If it is 100 KB or more, round to whole degrees for lines in the polar regions
  first, and record that as a ruling.
- [ ] **Step 5: Commit** `scripts/make_coastlines.py static/data/coastlines.json tests/test_coastlines.py`:
  "Weather: coastlines from Natural Earth (1:110m), and the script that makes them".

---

### Task 2: Weather in the spaces list, measured

**Files:**
- Modify: `config.py`: `SPACES = ("home", "work", "weather")`.
- Modify: `spaces.py`: the description gains "weather has a globe and the weather for a place;"
  after the `work` sentence, and nothing else changes.
- Modify: `evals/cases.py`: in the spaces block,
  `Case("space_weather", "Open the weather.", expect=[("open_space", {"name": "weather"})], max_calls={"open_space": 1})`
  and `Case("space_weather_mentioned_no_switch", "I love rainy weather.", forbid=["open_space"])`.
- Test: `tests/test_spaces.py`, `tests/test_server.py`.

**Interfaces:**
- Produces: `/chat` accepts `space: "weather"`, so the stamp reads `[… · Weather]`, and
  `open_space(name="weather")` returns `ShowSpace("weather", …)`.

- [ ] **Step 1: Baseline eval, before any change.** Run `python -m evals > <workspace>/eval-before.log 2>&1`
  in the background (about 12 minutes; Ollama must be running, check with `curl -s 127.0.0.1:11434/api/version`).
  Record the score and the prompt hash from its last lines. If Ollama is not running, stop and
  ask the owner.
- [ ] **Step 2: Write the failing tests**

```python
def test_weather_is_a_space():
    assert spaces.open_space("Weather").name == "weather"

# tests/test_server.py
def test_chat_accepts_the_weather_space(client, model):
    model(say("Hello."))
    r = client.post("/chat", json={"message": "hi", "space": "weather"})
    assert r.status_code == 200
    assert " · Weather] hi" in server.assistant.messages[1]["content"]
```

`test_the_schema_lists_the_spaces` already follows `config.SPACES`. (`brain.time_stamp`
already names any space, so the server test is the one that proves `/chat` takes it.)

- [ ] **Step 3: Run them to make sure they fail.** `open_space` returns the "no space called"
  error string, so `.name` raises `AttributeError`, and `/chat` answers 422. Run:
  `python -m pytest -q tests/test_spaces.py tests/test_server.py -k "weather"`.
- [ ] **Step 4: Make the three edits above.** Run `ruff check .` and `python -m pytest -q`.
  Expected: all pass.
- [ ] **Step 5: The eval after.** Run `python -m evals > <workspace>/eval-after.log 2>&1` (70
  cases × 3). Read every failure with `-v` before calling it the model's (CLAUDE.md).
  Expected: the hash differs from Step 1, and the two new cases pass in most runs. Any old case
  that drops by more than run-to-run variation (a case that passed 3/3 now passing 1/3 or
  less) is reported to the owner before going on.
- [ ] **Step 6: Commit** `config.py spaces.py evals/cases.py tests/`: "Weather joins the spaces
  list (open_space), measured". The message gives both scores and both prompt hashes.

---

### Task 3: The globe

**Files:**
- Create: `static/js/globe.js`.
- Create: `static/css/space-weather.css`, the globe view part. The section fills its cell, the
  canvas fills the section, and the search box and home settings float over it as glass.
- Modify: `static/index.html`:
  - the stylesheet link after `space-work.css`;
  - `<section class="space" id="space-weather" data-space="weather" data-view="globe" aria-label="Weather" hidden>`
    after Work's section, holding the globe view (`<canvas id="wx-globe">`), the search box
    (`<input id="wx-query" maxlength="80">`, `<button id="wx-go">SEARCH</button>`,
    `<div id="wx-note">`), the ping card (`#wx-ping` with `#wx-ping-name`, `#wx-ping-where`,
    `#wx-yes` THIS ONE, `#wx-no` NOT THIS ONE, hidden), the home settings (`#wx-open-home`
    checkbox "Open on home", `#wx-home-name`) and an empty `#wx-page`;
  - `globe.js` and `space-weather.js` after `space-work.js`, before `motion.js`.
- Create: `static/js/space-weather.js`, this task's part: only
  `registerSpace({ name: 'weather', title: 'WEATHER', key: '3', section, enter, leave, ready, readout })`.
  `enter` loads the coastlines once and starts turning; `leave` stops; `ready` is
  `() => globe.drawn`; `readout` gives `'GLOBE ONLINE'` (the place's name in Task 5).

**Interfaces:**
- Produces (`globe.js`, globals):
  - `globeMath.project(lat, lon, centerLat, centerLon) -> {x, y, visible}`: unit sphere, y up,
    `visible` when the point faces the viewer (`cos c >= 0`).
  - `globeMath.shortest(fromLon, toLon) -> number`: the signed turn in degrees, from −180 to 180.
  - `makeGlobe(canvas) -> globe`, where `globe` has:
    - `setLines(lines)`;
    - `start()` and `stop()` (the drawing loop);
    - `spinTo(lat, lon) -> Promise`, `zoomTo(lat, lon) -> Promise`, `unzoom()`;
    - `ping(lat, lon)` and `clearPing()`;
    - `screenPoint(lat, lon) -> {x, y, visible}` (CSS pixels in the canvas);
    - `drawn: boolean`.
  - The loop uses `requestAnimationFrame` and draws nothing while `document.hidden` or
    `body.fx-ambient`. It sizes the canvas for `devicePixelRatio`, and reads its colours from
    the CSS variables once (`--accent`).
  - Reduce motion is read as `motion.js`'s `calm()` reads it, by a function of its own here,
    because `globe.js` loads first.

- [ ] **Step 1: Write the globe and its section** as above. Drawing order: rim glow, grid every
  30° (meridians and parallels as sampled lines), coastlines, ping. The math:
  `cos c = sin φ0 sin φ + cos φ0 cos φ cos(λ − λ0)`, `x = cos φ sin(λ − λ0)`,
  `y = cos φ0 sin φ − sin φ0 cos φ cos(λ − λ0)`. Turning at rest is 6° per second of real
  time. Spin and zoom ease in and out (`t < .5 ? 2t² : 1 − (−2t + 2)² / 2`).
- [ ] **Step 2: Lint and tests.** Run `ruff check .` and `python -m pytest -q`. Expected: all
  pass, including stage 1's scans of `index.html` and `static/js/` and
  `test_every_file_the_page_loads_exists`.
- [ ] **Step 3: Demo check** (made-up data, port 8016, 1440×900; a `securitypolicyviolation`
  listener as in stage 1). Each item is a `javascript_tool` check:
  - `globeMath.project(0, 0, 0, 0)` gives `{x: 0, y: 0, visible: true}`;
    `project(0, 180, 0, 0).visible` is `false`; `project(90, 0, 0, 0).y` is `1`.
  - `globeMath.shortest(170, -170)` is `20`; `shortest(-170, 170)` is `-20`; `shortest(0, 180)`
    is `180` or `-180`.
  - Key 3 opens Weather with the access sequence; the readout says GLOBE ONLINE; the address is
    `#weather`; the canvas is drawn (`globe.drawn`), and a screenshot shows the coastlines.
  - Turning: the centre longitude changes by about 6° a second; with Reduce motion on, it does
    not change.
  - Key 1 stops the loop (count frames with a wrapped `requestAnimationFrame`: no new frames
    from the globe after leaving). Adding `fx-ambient` to the body stops the drawing too.
  - With the coastlines file renamed for a moment (fetch fails), the grid and rim still draw.
    No console errors, no policy violations.
- [ ] **Step 4: Commit** `static/`: "Weather: the space and its globe (key 3)".

---

### Task 4: Search, ping and confirm

**Files:**
- Modify: `static/js/space-weather.js`.
- Modify: `static/css/space-weather.css` (the ping card and the note).
- Create (scratch, not committed): the demo launcher `demo3/run_demo.py`. It is like stage 2's,
  with a `--canned` mode that replaces `weather._fetch` with made-up replies from
  `tests/weather_data.py`:
  - a geocoding query containing "Nowhere" gets no matches, and one containing "Broken" gets
    `URLError`;
  - any other query gets `PARIS_FR`, `PARIS_TX` and `NO_POPULATION`;
  - a forecast for latitude 10.0 gets `forecast(nulls=True)` with the current temperature set
    to `None`; anything else gets `forecast()`;
  - air quality gets `air()`.

**Interfaces:**
- Consumes: `makeGlobe`, `globe.*` (Task 3); `POST /weather/places` → `{matches}`,
  `POST /weather/confirm {id}` → payload with `spoken` (stage 2); `say`, `speak`,
  `showSteps` (chat.js and voice.js).
- Produces:
  - `weatherShowMatches(matches)` (global, for stage 4): switch to Weather if needed, then spin
    to the first match and show the ping;
  - `weatherShowPayload(payload)`, which Task 5 fills in (here: zoom, then `data-view="page"`);
  - the section's `data-view` (`globe`, `ping` or `page`).

- [ ] **Step 1: Write the flow.**
  - **Search:** Enter in `#wx-query` or a click on SEARCH sends `POST /weather/places`. An
    empty list writes "I couldn't find a place called …" in `#wx-note`. Not OK writes the
    server's `detail` in the note and shows it in the ticker as an `error` step. A newer search
    replaces an older one: a counter makes a late reply be ignored.
  - **Ping:** spin, then `globe.ping`. The card goes beside `globe.screenPoint`, kept inside
    the section, and shows the name, "region · country" and "1 of N". Focus moves to `#wx-yes`.
  - **Not this one:** the next match, or after the last, cancel with the note from Decisions.
  - **This one:** disable both buttons, then `POST /weather/confirm`.
    - OK: `say(spoken)` and `speak(spoken)`, then `weatherShowPayload(payload)`.
    - 404: the note says "That place has expired. Search again." and the view goes back to the
      globe.
    - 502: the note and the ticker show the error, and the globe stays.
  - **Escape** (a `keydown` listener): ignored when Weather is not shown, when a sequence is
    playing (`seq`), or while typing (`spaces.js` already blurs). From `ping` it cancels; from
    `page` it goes back to the globe. Back to globe calls `globe.unzoom()`, `clearPing()`, and
    sets `data-view="globe"`.
  - **Leaving** (`leave`) stops the globe. Any animation still waiting resolves without
    drawing.
- [ ] **Step 2: Lint and tests.** Run `ruff check .` and `python -m pytest -q`. Expected: all pass.
- [ ] **Step 3: Demo check** (canned mode, violation listener):
  - "Paris" spins to France, and the card says "Paris?" with "Île-de-France · France" and
    "1 of 3". Focus is on THIS ONE.
  - Not this one moves to Texas, then the third match. After it, the globe and the note.
  - "Nowhere" gives "I couldn't find a place called Nowhere". "Broken" gives the 502 message
    in the note and an error step in the ticker.
  - **Escape:** typing in the box, Escape only blurs it (the ping stays). A second Escape
    cancels the ping. On the page, Escape goes back to the globe.
  - **One at a time:** wrap `fetch` to count `/weather/confirm` calls, and double-click THIS
    ONE: one call. Two quick searches ("Paris", then "Nowhere"): the note shows the "Nowhere"
    result, and no ping from the first.
  - **Leaving mid-way:** key 1 during a spin, during a ping and during a zoom, then key 3. No
    console errors, and the globe is turning.
  - **Confirm:** the spoken line appears in the chat and `/weather/confirm` returned 200.
  - **404:** `weatherShowMatches([{id: 'never-issued', name: 'Nowhere', region: '', country: '', lat: 0, lon: 0}])`,
    then click THIS ONE. The server answers 404, and the note says "That place has expired.
    Search again."
- [ ] **Step 4: Commit** `static/`: "Weather: search, the ping and confirming".

---

### Task 5: The weather page

**Files:**
- Modify: `static/js/space-weather.js` (`weatherShowPayload` and the panel builders).
- Modify: `static/css/space-weather.css` (the page grid, the panels, the chart, the bars, the
  AQI colours by `data-band`).
- Modify: `static/index.html`: `#wx-page`'s panels:
  - `.wx-top`, with `#wx-place`, `#wx-local`, `#wx-back` BACK TO GLOBE and `#wx-sethome` SET
    AS HOME;
  - `#wx-now`, `#wx-hours`, `#wx-days`, `#wx-details`, `#wx-air`;
  - the credit, `<a class="wx-credit" href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">`.

**Interfaces:**
- Consumes: Task 4's `weatherShowPayload` and view states; stage 2's payload (`place`, `now`,
  `hours`, `rain`, `days`, `details`, `air`, `spoken`).
- Produces:
  - `wxIcon(name, isDay) -> SVGElement`, for `sun`, `moon`, `part-cloud`, `cloud`, `fog`,
    `rain`, `snow`, `thunder`; anything else draws the cloud;
  - `svg(tag, attrs) -> SVGElement`, which throws on an attribute named `style` or starting
    with `on`;
  - `readout()` gives the place's name, upper case, once the page is shown.

- [ ] **Step 1: Write the page.**
  - **Now:** the large icon, `64°F` with a small `18°C`, the condition, "Feels like 61°F", and
    "High 71° · Low 50°" (°F) from `days[0]`.
  - **Next 24 hours:** one SVG with `viewBox="0 0 480 140"`. The temperature (°F) is a
    polyline scaled to the 24 hours' range, broken where a value is missing. The rain chances
    are bars along the bottom, and labels every 3 hours use `fmtTime`. The `rain` sentence
    goes under it when there is one.
  - **7 days:** a row per day: the weekday (`days[0]` says "Today"), the icon, the rain chance,
    the low-to-high bar placed on one scale for the week (`style.left` and `style.width` in %),
    and the low and high in °F.
  - **Details:** the wind (mph · km/h, and an arrow rotated `wind_dir + 180`), humidity %, UV
    with its label, sunrise and sunset (`fmtTime`), pressure (inHg · hPa), visibility
    (mi · km).
  - **Air quality:** the AQI number and label, and a bar coloured by band (`data-band` from
    the label), PM2.5 µg/m³, ozone µg/m³, and the pollen (hidden when `null`). With
    `air: null`: "Air quality unavailable".
  - **Top line:** the place, written as "Paris · Île-de-France · France" with the empty parts
    left out. The local time comes from `utc_offset_seconds` and is refreshed every 30 s while
    the page is shown; there is no local time when the offset is missing.
  - **Showing the page:** `weatherShowPayload` zooms (or fades, with Reduce motion), fills the
    panels and sets `data-view="page"`. Back to globe clears the 30 s timer.
- [ ] **Step 2: Credit wording.** Read `https://open-meteo.com/en/license` (WebFetch). If it
  asks for wording, use it. If it can't be read, use "Weather data by Open-Meteo.com" and
  record that as a ruling.
- [ ] **Step 3: Lint and tests.** Run `ruff check .` and `python -m pytest -q`. Expected: all pass.
- [ ] **Step 4: Demo check** (canned mode, violation listener, 1440×900, then a screenshot of
  the page for the report):
  - **Paris:** 65°F and 18°C, "clear" with the moon, 24 hours from 21:00 with the rain bars at
    14:00–16:00 tomorrow and "from 2 pm to 5 pm", 7 rows starting "Today", AQI 42 "Good",
    and the credit link with `rel="noopener noreferrer"` and `target="_blank"`.
  - **Missing values:** search "Paris" and confirm the third match (latitude 10, `nulls=True`
    with no current temperature). `document.getElementById('space-weather').textContent` holds
    no "null", "NaN" or "undefined"; the missing temperature shows `–`; and the chart line
    has a gap.
  - **`svg('rect', {style: 'x'})` throws,** and so does `svg('g', {onclick: 'x'})`.
  - **Readout:** switching away and back plays the sequence with the place's name.
  - **Live, once:** the launcher without `--canned`, "Rome", confirm. The page draws real data
    with no console errors.
- [ ] **Step 5: Commit** `static/`: "Weather: the weather page".

---

### Task 6: Home settings

**Files:**
- Modify: `static/js/space-weather.js`, `static/css/space-weather.css`.

**Interfaces:**
- Consumes: `POST /weather/home {name, lat, lon}` (stage 2), `weatherShowPayload`.
- Produces:
  - `localStorage.weatherHome` = `JSON.stringify({name, lat, lon})`;
  - `localStorage.weatherOpenOnHome` = `'1'` or `'0'`.

- [ ] **Step 1: Write the settings.**
  - **SET AS HOME** saves the place shown (`payload.place.name`, `.lat`, `.lon`). The button
    then reads "HOME ✓", and `#wx-home-name` shows the name.
  - **The switch** saves itself.
  - **Entering Weather with the switch on and a valid home:** jump the globe to the home
    (no spin), `POST /weather/home`, then show the page. On failure, the globe and the note.
  - **Valid** means a name of 1 to 60 characters, and finite numbers with latitude −90 to 90
    and longitude −180 to 180. Anything else is ignored, as if no home were set.
- [ ] **Step 2: Lint and tests.** Run `ruff check .` and `python -m pytest -q`.
- [ ] **Step 3: Demo check** (canned mode, violation listener):
  - Set Paris as home. Turn the switch on, go to Home and back: the page opens straight on
    Paris, with no ping and with `/weather/home` called once.
  - Turn the switch off: Weather opens on the globe.
  - A home saved as `{"name": "", "lat": 999}` by hand is ignored.
  - **No storage:** replace `Storage.prototype.getItem` and `setItem` with throwing functions
    and reload. The page loads, a search and confirm work, and SET AS HOME does nothing, with
    no uncaught error.
  - Reset the storage afterwards.
- [ ] **Step 4: Commit** `static/`: "Weather: home settings (set as home, open on home)".

---

### Task 7: Docs, and the last checks

**Files:**
- Modify: `README.md`: the spaces paragraph (**1 HOME · 2 WORK · 3 WEATHER**), how Weather is
  used (search, ping, This one / Not this one / Esc, home settings), and that it asks
  Open-Meteo.
- Modify: `CLAUDE.md`: the `static/` row lists `globe.js`, `space-weather.js`,
  `css/space-weather.css`, `data/coastlines.json`; the file table gains
  `scripts/make_coastlines.py`; and `spaces.py`'s row mentions three spaces.
- Modify: `CHANGELOG.md`:
  - section `## 57. Weather, stage 3: the page`, in the style of section 53: the globe and how
    it works, the flow, the decisions above, both eval scores and hashes, the demo's checks
    with real results, the live run, and what was not checked (Safari, how it looks in motion
    by eye, phone width);
  - the file layout (`scripts/`, `static/data/`, the new scripts, `tests/test_coastlines.py`);
  - a Status row and the "last updated" date.

- [ ] **Step 1: The last checks, all together, in canned mode with the violation listener:**
  - a full round from key 3 to the page and back with Reduce motion on;
  - the tab hidden for a moment (wrapped `requestAnimationFrame`: no globe frames while
    `document.hidden`);
  - `read_console_messages` with `onlyErrors`: none.
- [ ] **Step 2: Write the docs.** Check every count and claim against the code and the ledger.
  Run `ruff check .` and `python -m pytest -q`.
- [ ] **Step 3: Commit** `README.md CLAUDE.md CHANGELOG.md`: "Document Weather stage 3 (CHANGELOG
  section 57)". The report ends with the owner's Safari check: key 3, search, ping, confirm,
  the page, Escape, home settings, voice on, and the Web Inspector console open.
