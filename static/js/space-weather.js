// ---------- The Weather space (docs/specs/2026-11-05-weather-space.md) ----------
// Opens on a slowly turning globe (globe.js). A search spins it to the place, a ping asks
// "Paris?", and confirming zooms in and shows the weather page. Everything here talks only
// to JARVIS's own /weather/... endpoints (weather.py), which do the fetching and every sum.

const wxSection = document.getElementById('space-weather');
const wxCanvas = document.getElementById('wx-globe');
const globe = makeGlobe(wxCanvas);
let wxLinesLoaded = false;

// The coastlines, once; if they fail, the globe still draws its grid and rim
async function wxLoadLines() {
  if (wxLinesLoaded) return;
  wxLinesLoaded = true;
  try {
    const res = await fetch('/static/data/coastlines.json');
    if (!res.ok) throw new Error('coastlines ' + res.status);
    globe.setLines((await res.json()).lines);
  } catch (e) {
    console.warn('coastlines unavailable; drawing the grid only', e);
  }
}

function wxView() { return wxSection.dataset.view; }
function wxSetView(view) { wxSection.dataset.view = view; }

registerSpace({
  name: 'weather', title: 'WEATHER', key: '3', section: wxSection,
  enter() {
    wxLoadLines();
    globe.start();
    if (wxPending) { const m = wxPending; wxPending = null; wxShowMatchesNow(m); }
    else if (wxView() === 'page' && wxPayload) globe.zoomTo(wxPayload.place.lat, wxPayload.place.lon);
    else if (wxView() === 'globe') globe.turn(true);
  },
  // A ping left open is cancelled; the page stays, to come back to
  leave() { if (wxView() === 'ping') wxCancel(); globe.stop(); },
  ready: () => globe.drawn,
  readout: () => (wxView() === 'page' && wxPayload ? String(wxPayload.place.name || '').toUpperCase() : 'GLOBE ONLINE'),
});

// ---------- search, the ping, confirming ----------
const wxQuery = document.getElementById('wx-query');
const wxNote = document.getElementById('wx-note');
const wxPing = document.getElementById('wx-ping');
const wxPingName = document.getElementById('wx-ping-name');
const wxPingWhere = document.getElementById('wx-ping-where');
const wxYes = document.getElementById('wx-yes');
const wxNo = document.getElementById('wx-no');
const wxGlobeView = document.getElementById('wx-globe-view');

let wxMatches = [];       // the places offered, largest first (weather.find_places)
let wxIndex = 0;          // the one the ping is on
let wxPending = null;     // matches that arrived while another space was shown
let wxPayload = null;     // the place shown on the page
let wxSearchToken = 0;    // the newest search wins: a late reply to an older one is ignored
let wxSpinToken = 0;      // likewise for spins: only the newest may show its ping
let wxBusy = false;       // one confirm at a time

function wxSay(text) { wxNote.textContent = text || ''; }
function wxError(text) { wxSay(text); showSteps([{ status: 'error', text }]); }

async function wxPost(path, body) {
  try {
    const res = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    let data = {};
    try { data = (await res.json()) || {}; } catch (e) { /* not JSON: keep {} */ }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return { ok: false, status: 0, data: {} };
  }
}
// The server's own words when it gives some (weather.py's plain messages), else the usual one
function wxDetail(r) {
  return typeof r.data.detail === 'string' ? r.data.detail : "Couldn't reach the weather service.";
}

async function wxSearch() {
  const q = wxQuery.value.trim();
  if (!q) return;
  const token = ++wxSearchToken;
  wxSay('Searching\u2026');
  const r = await wxPost('/weather/places', { query: q });
  if (token !== wxSearchToken) return;
  if (!r.ok) { wxError(wxDetail(r)); return; }
  const matches = Array.isArray(r.data.matches) ? r.data.matches : [];
  if (!matches.length) { wxCancel(); wxSay("I couldn't find a place called " + q + '.'); return; }
  wxSay('');
  weatherShowMatches(matches);
}

// Spin to the first match and ask. The search box uses it; in stage 4 the chat will too,
// from any space, so it waits for Weather to be on screen before spinning.
function weatherShowMatches(matches) {
  if (!Array.isArray(matches) || !matches.length) return;
  if (currentSpace !== 'weather') { wxPending = matches; switchSpaceWhenFree('weather'); return; }
  wxShowMatchesNow(matches);
}

function wxShowMatchesNow(matches) {
  wxMatches = matches;
  wxIndex = 0;
  wxPointAt(0);
}

async function wxPointAt(i) {
  const m = wxMatches[i];
  const token = ++wxSpinToken;
  wxPing.hidden = true;
  globe.clearPing();
  globe.unzoom();
  wxSetView('ping');
  const arrived = await globe.spinTo(m.lat, m.lon);
  if (!arrived || token !== wxSpinToken || wxView() !== 'ping') return;
  globe.ping(m.lat, m.lon);
  wxPingName.textContent = m.name + '?';
  const where = [m.region, m.country].filter(Boolean).join(' \u00b7 ');
  wxPingWhere.textContent = where + (wxMatches.length > 1 ? (where ? ', ' : '') + (i + 1) + ' of ' + wxMatches.length : '');
  wxYes.disabled = wxNo.disabled = false;
  wxPing.hidden = false;
  wxPlacePing();
  wxYes.focus();            // so Enter confirms, with no key handling of its own
}

// Beside the ping, kept inside the globe's area
function wxPlacePing() {
  const m = wxMatches[wxIndex];
  if (!m || wxPing.hidden) return;
  const p = globe.screenPoint(m.lat, m.lon);
  const w = wxGlobeView.clientWidth, hgt = wxGlobeView.clientHeight;
  const x = Math.max(8, Math.min(p.x + 24, w - wxPing.offsetWidth - 8));
  const y = Math.max(8, Math.min(p.y - wxPing.offsetHeight / 2, hgt - wxPing.offsetHeight - 8));
  wxPing.style.left = x + 'px';
  wxPing.style.top = y + 'px';
}
window.addEventListener('resize', wxPlacePing);

function wxNext() {
  if (wxBusy) return;
  wxIndex += 1;
  if (wxIndex < wxMatches.length) { wxPointAt(wxIndex); return; }
  wxCancel();
  wxSay('No other matches. Try adding the country, like \u201cParis, Texas\u201d.');
}

// Back to the turning globe, from the ping or from the page
function wxCancel() {
  ++wxSpinToken;
  clearInterval(wxClock);
  wxPing.hidden = true;
  globe.clearPing();
  globe.unzoom();
  wxSetView('globe');
  globe.turn(true);
}

async function wxConfirm() {
  const m = wxMatches[wxIndex];
  if (wxBusy || !m) return;
  wxBusy = true;
  wxYes.disabled = wxNo.disabled = true;
  const r = await wxPost('/weather/confirm', { id: m.id });
  wxBusy = false;
  if (r.status === 404) { wxCancel(); wxSay(wxDetail(r)); return; }
  if (!r.ok) { wxYes.disabled = wxNo.disabled = false; wxError(wxDetail(r)); return; }
  wxPing.hidden = true;
  wxSay('');
  // Written by weather.py, already added to the conversation by the server
  say(r.data.spoken);
  speak(r.data.spoken).catch(() => {});
  weatherShowPayload(r.data);
}

// Zoom in and show the page (the panels are drawn by drawWeather)
async function weatherShowPayload(payload) {
  wxPayload = payload;
  globe.clearPing();
  globe.turn(false);
  await globe.zoomTo(payload.place.lat, payload.place.lon);
  if (typeof drawWeather === 'function') drawWeather(payload);
  wxSetView('page');
}

document.getElementById('wx-go').addEventListener('click', wxSearch);
wxQuery.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); wxSearch(); } });
wxYes.addEventListener('click', wxConfirm);
wxNo.addEventListener('click', wxNext);

// Escape: cancels the ping, or goes back to the globe from the page. Not while typing (the
// first Escape only leaves the box, spaces.js) or while an access sequence plays.
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape' || currentSpace !== 'weather') return;
  if (typeof seq !== 'undefined' && seq) return;
  if (typingIn(e.target)) return;
  if (wxView() !== 'globe') { e.preventDefault(); wxCancel(); }
});

// ---------- the weather page (every figure comes worked out from weather.py) ----------
const SVG_NS = 'http://www.w3.org/2000/svg';

// An SVG element. Refuses a style or on... attribute: the security policy would block them
// silently, and its tests cannot see attributes set while the page runs (stage 1 review)
function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'style' || k.toLowerCase().startsWith('on')) throw new Error('svg(): no ' + k + ' attribute');
    e.setAttribute(k, v);
  }
  return e;
}

// The weather icons, drawn in code (spec: sun, moon, cloud, part cloud, rain, snow, thunder,
// fog); anything else is the cloud
const WX_CLOUD = 'M14 32h20a7 7 0 0 0 0-14 10 10 0 0 0-19-2A8 8 0 0 0 14 32z';
function wxIcon(name, isDay) {
  const s = svg('svg', { viewBox: '0 0 48 48', class: 'wx-icon', 'aria-hidden': 'true' });
  const sun = (cx, cy, r) => {
    s.appendChild(svg('circle', { cx, cy, r }));
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      s.appendChild(svg('line', { x1: cx + Math.cos(a) * (r + 3), y1: cy + Math.sin(a) * (r + 3),
        x2: cx + Math.cos(a) * (r + 7), y2: cy + Math.sin(a) * (r + 7) }));
    }
  };
  const moon = transform => s.appendChild(svg('path', { d: 'M29 9a14 14 0 1 0 10 23A11 11 0 0 1 29 9z', transform }));
  const cloud = transform => s.appendChild(svg('path', { d: WX_CLOUD, class: 'wx-cloud', transform }));
  const under = (marks) => { for (const m of marks) s.appendChild(m); };
  if (name === 'sun') sun(24, 24, 8);
  else if (name === 'moon') moon('');
  else if (name === 'part-cloud') {
    if (isDay) sun(17, 16, 6); else moon('translate(-8 -6) scale(.8)');
    cloud('translate(4 6)');
  } else if (name === 'fog') {
    for (const y of [18, 25, 32]) s.appendChild(svg('line', { x1: 10, y1: y, x2: 38, y2: y }));
  } else {
    cloud('translate(0 -4)');
    if (name === 'rain') under([16, 24, 32].map(x => svg('line', { x1: x, y1: 34, x2: x - 3, y2: 41 })));
    if (name === 'snow') under([16, 24, 32].map(x => svg('circle', { cx: x, cy: 38, r: 1.6, class: 'wx-dot' })));
    if (name === 'thunder') under([svg('path', { d: 'M26 30l-5 8h6l-4 8', class: 'wx-bolt' })]);
  }
  return s;
}

const wxDash = '\u2013';
const wxDeg = n => (n == null ? wxDash : n + '\u00b0');
const wxOr = (n, unit) => (n == null ? wxDash : n + unit);
const wxClockText = t => (typeof t === 'string' && /^\d\d:\d\d$/.test(t) ? fmtTime(t) : wxDash);
let wxClock = null;

function wxRow(label, value) {
  const row = h('div', 'wx-row');
  row.append(h('span', 'muted', label), typeof value === 'string' ? h('span', null, value) : value);
  return row;
}

// The place's own time, from its offset (refreshed every 30 s while shown)
function wxLocalTime(offset) {
  if (typeof offset !== 'number') return '';
  const d = new Date(Date.now() + offset * 1000);
  const hm = String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0');
  return fmtTime(hm) + ' local time';
}

function drawWeather(p) {
  const place = p.place || {};
  document.getElementById('wx-place').textContent =
    [place.name, place.region, place.country].filter(Boolean).join(' \u00b7 ');
  const local = document.getElementById('wx-local');
  local.textContent = wxLocalTime(place.utc_offset_seconds);
  clearInterval(wxClock);
  wxClock = setInterval(() => { local.textContent = wxLocalTime(place.utc_offset_seconds); }, 30000);

  const today = (p.days || [])[0] || {};
  const now = p.now || {};
  const nowBox = document.getElementById('wx-now');
  nowBox.textContent = '';
  const big = h('div', 'wx-now-main');
  big.appendChild(wxIcon(now.icon, now.is_day));
  const temp = h('div', 'wx-temp');
  temp.append(h('span', 'wx-f', wxDeg(now.temp_f) + (now.temp_f == null ? '' : 'F')),
              h('span', 'wx-c', now.temp_c == null ? '' : now.temp_c + '\u00b0C'));
  big.appendChild(temp);
  nowBox.append(big, h('div', 'wx-cond', now.condition || wxDash),
    h('div', 'muted', 'Feels like ' + wxDeg(now.feels_f) + (now.feels_f == null ? '' : 'F')),
    h('div', 'muted', 'High ' + wxDeg(today.high_f) + ' \u00b7 Low ' + wxDeg(today.low_f)));

  wxDrawHours(p.hours || [], p.rain);
  wxDrawDays(p.days || []);

  const d = p.details || {};
  const det = document.getElementById('wx-details');
  det.textContent = '';
  const wind = h('span', 'wx-wind');
  wind.textContent = d.wind_mph == null ? wxDash : d.wind_mph + ' mph \u00b7 ' + d.wind_kmh + ' km/h';
  if (typeof d.wind_dir === 'number') {
    // The wind comes from wind_dir; the arrow points where it blows to
    const arrow = svg('svg', { viewBox: '0 0 24 24', class: 'wx-arrow', 'aria-hidden': 'true' });
    const g = svg('g', { transform: 'rotate(' + ((d.wind_dir + 180) % 360) + ' 12 12)' });
    g.append(svg('line', { x1: 12, y1: 20, x2: 12, y2: 5 }), svg('path', { d: 'M7 10l5-5 5 5' }));
    arrow.appendChild(g);
    wind.prepend(arrow);
  }
  det.append(wxRow('Wind', wind), wxRow('Humidity', wxOr(d.humidity, '%')),
    wxRow('UV', d.uv == null ? wxDash : d.uv + (d.uv_label ? ' \u00b7 ' + d.uv_label : '')),
    wxRow('Sunrise', wxClockText(d.sunrise)), wxRow('Sunset', wxClockText(d.sunset)),
    wxRow('Pressure', d.pressure_inhg == null ? wxDash : d.pressure_inhg + ' inHg \u00b7 ' + d.pressure_hpa + ' hPa'),
    wxRow('Visibility', d.visibility_mi == null ? wxDash : d.visibility_mi + ' mi \u00b7 ' + d.visibility_km + ' km'));

  const airBox = document.getElementById('wx-air');
  airBox.textContent = '';
  const a = p.air;
  if (!a) { airBox.appendChild(h('div', 'muted', 'Air quality unavailable')); return; }
  const top = h('div', 'wx-aqi');
  top.append(h('span', 'wx-aqi-n', a.aqi == null ? wxDash : String(a.aqi)),
             h('span', null, 'US AQI' + (a.aqi_label ? ' \u00b7 ' + a.aqi_label : '')));
  const bar = h('div', 'wx-aqi-bar');
  bar.dataset.band = (a.aqi_label || '').toLowerCase().replace(/[^a-z]+/g, '-');
  const fill = document.createElement('i');
  fill.style.width = Math.min(100, Math.max(0, (a.aqi || 0) / 3)) + '%';   // 300 fills it
  bar.appendChild(fill);
  airBox.append(top, bar, wxRow('PM2.5', wxOr(a.pm2_5, ' \u00b5g/m\u00b3')), wxRow('Ozone', wxOr(a.ozone, ' \u00b5g/m\u00b3')));
  if (a.pollen) {
    const names = Object.entries(a.pollen).map(([kind, n]) => kind[0].toUpperCase() + kind.slice(1) + ' ' + n);
    airBox.appendChild(wxRow('Pollen', names.join(' \u00b7 ')));
  }
}

// Temperature as a line (°F), rain chance as bars, labels every 3 hours
function wxDrawHours(hours, rain) {
  const box = document.getElementById('wx-hours');
  box.textContent = '';
  const W = 480, H = 140, left = 14, right = 466;
  const chart = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, class: 'wx-chart', role: 'img',
    'aria-label': 'Temperature and chance of rain for the next 24 hours' });
  const temps = hours.map(x => x.temp_f).filter(t => typeof t === 'number');
  const lo = Math.min(...temps), hi = Math.max(...temps);
  const xAt = i => left + (hours.length > 1 ? i * (right - left) / (hours.length - 1) : 0);
  const yAt = t => 24 + (hi > lo ? (hi - t) / (hi - lo) : 0.5) * 52;
  let points = [];
  const flush = () => { if (points.length > 1) chart.appendChild(svg('polyline', { points: points.join(' '), class: 'wx-line' })); points = []; };
  hours.forEach((x, i) => {
    if (typeof x.rain_chance === 'number' && x.rain_chance > 0) {
      const bh = x.rain_chance / 100 * 30;
      chart.appendChild(svg('rect', { x: xAt(i) - 6, y: 116 - bh, width: 12, height: bh, class: 'wx-rainbar' }));
    }
    if (typeof x.temp_f === 'number') points.push(xAt(i).toFixed(1) + ',' + yAt(x.temp_f).toFixed(1));
    else flush();                    // a gap where a value is missing
    if (i % 3 === 0) {
      const t = svg('text', { x: xAt(i), y: 134, class: 'wx-label' });
      t.textContent = wxClockText(x.time).replace(':00', '');
      const v = svg('text', { x: xAt(i), y: typeof x.temp_f === 'number' ? yAt(x.temp_f) - 8 : 16, class: 'wx-label wx-tval' });
      v.textContent = wxDeg(x.temp_f);
      chart.append(t, v);
    }
  });
  flush();
  box.appendChild(chart);
  if (rain) box.appendChild(h('div', 'muted wx-rain', 'Rain likely ' + rain));
}

// One row a day; the low-to-high bars share one scale for the week, so days compare honestly
function wxDrawDays(days) {
  const box = document.getElementById('wx-days');
  box.textContent = '';
  const all = days.flatMap(d => [d.low_f, d.high_f]).filter(t => typeof t === 'number');
  const lo = Math.min(...all), hi = Math.max(...all);
  const at = t => (hi > lo ? (t - lo) / (hi - lo) * 100 : 50);
  days.forEach((d, i) => {
    const row = h('div', 'wx-day');
    const range = h('div', 'wx-range');
    if (typeof d.low_f === 'number' && typeof d.high_f === 'number') {
      const fill = document.createElement('i');
      fill.style.left = at(d.low_f) + '%';
      fill.style.width = Math.max(2, at(d.high_f) - at(d.low_f)) + '%';
      range.appendChild(fill);
    }
    row.append(h('span', 'wx-dname', i === 0 ? 'Today' : (d.weekday || d.date || wxDash)),
      wxIcon(d.icon, true), h('span', 'wx-dchance', wxOr(d.rain_chance, '%')),
      h('span', 'muted wx-dlow', wxDeg(d.low_f)), range, h('span', 'wx-dhigh', wxDeg(d.high_f)));
    box.appendChild(row);
  });
}

document.getElementById('wx-back').addEventListener('click', wxCancel);
