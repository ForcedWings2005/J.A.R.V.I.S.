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

registerSpace({
  name: 'weather', title: 'WEATHER', key: '3', section: wxSection,
  enter() {
    wxLoadLines();
    globe.start();
    if (wxView() === 'globe') globe.turn(true);
  },
  leave() { globe.stop(); },
  ready: () => globe.drawn,
  readout: () => 'GLOBE ONLINE',
});
