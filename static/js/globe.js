// ---------- The Weather globe (docs/specs/2026-11-05-weather-space.md, "The page") ----------
// Drawing only: a wireframe Earth on a canvas, seen from far away (an orthographic
// projection), that turns, spins to a place, pings it and zooms in. It never fetches;
// space-weather.js gives it the coastlines and tells it what to do.

// The maths, kept apart so it can be checked on its own (and tested, if a JS test runner
// is ever added). Angles in degrees; a unit sphere, x to the right, y up.
const globeMath = {
  // Where a point lands when the globe is turned so (centerLat, centerLon) faces you.
  // visible: false for points on the far side.
  project(lat, lon, centerLat, centerLon) {
    const r = Math.PI / 180;
    const p = lat * r, l = lon * r, p0 = centerLat * r, l0 = centerLon * r;
    const cosc = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l - l0);
    return {
      x: Math.cos(p) * Math.sin(l - l0),
      y: Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l - l0),
      visible: cosc >= 0,
    };
  },
  // The signed turn, -180 to 180, the short way round: 170 to -170 is +20, not -340
  shortest(fromLon, toLon) {
    return ((toLon - fromLon) % 360 + 540) % 360 - 180;
  },
  ease(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; },
};

// Like motion.js's calm(), which loads later
function globeCalm() {
  return document.body.classList.contains('reduce') ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

const GLOBE_TURN_DEG_PER_S = 6;     // one turn a minute at rest
const GLOBE_SPIN_MS = 1500;
const GLOBE_ZOOM_MS = 800;
const GLOBE_ZOOM = 4;

function makeGlobe(canvas) {
  const ctx = canvas.getContext('2d');
  const state = { lat: 20, lon: 0, zoom: 1, lines: [], ping: null, running: false, turning: false };
  let anim = null;        // { from, to, start, ms, done }: a spin or a zoom in progress
  let frame = null;
  let last = 0;
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue('--accent').trim() || '#4cc9f0';

  function size() {
    const ratio = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, hgt = canvas.clientHeight;
    if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(hgt * ratio)) {
      canvas.width = Math.round(w * ratio);
      canvas.height = Math.round(hgt * ratio);
    }
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { w, hgt, r: Math.min(w, hgt) * 0.42 * state.zoom };
  }

  // A line of [lon, lat] points, split where it goes round to the far side
  function stroke(points, s) {
    ctx.beginPath();
    let pen = false;
    for (const [lon, lat] of points) {
      const p = globeMath.project(lat, lon, state.lat, state.lon);
      if (!p.visible) { pen = false; continue; }
      const x = s.w / 2 + p.x * s.r, y = s.hgt / 2 - p.y * s.r;
      if (pen) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      pen = true;
    }
    ctx.stroke();
  }

  function draw(now) {
    const s = size();
    ctx.clearRect(0, 0, s.w, s.hgt);
    // The rim and its glow
    ctx.save();
    ctx.shadowColor = accent;
    ctx.shadowBlur = 24;
    ctx.strokeStyle = accent;
    ctx.globalAlpha = 0.7;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(s.w / 2, s.hgt / 2, s.r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
    // The grid, every 30 degrees
    ctx.strokeStyle = accent;
    ctx.lineWidth = 0.6;
    ctx.globalAlpha = 0.18;
    for (let lon = -180; lon < 180; lon += 30) {
      const meridian = [];
      for (let lat = -90; lat <= 90; lat += 5) meridian.push([lon, lat]);
      stroke(meridian, s);
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const parallel = [];
      for (let lon = -180; lon <= 180; lon += 5) parallel.push([lon, lat]);
      stroke(parallel, s);
    }
    // The coastlines
    ctx.globalAlpha = 0.85;
    ctx.lineWidth = 1;
    for (const line of state.lines) stroke(line, s);
    // The ping: a dot and a ring that grows and fades, once a second
    if (state.ping) {
      const p = globe.screenPoint(state.ping.lat, state.ping.lon);
      if (p.visible) {
        const t = (now % 1000) / 1000;
        ctx.globalAlpha = 1;
        ctx.fillStyle = accent;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1 - t;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 6 + t * 22, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    globe.drawn = true;
  }

  function step(now) {
    frame = null;
    if (!state.running) return;
    const dt = last ? (now - last) / 1000 : 0;
    last = now;
    // A hidden tab or the idle dimming: draw nothing, look again in a second
    if (document.hidden || document.body.classList.contains('fx-ambient')) {
      last = 0;
      frame = setTimeout(() => { frame = null; if (state.running) frame = requestAnimationFrame(step); }, 1000);
      return;
    }
    if (anim) {
      const t = Math.min(1, (now - anim.start) / anim.ms);
      const e = globeMath.ease(t);
      for (const k of Object.keys(anim.to)) state[k] = anim.from[k] + (anim.to[k] - anim.from[k]) * e;
      if (t >= 1) { const done = anim.done; anim = null; done(true); }
    } else if (state.turning && !globeCalm()) {
      state.lon = ((state.lon + GLOBE_TURN_DEG_PER_S * dt + 540) % 360) - 180;
    }
    draw(now);
    frame = requestAnimationFrame(step);
  }

  // Animate some of lat, lon and zoom; instant with Reduce motion. Resolves false if
  // interrupted (another animation, or the globe stopped).
  function animate(to, ms) {
    if (anim) { const done = anim.done; anim = null; done(false); }
    if (globeCalm() || !state.running) {
      Object.assign(state, to);
      if (state.running) draw(performance.now());
      return Promise.resolve(true);
    }
    const from = {};
    for (const k of Object.keys(to)) from[k] = state[k];
    return new Promise(done => {
      // A safety timeout, as motion.js has: a hidden tab gets no frames, and a spin or zoom
      // must still finish, or the ping and the page would wait until the tab came back
      const safety = setTimeout(() => {
        if (anim !== mine) return;
        Object.assign(state, to);
        anim = null;
        done(true);
      }, ms + 250);
      const mine = { from, to, start: performance.now(), ms, done: ok => { clearTimeout(safety); done(ok); } };
      anim = mine;
    });
  }

  const globe = {
    drawn: false,
    get center() { return { lat: state.lat, lon: state.lon, zoom: state.zoom }; },
    setLines(lines) { state.lines = Array.isArray(lines) ? lines : []; },
    start() {
      if (state.running) return;
      state.running = true;
      last = 0;
      frame = requestAnimationFrame(step);
    },
    stop() {
      state.running = false;
      if (frame) { cancelAnimationFrame(frame); clearTimeout(frame); frame = null; }
      if (anim) { const done = anim.done; anim = null; done(false); }
    },
    turn(on) { state.turning = on; },
    // The short way round, keeping the centre longitude between -180 and 180
    spinTo(lat, lon) {
      state.turning = false;
      const target = state.lon + globeMath.shortest(state.lon, lon);
      return animate({ lat, lon: target }, GLOBE_SPIN_MS).then(ok => {
        state.lon = ((state.lon + 540) % 360) - 180;
        return ok;
      });
    },
    jumpTo(lat, lon) {
      state.turning = false;
      state.lat = lat;
      state.lon = lon;
    },
    zoomTo(lat, lon) {
      state.turning = false;
      return animate({ lat, lon: state.lon + globeMath.shortest(state.lon, lon), zoom: GLOBE_ZOOM }, GLOBE_ZOOM_MS);
    },
    unzoom() {
      if (anim) { const done = anim.done; anim = null; done(false); }
      state.zoom = 1;
    },
    ping(lat, lon) { state.ping = { lat, lon }; },
    clearPing() { state.ping = null; },
    // CSS pixels inside the canvas
    screenPoint(lat, lon) {
      const w = canvas.clientWidth, hgt = canvas.clientHeight;
      const r = Math.min(w, hgt) * 0.42 * state.zoom;
      const p = globeMath.project(lat, lon, state.lat, state.lon);
      return { x: w / 2 + p.x * r, y: hgt / 2 - p.y * r, visible: p.visible };
    },
  };
  return globe;
}
