// ---------- Calendar ----------
const WEEK_START = 0;      // 0 = Sunday, 1 = Monday
const HOUR_PX = 48;        // height of one hour in the week/day views
const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const DOWS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const REPEAT_LABEL = { daily:'daily', weekdays:'weekdays', weekly:'weekly', biweekly:'every 2 weeks', monthly:'monthly' };

const schedPanel = document.getElementById('sched-panel');
// One calendar, drawn into cal.box: Home's Schedule panel or the Work space. Only one space
// shows at a time, so it never needs to be in both (spaces stage 2)
const cal = { open: false, view: 'year', anchor: new Date(), fresh: true, box: null };
let calToken = 0;
let calBody = null;

// --- small helpers ---
function h(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function iso(d) { return d.toLocaleDateString('en-CA'); }
function parseISO(s) { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }
function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
function startOfWeek(d) { return addDays(d, -((d.getDay() - WEEK_START + 7) % 7)); }
function mins(t) { const [H, M] = t.split(':').map(Number); return H * 60 + M; }
function fmtTime(t) {
  const [H, M] = t.split(':').map(Number);
  return (H % 12 || 12) + (M ? ':' + String(M).padStart(2, '0') : '') + ' ' + (H >= 12 ? 'PM' : 'AM');
}
function fmtRange(ev) {
  return ev.end_time ? fmtTime(ev.time) + ' \u2013 ' + fmtTime(ev.end_time) : fmtTime(ev.time);
}
function metaLine(ev) {
    return fmtRange(ev) + (ev.repeat !== 'none' ? '  \u21bb ' + ev.repeat_label : '');
}
async function fetchEvents(a, b) {
  const res = await fetch('/calendar?start=' + iso(a) + '&end=' + iso(b));
  if (!res.ok) throw new Error('calendar ' + res.status);
  return (await res.json()).events;
}
function groupByDate(events) {
  const map = {};
  for (const ev of events) (map[ev.date] ||= []).push(ev);
  return map;
}

// --- up next: the event happening now, or the next one ---
let upcoming = [];         // the last 7 days of events loaded, for recomputing the countdown

function startOf(ev) { const d = parseISO(ev.date); d.setMinutes(mins(ev.time)); return d; }
function endOf(ev) {
  const d = parseISO(ev.date);
  d.setMinutes(ev.end_time ? mins(ev.end_time) : mins(ev.time) + 60);
  return d;
}
function inWords(minutes) {
  if (minutes < 1) return 'now';
  if (minutes < 60) return 'in ' + minutes + ' min';
  const hrs = Math.floor(minutes / 60), rest = minutes % 60;
  return 'in ' + hrs + ' h' + (rest ? ' ' + rest + ' min' : '');
}
function dayWord(d, now) {
  const days = Math.round((parseISO(iso(d)) - parseISO(iso(now))) / 86400000);
  return days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : DOWS[d.getDay()];
}
function renderUpNext() {
  const box = document.getElementById('upnext');
  const now = new Date();
  const next = upcoming.filter(ev => endOf(ev) > now).sort((a, b) => startOf(a) - startOf(b));
  const inEl = document.getElementById('upnext-in');
  box.innerHTML = '';
  if (!next.length) {
    inEl.textContent = '';
    box.appendChild(h('div', 'muted', 'Nothing in the next 7 days'));
    return;
  }
  const ev = next[0], start = startOf(ev), end = endOf(ev), live = start <= now;
  inEl.textContent = live ? 'NOW' : inWords(Math.round((start - now) / 60000)).toUpperCase();
  const card = h('div', 'next');
  card.appendChild(h('div', 'when' + (live ? ' live' : ''),
    (live ? 'NOW' : dayWord(start, now).toUpperCase()) + ' \u00b7 ' + fmtRange(ev)));
  card.appendChild(h('div', 'what', ev.title));
  if (live) {                            // how far through it we are
    const bar = h('div', 'progress'), fill = h('i');
    fill.style.width = Math.min(100, Math.round((now - start) / (end - start) * 100)) + '%';
    bar.appendChild(fill);
    card.appendChild(bar);
  }
  box.appendChild(card);
  if (next[1]) {
    const then = startOf(next[1]);
    box.appendChild(h('div', 'nthen', 'Then: ' + next[1].title + ', ' +
      (dayWord(then, now) === 'Today' ? '' : dayWord(then, now) + ' ') + fmtTime(next[1].time)));
  }
}
// --- today's timeline, across the top of the page ---
function renderTimeline() {
  const box = document.getElementById('timeline');
  const now = new Date(), today = iso(now);
  const evs = upcoming.filter(ev => ev.date === today);
  const hourOf = d => d.getHours() + d.getMinutes() / 60;
  // 07:00 to 23:00, widened to fit any event outside it
  let first = 7, last = 23;
  for (const ev of evs) {
    first = Math.min(first, Math.floor(hourOf(startOf(ev))));
    last = Math.max(last, Math.ceil(hourOf(endOf(ev)) || 24));
  }
  const pos = hrs => ((hrs - first) / (last - first) * 100) + '%';
  box.innerHTML = '';
  for (let hr = first; hr <= last; hr += 2) {
    const mark = h('div', 'hour', String(hr % 24).padStart(2, '0') + ':00');
    mark.style.left = pos(hr);
    box.appendChild(mark);
  }
  for (const ev of evs) {
    const a = hourOf(startOf(ev)), b = endOf(ev).getDate() !== startOf(ev).getDate() ? 24 : hourOf(endOf(ev));
    const state = endOf(ev) <= now ? ' past' : startOf(ev) <= now ? ' live' : '';
    const bar = h('div', 'ev' + state, ev.title);
    bar.title = ev.title + ', ' + fmtRange(ev);
    bar.dataset.key = ev.id + '|' + ev.date;
    bar.style.left = pos(a);
    bar.style.width = 'calc(' + pos(b) + ' - ' + pos(a) + ')';
    box.appendChild(bar);
  }
  if (!evs.length) box.appendChild(h('div', 'tempty', 'Nothing on the calendar today'));
  const nowLine = h('div', 'now');
  nowLine.style.left = pos(Math.min(Math.max(hourOf(now), first), last));
  box.appendChild(nowLine);
}

// Marks the schedule's cards as over, happening now, or next
function markSchedule() {
  const now = new Date();
  let nextFound = false;
  for (const card of document.querySelectorAll('#sched .evc')) {
    const start = new Date(+card.dataset.start), end = new Date(+card.dataset.end);
    const state = end <= now ? 'past' : start <= now ? 'live' : nextFound ? '' : 'next';
    if (state === 'next') nextFound = true;        // an event happening now is not 'next'
    card.classList.toggle('past', state === 'past');
    card.classList.toggle('live', state === 'live');
    card.classList.toggle('next', state === 'next');
  }
}
setInterval(() => { renderUpNext(); markSchedule(); renderTimeline(); }, 30000);

// --- compact view: the next 7 days ---
async function loadEvents() {
  const box = document.getElementById('sched');
  const today = new Date();
  let evs;
  try { evs = await fetchEvents(today, addDays(today, 6)); }
  catch (e) { box.textContent = 'Could not load the schedule.'; return; }
  upcoming = evs;
  renderUpNext();
  renderTimeline();
  const map = groupByDate(evs);
  box.innerHTML = '';
  for (let i = 0; i < 7; i++) {
    const d = addDays(today, i);
    const label = i === 0 ? 'TODAY' : i === 1 ? 'TOMORROW' : DOWS[d.getDay()].toUpperCase();
    box.appendChild(h('div', 'sday', label + ' \u00b7 ' + MONTHS[d.getMonth()].slice(0, 3) + ' ' + d.getDate()));
    const list = map[iso(d)] || [];
    if (!list.length) box.appendChild(h('div', 'sempty', 'Nothing scheduled'));
    for (const ev of list) {
      const card = h('div', 'evc');
      card.dataset.key = ev.id + '|' + ev.date;     // lets motion.js spot new and removed events
      card.dataset.start = +startOf(ev);
      card.dataset.end = +endOf(ev);
      card.appendChild(h('div', 'et', ev.title));
      card.appendChild(h('div', 'em', metaLine(ev)));
      box.appendChild(card);
    }
  }
  markSchedule();
  if (cal.open) renderCal();
}

// --- expanded view ---
function rangeFor(view, a) {
  if (view === 'year') return [new Date(a.getFullYear(), 0, 1), new Date(a.getFullYear(), 11, 31)];
  if (view === 'month') {
    const first = new Date(a.getFullYear(), a.getMonth(), 1);
    const last = new Date(a.getFullYear(), a.getMonth() + 1, 0);
    return [startOfWeek(first), addDays(startOfWeek(last), 6)];
  }
  if (view === 'week') { const s = startOfWeek(a); return [s, addDays(s, 6)]; }
  return [a, a];
}

function titleFor() {
  const a = cal.anchor;
  if (cal.view === 'year') return String(a.getFullYear());
  if (cal.view === 'month') return MONTHS[a.getMonth()] + ' ' + a.getFullYear();
  if (cal.view === 'week') {
    const s = startOfWeek(a), e = addDays(s, 6);
    return MONTHS[s.getMonth()].slice(0, 3) + ' ' + s.getDate() + ' \u2013 ' +
           MONTHS[e.getMonth()].slice(0, 3) + ' ' + e.getDate() + ', ' + e.getFullYear();
  }
  return DOWS[a.getDay()] + ', ' + MONTHS[a.getMonth()] + ' ' + a.getDate() + ', ' + a.getFullYear();
}

function zoomTo(view, date) {
  cal.view = view;
  cal.anchor = date;
  cal.fresh = true;
  renderCal();
}

function shift(dir) {
  const a = cal.anchor;
  if (cal.view === 'year') cal.anchor = new Date(a.getFullYear() + dir, 0, 1);
  else if (cal.view === 'month') cal.anchor = new Date(a.getFullYear(), a.getMonth() + dir, 1);
  else if (cal.view === 'week') cal.anchor = addDays(a, 7 * dir);
  else cal.anchor = addDays(a, dir);
  renderCal();
}

function buildToolbar() {
  const bar = h('div', 'ctool');
  const prev = h('button', 'cbtn', '\u2039');
  prev.onclick = () => shift(-1);
  const today = h('button', 'cbtn', 'Today');
  today.onclick = () => zoomTo(cal.view, new Date());
  const next = h('button', 'cbtn', '\u203a');
  next.onclick = () => shift(1);
  bar.append(prev, today, next, h('div', 'ctitle', titleFor()));
  const tabs = h('div', 'tabs');
  for (const v of ['year', 'month', 'week', 'day']) {
    const b = h('button', 'cbtn' + (v === cal.view ? ' on' : ''), v[0].toUpperCase() + v.slice(1));
    b.onclick = () => zoomTo(v, cal.anchor);
    tabs.appendChild(b);
  }
  bar.appendChild(tabs);
  return bar;
}

async function renderCal() {
  const token = ++calToken;
  const [from, to] = rangeFor(cal.view, cal.anchor);
  let evs;
  try { evs = await fetchEvents(from, to); }
  catch (e) { if (cal.box) cal.box.textContent = 'Could not load the calendar.'; return; }
  if (token !== calToken || !cal.open) return;     // a newer render or a close won

  const prevScroll = calBody ? calBody.scrollTop : 0;
  cal.box.innerHTML = '';
  cal.box.appendChild(buildToolbar());
  calBody = h('div', 'cbody');
  cal.box.appendChild(calBody);

  const map = groupByDate(evs);
  if (cal.view === 'year') drawYear(calBody, map);
  else if (cal.view === 'month') drawMonth(calBody, map);
  else if (cal.view === 'week') {
    const s = startOfWeek(cal.anchor);
    drawTimeGrid(calBody, [0, 1, 2, 3, 4, 5, 6].map(i => addDays(s, i)), map);
  } else drawTimeGrid(calBody, [cal.anchor], map);

  const grid = cal.view === 'week' || cal.view === 'day';
  calBody.scrollTop = cal.fresh ? (grid ? 7 * HOUR_PX : 0) : prevScroll;
  cal.fresh = false;
}

function drawYear(box, map) {
  const y = cal.anchor.getFullYear();
  const todayKey = iso(new Date());
  const grid = h('div', 'ygrid');
  for (let m = 0; m < 12; m++) {
    const card = h('div', 'ymonth');
    const title = h('button', 'ym-title', MONTHS[m].toUpperCase());
    title.onclick = () => zoomTo('month', new Date(y, m, 1));
    card.appendChild(title);
    const g = h('div', 'ym-grid');
    for (let i = 0; i < 7; i++) g.appendChild(h('div', 'dow', DOWS[(i + WEEK_START) % 7][0]));
    const lead = (new Date(y, m, 1).getDay() - WEEK_START + 7) % 7;
    for (let i = 0; i < lead; i++) g.appendChild(h('div', 'yd out'));
    const count = new Date(y, m + 1, 0).getDate();
    for (let d = 1; d <= count; d++) {
      const key = iso(new Date(y, m, d));
      const cell = h('div', 'yd' + (key === todayKey ? ' today' : ''), String(d));
      const n = (map[key] || []).length;
      if (n) cell.style.background = 'rgba(76,201,240,' + (0.18 + Math.min(n, 4) * 0.14) + ')';
      cell.onclick = () => zoomTo('month', new Date(y, m, 1));
      g.appendChild(cell);
    }
    card.appendChild(g);
    grid.appendChild(card);
  }
  box.appendChild(grid);
}

function drawMonth(box, map) {
  const month = cal.anchor.getMonth();
  const [from, to] = rangeFor('month', cal.anchor);
  const todayKey = iso(new Date());
  const dow = h('div', 'mdow');
  for (let i = 0; i < 7; i++) dow.appendChild(h('div', null, DOWS[(i + WEEK_START) % 7].toUpperCase()));
  box.appendChild(dow);
  const grid = h('div', 'mgrid');
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const day = d;
    const key = iso(day);
    const cell = h('div', 'mcell' + (day.getMonth() !== month ? ' out' : '') + (key === todayKey ? ' today' : ''));
    cell.appendChild(h('span', 'num', String(day.getDate())));
    const list = map[key] || [];
    for (const ev of list.slice(0, 3)) cell.appendChild(h('div', 'chip', fmtTime(ev.time) + ' ' + ev.title));
    if (list.length > 3) cell.appendChild(h('div', 'more', '+' + (list.length - 3) + ' more'));
    cell.onclick = () => zoomTo('week', day);
    grid.appendChild(cell);
  }
  box.appendChild(grid);
}

// Put overlapping events side by side instead of on top of each other
function layoutDay(evs) {
  const items = evs.map(ev => {
    const s = mins(ev.time);
    const e = ev.end_time ? mins(ev.end_time) : s + 60;
    return { ev, s, e: Math.max(e, s + 20) };
  }).sort((a, b) => a.s - b.s || a.e - b.e);
  let cluster = [], clusterEnd = 0, colEnds = [];
  const flush = () => {
    cluster.forEach(it => { it.cols = colEnds.length; });
    cluster = []; colEnds = []; clusterEnd = 0;
  };
  for (const it of items) {
    if (cluster.length && it.s >= clusterEnd) flush();
    let c = colEnds.findIndex(end => end <= it.s);
    if (c === -1) { c = colEnds.length; colEnds.push(it.e); } else colEnds[c] = it.e;
    it.col = c;
    cluster.push(it);
    clusterEnd = Math.max(clusterEnd, it.e);
  }
  flush();
  return items;
}

function drawTimeGrid(box, days, map) {
  const todayKey = iso(new Date());
  const wrap = h('div', 'tg');
  wrap.style.gridTemplateColumns = '56px repeat(' + days.length + ', minmax(0, 1fr))';

  wrap.appendChild(h('div', 'tgh'));
  for (const d of days) {
    const head = h('button', 'tgh' + (iso(d) === todayKey ? ' today' : ''), DOWS[d.getDay()] + ' ' + d.getDate());
    if (days.length > 1) head.onclick = () => zoomTo('day', d);
    wrap.appendChild(head);
  }

  const gutter = h('div', 'gutter');
  gutter.style.height = (24 * HOUR_PX) + 'px';
  for (let hr = 1; hr < 24; hr++) {
    const lab = h('span', null, fmtTime(String(hr).padStart(2, '0') + ':00'));
    lab.style.top = (hr * HOUR_PX - 7) + 'px';
    gutter.appendChild(lab);
  }
  wrap.appendChild(gutter);

  for (const d of days) {
    const key = iso(d);
    const col = h('div', 'dcol');
    col.style.height = (24 * HOUR_PX) + 'px';
    col.style.backgroundSize = '100% ' + HOUR_PX + 'px';
    for (const it of layoutDay(map[key] || [])) {
      const blk = h('div', 'tev');
      const top = it.s / 60 * HOUR_PX;
      const height = (it.e - it.s) / 60 * HOUR_PX - 2;
      blk.style.cssText = 'top:' + top + 'px;height:' + height + 'px;left:' + (100 * it.col / it.cols) + '%;width:' + (100 / it.cols) + '%';
      blk.appendChild(h('div', null, it.ev.title + (it.ev.repeat !== 'none' ? ' \u21bb' : '')));
      if (height >= 38) blk.appendChild(h('div', 'tm', fmtRange(it.ev)));
      col.appendChild(blk);
    }
    if (key === todayKey) {
      const now = new Date();
      const line = h('div', 'nowline');
      line.style.top = ((now.getHours() * 60 + now.getMinutes()) / 60 * HOUR_PX) + 'px';
      col.appendChild(line);
    }
    wrap.appendChild(col);
  }
  box.appendChild(wrap);
}

function openCal(box = document.getElementById('cal'), view = 'year') {
  if (cal.box && cal.box !== box) cal.box.innerHTML = '';
  cal.box = box;
  cal.open = true;
  cal.view = view;
  cal.anchor = new Date();
  cal.fresh = true;
  renderCal();
}
// Closes the calendar only if it is still in `box`. Home's Schedule panel closes with an
// animation, so its close can arrive after the calendar has moved to Work: it must then
// leave Work's calendar alone (review of stage 2)
function closeCal(box = cal.box) {
  if (!box || box !== cal.box) return;
  cal.open = false;
  calBody = null;
  if (cal.box) cal.box.innerHTML = '';
  cal.box = null;
}

