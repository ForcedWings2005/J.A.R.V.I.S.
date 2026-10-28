// ---------- Spaces (docs/specs/2026-10-27-spaces-and-work.md) ----------
// Home is today's dashboard; every other space is a <section class="space"> that takes the
// place of Home's columns, with JARVIS docked on the right. One page, so the conversation,
// voice and a waiting card carry on. <body data-space="..."> says which one is shown; the
// layout itself is in the CSS. Each space registers itself, the way a tool uses @tool.

const spaces = [];              // { name, title, key, section, enter?, leave? }
let currentSpace = 'home';
const spacesNav = document.getElementById('spaces');

function registerSpace(space) {
  spaces.push(space);
  drawSpaceNames();
}

function drawSpaceNames() {
  spacesNav.textContent = '';
  for (const s of spaces) {
    const b = document.createElement('button');
    b.className = 'space-chip' + (s.name === currentSpace ? ' on' : '');
    b.dataset.space = s.name;
    b.textContent = s.key + ' ' + s.title;
    if (s.name === currentSpace) b.setAttribute('aria-current', 'true');
    b.addEventListener('click', () => switchSpace(s.name));
    spacesNav.appendChild(b);
  }
}

// A space's own code failing must never stop the switch, or Home (spec, When something goes wrong)
function runSafely(space, what) {
  try { if (space[what]) space[what](); } catch (e) { console.error(`space ${space.name}: ${what} failed`, e); }
}

function switchSpace(name, opts = {}) {
  const next = spaces.find(s => s.name === name);
  if (!next || name === currentSpace) return false;
  if (typeof seq !== 'undefined' && seq) return false;   // a panel is still opening (motion.js)
  const old = spaces.find(s => s.name === currentSpace);
  if (currentSpace === 'home' && focused) closeFocus();  // with motion.js this animates closed
  if (old) runSafely(old, 'leave');
  currentSpace = name;
  document.body.dataset.space = name;
  for (const s of spaces) if (s.section) s.section.hidden = s.name !== name;
  drawSpaceNames();
  runSafely(next, 'enter');
  if (!opts.fromAddress) {
    history.pushState(null, '', name === 'home' ? location.pathname + location.search : '#' + name);
  }
  return true;
}

// '#work' -> 'work'; nothing, or a name that is not a space, means Home
function spaceFromAddress() {
  const name = location.hash.slice(1).toLowerCase();
  return spaces.some(s => s.name === name) ? name : 'home';
}

registerSpace({ name: 'home', title: 'HOME', key: '1', section: null });

// Number keys, unless you are typing somewhere or using a shortcut such as Cmd+1
document.addEventListener('keydown', e => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.target.matches('input, textarea')) return;
  const s = spaces.find(x => x.key === e.key);
  if (!s) return;
  e.preventDefault();
  switchSpace(s.name);
});

// The Back button, and an address typed by hand
const followAddress = () => switchSpace(spaceFromAddress(), { fromAddress: true });
window.addEventListener('popstate', followAddress);
window.addEventListener('hashchange', followAddress);

// Every script has run by now, so every space has registered
document.addEventListener('DOMContentLoaded', () => {
  if (location.hash && spaceFromAddress() === 'home') {
    history.replaceState(null, '', location.pathname + location.search);   // '#gym': Home
  }
  followAddress();
});
