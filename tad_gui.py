"""
TAD GUI v0.3 — with night mode + overnight report + morning briefing on wake
+ voice input via faster-whisper
"""

import customtkinter as ctk
import threading
import os
import sys
import json
import queue
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from agent import run_task
from scheduler import start_scheduler, check_pending_briefing
from night_mode import start_night_mode, check_overnight_report, is_running as night_is_running
from tad_visual import show_morning_briefing, show_research_report, MorningBriefingDashboard
from voice_input import start_listening
from voice_loop import register_hotkey, toggle_voice_loop, is_active as voice_loop_active, pause_for_tad_speaking, resume_after_tad_speaking, get_status_text
import pyttsx3
import keyboard
import tkinter as tk

load_dotenv()

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
client = OpenAI(
    api_key=KIMI_API_KEY,
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


def _load_memory() -> str:
    profile_path = Path("memory/profile.json")
    history_path = Path("memory/history.jsonl")
    profile_text = ""
    history_text = ""

    if profile_path.exists():
        p = json.loads(profile_path.read_text(encoding="utf-8"))
        profile_text = f"""
USER PROFILE:
- Name: {p.get('name', 'unknown')}
- Goals: {', '.join(p.get('goals', []))}
- Style: {p.get('preferences', {}).get('voice', '')}
- Language: {p.get('preferences', {}).get('language', '')}
- Context: {', '.join(p.get('context', []))}
- Vision: {p.get('vision', '')}
- Role: {p.get('role', '')}
"""

    if history_path.exists():
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        last5 = lines[-5:] if len(lines) >= 5 else lines
        snippets = []
        for line in last5:
            try:
                e = json.loads(line)
                snippets.append(f"  {e['user']} → {e['tad'][:80]}")
            except Exception:
                pass
        if snippets:
            history_text = "\nRECENT CONVERSATIONS:\n" + "\n".join(snippets)

    # Load THE_MONKEY.md so TAD always knows the project state
    monkey_text = ""
    monkey_path = Path("THE_MONKEY.md")
    if monkey_path.exists():
        monkey_text = "\n\nTAD PROJECT STATE (THE_MONKEY.md):\n" + monkey_path.read_text(encoding="utf-8")[:2000]

    return f"""You are TAD — Joshua's sovereign personal AI agent running locally on his machine.
You know Joshua personally. Address him by name occasionally.
Speak like a smart friend — casual, direct, no corporate talk.
Keep responses concise unless asked for detail.
You ALWAYS know your own project state — never ask Joshua to paste THE_MONKEY.md.
{profile_text}{history_text}{monkey_text}"""


SYSTEM_PROMPT = _load_memory()

tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 175)
voices = tts_engine.getProperty("voices")
if len(voices) > 1:
    tts_engine.setProperty("voice", voices[1].id)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

TASK_KEYWORDS = [
    "research", "analyze", "analyse", "search", "find",
    "what is profitable", "market", "trend", "opportunity",
    "niche", "report", "look up", "investigate", "what are the", "best ai",
]


class TADApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("TAD v0.3 — sovereign agent")
        self.geometry("520x720")
        self.resizable(False, False)
        self.configure(fg_color="#0d0d0f")

        self.conversation        = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.msg_queue           = queue.Queue()
        self.speaking            = False
        self._first_interaction  = True
        self._voice_active       = False  # voice state flag

        self._build_ui()
        self._register_hotkey()
        self._register_voice_hotkey()
        self._poll_queue()
        self.after(600, lambda: self._set_status("idle"))

        # Start background services
        start_scheduler(
            status_callback=lambda msg: self.msg_queue.put(("status", msg))
        )

        # Bind minimize event for night mode
        self.bind("<Unmap>", self._on_minimize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI BUILD ──────────────────────────────

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color="#141418", corner_radius=0, height=42)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="● ● ●", text_color="#444455",
                     font=("Courier", 11)).pack(side="left", padx=14)
        ctk.CTkLabel(top, text="TAD v0.3 — sovereign agent",
                     text_color="#555566", font=("Courier", 11)).pack(side="left", padx=6)

        self.status_pill = ctk.CTkLabel(
            top, text="● idle",
            fg_color="#1e1e2e", text_color="#7f77dd",
            corner_radius=10, font=("Courier", 11),
            padx=10, pady=3
        )
        self.status_pill.pack(side="right", padx=14)

        avatar_frame = ctk.CTkFrame(self, fg_color="#0d0d0f", corner_radius=0)
        avatar_frame.pack(fill="x", pady=(24, 0))

        self.avatar_canvas = ctk.CTkCanvas(
            avatar_frame, width=120, height=120,
            bg="#0d0d0f", highlightthickness=0
        )
        self.avatar_canvas.pack(anchor="center")
        self._draw_face("idle")

        ctk.CTkLabel(avatar_frame, text="T  A  D",
                     font=("Courier", 22, "bold"),
                     text_color="#e0e0f0").pack(pady=(12, 2))

        self.subtitle_label = ctk.CTkLabel(
            avatar_frame, text="your personal agentic AI",
            font=("Courier", 11), text_color="#444455"
        )
        self.subtitle_label.pack()

        self.transcript = ctk.CTkLabel(
            self, text="press Ctrl+Space or type below...",
            fg_color="#111115", corner_radius=8,
            font=("Courier", 12), text_color="#555566",
            wraplength=420, justify="center",
            padx=16, pady=12
        )
        self.transcript.pack(fill="x", padx=30, pady=(20, 8))

        self.chat_box = ctk.CTkTextbox(
            self, height=200, font=("Courier", 12),
            fg_color="#0a0a0d", text_color="#8a8a9e",
            border_color="#1e1e28", border_width=1,
            corner_radius=8, wrap="word", state="disabled"
        )
        self.chat_box.pack(fill="x", padx=30, pady=(0, 8))

        input_frame = ctk.CTkFrame(self, fg_color="#0d0d0f", corner_radius=0)
        input_frame.pack(fill="x", padx=30, pady=(0, 8))

        self.input_box = ctk.CTkEntry(
            input_frame, placeholder_text="type a message...",
            font=("Courier", 12), fg_color="#111115",
            border_color="#2a2a3a", text_color="#e0e0f0",
            corner_radius=8, height=38
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_box.bind("<Return>", self._on_enter)

        # ── Mic button (NEW) ──────────────────
        self.mic_btn = ctk.CTkButton(
            input_frame, text="🎙", width=38, height=38,
            font=("Courier", 13), fg_color="#0a0a1e",
            hover_color="#141428", text_color="#7f77dd",
            corner_radius=8, border_color="#2a2a4a", border_width=1,
            command=self._toggle_voice
        )
        self.mic_btn.pack(side="right", padx=(4, 0))

        self.voice_loop_btn = ctk.CTkButton(
            input_frame, text="🔊", width=38, height=38,
            font=("Courier", 13), fg_color="#0a0a1e",
            hover_color="#141428", text_color="#444455",
            corner_radius=8, border_color="#2a2a4a", border_width=1,
            command=self._toggle_voice_loop
        )
        self.voice_loop_btn.pack(side="right", padx=(4, 0))

        self.send_btn = ctk.CTkButton(
            input_frame, text="send", width=60, height=38,
            font=("Courier", 12), fg_color="#1e1a30",
            hover_color="#2a2440", text_color="#afa9ec",
            corner_radius=8, command=self._on_send
        )
        self.send_btn.pack(side="right", padx=(4, 0))

        # Night mode button
        night_frame = ctk.CTkFrame(self, fg_color="#0d0d0f", corner_radius=0)
        night_frame.pack(fill="x", padx=30, pady=(0, 4))

        self.night_btn = ctk.CTkButton(
            night_frame, text="🌙  start night mode — TAD builds while you sleep",
            font=("Courier", 11), height=34,
            fg_color="#0a0a14", hover_color="#141428",
            text_color="#534AB7", corner_radius=8,
            border_color="#2a2a4a", border_width=1,
            command=self._start_night_mode
        )
        self.night_btn.pack(fill="x")

        bottom = ctk.CTkFrame(self, fg_color="#0a0a0d", corner_radius=0, height=32)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        ctk.CTkLabel(bottom, text="kimi-k2.6 · moonshot ai",
                     font=("Courier", 10), text_color="#2a2a3a").pack(side="left", padx=12)
        ctk.CTkLabel(bottom, text="Ctrl+Space to wake",
                     font=("Courier", 10), text_color="#2a2a3a").pack(side="right", padx=12)

    # ── VOICE INPUT (NEW) ─────────────────────

    def _toggle_voice(self):
        """Single-shot voice capture — listens once, transcribes, auto-sends."""
        if self._voice_active:
            return  # already listening, ignore double-tap
        self._voice_active = True
        self.mic_btn.configure(fg_color="#3a0a0a", text_color="#ff6666", text="⏹")
        self._set_status("thinking", "listening for your voice...")

        def on_transcript(text: str):
            # called from background thread — marshal to main thread
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
            self._on_send()
        else:
            self._voice_reset()

    def _voice_reset(self):
        """Reset mic button to idle state."""
        self._voice_active = False
        self.mic_btn.configure(fg_color="#0a0a1e", text_color="#7f77dd", text="🎙")
        self._set_status("idle")

    # ── VOICE LOOP (Ctrl+M hands-free) ──────────

    def _register_voice_hotkey(self):
        """Register Ctrl+M to toggle continuous voice loop."""
        register_hotkey(
            on_transcript=lambda t: self.after(0, lambda: self._inject_voice(t)),
            on_status=lambda s, m: self.after(0, lambda: self._update_voice_loop_ui(s))
        )

    def _toggle_voice_loop(self):
        """Toggle continuous hands-free voice loop on/off."""
        active = toggle_voice_loop(
            on_transcript=lambda t: self.after(0, lambda: self._inject_voice(t)),
            on_status=lambda s, m: self.after(0, lambda: self._update_voice_loop_ui(s))
        )
        self._update_voice_loop_ui("active" if active else "idle")

    def _update_voice_loop_ui(self, state: str):
        """Update voice loop button appearance."""
        if state == "active":
            self.voice_loop_btn.configure(
                fg_color="#0a1e0a", text_color="#1d9e75", text="🔊"
            )
            self._set_status("thinking", "🔊 Hands-free mode active — speak anytime")
        elif state == "error":
            self.voice_loop_btn.configure(
                fg_color="#1e0a0a", text_color="#e24b4a", text="⚠️"
            )
        else:
            self.voice_loop_btn.configure(
                fg_color="#0a0a1e", text_color="#444455", text="🔊"
            )

    # ── NIGHT MODE ────────────────────────────

    def _start_night_mode(self):
        """Launch TAD autonomous overnight builder."""
        if night_is_running():
            self._append_chat("tad", "Night mode is already running — TAD is building.")
            return

        self.night_btn.configure(
            text="🌙  night mode active — TAD is building...",
            fg_color="#0a1428",
            text_color="#1d9e75"
        )
        self._set_status("thinking", "night mode — building autonomously...")
        self._append_chat("tad",
            "Night mode activated. TAD is building everything on the priority list. "
            "Go sleep — I'll have a full report ready when you wake up."
        )
        self._speak_text(
            "Night mode activated. I am building everything while you sleep. "
            "I will have a full report ready when you wake up Joshua."
        )

        start_night_mode(
            status_callback=lambda msg: self.msg_queue.put(("night_status", msg))
        )

    # ── FACE ──────────────────────────────────

    def _draw_face(self, state="idle"):
        c = self.avatar_canvas
        c.delete("all")
        cx, cy, r = 60, 60, 50
        colors = {
            "idle":     ("#2a2a38", "#7f77dd"),
            "thinking": ("#2a1e10", "#ef9f27"),
            "speaking": ("#102820", "#1d9e75"),
            "night":    ("#0a0a1e", "#534AB7"),
            "error":    ("#2a1010", "#e24b4a"),
        }
        bg, ring = colors.get(state, colors["idle"])
        c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=ring, width=2, fill=bg)
        eye_color = ring
        if state == "thinking" or state == "night":
            c.create_arc(cx-22, cy-12, cx-10, cy-4, start=0, extent=180, fill=eye_color, outline="")
            c.create_arc(cx+10, cy-12, cx+22, cy-4, start=0, extent=180, fill=eye_color, outline="")
        else:
            c.create_oval(cx-22, cy-16, cx-10, cy-4, fill=eye_color, outline="")
            c.create_oval(cx+10, cy-16, cx+22, cy-4, fill=eye_color, outline="")
            c.create_oval(cx-18, cy-13, cx-14, cy-9, fill="#0d0d0f", outline="")
            c.create_oval(cx+14, cy-13, cx+18, cy-9, fill="#0d0d0f", outline="")
        if state == "idle":
            c.create_arc(cx-16, cy+4, cx+16, cy+22, start=200, extent=140,
                         style="arc", outline=ring, width=2)
        elif state == "speaking":
            c.create_oval(cx-10, cy+8, cx+10, cy+22, fill=ring, outline="")
        elif state in ("thinking", "night"):
            c.create_line(cx-12, cy+16, cx+12, cy+16, fill=ring, width=2)
        elif state == "error":
            c.create_arc(cx-16, cy+10, cx+16, cy+24, start=20, extent=140,
                         style="arc", outline=ring, width=2)

    # ── STATUS ────────────────────────────────

    def _set_status(self, state, text=None):
        labels = {
            "idle":     "● idle",
            "thinking": "● thinking",
            "speaking": "● speaking",
            "night":    "● building...",
            "error":    "● error",
        }
        colors = {
            "idle":     ("#1e1e2e", "#7f77dd"),
            "thinking": ("#2a1e10", "#ef9f27"),
            "speaking": ("#102820", "#1d9e75"),
            "night":    ("#0a0a1e", "#534AB7"),
            "error":    ("#2a1010", "#e24b4a"),
        }
        fg, tc = colors.get(state, colors["idle"])
        self.status_pill.configure(
            text=labels.get(state, "● idle"),
            fg_color=fg, text_color=tc
        )
        self._draw_face(state)
        if text:
            self.transcript.configure(text=text, text_color="#ccccdd")
        else:
            self.transcript.configure(
                text="press Ctrl+Space or type below...",
                text_color="#555566"
            )

    # ── CHAT ──────────────────────────────────

    def _append_chat(self, role, text):
        self.chat_box.configure(state="normal")
        ts = datetime.now().strftime("%H:%M")
        prefix = "you" if role == "user" else "tad"
        self.chat_box.insert("end", f"\n[{ts}] {prefix}: {text}\n")
        self.chat_box.configure(state="disabled")
        self.chat_box.see("end")

    def _on_enter(self, event=None):
        self._on_send()

    def _on_send(self):
        text = self.input_box.get().strip()
        if not text:
            return
        self.input_box.delete(0, "end")
        self._handle_input(text)

    def _handle_input(self, text):
        if self._first_interaction:
            self._first_interaction = False
            self.after(200, self._check_on_wake)

        self._append_chat("user", text)
        self.transcript.configure(text=f'"{text}"', text_color="#ccccdd")
        self._set_status("thinking", f'"{text}"')

        is_task = any(k in text.lower() for k in TASK_KEYWORDS)
        if is_task:
            threading.Thread(target=self._run_agent, args=(text,), daemon=True).start()
        else:
            threading.Thread(target=self._call_kimi, args=(text,), daemon=True).start()

    def _check_on_wake(self):
        def _do_check():
            overnight = check_overnight_report()
            if overnight:
                self.after(0, lambda: self._show_overnight_report(overnight))
                return
            briefing = check_pending_briefing()
            if briefing:
                self.after(0, lambda: self._show_briefing_safe(briefing))
        threading.Thread(target=_do_check, daemon=True).start()

    def _show_briefing_safe(self, briefing: dict):
        """Show morning briefing on main thread safely."""
        try:
            win = MorningBriefingDashboard(briefing)
            win.lift()
        except Exception as e:
            self._append_chat("tad", f"Morning briefing ready — check memory/morning_briefing.json")

    def _show_overnight_report(self, report: dict):
        try:
            from tad_visual import OvernightReportDashboard
            def _launch():
                win = OvernightReportDashboard(report)
                win.mainloop()
            threading.Thread(target=_launch, daemon=True).start()
        except Exception as e:
            built   = report.get("total_built", 0)
            files   = report.get("total_files", 0)
            summary = report.get("exec_summary", "Overnight build complete.")
            self._append_chat("tad",
                f"Overnight build complete. {built} items built, {files} files created.\n\n{summary}"
            )
            self._speak_text(f"Good morning Joshua. {summary}")

        self.night_btn.configure(
            text="🌙  start night mode — TAD builds while you sleep",
            fg_color="#0a0a14",
            text_color="#534AB7"
        )

    # ── AGENT ─────────────────────────────────

    def _run_agent(self, text):
        try:
            def status_update(msg):
                self.msg_queue.put(("status", msg))
            result = run_task(text, status_callback=status_update)
            self.msg_queue.put(("reply", result))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    # ── KIMI CHAT ─────────────────────────────

    def _call_kimi(self, user_text):
        try:
            self.conversation.append({"role": "user", "content": user_text})
            response = client.chat.completions.create(
                model=MODEL,
                messages=self.conversation,
                max_tokens=1024,
            )
            reply = response.choices[0].message.content
            if reply:
                self.conversation.append({"role": "assistant", "content": reply})
            self._save_to_memory(user_text, reply)
            self.msg_queue.put(("reply", reply))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    # ── MEMORY ────────────────────────────────

    def _save_to_memory(self, user_text, reply):
        mem_dir = Path("memory")
        mem_dir.mkdir(exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), "user": user_text, "tad": reply}
        with open(mem_dir / "history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ── TTS ───────────────────────────────────

    def _speak_text(self, text: str):
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    def _speak(self, text):
        self.speaking = True
        pause_for_tad_speaking()   # stop voice loop picking up TAD's voice
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception:
            pass
        self.speaking = False
        resume_after_tad_speaking()  # resume listening after TAD finishes
        self.msg_queue.put(("done_speaking", None))

    # ── QUEUE POLLING ─────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "status":
                    self._set_status("thinking", data)
                elif msg_type == "night_status":
                    if "complete" in str(data).lower():
                        self._set_status("idle", "night build complete — tap to see results")
                    else:
                        self._set_status("night", str(data)[:60])
                elif msg_type == "reply":
                    self._append_chat("tad", data)
                    self._set_status("speaking", data[:80] + ("..." if len(data) > 80 else ""))
                    self._speak_text(data)
                elif msg_type == "done_speaking":
                    if not night_is_running():
                        self._set_status("idle")
                elif msg_type == "error":
                    self._set_status("error", f"error: {data}")
                    self._append_chat("tad", f"[error] {data}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ── HOTKEY ────────────────────────────────

    def _register_hotkey(self):
        try:
            keyboard.add_hotkey("ctrl+space", self._on_hotkey_wake)
        except Exception:
            pass

    def _on_hotkey_wake(self):
        self.after(0, self._focus_input)

    def _focus_input(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.input_box.focus()
        self._set_status("idle", "listening... type your message")

    # ── MINIMIZE / CLOSE ──────────────────────

    def _on_minimize(self, event):
        """Auto-start night mode when minimized between 10pm and 5am."""
        if event.widget != self:
            return
        hour = datetime.now().hour
        if (hour >= 22 or hour < 5) and not night_is_running():
            print("[gui] Minimized — auto-starting night mode")
            self.after(2000, self._start_night_mode)

    def _on_close(self):
        """Confirm before closing if night mode is running."""
        if night_is_running():
            self._append_chat("tad",
                "Night mode is still running! TAD is building. "
                "Minimize instead to keep building while you sleep."
            )
        else:
            self.destroy()


if __name__ == "__main__":
    if not KIMI_API_KEY:
        print("ERROR: KIMI_API_KEY not found in .env file")
        sys.exit(1)
    app = TADApp()
    app.mainloop()