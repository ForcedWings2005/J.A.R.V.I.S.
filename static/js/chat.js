// ---------- Shared elements and state ----------
const statusEl = document.getElementById('status');
function setState(name) {
  document.body.dataset.state = name;
  statusEl.textContent = name === 'idle' ? 'STANDING BY' : name.toUpperCase();
}

const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const youEl = document.getElementById('you');
const botEl = document.getElementById('bot');
const tickerEl = document.getElementById('ticker');
const confirmEl = document.getElementById('confirm');
const confirmText = document.getElementById('confirm-text');
let pendingId = null;

// ---------- Ticker and confirmation ----------
function showSteps(steps) {
  tickerEl.textContent = '';
  if (steps.length === 0) { tickerEl.textContent = '\u00a0'; return; }
  for (const s of steps) {
    const span = document.createElement('span');
    span.className = 'step ' + s.status;
    span.textContent = s.text;
    tickerEl.appendChild(span);
  }
}

function showConfirm(c) {
  pendingId = c.id;
  confirmText.textContent = c.text;
  confirmEl.classList.add('show');
  document.getElementById('ok').focus();
}

function hideConfirm() {
  pendingId = null;
  confirmEl.classList.remove('show');
}

// ---------- Chat ----------
async function send(spoken) {
  const text = (typeof spoken === 'string' ? spoken : input.value).trim();
  if (!text) return;
  if (typeof spoken !== 'string') input.value = '';
  stopSpeaking();
  hideConfirm();
  youEl.textContent = text;
  botEl.textContent = '';
  tickerEl.textContent = 'working...';
  setState('thinking');
  sendBtn.disabled = true;

  const speaker = createSpeaker();
  const steps = [];
  let full = '';        // everything shown on screen
  let buf = '';         // text not yet sent to speech
  let confirm = null;

  const feed = (flush) => {
    const t = takeSentences(buf, flush);
    buf = t.rest;
    t.sentences.forEach(s => speaker.push(s));
  };

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    });
    if (!res.ok || !res.body) throw new Error('Server error ' + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = pending.indexOf('\n')) >= 0) {
        const line = pending.slice(0, nl).trim();
        pending = pending.slice(nl + 1);
        if (!line) continue;
        const msg = JSON.parse(line);
        if (msg.type === 'delta') {
          full += msg.text;
          buf += msg.text;
          botEl.textContent = full;
          feed(false);
        } else if (msg.type === 'step') {
          steps.push(msg.step);
          showSteps(steps);
        } else if (msg.type === 'break') {
          feed(true);
          if (full) full += ' ';
        } else if (msg.type === 'done') {
          confirm = msg.confirm;
          showSteps(msg.steps);
        } else if (msg.type === 'error') {
          throw new Error(msg.text);
        }
      }
    }
    feed(true);
    speaker.end();
    if (confirm) showConfirm(confirm);
  } catch (err) {
    stopSpeaking();
    botEl.textContent = full ? full + ' [Error: ' + err.message + ']' : 'Error: ' + err.message;
    tickerEl.textContent = '\u00a0';
    setState('idle');
  }
  sendBtn.disabled = false;
  if (!pendingId) input.focus();
  loadEvents();
  loadTasks();
}

async function resolveAction(approve) {
  if (!pendingId) return;
  const id = pendingId;
  hideConfirm();
  try {
    const res = await fetch('/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id, approve: approve })
    });
    if (!res.ok) throw new Error('Server error ' + res.status);
    const data = await res.json();
    botEl.textContent = data.reply;
    speak(data.reply).catch(() => {});
  } catch (err) {
    botEl.textContent = 'Error: ' + err.message;
  }
  input.focus();
  loadEvents();
}

