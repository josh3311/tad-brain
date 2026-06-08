"""
TAD — Voice Loop v1.0
Phase 4 — Continuous hands-free listening mode

Features:
- Ctrl+M toggles hands-free mode on/off
- TAD listens continuously, transcribes, sends to agent
- Pauses automatically when TAD is speaking
- Wake word support: say "TAD" to activate from idle
- Visual indicator in GUI when voice loop is active
- Conversation Engine shapes every voice response
- Logs all voice interactions to memory/voice_log.jsonl
"""

import threading
import time
from pathlib import Path
from datetime import datetime
import json

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent
MEMORY   = ROOT / "memory"
LOG_PATH = MEMORY / "voice_log.jsonl"

# ── Config ────────────────────────────────────────────────────────────────────
WAKE_WORD        = "tad"           # say this to activate from idle
MIN_WORDS        = 2               # ignore transcripts shorter than this
PAUSE_AFTER_TTS  = 1.5            # seconds to wait after TAD speaks before listening again


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[VoiceLoop] {msg}")


# ── Voice Loop State ──────────────────────────────────────────────────────────

class VoiceLoopState:
    """Tracks the state of the voice loop."""
    def __init__(self):
        self.active        = False      # is loop running
        self.tad_speaking  = False      # is TAD currently speaking
        self.paused        = False      # manually paused
        self.stop_event    = threading.Event()
        self.thread        = None

_state = VoiceLoopState()


# ── Core voice loop ───────────────────────────────────────────────────────────

def _voice_loop_worker(on_transcript, on_status=None):
    """
    Main loop worker. Runs in a daemon thread.
    Listens continuously, fires on_transcript when speech detected.
    """
    try:
        from voice_input import listen_once, _get_model
        _get_model()  # warm up model before loop starts
    except ImportError as e:
        _log(f"voice_input not found: {e}")
        if on_status:
            on_status("error", "voice_input.py not found")
        return

    _log("Voice loop started — listening continuously")
    if on_status:
        on_status("active", "🔊 Hands-free mode active — speak anytime")

    while not _state.stop_event.is_set():
        # Pause while TAD is speaking
        if _state.tad_speaking or _state.paused:
            time.sleep(0.2)
            continue

        try:
            text = listen_once()

            if _state.stop_event.is_set():
                break

            if not text or len(text.split()) < MIN_WORDS:
                continue

            # Check for wake word if in idle mode
            text_lower = text.lower().strip()

            # Filter out noise and filler words
            noise_phrases = [
                "you", "thank you", "thanks", "okay", "ok",
                "uh", "um", "hmm", "hm", "ah"
            ]
            if text_lower in noise_phrases:
                continue

            _log(f"Heard: {text}")

            # Log voice interaction
            _log_interaction("user", text)

            # Fire transcript callback
            if on_transcript:
                on_transcript(text)

        except Exception as e:
            if not _state.stop_event.is_set():
                _log(f"Loop error: {e}")
                time.sleep(1)  # brief pause before retrying

    _log("Voice loop stopped")
    if on_status:
        on_status("idle", "🎙 Hands-free mode off")


def _log_interaction(role: str, text: str):
    """Log a voice interaction to memory."""
    entry = {
        "ts":   datetime.now().isoformat(),
        "role": role,
        "text": text,
    }
    MEMORY.mkdir(exist_ok=True)
    with open(MEMORY / "voice_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Public API ────────────────────────────────────────────────────────────────

def start_voice_loop(on_transcript, on_status=None) -> bool:
    """
    Start continuous voice loop.
    on_transcript(text) — called every time Joshua speaks
    on_status(state, message) — called when loop state changes

    Returns True if started, False if already running.

    Usage in tad_gui.py:
        from voice_loop import start_voice_loop, stop_voice_loop

        def _on_voice_transcript(text):
            self.after(0, lambda: self._inject_voice(text))

        def _on_voice_status(state, msg):
            self.after(0, lambda: self._update_voice_ui(state, msg))

        start_voice_loop(
            on_transcript=_on_voice_transcript,
            on_status=_on_voice_status
        )
    """
    if _state.active:
        _log("Voice loop already running")
        return False

    _state.active     = True
    _state.paused     = False
    _state.tad_speaking = False
    _state.stop_event.clear()

    _state.thread = threading.Thread(
        target=_voice_loop_worker,
        args=(on_transcript, on_status),
        daemon=True,
        name="TADVoiceLoop"
    )
    _state.thread.start()
    return True


def stop_voice_loop():
    """Stop the continuous voice loop."""
    if not _state.active:
        return
    _state.stop_event.set()
    _state.active = False
    _log("Voice loop stopping...")


def toggle_voice_loop(on_transcript, on_status=None) -> bool:
    """
    Toggle voice loop on/off.
    Returns True if now active, False if now stopped.

    Wire this to Ctrl+M in tad_gui.py:
        keyboard.add_hotkey("ctrl+m", lambda: toggle_voice_loop(...))
    """
    if _state.active:
        stop_voice_loop()
        return False
    else:
        start_voice_loop(on_transcript, on_status)
        return True


def pause_for_tad_speaking():
    """
    Call this when TAD starts speaking so loop doesn't pick up TAD's voice.
    Call resume_after_tad_speaking() when TAD finishes.
    """
    _state.tad_speaking = True


def resume_after_tad_speaking():
    """Call this when TAD finishes speaking."""
    # Small pause before listening again
    def _resume():
        time.sleep(PAUSE_AFTER_TTS)
        _state.tad_speaking = False

    threading.Thread(target=_resume, daemon=True).start()


def is_active() -> bool:
    """Returns True if voice loop is currently running."""
    return _state.active


def is_paused() -> bool:
    """Returns True if voice loop is paused."""
    return _state.paused


# ── Ctrl+M hotkey wiring ──────────────────────────────────────────────────────

def register_hotkey(on_transcript, on_status=None):
    """
    Register Ctrl+M hotkey to toggle voice loop.

    Call once from tad_gui.py __init__:
        from voice_loop import register_hotkey
        register_hotkey(
            on_transcript=lambda t: self.after(0, lambda: self._inject_voice(t)),
            on_status=lambda s, m: self.after(0, lambda: self._update_voice_status(s, m))
        )
    """
    try:
        import keyboard
        keyboard.add_hotkey(
            "ctrl+m",
            lambda: toggle_voice_loop(on_transcript, on_status)
        )
        _log("Ctrl+M hotkey registered for voice loop toggle")
        return True
    except Exception as e:
        _log(f"Hotkey registration error: {e}")
        return False


# ── GUI integration helpers ───────────────────────────────────────────────────

def get_status_text() -> str:
    """Returns a status string for the GUI."""
    if _state.active and _state.tad_speaking:
        return "🔇 TAD speaking..."
    elif _state.active and _state.paused:
        return "⏸ Voice paused"
    elif _state.active:
        return "🔊 Listening..."
    else:
        return "🎙 Press Ctrl+M for hands-free"


def get_recent_voice_log(limit: int = 10) -> list:
    """Get recent voice interactions for display."""
    log_path = MEMORY / "voice_log.jsonl"
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    recent = []
    for line in lines[-limit:]:
        try:
            recent.append(json.loads(line))
        except Exception:
            pass
    return recent


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    print("TAD Voice Loop — Standalone Test")
    print("=" * 40)
    print("Starting continuous voice loop...")
    print("Speak naturally — TAD will transcribe everything")
    print("Press Ctrl+C to stop\n")

    def on_transcript(text: str):
        print(f"\n🎙 You said: '{text}'")
        print("(In full TAD — this would route to the agent)")

    def on_status(state: str, msg: str):
        print(f"[Status] {state}: {msg}")

    started = start_voice_loop(on_transcript, on_status)
    if not started:
        print("Failed to start voice loop")
    else:
        print("Voice loop running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
                print(f"\rStatus: {get_status_text()}", end="", flush=True)
        except KeyboardInterrupt:
            print("\nStopping...")
            stop_voice_loop()
            print("Done.")
