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
  readout: () => 'GLOBE ONLINE',
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
