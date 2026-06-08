# TAD GUI — Voice Input Patch
# Apply to tad_gui.py — 4 surgical changes only

---

## CHANGE 1 — Add imports (top of file, with existing imports)

ADD these two lines near the top with the other imports:

```python
from voice_input import start_listening
```

---

## CHANGE 2 — Add mic button inside _build_ui

FIND this block (around line 132):
```python
        self.send_btn = ctk.CTkButton(
            input_frame, text="send", width=60, height=38,
            font=("Courier", 12), fg_color="#1e1a30",
            hover_color="#2a2440", text_color="#afa9ec",
            corner_radius=8, command=self._on_send
        )
        self.send_btn.pack(side="right")
```

REPLACE with:
```python
        self.send_btn = ctk.CTkButton(
            input_frame, text="send", width=60, height=38,
            font=("Courier", 12), fg_color="#1e1a30",
            hover_color="#2a2440", text_color="#afa9ec",
            corner_radius=8, command=self._on_send
        )
        self.send_btn.pack(side="right", padx=(4, 0))

        self.mic_btn = ctk.CTkButton(
            input_frame, text="🎙", width=38, height=38,
            font=("Courier", 13), fg_color="#0a0a1e",
            hover_color="#141428", text_color="#7f77dd",
            corner_radius=8, border_color="#2a2a4a", border_width=1,
            command=self._toggle_voice
        )
        self.mic_btn.pack(side="right", padx=(0, 4))
```

---

## CHANGE 3 — Add _toggle_voice and helpers to TADApp class

ADD these three methods anywhere inside the TADApp class
(good place: right after _on_send, before _check_on_wake):

```python
    # ── VOICE INPUT ───────────────────────────

    def _toggle_voice(self):
        """Single-shot voice capture — listens once, transcribes, sends."""
        if getattr(self, "_voice_active", False):
            return  # already listening, ignore double-tap
        self._voice_active = True
        self.mic_btn.configure(fg_color="#3a0a0a", text_color="#ff6666", text="⏹")
        self._set_status("thinking", "listening for your voice...")

        def on_transcript(text: str):
            # called from background thread — marshal back to main thread
            self.after(0, lambda: self._inject_voice(text))

        def on_error(e: Exception):
            self.after(0, self._voice_reset)
            self.msg_queue.put(("error", f"voice input error: {e}"))

        start_listening(on_transcript=on_transcript, on_error=on_error)

    def _inject_voice(self, text: str):
        """Put transcript into input box and auto-send."""
        if text.strip():
            self.input_box.delete(0, "end")
            self.input_box.insert(0, text.strip())
            self._voice_reset()
            self._on_send()   # ← correct method name in your codebase
        else:
            self._voice_reset()

    def _voice_reset(self):
        """Reset mic button to idle state."""
        self._voice_active = False
        self.mic_btn.configure(fg_color="#0a0a1e", text_color="#7f77dd", text="🎙")
        self._set_status("idle")
```

---

## CHANGE 4 — Install the dependency (run once in terminal)

```bash
cd C:\TAD
.venv\Scripts\activate
pip install faster-whisper sounddevice numpy
```

First run will download the Whisper base.en model (~150MB) — one time only.

---

## WHAT YOU ALSO GET FOR FREE (already in your code)

- Fix 3 (minimize loop) → ALREADY DONE — `event.widget != self` guard is in your code ✓
- Night mode auto-launch on minimize (10pm–5am) → ALREADY IN your `_on_minimize` ✓  
- Scheduler already called in `__init__` ✓

Only the voice mic button was missing.