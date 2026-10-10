import io
import re
import threading
import wave
import numpy as np
from kokoro_onnx import Kokoro

VOICE = None
LANG = "en-gb"
SPEED = 1.1

kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")
VOICE = kokoro.get_voice_style("bm_daniel") * 0.5 + kokoro.get_voice_style("bm_lewis") * 0.5
lock = threading.Lock()

PRONUNCIATIONS = {
    "Hephaestus": "Heh-fess-tus",    
    "Trastevere": "Trah-stay-veh-reh",
    "piazza": "pee-aht-sah",
}

def fix_pronunciations(text: str) -> str:
    for word, spoken in PRONUNCIATIONS.items():
        text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)
    return text

def synthesize(text: str) -> bytes:
    text = re.sub(r"[*_`#]", "", text).strip()
    text = fix_pronunciations(text)
    with lock:
        samples, sample_rate = kokoro.create(text, voice=VOICE, speed=SPEED, lang=LANG)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()