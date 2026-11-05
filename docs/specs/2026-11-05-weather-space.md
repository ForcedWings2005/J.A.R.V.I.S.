# The Weather space, and a Content Security Policy

Status: designed, not built. Design agreed with the owner in conversation on 2026-11-04 and
2026-11-05. Builds on `docs/specs/2026-10-27-spaces-and-work.md` (spaces, `registerSpace`,
the access sequence).

## Why

Weather is the third space and the first time JARVIS reads anything from the internet. It was
chosen before Sports (paused, decisions kept) because a free weather service needs no key and
no account. It also sets the pattern Sports will follow: fixed addresses, fetched by the
server, cached, and checked in code.

## What the owner asked for

- A globe on the page. Ask for a place's weather and the globe spins and lands on it, with a
  ping: "this [place]?". Confirm, and it zooms into that area and turns into a weather page
  for that place: current conditions, the coming hours and days.
- Both °F and °C shown.
- Air quality.
- A Content Security Policy for the whole page.

## Decisions

| Question | Decision | Why |
|---|---|---|
| Weather service | **Open-Meteo**: geocoding, forecast and air quality | Free for non-commercial use, no key, no account. Data under CC BY 4.0 (a credit line is required). |
| What Weather shows when opened | **The globe slowly turning, nothing fetched.** Optional: **Set as home**, and an **Open on home** switch (off by default) that skips the globe and the confirm | Nothing goes online until you ask. The switch is for those who always want their own weather. |
| Where the home place is kept | **In the browser** (local storage), not in `jarvis.db` | It is a view setting. No schema change, nothing new in backups. |
| How the place is confirmed | **Click the ping, or Enter.** **Not this one** flies to the next match; **Esc** cancels | The page never shows a forecast for a place you did not pick. |
| How to ask | **Both:** JARVIS (new tools) and a search box on the globe | Voice for asking naturally; the box for when the model is not needed. |
| Units | **°F first, °C smaller**, everywhere on the page. Fetched in °C, converted in code | The owner wants both. Fahrenheit first is an assumption the owner can change. One unit fetched, so the two never disagree. |
| The spoken line after confirming | **Written by code**, both units for the current temperature only | Numbers must be right (the core rule). Both units throughout would be too long to hear. |
| Follow-up questions ("will it rain there tomorrow?") | **The model answers from forecast facts written by code** for the confirmed place | It chooses the tool and words the answer; the figures come from code. |
| Panels | **Now, Next 24 hours, 7 days, Details, Air quality** | The usual weather questions. |
| Radar | **Not included** | Free radar tiles disappeared (RainViewer, January 2026); maybe a later stage. |
| Who fetches | **The server**, `weather.py`, with the Python standard library (`urllib`) | The page only ever talks to `127.0.0.1`, so the CSP can forbid every other address. No new dependency. |
| Globe | **A wireframe on a canvas**, coastlines from Natural Earth (public domain), plain JavaScript | No library, no map tiles, nothing fetched from outside. |
| Content Security Policy | **Yes, its own stage, first** | The page loads only its own files today, so a strict policy costs nothing and makes it hard for injected code to run or send data anywhere. |
| Privacy | **The rule agreed for Sports covers Weather**, and **coordinates are rounded to 2 decimal places** before they are sent | About 1 km: the forecast is the same, but it does not pinpoint a street. |

## The privacy rule

The project's rule was "nothing leaves the Mac unencrypted (except the encrypted backup copy)".
Weather is the first exception, so the rule becomes (wording agreed by the owner for Sports):

> Nothing personal leaves the Mac unencrypted, and only I hold the key. JARVIS may fetch public
> data over HTTPS from a short list of fixed addresses, written in code. Those requests carry
> only what the service needs to answer, and the model never chooses the address.

For Weather, "what the service needs" is the place name typed or said (geocoding) and the
place's coordinates, rounded to 2 decimal places (forecast and air quality). That includes the
home place's coordinates each time it is opened.

What the service sees anyway: the Mac's IP address, as every website does. Open-Meteo's terms
(read 2026-11-05) say its server logs "may contain sensitive information such as geographical
coordinates" and are deleted after 90 days. Accepted: the requests name a place, not a person,
and no account links them to the owner.

This wording goes into `SECURITY.md` (sections 4, 5 and 8) and `CLAUDE.md` (the opening
paragraph and the safety boundaries) in stage 2, when the first outside request is written.

## Version 1: what is in it

### How it works, end to end

1. **Asking.** "What's the weather in Paris?" from any space, or "Paris" in the search box on
   the globe.
2. **Finding the place, in code.** The server asks Open-Meteo's geocoding for up to 5 matches
   and sorts them by population, largest first (a match without a population goes last). The
   model passes on only the words; it never gives coordinates.
3. **The globe.** Weather opens (the access sequence) and the globe spins to the first match.
   The ping card asks "**Paris?** Île-de-France · France, 1 of 4" with **This one** and **Not
   this one**.
4. **Confirming.** The click sends the match's id, a short random id the server made. The
   model cannot confirm a place, and the page cannot invent one, except through the home
   button (below). The server remembers the confirmed place as the place on screen.
5. **Zoom and page.** The globe zooms into the region and the panels fade in.
6. **The spoken line**, from code: "Paris: 64 degrees, 18 Celsius, and clear. High of 70,
   10 percent chance of rain." It appears in the chat like any reply and is spoken when voice
   is on.
7. **Follow-ups.** "Will it rain there tomorrow?" makes the model call `get_forecast`, which
   uses the place on screen.
8. **Back to globe** (button or Esc) returns to the turning globe. The place on screen stays
   the last one confirmed, until another is confirmed or the conversation is reset.

### The page

- **Key `3`** and the address `#weather`, like Work. The opening animation's readout gives the
  place name, or "GLOBE ONLINE".
- **The globe** (`globe.js`, a canvas in JARVIS cyan):
  - A faint grid every 30°, the coastlines, and a soft rim glow. Only the near side is drawn
    (an orthographic projection, about 60 lines of plain JavaScript).
  - At rest, it turns once a minute.
  - To a place: about 1.5 s, the short way round (correct across 180° longitude), easing in
    and out.
  - The ping: an expanding ring on the spot and a glass card beside it. When it appears, the
    keyboard focus moves to **This one**, so Enter confirms with no extra key handling.
  - Zoom: about four times around the place in 0.8 s while the panels fade in. The globe stays
    behind them, dimmed and still.
  - Reduce motion: no turning at rest, the spin becomes a jump, the zoom a plain fade.
  - Drawing stops when Weather is left, when the tab is hidden, and while the panels are
    dimmed after 3 minutes idle.
  - If `coastlines.json` does not load, the globe still works with only the grid and rim.
- **The search box** on the globe view: up to 80 characters; it calls `POST /weather/places`
  and the globe behaves exactly as when JARVIS was asked.
- **Home settings**, in a corner of the globe view: **Set as home** stores the place's name
  and coordinates in local storage; **Open on home** (off by default) makes entering Weather
  call `POST /weather/home` and zoom straight from that spot. If storage is unavailable (a
  private window), both do nothing. Every storage read and write is wrapped in `try`.
- **The weather page**, with JARVIS docked on the right as in Work:

| Panel | Shows |
|---|---|
| Top line | The place, its local time, **Back to globe**, **Set as home** |
| Now | Large icon, **64°F** with 18°C smaller, the condition, feels like, today's high and low |
| Next 24 hours | A temperature line with rain-chance bars under it, labelled every 3 hours |
| 7 days | A row per day: icon, rain chance, a low-to-high bar on one shared scale, both temperatures |
| Details | Wind with a direction arrow, humidity, UV with its label, sunrise and sunset, pressure, visibility |
| Air quality | US AQI with its label and a coloured bar, PM2.5, ozone; pollen only where the service has it (Europe), otherwise hidden |

- **Icons** drawn by code as SVG elements: sun, moon, cloud, part cloud, rain, snow, thunder,
  fog. Day or night comes from the forecast.
- **The credit line** at the bottom, a link to open-meteo.com that opens in a new tab with
  `rel="noopener noreferrer"`. Its exact wording is checked against Open-Meteo's licence page
  in stage 3 (it could not be read on 2026-11-05).
- **Phone width:** not designed now (owner's choice: phone layout later).

## How it works

### Files

| File | What it holds |
|---|---|
| `weather.py` (new) | The outside requests, the geocoding, the forecast and air quality summaries, the cache, the place on screen, the tools `find_place` and `get_forecast`. |
| `config.py` | The settings below, and `"weather"` added to `SPACES`. |
| `tools.py` | `ShowPlaces`, a tool result that changes only the view, like `ShowSpace`. |
| `brain.py` | `import weather` last, so the existing tools keep their order. `run_tool` handles `ShowPlaces`; `chat_stream` streams the `places` event; `reset()` also forgets the place on screen. |
| `server.py` | The CSP header; `POST /weather/places`, `/weather/confirm`, `/weather/home`. |
| `static/js/globe.js` (new) | Drawing only: projection, turning, spinning, zooming, the ping. Never fetches. |
| `static/js/space-weather.js` (new) | `registerSpace` for Weather, the search box, the ping card, the panels, the home settings. Talks only to `/weather/...`. |
| `static/css/space-weather.css` (new) | Layout and glass, using `--glass`, `--blur`, `--rim`. |
| `static/data/coastlines.json` (new) | Natural Earth 1:110m coastlines, as lists of coordinates rounded to 1 decimal. Size to be measured (expected 30 to 80 KB). |
| `scripts/make_coastlines.py` (new) | Standard library only: turns Natural Earth's GeoJSON into `coastlines.json`, so the file can be remade. The original is downloaded only with the owner's permission. |
| `static/index.html` | The Weather section and the new files, in order. |

### Settings (`config.py`)

| Setting | Value |
|---|---|
| `WEATHER_GEOCODE_URL` | `https://geocoding-api.open-meteo.com/v1/search` |
| `WEATHER_FORECAST_URL` | `https://api.open-meteo.com/v1/forecast` |
| `WEATHER_AIR_URL` | `https://air-quality-api.open-meteo.com/v1/air-quality` |
| `WEATHER_TIMEOUT_SECONDS` | 5 |
| `WEATHER_MAX_BYTES` | 1,000,000 |
| `WEATHER_CACHE_SECONDS` | 600 (matches, forecasts and air quality) |
| `WEATHER_CACHE_ENTRIES` | 50 |
| `WEATHER_MATCHES` | 5 |
| `WEATHER_QUERY_MAX` | 80 characters |
| `WEATHER_NAME_MAX` | 60 characters (each outside name) |
| `WEATHER_COORD_DECIMALS` | 2 |

### Going online (`weather.py`)

One function makes every outside request. Its rules:

- The address is one of the three settings above. Code adds the query with
  `urllib.parse.urlencode`, so no text can change the address.
- HTTPS only (all three settings are `https://`; a test pins it).
- **Redirects are refused.** `urllib` normally follows a "go over there instead" reply, which
  could take JARVIS to another site. A redirect handler that refuses keeps the fixed-address
  rule true.
- 5 seconds at most per request; at most 1 MB read; anything that is not valid JSON is refused.
- Coordinates are rounded to 2 decimal places before any request (and are the cache key).
- Every request is logged with its host, how long it took, and its status. Not its address,
  which holds the place.
- Any failure becomes one error type, `WeatherError`, with a plain message.
- **Outside text is cleaned** before the model or the page uses it: place, region and country
  names are cut to 60 characters, with control characters removed. This is the first outside
  text JARVIS reads (prompt injection, `SECURITY.md` section 8). Today it is only short
  names; anything longer, like news, needs its own design.

### Worked out in code

- °F from °C, rounded once at the end: `round(c * 9 / 5 + 32)`.
- WMO weather codes (the numbers Open-Meteo uses) to words and an icon name; an unknown code
  is "unknown".
- US AQI bands and labels: 0–50 Good, 51–100 Moderate, 101–150 Unhealthy for sensitive groups,
  151–200 Unhealthy, 201–300 Very unhealthy, 301 and above Hazardous.
- UV labels: 0–2 Low, 3–5 Moderate, 6–7 High, 8–10 Very high, 11 and above Extreme.
- The next 24 hours from the current hour, in the place's own time zone (`timezone=auto`), so
  it is right across midnight.
- Rain windows: hours with a rain chance of 40 % or more, joined into "from 2 pm to 6 pm".
- The spoken line, and the facts `get_forecast` returns.

### The cache, the ids and the place on screen

- All in memory, never in `jarvis.db`: no schema change, nothing in backups.
- Matches for a query, a forecast and an air quality reading are each kept 10 minutes. At most
  50 entries; the oldest goes first.
- Each match gets an id from `secrets.token_urlsafe(6)`, valid 10 minutes.
- The place on screen is held in `weather.py` behind a lock. `Assistant.reset()` clears it.

### The tools

Registered last (`import weather` after `spaces` in `brain.py`).

- **`find_place(query)`**: the words the user said. Returns `ShowPlaces(matches, reply)`, and
  the page opens Weather and spins. The model sees: "Asked the user to confirm Paris, France on
  the globe. Give no weather until they confirm." No match: "I couldn't find a place called
  ...". Service down: "Error: couldn't reach the weather service."
- **`get_forecast(day="")`**: a `YYYY-MM-DD` date within the place's 7 days, or nothing for now
  and today. Uses only the place on screen. Returns facts written by code (high and low in both
  units, the condition, rain chance and its window, wind, air quality). No place on screen:
  "Error: no place is confirmed yet. Ask which place, or call find_place."
- The ticker line for each (`brain.py`'s step labels): "Looked for Paris", "Forecast for Paris".
- Neither tool needs a confirmation card: they change nothing.

### Chat events

`places` is new, streamed straight after `find_place`'s step:
`{"type": "places", "matches": [{"id", "name", "region", "country", "lat", "lon"}]}`. Weather
opens through the existing `space` event (`"weather"`), sent first.

### Endpoints

All three are POST, though they only read, so every request that makes JARVIS go online is
covered by the `Origin` check and the `text/plain` refusal. Another website cannot make the Mac
send requests.

- **`POST /weather/places`** `{query}`: the search box. Returns the matches with their ids.
  An empty or over-long query: 422.
- **`POST /weather/confirm`** `{id}`: "This one". Sets the place on screen and adds the spoken
  line to the conversation as an assistant message (as `/confirm` does, `brain.py`
  `resolve_pending`), so the model knows what is on screen. Returns the panels' data and the
  spoken line. An unknown or expired id: 404 with a clear `detail`.
- **`POST /weather/home`** `{name, lat, lon}`: the home button. The one place the page supplies
  a place itself; acceptable because only JARVIS's own page passes the `Origin` check. Latitude
  must be −90 to 90, longitude −180 to 180, the name 1 to 60 characters, else 422. Otherwise
  the same as confirm.
- When the forecast cannot be fetched: 502 with "Couldn't reach the weather service." When only
  air quality fails, the reply has the forecast and marks air quality unavailable.

### When something goes wrong

- Open-Meteo slow or down: the page says "Couldn't reach the weather service" in place of the
  panels, and the ticker shows the error. Nothing else in JARVIS waits on it.
- Air quality down: its panel says "Air quality unavailable"; the rest shows.
- No match: JARVIS says so and the globe stays where it is.
- The space's own code failing never stops a switch (`runSafely`, as for Work).

## The Content Security Policy

A header sent with every response, telling the browser what this page may do. Set in a small
middleware of its own in `server.py`, on every path:

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self';
font-src 'self'; connect-src 'self'; media-src 'self' blob: data:;
object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

In plain terms:

- **Scripts, styles, images and fonts come only from JARVIS itself.** An injected
  `<script>` or inline code would not run. There is no `'unsafe-inline'`.
- **The page can talk only to JARVIS** (`connect-src`). Even if something did run, it could
  not send data to another site.
- **Audio from JARVIS, or made in the page.** `blob:` is the spoken reply built in the page
  (`voice.js`, `URL.createObjectURL`), and `data:` the short silent clip that unlocks audio
  (`voice.js`, `SILENCE`).
- **No plug-ins, no changing the page's base address, forms only to JARVIS.**
- **No other site can put JARVIS inside its own page** (`frame-ancestors 'none'`). This stops
  clickjacking: a site hiding JARVIS under its own buttons so a click lands on Confirm.

Checked on 2026-11-05: `index.html` loads only `/static` files and has no inline scripts,
inline styles or `style=` attributes. The scripts never use `eval`, `new Function`,
`insertAdjacentHTML` or `setAttribute('style', ...)`. They set styles through the style
object (`calendar.js`, `style.cssText`), which a CSP allows. No outside fonts or URLs. The
Weather code must keep to the same rules.

## Security and privacy

- The privacy rule above, written into `SECURITY.md` and `CLAUDE.md` in stage 2.
- Three fixed HTTPS addresses in `config.py`; the model never supplies an address or
  coordinates; redirects refused; coordinates rounded.
- Outside text cleaned and capped before use (above).
- Every new endpoint is a POST behind the `Origin` check and the JSON-only rule.
- The CSP (stage 1).
- Nothing new is stored on disk except the coastline file in git. The log records the
  requests' hosts and timings, and, as today, what was said to JARVIS (so a place asked about
  is in the log, as any message is).
- `SECURITY.md` section 6 or 7 records the accepted risk: Open-Meteo sees the Mac's IP address
  and the places asked about, and keeps logs up to 90 days.

## Testing

pytest, under a second, never online. One function in `weather.py` makes every outside
request. The tests replace it with made-up replies shaped like Open-Meteo's. An autouse
fixture makes the real one fail loudly if a test ever reaches it.

- **Going online:** only the three addresses; a query such as `Paris&x=1` or `../` stays inside
  the query string; a redirect is refused; a timeout, more than 1 MB, or bad JSON gives
  `WeatherError`; coordinates are rounded to 2 decimals in the request.
- **Outside text:** names cut to 60 characters, control characters removed.
- **Figures:** °C to °F (−40 → −40, 0 → 32, 100 → 212, and rounding at .5); every WMO code
  has words, an unknown one gives "unknown"; AQI and UV band edges (50/51, 100/101, ...); rain
  windows; the next 24 hours across midnight in the place's time zone; matches sorted by
  population.
- **Cache:** a second ask within 10 minutes does not go online, after 10 minutes it does; at
  most 50 entries; ids expire.
- **Tools:** no match, service down, no place on screen, a date outside the 7 days, each a
  clear message; a confirmed place gives facts; `places` is streamed after the step, with
  `space` first.
- **Endpoints:** each one; unknown or expired id (404); `/weather/home` refuses latitude 91,
  longitude 181 and a 61-character name; each of the three refuses another `Origin` (403)
  and `text/plain` (422), in separate tests; confirming adds the line to the conversation;
  `/reset` forgets the place on screen.
- **CSP:** the exact header on `/`, on a `/static` file, and on a JSON reply.
- **Config:** `SPACES` includes `weather`, and `open_space`'s list follows.

The page has no automated tests (no JavaScript test runner, as for Work). It is checked in a
demo in the browser with made-up data and no CSP errors in the console, then by the owner in
Safari.

### Evals

About 8 new cases (68 to about 76), for example:

- "what's the weather in Paris" calls `find_place` and gives no weather yet;
- "weather in Paris, Texas" keeps "Texas" in the query;
- "will it rain tomorrow?" with a place on screen calls `get_forecast` with tomorrow's date;
- the same with no place on screen asks where (or calls `find_place`), and claims no weather;
- "open the weather" calls `open_space("weather")`;
- "I'm feeling under the weather" calls no weather tool.

A full eval before and after each stage that changes the prompt, with both scores and the
prompt hash in the commit message: a baseline, after stage 3 (`open_space`'s list changes), and
after stage 4 (the new tools).

## Build order

Each stage is its own branch, plan (`docs/plans/`), commits, push, CI and merge.

1. **The Content Security Policy.** The middleware, its test, a demo check that voice, the
   calendar and the animations work with no CSP errors, and the docs (`SECURITY.md` section 4,
   `CLAUDE.md` boundaries). Separate so a CSP problem is never mixed up with weather code.
2. **The server.** `weather.py` (requests, summaries, cache, place on screen), the settings,
   the three endpoints, the tests, and the privacy rule in `SECURITY.md` and `CLAUDE.md`.
   Nothing on screen yet.
3. **The page.** The coastline file (download with permission) and its script, the globe, the
   search box, the ping, the panels, the home settings, key 3, `"weather"` in `SPACES`. Full
   eval before and after.
4. **JARVIS.** `find_place`, `get_forecast`, `ShowPlaces`, the `places` event, the eval cases,
   the full eval, and the docs (`README`, `plan.md`, CHANGELOG status).

Every stage adds its CHANGELOG section.

## Risks

- **The model gives weather before confirming,** or makes figures up instead of calling
  `get_forecast`. The tool results say not to, and the evals measure it. The page's numbers
  never come from the model, whatever it says.
- **New tool descriptions unsettle unrelated cases,** as in CHANGELOG sections 39 and 47. The
  full eval before and after shows it.
- **Open-Meteo changes or limits its free service.** One file to change. The free limit
  (10,000 calls a day) is far above one person's use, with the cache.
- **The coastline file is larger than expected.** Then a coarser simplification; measured in
  stage 3.
- **Safari draws the canvas or the CSP differently.** The owner's Safari check, as for every
  stage.
