import io
import threading
import wave

import config
from speech_text import prepare

_engine = None
lock = threading.Lock()


def _load():
    """Load Kokoro the first time something is spoken, not on import.

    This keeps server start-up fast and lets tests import the server without
    the model files (CI does not have them).
    """
    global _engine
    if _engine is None:
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(str(config.MODELS_DIR / "kokoro-v1.0.onnx"),
                        str(config.MODELS_DIR / "voices-v1.0.bin"))
        voice = kokoro.get_voice_style("bm_daniel") * 0.5 + kokoro.get_voice_style("bm_lewis") * 0.5
        _engine = (kokoro, voice)
    return _engine


def synthesize(text: str) -> bytes:
    import numpy as np

    text = prepare(text)
    with lock:
        kokoro, voice = _load()
        samples, sample_rate = kokoro.create(
            text, voice=voice, speed=config.VOICE_SPEED, lang=config.VOICE_LANG
        )
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
