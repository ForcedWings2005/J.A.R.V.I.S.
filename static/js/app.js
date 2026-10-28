// ---------- Panel focus ----------
let focused = null;
function focusPanel(p) {
  if (focused) return;
  focused = p;
  p.classList.add('focused');
  document.body.classList.add('has-focus');
  p.querySelector('.hint').textContent = 'ESC TO CLOSE';
  if (p === schedPanel) openCal();          // NEW
}
function closeFocus() {
  if (!focused) return;
  if (focused === schedPanel) closeCal(document.getElementById('cal'));   // only Home's calendar
  focused.classList.remove('focused');
  document.body.classList.remove('has-focus');
  focused.querySelector('.hint').textContent = 'EXPAND +';
  focused = null;
}
// Only panels with an EXPAND label can expand: clicking Up next used to fail and leave the
// page dimmed (CHANGELOG section 40)
document.querySelectorAll('.panel').forEach(p => {
  if (!p.querySelector('.hint')) return;
  p.addEventListener('click', () => focusPanel(p));
  p.addEventListener('keydown', e => { if (e.key === 'Enter') focusPanel(p); });
});
document.getElementById('scrim').addEventListener('click', closeFocus);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFocus(); });

// ---------- Reduce motion ----------
const motionBtn = document.getElementById('motion');
function setReduce(on) {
  document.body.classList.toggle('reduce', on);
  motionBtn.setAttribute('aria-checked', String(on));
  try { localStorage.setItem('reduceMotion', on ? '1' : '0'); } catch (e) {}
}
let saved = null;
try { saved = localStorage.getItem('reduceMotion'); } catch (e) {}
setReduce(saved === '1');
motionBtn.addEventListener('click', () => setReduce(!document.body.classList.contains('reduce')));

// ---------- Event listeners ----------
document.getElementById('ok').addEventListener('click', () => resolveAction(true));
document.getElementById('cancel').addEventListener('click', () => resolveAction(false));

voiceBtn.addEventListener('click', () => {
  if (!voiceOn) unlockAudio();
  setVoice(!voiceOn);
});

micBtn.addEventListener('pointerdown', e => {
  e.preventDefault();
  unlockAudio();
  if (latched) { stopRecording(); return; }
  pointerDown = true;
  pressStart = Date.now();
  startRecording();
});
micBtn.addEventListener('pointerup', () => {
  if (!pointerDown) return;
  pointerDown = false;
  if (!holding) return;
  if (Date.now() - pressStart < 400) latched = true;
  else stopRecording();
});
const abortHold = () => {
  if (pointerDown && !latched) { pointerDown = false; stopRecording(); }
};
micBtn.addEventListener('pointerleave', abortHold);
micBtn.addEventListener('pointercancel', abortHold);

document.addEventListener('keydown', e => {
  if (!voiceOn || e.code !== 'Space' || e.repeat) return;
  const t = e.target;
  const typing = t.tagName === 'INPUT' && t.value !== '';
  if (typing || t.tagName === 'BUTTON' || t.tagName === 'TEXTAREA') return;
  e.preventDefault();
  startRecording();
});
document.addEventListener('keyup', e => { if (e.code === 'Space') stopRecording(); });

sendBtn.addEventListener('click', send);

// ---------- New conversation ----------
// Asks the server to forget the conversation and any waiting confirmation.
const newChatBtn = document.getElementById('newchat');
async function newConversation() {
  if (sendBtn.disabled) return;           // a reply is still coming in
  stopSpeaking();
  hideConfirm();
  newChatBtn.disabled = true;
  try {
    const res = await fetch('/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}'
    });
    if (!res.ok) throw new Error('Server error ' + res.status);
    transcriptEl.innerHTML = '';
    document.body.classList.remove('chatting');
    say('New conversation started.');
    tickerEl.textContent = '';
    setState('idle');
  } catch (err) {
    say('Error: ' + err.message);
  }
  newChatBtn.disabled = false;
  input.focus();
}
newChatBtn.addEventListener('click', newConversation);
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

// ---------- Clock ----------
function tick() {
  const d = new Date();
  document.getElementById('clock-time').textContent =
    String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
  document.getElementById('clock-date').textContent =
    d.toLocaleDateString('en-GB', { weekday: 'long' }).toUpperCase() + ' \u00b7 ' +
    d.getDate() + ' ' + d.toLocaleDateString('en-GB', { month: 'long' }).toUpperCase();
}

// ---------- Status readouts: model, Ollama, last backup ----------
function backupWords(stamp) {
  if (!stamp) return { text: 'NONE', warn: true };
  const [day, time] = stamp.split(' ');
  const [y, m, dd] = day.split('-').map(Number);
  const now = new Date();
  const days = Math.round((new Date(now.getFullYear(), now.getMonth(), now.getDate()) - new Date(y, m - 1, dd)) / 86400000);
  if (days <= 0) return { text: time + ' \u2713', warn: false };
  if (days === 1) return { text: 'YESTERDAY ' + time, warn: false };
  return { text: days + ' DAYS AGO', warn: true };
}
async function loadInfo() {
  const dot = document.getElementById('ollama-dot');
  try {
    const info = await (await fetch('/info')).json();
    document.getElementById('model-name').textContent = info.model;
    dot.className = 'dot ' + (info.ollama ? 'ok' : 'bad');
    document.getElementById('model-chip').title = info.ollama ? 'Ollama is answering' : 'Ollama is not answering: start it, then try again';
    const b = backupWords(info.last_backup);
    document.getElementById('backup-time').textContent = b.text;
    document.getElementById('backup-chip').classList.toggle('warn', b.warn);
    document.getElementById('backup-chip').title = info.last_backup ? 'Last backup: ' + info.last_backup : 'No backup found';
    document.getElementById('boot-model').textContent = info.ollama ? 'ONLINE' : 'NOT ANSWERING';
  } catch (e) {
    dot.className = 'dot bad';
    document.getElementById('model-name').textContent = '?';
  }
}

// ---------- Boot sequence: once per browser session, never with Reduce motion ----------
function bootOnce() {
  let seen = false;
  try { seen = sessionStorage.getItem('jarvisBooted') === '1'; sessionStorage.setItem('jarvisBooted', '1'); } catch (e) {}
  const reduced = document.body.classList.contains('reduce') ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (seen || reduced) return;
  const hour = new Date().getHours();
  document.getElementById('boot-greeting').textContent =
    '> GOOD ' + (hour < 12 ? 'MORNING' : hour < 18 ? 'AFTERNOON' : 'EVENING') + ', SIR.';
  const boot = document.getElementById('boot');
  boot.hidden = false;
  document.body.classList.add('booting');
  setTimeout(() => { boot.hidden = true; document.body.classList.remove('booting'); }, 3200);
}

// "/" jumps to the command box, unless you are already typing somewhere
document.addEventListener('keydown', e => {
  if (e.key !== '/' || e.target.matches('input, textarea')) return;
  e.preventDefault();
  input.focus();
});

// ---------- Startup ----------
bootOnce();
buildOrb();
tick();
setInterval(tick, 10000);
loadInfo();
setInterval(loadInfo, 60000);
loadEvents();
loadTasks();
loadNotes();
setVoice(false);
input.focus();
