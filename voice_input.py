"""
TAD — Voice Input Module v1.0
mic → faster-whisper (local STT) → returns transcript string
Plugs into tad_gui.py: call start_listening() in a thread,
result fires the on_transcript(text) callback.

Install:
    pip install faster-whisper sounddevice numpy

GPU (optional, faster):
    pip install faster-whisper[cuda]
"""

import threading
import numpy as np
import queue
import sounddevice as sd
from faster_whisper import WhisperModel

# ── Config ────────────────────────────────────────────────────────────────────
SAMPLE_RATE     = 16000          # Whisper expects 16kHz
BLOCK_SIZE      = 1024           # frames per audio block
SILENCE_LIMIT   = 2.0            # seconds of silence to stop recording
SILENCE_THRESH  = 0.01           # RMS below this = silence
WHISPER_MODEL   = "base.en"      # tiny.en / base.en / small.en / medium.en
COMPUTE_TYPE    = "int8"         # int8 = fast CPU, float16 = GPU

# Lazy-load model so import doesn't block startup
_model: WhisperModel | None = None
_model_lock = threading.Lock()


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                print("[Voice] Loading Whisper model...")
                _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=COMPUTE_TYPE)
                print("[Voice] Model ready.")
    return _model


# ── Audio capture ──────────────────────────────────────────────────────────────

def _record_until_silence() -> np.ndarray:
    """
    Record from mic until SILENCE_LIMIT seconds of silence detected.
    Returns raw float32 numpy array at SAMPLE_RATE.
    """
    q: queue.Queue = queue.Queue()
    frames: list[np.ndarray] = []
    silent_blocks = 0
    silence_block_limit = int((SAMPLE_RATE / BLOCK_SIZE) * SILENCE_LIMIT)

    def callback(indata, frame_count, time_info, status):
        q.put(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                        dtype="float32", blocksize=BLOCK_SIZE,
                        callback=callback):
        print("[Voice] 🎙 Listening...")
        while True:
            block = q.get()
            frames.append(block)
            rms = float(np.sqrt(np.mean(block ** 2)))

            if rms < SILENCE_THRESH:
                silent_blocks += 1
            else:
                silent_blocks = 0  # reset on sound

            if silent_blocks >= silence_block_limit and len(frames) > silence_block_limit:
                break

    audio = np.concatenate(frames, axis=0).flatten()
    print(f"[Voice] Captured {len(audio)/SAMPLE_RATE:.1f}s of audio")
    return audio


# ── Transcription ──────────────────────────────────────────────────────────────

def transcribe(audio: np.ndarray) -> str:
    """Run faster-whisper on a float32 numpy array. Returns transcript string."""
    model = _get_model()
    segments, _ = model.transcribe(audio, beam_size=5, language="en")
    text = " ".join(seg.text.strip() for seg in segments).strip()
    print(f"[Voice] Transcript: {text}")
    return text


# ── Public API ─────────────────────────────────────────────────────────────────

def listen_once() -> str:
    """
    Block until user speaks and goes silent.
    Returns the transcript string.
    Usage: text = listen_once()
    """
    audio = _record_until_silence()
    if audio is None or len(audio) < SAMPLE_RATE * 0.3:
        return ""   # too short to be a real utterance
    return transcribe(audio)


def start_listening(on_transcript, on_error=None):
    """
    Non-blocking — runs in a background thread.
    Calls on_transcript(text: str) when speech is detected and transcribed.
    Calls on_error(e: Exception) on failure.

    Usage in tad_gui.py:
        from voice_input import start_listening
        start_listening(on_transcript=self._handle_voice)

    def _handle_voice(self, text: str):
        self.chat_input.insert(tk.END, text)
        self._send_message()
    """
    def _worker():
        try:
            text = listen_once()
            if text:
                on_transcript(text)
        except Exception as e:
            print(f"[Voice] Error: {e}")
            if on_error:
                on_error(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


# ── Continuous loop mode ───────────────────────────────────────────────────────

def voice_loop(on_transcript, stop_event: threading.Event):
    """
    Runs continuously until stop_event is set.
    Each utterance fires on_transcript(text).

    Usage in tad_gui.py (run in a daemon thread):
        from voice_input import voice_loop
        self._voice_stop = threading.Event()
        t = threading.Thread(
            target=voice_loop,
            args=(self._handle_voice, self._voice_stop),
            daemon=True
        )
        t.start()
    """
    _get_model()  # warm up model before loop
    print("[Voice] Continuous loop started. Speak anytime.")
    while not stop_event.is_set():
        try:
            text = listen_once()
            if text and not stop_event.is_set():
                on_transcript(text)
        except Exception as e:
            print(f"[Voice] Loop error: {e}")
    print("[Voice] Loop stopped.")


# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Voice Input — tap Enter to record, Ctrl+C to quit")
    while True:
        input("Press Enter to speak → ")
        result = listen_once()
        print(f"You said: '{result}'\n")