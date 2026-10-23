// ---------- Voice out (spoken replies) ----------
const voiceBtn = document.getElementById('voice');
let voiceOn = false;

// Tiny silent WAV, played once on a user click to unlock audio playback
const SILENCE = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
function unlockAudio() {
  const a = new Audio(SILENCE);
  a.play().catch(() => {});
}

let cancelPlayback = null;
let speakToken = 0;

function stopSpeaking() {
  speakToken++;                       // invalidates every queued sentence
  if (cancelPlayback) cancelPlayback();
  if (document.body.dataset.state === 'speaking') setState('idle');
}

async function fetchSpeech(text) {
  const res = await fetch('/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text })
  });
  if (!res.ok) throw new Error('Speech error ' + res.status);
  return res.blob();
}

function playBlob(blob, token) {
  return new Promise(resolve => {
    if (token !== speakToken) { resolve(); return; }
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    const done = () => {
      audio.pause();
      URL.revokeObjectURL(url);
      if (cancelPlayback === done) cancelPlayback = null;
      resolve();
    };
    cancelPlayback = done;
    audio.onplay = () => { if (token === speakToken) setState('speaking'); };
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(done);
  });
}

// Words that end in a period but do not end a sentence
const ABBREV = /\b(?:Mr|Mrs|Ms|Dr|St|vs|etc|a\.m|p\.m|e\.g|i\.e)\.$/i;

function takeSentences(buf, flush) {
  const out = [];
  let start = 0;
  const re = /[.!?]+["')\]]*\s+|\n+/g;
  let m;
  while ((m = re.exec(buf)) !== null) {
    const end = m.index + m[0].length;
    const piece = buf.slice(start, end).trim();
    if (ABBREV.test(piece)) continue;
    if (piece.length < 12) continue;
    out.push(piece);
    start = end;
  }
  let rest = buf.slice(start);
  if (flush && rest.trim()) { out.push(rest.trim()); rest = ''; }
  return { sentences: out, rest: rest };
}

function createSpeaker() {
  stopSpeaking();
  const token = speakToken;
  const queue = [];        // promises of audio, in speaking order
  let finished = false;    // no more text is coming
  let running = false;

  function settle() {
    if (token === speakToken && finished && !running && !queue.length) setState('idle');
  }

  async function run() {
    if (running) return;
    running = true;
    while (token === speakToken && queue.length) {
      let blob;
      try { blob = await queue.shift(); }
      catch (err) { tickerEl.textContent = 'voice error: ' + err.message; continue; }
      if (token !== speakToken) break;
      await playBlob(blob, token);
    }
    running = false;
    settle();
  }

  return {
    push(text) {
      text = text.trim();
      if (!voiceOn || !text || token !== speakToken) return;
      const p = fetchSpeech(text);
      p.catch(() => {});   // real handling happens in run()
      queue.push(p);
      run();
    },
    end() { finished = true; settle(); }
  };
}

// Speak a whole piece of text (used for confirmation results)
function speak(text) {
  const s = createSpeaker();
  s.push(text);
  s.end();
  return Promise.resolve(true);
}

// ---------- Voice in (microphone) ----------
const micBtn = document.getElementById('mic');
const micState = document.getElementById('mic-state');
const hintEl = document.getElementById('hint');
const MAX_RECORD_MS = 30000;
let stream = null;
let recorder = null;
let chunks = [];
let holding = false;
let latched = false;
let discard = false;
let pointerDown = false;
let recStart = 0;
let pressStart = 0;
let latchTimer = null;

function releaseMic() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
}

async function startRecording() {
  if (!voiceOn || holding || recorder || sendBtn.disabled) return;
  stopSpeaking();
  holding = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    holding = false;
    say('Microphone unavailable: ' + err.message);
    return;
  }
  if (!holding || !voiceOn) { holding = false; releaseMic(); return; }
  chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  recorder.onstop = finishRecording;
  recorder.start();
  recStart = Date.now();
  latchTimer = setTimeout(stopRecording, MAX_RECORD_MS);
  micBtn.classList.add('live');
  micState.textContent = 'LIVE';
  setState('listening');
}

function stopRecording() {
  holding = false;
  latched = false;
  clearTimeout(latchTimer);
  if (recorder && recorder.state === 'recording') recorder.stop();
}

function cancelRecording() {
  holding = false;
  latched = false;
  clearTimeout(latchTimer);
  if (recorder && recorder.state === 'recording') {
    discard = true;
    recorder.stop();
  } else {
    releaseMic();
  }
}

async function finishRecording() {
  const type = recorder.mimeType || 'audio/webm';
  const tooShort = Date.now() - recStart < 500;
  const dropped = discard;
  discard = false;
  recorder = null;
  holding = false;
  latched = false;
  clearTimeout(latchTimer);
  releaseMic();
  micBtn.classList.remove('live');
  micState.textContent = voiceOn ? 'READY' : 'OFF';
  if (dropped || tooShort) { setState('idle'); return; }

  const form = new FormData();
  form.append('file', new Blob(chunks, { type: type }), type.includes('mp4') ? 'speech.mp4' : 'speech.webm');
  startExchange('...');
  tickerEl.textContent = 'transcribing...';
  setState('thinking');
  try {
    const res = await fetch('/transcribe', { method: 'POST', body: form });
    if (!res.ok) throw new Error('Server error ' + res.status);
    const data = await res.json();
    if (!data.text) {
      youEl.textContent = '(nothing heard)';
      botEl.textContent = "I didn't catch that.";
      endExchange();
      tickerEl.textContent = '\u00a0';
      setState('idle');
      return;
    }
    await send(data.text);
  } catch (err) {
    botEl.textContent = 'Error: ' + err.message;
    endExchange();
    tickerEl.textContent = '\u00a0';
    setState('idle');
  }
}

// ---------- Voice mode master switch ----------
function setVoice(on) {
  voiceOn = on;
  voiceBtn.setAttribute('aria-checked', String(on));
  micBtn.disabled = !on;
  micState.textContent = on ? 'READY' : 'OFF';
  hintEl.textContent = on
    ? 'HOLD THE MIC OR SPACE TO TALK, OR TAP THE MIC TO START AND TAP AGAIN TO STOP'
    : 'VOICE MODE IS OFF - SWITCH IT ON TO USE THE MIC AND SPOKEN REPLIES';
  if (!on) { cancelRecording(); stopSpeaking(); }
}

