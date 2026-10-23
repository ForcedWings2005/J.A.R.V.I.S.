// ---------- Motion (CHANGELOG section 42) ----------
// Animations layered over the dashboard. Each wrapper below calls the original function, which
// still does all the real work, and adds an effect around it. Every class used here starts with
// "fx-", so it cannot clash with the page's own classes. Reduce motion turns all of it off.

const calm = () => document.body.classList.contains('reduce') ||
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const pause = ms => new Promise(r => setTimeout(r, ms));
function once(node, cls, ms) {                 // play a CSS animation once, restarting it if needed
  if (!node || calm()) return;
  node.classList.remove(cls); void node.offsetWidth;
  node.classList.add(cls);
  setTimeout(() => node.classList.remove(cls), ms);
}

// ---------- The orb: sound, thinking, colour ----------
// Wrap the orb in a group that grows with the sound level, and add the thinking effects
(function upgradeOrb() {
  const svg = document.getElementById('orb');
  const react = el('g', { class: 'fx-react' }, svg);
  while (svg.firstChild !== react) react.appendChild(svg.firstChild);
  const c = 230;
  const arc = (r, a0, a1) => {
    const p = a => [c + r * Math.cos(a * Math.PI / 180), c + r * Math.sin(a * Math.PI / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return 'M' + x0 + ' ' + y0 + 'A' + r + ' ' + r + ' 0 0 1 ' + x1 + ' ' + y1;
  };
  const radar = el('g', { class: 'fx-radar' }, react);      // a comet: a bright head, a fading tail
  for (let i = 0; i < 7; i++) {
    el('path', { d: arc(207, -8 * (i + 1), -8 * i), fill: 'none', stroke: 'currentColor',
      'stroke-width': 5 - i * 0.5, opacity: 1 - i * 0.14, 'stroke-linecap': 'round' }, radar);
  }
  const segs = el('g', { class: 'fx-segs' }, react);        // 24 segments that light in turn
  for (let i = 0; i < 24; i++) {
    const s = el('path', { d: arc(226, i * 15 + 2, i * 15 + 12), fill: 'none', stroke: 'currentColor', 'stroke-width': 3 }, segs);
    s.style.setProperty('--i', i);
  }
})();

// The sound level, 0 to 1, in the CSS variable --level. Two sources:
// - your microphone while it records (measured live; it is never played back), and
// - JARVIS's voice, from a loudness map of each sentence's sound file, followed as it plays.
//   Speech is not routed through the audio engine, so this can never silence it.
let fxCtx = null;              // the browser's audio engine, started by a click (Safari's rule)
let fxSource = null;           // what is being measured now: { read() } returning 0 to 1
let fxLevel = 0;
let fxLoop = null;

const unlockAudioPlain = unlockAudio;
unlockAudio = () => {
  unlockAudioPlain();
  try {
    fxCtx = fxCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (fxCtx.state === 'suspended') fxCtx.resume();
  } catch (e) { fxCtx = null; }   // no audio engine: the orb just does not react to sound
};

function fxRun() {
  if (fxLoop) return;
  const step = () => {
    const target = fxSource && !calm() ? fxSource.read() : 0;
    fxLevel = Math.max(target, fxLevel * 0.85);          // rise at once, fall gently
    document.body.style.setProperty('--level', fxLevel.toFixed(3));
    if (!fxSource && fxLevel < 0.01) {
      document.body.style.setProperty('--level', 0);
      fxLoop = null;
      return;
    }
    fxLoop = requestAnimationFrame(step);
  };
  fxLoop = requestAnimationFrame(step);
}

function fxHearStop() {
  if (fxSource && fxSource.stop) fxSource.stop();
  fxSource = null;
}

function fxHearMic(stream) {
  if (!fxCtx || calm()) return;
  try {
    const node = fxCtx.createMediaStreamSource(stream);
    const analyser = fxCtx.createAnalyser();
    analyser.fftSize = 512;
    node.connect(analyser);                                 // not to the speakers: no echo
    const data = new Uint8Array(analyser.fftSize);
    fxHearStop();
    fxSource = {
      read() {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (const v of data) sum += ((v - 128) / 128) ** 2;
        return Math.min(1, Math.sqrt(sum / data.length) * 4);
      },
      stop() { node.disconnect(); },
    };
    fxRun();
  } catch (e) { /* the orb simply does not react */ }
}

const STEP = 0.05;                                          // one loudness reading per 50 ms
async function loudnessMap(blob) {
  const bytes = await blob.arrayBuffer();
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const sound = await new Offline(1, 1, 44100).decodeAudioData(bytes);
  const samples = sound.getChannelData(0), per = Math.floor(sound.sampleRate * STEP), map = [];
  for (let i = 0; i < samples.length; i += per) {
    let sum = 0;
    const end = Math.min(i + per, samples.length);
    for (let j = i; j < end; j++) sum += samples[j] * samples[j];
    map.push(Math.sqrt(sum / (end - i)));
  }
  const loudest = Math.max(...map, 0.0001);
  return map.map(v => v / loudest);
}

function fxFollowSpeech(audio, blob) {
  if (calm()) return;
  loudnessMap(blob).then(map => {
    const follow = () => {
      fxHearStop();
      fxSource = { audio, read: () => (audio.paused || audio.ended) ? 0 : map[Math.floor(audio.currentTime / STEP)] || 0 };
      fxRun();
    };
    if (!audio.paused) follow();          // it may have started while the map was being made
    audio.addEventListener('playing', follow);
    const end = () => { if (fxSource && fxSource.audio === audio) fxHearStop(); };
    audio.addEventListener('ended', end);
    audio.addEventListener('pause', end);
  }).catch(() => { /* an unreadable file: the orb simply does not react */ });
}

// ---------- Small helpers for the effects ----------
function stagger(container, selector, max = 60) {          // items arrive one after another
  if (calm()) return;
  [...container.querySelectorAll(selector)].slice(0, max).forEach((item, i) => {
    item.style.setProperty('--i', i);
    item.classList.remove('fx-seq'); void item.offsetWidth; item.classList.add('fx-seq');
    setTimeout(() => item.classList.remove('fx-seq'), 1200 + i * 35);
  });
}

const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&*+<>/\\';
function decode(target, ms = 650) {                        // scramble, then settle on the real text
  if (!target || calm()) return;
  const text = target.dataset.text || target.textContent;
  target.dataset.text = text;
  const start = performance.now();
  const step = now => {
    const done = Math.min(1, (now - start) / ms);
    const fixed = Math.floor(done * text.length);
    target.textContent = [...text].map((ch, i) =>
      i < fixed || ch === ' ' ? ch : GLYPHS[Math.floor(Math.random() * GLYPHS.length)]).join('');
    if (done < 1) requestAnimationFrame(step); else target.textContent = text;
  };
  requestAnimationFrame(step);
}
function decodeTitles() { document.querySelectorAll('.h .l').forEach((t, i) => setTimeout(() => decode(t), i * 120)); }

function countUp(node, from) {                              // "3 OPEN" counts to "2 OPEN"
  const m = node.textContent.match(/^(\d+)(.*)$/);
  if (!m || isNaN(from) || calm()) return;
  const to = +m[1], rest = m[2];
  if (from === to) return;
  const start = performance.now();
  const step = now => {
    const f = Math.min(1, (now - start) / 400);
    node.textContent = Math.round(from + (to - from) * f) + rest;
    if (f < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// ---------- Screens: the access sequence ----------
// Each stage waits for the one before it, and the content stays hidden until the end.
// A click or Escape during the opening skips straight to the content.
let seq = null;                                             // the sequence that is running, if any

function stageWait(s, ms) {                                 // a pause that a skip cuts short
  return new Promise(resolve => {
    const t = setTimeout(resolve, ms);
    s.wake = () => { clearTimeout(t); resolve(); };
  });
}
function stageRace(s, promise) {                            // an animation that a skip cuts short
  return Promise.race([promise, new Promise(resolve => { s.wake = resolve; })]);
}
function skipSequence() { if (seq) { seq.skip = true; if (seq.wake) seq.wake(); } }

const box = r => ({ left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' });

function shockwave(r) {
  const ring = document.createElement('div');
  ring.className = 'fx-shock';
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2, size = Math.max(r.width, r.height) * 2.6;
  document.body.appendChild(ring);
  ring.animate([
    { left: cx + 'px', top: cy + 'px', width: '0px', height: '0px', opacity: 1 },
    { left: (cx - size / 2) + 'px', top: (cy - size / 2) + 'px', width: size + 'px', height: size + 'px', opacity: 0 },
  ], { duration: 600, easing: 'cubic-bezier(.2,.8,.3,1)' }).finished.then(() => ring.remove(), () => ring.remove());
}

function makeFrame(withReadout) {                           // the empty frame that flies out
  const f = document.createElement('div');
  f.className = 'fx-frame';
  for (let i = 0; i < 4; i++) { const c = document.createElement('span'); c.className = 'fx-corner'; f.appendChild(c); }
  if (withReadout) {
    const body = document.createElement('div');
    body.className = 'fx-readout';
    const title = document.createElement('div'); title.className = 'fx-title';
    const bar = document.createElement('div'); bar.className = 'fx-bar';
    for (let i = 0; i < 20; i++) bar.appendChild(document.createElement('i'));
    const pct = document.createElement('div'); pct.className = 'fx-pct'; pct.textContent = '0%';
    const line = document.createElement('div'); line.className = 'fx-line';
    body.append(title, bar, pct, line);
    f.appendChild(body);
  }
  document.body.appendChild(f);
  return f;
}

function lockOn(p) {                                         // corner brackets, added once per panel
  if (p.querySelector('.fx-lockon')) return;
  const lock = document.createElement('div');
  lock.className = 'fx-lockon';
  for (let i = 0; i < 4; i++) lock.appendChild(document.createElement('span'));
  p.appendChild(lock);
}

function accessWords(p) {                                    // the readout, from the real contents
  if (p.id === 'sched-panel') return ['SCHEDULE', 'SYNCING 7 DAYS · ' + upcoming.length + ' EVENTS'];
  if (p.querySelector('#tasks')) {
    const all = p.querySelectorAll('.task').length, done = p.querySelectorAll('.task.done').length;
    return ['TO-DO', (all - done) + ' OPEN · ' + done + ' DONE'];
  }
  if (p.querySelector('#notes')) return ['MEMORY', p.querySelectorAll('.note').length + ' NOTES ON FILE'];
  const l = p.querySelector('.h .l');
  return [(l.dataset.text || l.textContent).trim(), ''];
}

async function contentReady(p) {                             // the calendar draws itself late
  const start = performance.now();
  while (p.id === 'sched-panel' && !p.querySelector('#cal .cbody > *') && performance.now() - start < 3000) await pause(30);
}

async function fillBar(s, frame, ready) {                    // 90% on time, the rest when ready
  const cells = frame.querySelectorAll('.fx-bar i'), pct = frame.querySelector('.fx-pct');
  const show = f => {
    const lit = Math.round(f * cells.length);
    cells.forEach((c, i) => c.classList.toggle('fx-on', i < lit));
    pct.textContent = Math.round(f * 100) + '%';
  };
  let isReady = false;
  ready.then(() => { isReady = true; });
  const start = performance.now();
  while (!s.skip) {
    const t = (performance.now() - start) / 850;
    show(Math.min(t, 1) * (isReady ? 1 : 0.9));
    if (t >= 1 && isReady) break;
    await stageWait(s, 30);
  }
  show(1);
}

const STAGGER_ITEMS = '.task, .note, .cbody .ygrid > *, .cbody .mcell, .cbody .tgh, .cbody .tev';
const focusPanelPlain = focusPanel;
const closeFocusPlain = closeFocus;

async function openScreen(p) {
  const s = seq = { skip: false };
  let frame = null;
  const finish = () => {                                     // the reveal, and the end of a skip
    if (frame) frame.remove();
    if (!p.classList.contains('focused')) { focusPanelPlain(p); document.body.classList.add('fx-receding'); }
    p.classList.remove('fx-hidden');
    lockOn(p);
    once(p, 'fx-reveal', 900);
    setTimeout(() => once(p, 'fx-glitch', 450), 420);
    decode(p.querySelector('.h .l'), 700);
    setTimeout(() => stagger(p, STAGGER_ITEMS), 200);
    seq = null;
  };
  p.classList.remove('fx-tilt');
  const from = p.getBoundingClientRect();
  // 1. Charge
  once(p, 'fx-charge', 300);
  shockwave(from);
  await stageWait(s, 220);
  if (s.skip) return finish();
  // 2. Launch: open the screen invisibly, measure it, and fly an empty frame there
  focusPanelPlain(p);
  p.classList.add('fx-hidden');
  document.body.classList.add('fx-receding');
  const to = p.getBoundingClientRect();
  const ready = contentReady(p);
  frame = makeFrame(true);
  const fly = frame.animate([{ ...box(from), opacity: 0.4 }, { ...box(to), opacity: 1 }],
    { duration: 550, easing: 'cubic-bezier(.2,.9,.25,1.08)', fill: 'forwards' });
  // A safety timeout: if the browser never reports the end (a hidden tab), go on anyway
  await stageRace(s, Promise.race([fly.finished.catch(() => {}), pause(900)]));
  if (s.skip) return finish();
  // 3. Access: a big title, a segmented bar, a real readout
  const [title, line] = accessWords(p);
  frame.querySelector('.fx-title').textContent = 'ACCESSING ' + title;
  frame.querySelector('.fx-line').textContent = line;
  frame.classList.add('fx-loading');
  decode(frame.querySelector('.fx-title'), 600);
  await fillBar(s, frame, ready);
  if (s.skip) return finish();
  // 4. Access granted
  frame.querySelector('.fx-title').dataset.text = 'ACCESS GRANTED';
  frame.querySelector('.fx-title').textContent = 'ACCESS GRANTED';
  frame.classList.add('fx-granted');
  await stageWait(s, 320);
  // 5. Reveal
  finish();
}

async function closeScreen(p) {
  seq = { skip: false, closing: true };
  p.classList.add('fx-off');                                 // the content switches off
  await pause(260);
  const big = p.getBoundingClientRect();
  closeFocusPlain();
  p.classList.add('fx-hidden');
  p.classList.remove('fx-off');
  const small = p.getBoundingClientRect();
  document.body.classList.remove('fx-receding');
  const frame = makeFrame(false);
  const back = frame.animate([{ ...box(big), opacity: 1 }, { ...box(small), opacity: 0.5 }],
    { duration: 420, easing: 'cubic-bezier(.5,0,.75,0)', fill: 'forwards' });
  await Promise.race([back.finished.catch(() => {}), pause(800)]);   // the same safety timeout
  frame.remove();
  p.classList.remove('fx-hidden');
  once(p, 'fx-charge', 300);
  seq = null;
}

focusPanel = p => {
  if (focused || seq) return;
  if (calm()) focusPanelPlain(p); else openScreen(p);
};
closeFocus = () => {
  if (seq) { if (!seq.closing) skipSequence(); return; }
  if (!focused) return;
  return calm() ? closeFocusPlain() : closeScreen(focused);
};
// The background's click handler holds the original closeFocus; swap it for this one
const scrimEl = document.getElementById('scrim');
scrimEl.removeEventListener('click', closeFocusPlain);
scrimEl.addEventListener('click', () => closeFocus());
// A click anywhere during the opening skips it (the click that started it has already passed)
document.addEventListener('click', e => {
  if (seq && !seq.closing) { e.stopPropagation(); e.preventDefault(); skipSequence(); }
}, true);

// ---------- Feedback when something changes ----------
const keysIn = sel => new Set([...document.querySelectorAll(sel)].map(n => n.dataset.key || n.dataset.id));

const loadEventsPlain = loadEvents;
let knownEvents = null;
loadEvents = async () => {                                   // new events ping in
  await loadEventsPlain();
  const now = keysIn('#sched .evc');
  if (knownEvents) {
    for (const card of document.querySelectorAll('#sched .evc, #timeline .ev')) {
      if (!knownEvents.has(card.dataset.key)) once(card, 'fx-ping', 2500);
    }
  }
  knownEvents = now;
};

const resolveActionPlain = resolveAction;
resolveAction = async approve => {                           // a deleted event wipes away first
  const card = confirmText.textContent;
  const m = card.match(/^Delete (?:ALL occurrences of |only the (\S+) occurrence of )?'(.+?)'/);
  if (approve && m && !calm()) {
    const onlyDate = m[1], title = m[2].toLowerCase();       // onlyDate: one day of a repeat
    const doomed = [...document.querySelectorAll('#sched .evc, #timeline .ev')]
      .filter(n => (n.querySelector('.et') || n).textContent.toLowerCase() === title)
      .filter(n => !onlyDate || !n.dataset.key || n.dataset.key.endsWith('|' + onlyDate));
    doomed.forEach(n => n.classList.add('fx-wipe'));
    if (doomed.length) await pause(550);
  }
  return resolveActionPlain(approve);
};

const loadTasksPlain = loadTasks;
let knownTasks = false;
loadTasks = async () => {                                    // new tasks slide in, ticked ones burst
  const before = new Map([...document.querySelectorAll('#tasks .task')].map(t => [t.dataset.id, t.classList.contains('done')]));
  const countEl = document.getElementById('tasks-count');
  const oldCount = parseInt(countEl.textContent, 10);
  await loadTasksPlain();
  for (const row of document.querySelectorAll('#tasks .task')) {
    const id = row.dataset.id, done = row.classList.contains('done');
    if (knownTasks && !before.has(id)) once(row, 'fx-arrive', 900);
    else if (before.get(id) === false && done) once(row, 'fx-done', 900);
  }
  countUp(countEl, oldCount);
  knownTasks = true;
};

const loadNotesPlain = loadNotes;
let knownNotes = false;
loadNotes = async () => {                                    // new notes slide in
  const before = keysIn('#notes .note');
  const countEl = document.getElementById('notes-count');
  const oldCount = parseInt(countEl.textContent, 10);
  await loadNotesPlain();
  if (knownNotes) for (const row of document.querySelectorAll('#notes .note')) {
    if (!before.has(row.dataset.id)) once(row, 'fx-arrive', 900);
  }
  countUp(countEl, oldCount);
  knownNotes = true;
};

const renderUpNextPlain = renderUpNext;
let wasLive = null;
renderUpNext = () => {                                       // Up next flashes amber as an event starts
  renderUpNextPlain();
  const live = !!document.querySelector('#upnext .when.live');
  if (wasLive === false && live) once(document.getElementById('upnext-panel'), 'fx-flash', 3800);
  wasLive = live;
};

// ---------- Text ----------
const tickPlain = tick;
let lastMinute = null;
tick = () => {                                               // the clock flips as the minute changes
  tickPlain();
  const t = document.getElementById('clock-time');
  if (lastMinute !== null && t.textContent !== lastMinute) once(t, 'fx-flip', 600);
  lastMinute = t.textContent;
};
setInterval(() => tick(), 5000);           // app.js's timer holds the original tick

const startExchangePlain = startExchange;
startExchange = text => { startExchangePlain(text); botEl.classList.add('fx-streaming'); };
const endExchangePlain = endExchange;
endExchange = () => { if (botEl) botEl.classList.remove('fx-streaming'); endExchangePlain(); };

// ---------- The confirmation card: an amber orb and a countdown ring ----------
const CARD_SECONDS = 300;                  // config.CONFIRM_TIMEOUT_SECONDS: the server forgets it then
const ring = document.createElementNS(NS, 'svg');
ring.setAttribute('viewBox', '0 0 34 34');
ring.setAttribute('class', 'fx-countdown');
ring.setAttribute('aria-hidden', 'true');
el('circle', { class: 'fx-track', cx: 17, cy: 17, r: 14 }, ring);
el('circle', { class: 'fx-left', cx: 17, cy: 17, r: 14 }, ring);
confirmEl.prepend(ring);
let expiryTimer = null;
const showConfirmPlain = showConfirm;
showConfirm = c => {
  showConfirmPlain(c);
  document.body.classList.add('fx-awaiting');
  confirmEl.classList.remove('fx-expired');
  confirmEl.querySelector('.warn').textContent = 'CONFIRM ACTION';
  const left = ring.querySelector('.fx-left');
  left.style.setProperty('--secs', CARD_SECONDS + 's');
  left.style.animation = 'none'; void left.offsetWidth; left.style.animation = '';
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(() => {         // say so on the card instead of failing on a click
    confirmEl.classList.add('fx-expired');
    confirmEl.querySelector('.warn').textContent = 'EXPIRED · ASK AGAIN';
    document.body.classList.remove('fx-awaiting');
  }, CARD_SECONDS * 1000);
};
const hideConfirmPlain = hideConfirm;
hideConfirm = () => { clearTimeout(expiryTimer); document.body.classList.remove('fx-awaiting'); hideConfirmPlain(); };

// ---------- Ambient life ----------
document.addEventListener('mousemove', e => {               // panels lean towards the mouse, at most 3 degrees
  const panel = e.target.closest && e.target.closest('.panel:not(.focused)');
  document.querySelectorAll('.panel.fx-tilt').forEach(p => { if (p !== panel) p.classList.remove('fx-tilt'); });
  if (!panel || calm() || seq) return;
  const r = panel.getBoundingClientRect();
  panel.style.setProperty('--ry', (((e.clientX - r.left) / r.width) - 0.5) * 6 + 'deg');
  panel.style.setProperty('--rx', (0.5 - ((e.clientY - r.top) / r.height)) * 6 + 'deg');
  panel.classList.add('fx-tilt');
});

const AMBIENT_AFTER = 3 * 60 * 1000;     // ambient mode after 3 minutes with no mouse or keys
let idleTimer = null;
function wake() {
  document.body.classList.remove('fx-ambient');
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { if (!calm() && !focused) document.body.classList.add('fx-ambient'); }, AMBIENT_AFTER);
}
['mousemove', 'keydown', 'mousedown', 'touchstart'].forEach(ev => document.addEventListener(ev, wake, { passive: true }));
wake();
document.body.classList.add('fx-radar');

// app.js loaded the lists before this file existed. Load them once more through the wrappers,
// so they know what is already there and the first new item after opening the page animates.
loadEvents();
loadTasks();
loadNotes();

// After the boot sequence (or straight away), the panel titles decode in
setTimeout(decodeTitles, document.body.classList.contains('booting') ? 2700 : 200);
