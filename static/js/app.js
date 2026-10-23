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
  if (focused === schedPanel) closeCal();   // NEW
  focused.classList.remove('focused');
  document.body.classList.remove('has-focus');
  focused.querySelector('.hint').textContent = 'EXPAND +';
  focused = null;
}
document.querySelectorAll('.panel').forEach(p => {
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
    youEl.textContent = '\u00a0';
    botEl.textContent = 'New conversation started.';
    tickerEl.textContent = '\u00a0';
    setState('idle');
  } catch (err) {
    botEl.textContent = 'Error: ' + err.message;
  }
  newChatBtn.disabled = false;
  input.focus();
}
newChatBtn.addEventListener('click', newConversation);
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

// ---------- Startup ----------
buildOrb();
loadEvents();
loadTasks();
setVoice(false);
input.focus();
