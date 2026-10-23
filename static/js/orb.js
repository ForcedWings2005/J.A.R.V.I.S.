// ---------- Orb ----------
const NS = 'http://www.w3.org/2000/svg';
let seed = 7;
function rand() { seed = (seed * 16807) % 2147483647; return seed / 2147483647; }
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  parent.appendChild(e);
  return e;
}

function buildOrb() {
  const svg = document.getElementById('orb');
  const c = 230;
  const rings = el('g', { class: 'spin-slow' }, svg);
  const rdefs = [[215,1,.45,'2 6'],[200,3,.5,'60 14 6 20'],[180,1.5,.6,'120 30 8 8'],[160,5,.55,'150 60 40 90'],[138,1,.5,'4 4'],[118,3,.6,'90 40 30 60'],[92,2,.7,'70 30 140 20'],[66,1.5,.7,'30 12']];
  for (const [r, w, o, dash] of rdefs) {
    el('circle', { cx:c, cy:c, r:r, fill:'none', stroke:'currentColor', 'stroke-width':w, opacity:o, 'stroke-dasharray':dash }, rings);
  }
  const streaks = el('g', { class: 'spin-rev' }, svg);
  for (let i = 0; i < 260; i++) {
    const a = rand() * Math.PI * 2;
    const r = 95 + rand() * 123;
    const len = 3 + rand() * 13;
    const x1 = c + r * Math.cos(a), y1 = c + r * Math.sin(a);
    let x2, y2;
    if (rand() < 0.6) { x2 = c + (r + len) * Math.cos(a); y2 = c + (r + len) * Math.sin(a); }
    else { x2 = c + r * Math.cos(a + len / r); y2 = c + r * Math.sin(a + len / r); }
    el('line', { x1:x1, y1:y1, x2:x2, y2:y2, stroke:'currentColor', 'stroke-width':1 + rand() * 1.5, opacity:0.3 + rand() * 0.65 }, streaks);
  }
  const frags = el('g', { class: 'spin-slow' }, svg);
  for (let i = 0; i < 70; i++) {
    const a = rand() * Math.PI * 2;
    const r = 60 + rand() * 140;
    const x = c + r * Math.cos(a), y = c + r * Math.sin(a);
    const d = 'M' + x + ' ' + y + 'h' + (6 + rand() * 14) + 'v' + (4 + rand() * 8) + 'h' + (-3 - rand() * 7);
    el('path', { d:d, fill:'none', stroke:'currentColor', 'stroke-width':1, opacity:0.35 + rand() * 0.45 }, frags);
  }
  const arms = el('g', { class: 'spin-rev' }, svg);
  el('path', { d:'M105 335A140 140 0 0 1 150 120', fill:'none', stroke:'currentColor', 'stroke-width':8, opacity:.45 }, arms);
  el('path', { d:'M150 120C260 90 330 190 260 250C220 285 175 250 200 215', fill:'none', stroke:'currentColor', 'stroke-width':4, opacity:.85 }, arms);
  const core = el('g', { class: 'core' }, svg);
  el('circle', { cx:c, cy:c, r:26, fill:'currentColor', 'fill-opacity':.15, stroke:'currentColor', 'stroke-width':3 }, core);
  el('circle', { cx:c, cy:c, r:15, fill:'none', stroke:'currentColor', 'stroke-width':2 }, core);
  el('circle', { cx:c, cy:c, r:6, fill:'currentColor' }, core);
}

