"""
TAD GUI v0.4 — Claude UI + JARVIS Design
- Clean Claude-style chat layout
- Iron Man JARVIS aesthetic (holographic, HUD elements)
- Fixed empty responses (switched to Claude API)
- Fixed Tcl threading error (all popups via after())
- Sidebar with agent status
- Animated avatar ring
- Better typography
"""

import customtkinter as ctk
import threading
import os
import sys
import json
import queue
import math
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import tkinter as tk

from agent import run_task
from scheduler import start_scheduler, check_pending_briefing
from night_mode import start_night_mode, check_overnight_report, is_running as night_is_running
from voice_input import start_listening
from voice_loop import register_hotkey, toggle_voice_loop, is_active as voice_loop_active
from voice_loop import pause_for_tad_speaking, resume_after_tad_speaking
import pyttsx3
import keyboard

load_dotenv()

ROOT = Path(__file__).parent

# ── Claude API (replaces Kimi for conversation) ───────────────────────────────
claude  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
C_MODEL = "claude-haiku-4-5-20251001"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Color palette (Claude dark + JARVIS blue) ─────────────────────────────────
BG_DEEP    = "#080810"   # deepest background
BG_BASE    = "#0d0d18"   # main background
BG_SURFACE = "#12121f"   # cards / panels
BG_HOVER   = "#1a1a2e"   # hover states
ACCENT     = "#4f8ef7"   # JARVIS blue (primary)
ACCENT_DIM = "#2a4a8a"   # dimmed blue
GREEN      = "#1db87a"   # online / success
ORANGE     = "#f59e0b"   # thinking / warning
RED        = "#ef4444"   # error
PURPLE     = "#7c6ff7"   # TAD purple
TEXT_PRI   = "#e8e8f0"   # primary text
TEXT_SEC   = "#6b7280"   # secondary text
TEXT_DIM   = "#374151"   # dimmed text
BORDER     = "#1e2030"   # borders
RING_IDLE  = "#4f8ef7"
RING_THINK = "#f59e0b"
RING_SPEAK = "#1db87a"
RING_NIGHT = "#7c6ff7"


def _load_memory() -> str:
    profile_path = ROOT / "memory/profile.json"
    history_path = ROOT / "memory/history.jsonl"
    monkey_path  = ROOT / "THE_MONKEY.md"

    profile_text = ""
    history_text = ""
    monkey_text  = ""

    if profile_path.exists():
        try:
            p = json.loads(profile_path.read_text(encoding="utf-8"))
            profile_text = f"\nUSER: {p.get('name','Joshua')} | Goals: {', '.join(p.get('goals',[]))}"
        except Exception:
            pass

    if history_path.exists():
        try:
            lines   = history_path.read_text(encoding="utf-8").strip().splitlines()
            last5   = lines[-5:] if len(lines) >= 5 else lines
            snippets = []
            for line in last5:
                e = json.loads(line)
                snippets.append(f"  {e['user']} → {e['tad'][:60]}")
            if snippets:
                history_text = "\nRECENT:\n" + "\n".join(snippets)
        except Exception:
            pass

    if monkey_path.exists():
        monkey_text = "\n\nPROJECT STATE:\n" + monkey_path.read_text(encoding="utf-8")[:1500]

    return (
        "You are TAD — Joshua's sovereign AI business agent. "
        "Casual, direct, smart. Never corporate. Address Joshua by name. "
        "Keep responses concise unless detail is asked for. "
        f"{profile_text}{history_text}{monkey_text}"
    )


SYSTEM_PROMPT = _load_memory()

tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 175)
voices = tts_engine.getProperty("voices")
if len(voices) > 1:
    tts_engine.setProperty("voice", voices[1].id)

TASK_KEYWORDS = [
    "research", "analyze", "analyse", "search", "find", "market",
    "trend", "opportunity", "niche", "report", "look up", "scan",
    "what is profitable", "best ai", "investigate", "what are the",
    "run cseo", "evolve", "fix", "build", "score", "invoice",
    "health check", "p&l", "decide", "go or no go",
]


# ── Avatar canvas ──────────────────────────────────────────────────────────────

class AvatarCanvas(ctk.CTkCanvas):
    """Animated JARVIS-style avatar ring."""

    def __init__(self, parent, size=100, **kwargs):
        super().__init__(parent, width=size, height=size,
                        bg=BG_BASE, highlightthickness=0, **kwargs)
        self.size   = size
        self.cx     = size // 2
        self.cy     = size // 2
        self.state  = "idle"
        self._angle = 0
        self._anim  = None
        self._draw()

    def set_state(self, state: str):
        self.state = state
        self._draw()
        if state in ("thinking", "night"):
            self._start_spin()
        else:
            self._stop_spin()

    def _ring_color(self):
        return {
            "idle":     RING_IDLE,
            "thinking": RING_THINK,
            "speaking": RING_SPEAK,
            "night":    RING_NIGHT,
            "error":    RED,
        }.get(self.state, RING_IDLE)

    def _draw(self):
        self.delete("all")
        cx, cy, r = self.cx, self.cy, self.size//2 - 4
        color     = self._ring_color()

        # Outer glow ring
        self.create_oval(cx-r-3, cy-r-3, cx+r+3, cy+r+3,
                        outline=color, width=1,
                        fill=BG_BASE, stipple="gray25")

        # Main ring
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                        outline=color, width=2, fill=BG_SURFACE)

        # Spinning arc (for thinking/night)
        if self.state in ("thinking", "night"):
            a = self._angle % 360
            self.create_arc(cx-r, cy-r, cx+r, cy+r,
                           start=a, extent=120,
                           outline=color, width=3, style="arc")

        # Eyes
        ew, eh, ey = 10, 7, cy - 10
        ex_l, ex_r = cx - 16, cx + 6

        if self.state in ("thinking", "night"):
            # Squinting
            self.create_arc(ex_l, ey, ex_l+ew, ey+eh,
                           start=0, extent=180, fill=color, outline="")
            self.create_arc(ex_r, ey, ex_r+ew, ey+eh,
                           start=0, extent=180, fill=color, outline="")
        else:
            self.create_oval(ex_l, ey, ex_l+ew, ey+eh,
                            fill=color, outline="")
            self.create_oval(ex_r, ey, ex_r+ew, ey+eh,
                            fill=color, outline="")
            # Pupils
            self.create_oval(ex_l+3, ey+2, ex_l+6, ey+5,
                            fill=BG_DEEP, outline="")
            self.create_oval(ex_r+3, ey+2, ex_r+6, ey+5,
                            fill=BG_DEEP, outline="")

        # Mouth
        my = cy + 8
        if self.state == "idle":
            self.create_arc(cx-12, my, cx+12, my+12,
                           start=200, extent=140,
                           style="arc", outline=color, width=2)
        elif self.state == "speaking":
            self.create_oval(cx-8, my, cx+8, my+10,
                            fill=color, outline="")
        elif self.state == "error":
            self.create_arc(cx-12, my+4, cx+12, my+14,
                           start=20, extent=140,
                           style="arc", outline=color, width=2)
        else:
            self.create_line(cx-10, my+6, cx+10, my+6,
                            fill=color, width=2)

    def _start_spin(self):
        if self._anim:
            return
        self._spin()

    def _spin(self):
        if self.state not in ("thinking", "night"):
            self._anim = None
            return
        self._angle += 8
        self._draw()
        self._anim = self.after(40, self._spin)

    def _stop_spin(self):
        if self._anim:
            self.after_cancel(self._anim)
            self._anim = None
        self._draw()


# ── Chat bubble widget ────────────────────────────────────────────────────────

class ChatBubble(ctk.CTkFrame):
    """Claude-style chat message bubble."""

    def __init__(self, parent, role: str, text: str, ts: str, **kwargs):
        is_user = role == "user"
        super().__init__(parent,
                        fg_color="transparent",
                        corner_radius=0, **kwargs)

        bubble_frame = ctk.CTkFrame(
            self,
            fg_color=BG_SURFACE if is_user else "transparent",
            corner_radius=12,
        )

        if is_user:
            bubble_frame.pack(anchor="e", padx=(60, 8), pady=(2, 2))
        else:
            bubble_frame.pack(anchor="w", padx=(8, 60), pady=(2, 2))

        # Role label
        ctk.CTkLabel(
            bubble_frame,
            text="you" if is_user else "TAD",
            font=("Segoe UI", 10),
            text_color=ACCENT if is_user else PURPLE,
        ).pack(anchor="w", padx=12, pady=(8, 0))

        # Message text
        ctk.CTkLabel(
            bubble_frame,
            text=text,
            font=("Segoe UI", 13),
            text_color=TEXT_PRI,
            wraplength=360,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(2, 4))

        # Timestamp
        ctk.CTkLabel(
            bubble_frame,
            text=ts,
            font=("Segoe UI", 9),
            text_color=TEXT_DIM,
        ).pack(anchor="e", padx=12, pady=(0, 6))


# ── Main App ──────────────────────────────────────────────────────────────────

class TADApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("TAD — sovereign agent")
        self.geometry("780x860")
        self.minsize(680, 700)
        self.configure(fg_color=BG_DEEP)

        self.conversation       = [{"role": "user",
                                    "content": SYSTEM_PROMPT}]
        self.msg_queue          = queue.Queue()
        self.speaking           = False
        self._first_interaction = True
        self._voice_active      = False
        self._chat_widgets      = []

        self._build_ui()
        self._register_hotkeys()
        self._poll_queue()
        self.after(800, lambda: self._set_status("idle"))

        start_scheduler(
            status_callback=lambda msg: self.msg_queue.put(("status", msg))
        )

        self.bind("<Unmap>", self._on_minimize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Top bar (JARVIS HUD style) ────────────────────────────────────
        topbar = ctk.CTkFrame(self, fg_color=BG_SURFACE,
                              corner_radius=0, height=48)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        ctk.CTkLabel(
            topbar, text="◈  TAD",
            font=("Segoe UI", 14, "bold"),
            text_color=ACCENT
        ).pack(side="left", padx=20, pady=12)

        ctk.CTkLabel(
            topbar, text="sovereign agent · claude haiku · kimi k2",
            font=("Segoe UI", 10),
            text_color=TEXT_DIM
        ).pack(side="left", padx=4)

        self.status_pill = ctk.CTkLabel(
            topbar,
            text="◉  idle",
            fg_color=BG_HOVER,
            text_color=ACCENT,
            corner_radius=20,
            font=("Segoe UI", 11),
            padx=14, pady=4
        )
        self.status_pill.pack(side="right", padx=20, pady=10)

        # ── Main layout (sidebar + chat) ──────────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main.pack(fill="both", expand=True)

        # Sidebar
        sidebar = ctk.CTkFrame(main, fg_color=BG_SURFACE,
                               corner_radius=0, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Chat area
        chat_area = ctk.CTkFrame(main, fg_color=BG_BASE, corner_radius=0)
        chat_area.pack(side="left", fill="both", expand=True)
        self._build_chat_area(chat_area)

    def _build_sidebar(self, parent):
        # Avatar
        avatar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        avatar_frame.pack(fill="x", pady=(24, 8))

        self.avatar = AvatarCanvas(avatar_frame, size=80)
        self.avatar.pack(anchor="center")

        ctk.CTkLabel(
            avatar_frame,
            text="T  A  D",
            font=("Segoe UI", 16, "bold"),
            text_color=TEXT_PRI
        ).pack(pady=(8, 2))

        ctk.CTkLabel(
            avatar_frame,
            text="always running",
            font=("Segoe UI", 10),
            text_color=TEXT_DIM
        ).pack()

        # Divider
        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=16)

        # Agent status section
        ctk.CTkLabel(
            parent,
            text="AGENTS",
            font=("Segoe UI", 10, "bold"),
            text_color=TEXT_DIM
        ).pack(anchor="w", padx=16, pady=(0, 8))

        self.agent_labels = {}
        agents = [
            ("market",   "◈ Market"),
            ("decision", "◈ Decision"),
            ("build",    "◈ Build"),
            ("ceo",      "◈ CEO"),
            ("cseo",     "◈ CSEO"),
            ("ops",      "◈ Ops"),
        ]

        for key, label in agents:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)

            lbl = ctk.CTkLabel(
                row, text=label,
                font=("Segoe UI", 11),
                text_color=TEXT_SEC,
                anchor="w"
            )
            lbl.pack(side="left")

            dot = ctk.CTkLabel(
                row, text="●",
                font=("Segoe UI", 10),
                text_color=TEXT_DIM
            )
            dot.pack(side="right")
            self.agent_labels[key] = dot

        # Divider
        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=16)

        # Quick actions
        ctk.CTkLabel(
            parent,
            text="ACTIONS",
            font=("Segoe UI", 10, "bold"),
            text_color=TEXT_DIM
        ).pack(anchor="w", padx=16, pady=(0, 8))

        actions = [
            ("⟳  Market Scan",   "run a market scan and find the best opportunity right now"),
            ("◈  CEO Briefing",   "give me today's CEO briefing"),
            ("⚡  Ops Check",     "run a full system health check"),
            ("◎  Evolve CSEO",   "run cseo evolution cycle and fix all broken things"),
        ]

        for label, command in actions:
            btn = ctk.CTkButton(
                parent,
                text=label,
                font=("Segoe UI", 11),
                height=30,
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_SEC,
                anchor="w",
                corner_radius=6,
                command=lambda c=command: self._quick_action(c)
            )
            btn.pack(fill="x", padx=8, pady=1)

        # Night mode at bottom of sidebar
        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(
            fill="x", padx=16, pady=16)

        self.night_btn = ctk.CTkButton(
            parent,
            text="🌙  Night Mode",
            font=("Segoe UI", 11, "bold"),
            height=36,
            fg_color=ACCENT_DIM,
            hover_color=ACCENT,
            text_color=TEXT_PRI,
            corner_radius=8,
            command=self._start_night_mode
        )
        self.night_btn.pack(fill="x", padx=12, pady=4)

    def _build_chat_area(self, parent):
        # Chat header
        header = ctk.CTkFrame(parent, fg_color="transparent", height=44)
        header.pack(fill="x", padx=20, pady=(12, 0))
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="Chat",
            font=("Segoe UI", 14, "bold"),
            text_color=TEXT_PRI
        ).pack(side="left", pady=8)

        self.context_label = ctk.CTkLabel(
            header,
            text="",
            font=("Segoe UI", 11),
            text_color=TEXT_DIM
        )
        self.context_label.pack(side="right", pady=8)

        # Scrollable chat
        self.chat_scroll = ctk.CTkScrollableFrame(
            parent,
            fg_color="transparent",
            scrollbar_button_color=BG_SURFACE,
            scrollbar_button_hover_color=BG_HOVER,
        )
        self.chat_scroll.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # Welcome message
        self._add_system_message(
            "TAD online. Market intelligence active. Type or speak — "
            "Ctrl+Space to focus, Ctrl+M for hands-free."
        )

        # Input area
        input_area = ctk.CTkFrame(parent, fg_color=BG_SURFACE, corner_radius=12)
        input_area.pack(fill="x", padx=16, pady=12)

        # Input row
        input_row = ctk.CTkFrame(input_area, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(10, 4))

        self.input_box = ctk.CTkEntry(
            input_row,
            placeholder_text="Message TAD...",
            font=("Segoe UI", 13),
            fg_color=BG_BASE,
            border_color=BORDER,
            text_color=TEXT_PRI,
            placeholder_text_color=TEXT_DIM,
            corner_radius=8,
            height=40,
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_box.bind("<Return>", self._on_enter)

        # Buttons row
        btn_row = ctk.CTkFrame(input_area, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        self.send_btn = ctk.CTkButton(
            btn_row,
            text="Send  ↵",
            font=("Segoe UI", 12, "bold"),
            height=36,
            width=100,
            fg_color=ACCENT,
            hover_color="#3a7ef0",
            text_color="#ffffff",
            corner_radius=8,
            command=self._on_send
        )
        self.send_btn.pack(side="right")

        self.voice_loop_btn = ctk.CTkButton(
            btn_row,
            text="🔊  Hands-free",
            font=("Segoe UI", 11),
            height=36,
            fg_color=BG_HOVER,
            hover_color=BG_SURFACE,
            text_color=TEXT_SEC,
            corner_radius=8,
            command=self._toggle_voice_loop
        )
        self.voice_loop_btn.pack(side="right", padx=(0, 8))

        self.mic_btn = ctk.CTkButton(
            btn_row,
            text="🎙  Speak",
            font=("Segoe UI", 11),
            height=36,
            fg_color=BG_HOVER,
            hover_color=BG_SURFACE,
            text_color=TEXT_SEC,
            corner_radius=8,
            command=self._toggle_voice
        )
        self.mic_btn.pack(side="right", padx=(0, 8))

    # ── Chat methods ──────────────────────────────────────────────────────────

    def _add_system_message(self, text: str):
        msg = ctk.CTkLabel(
            self.chat_scroll,
            text=text,
            font=("Segoe UI", 11),
            text_color=TEXT_DIM,
            wraplength=480,
            justify="center",
        )
        msg.pack(pady=(16, 8))
        self._chat_widgets.append(msg)

    def _append_chat(self, role: str, text: str):
        if not text or not text.strip():
            return
        ts     = datetime.now().strftime("%H:%M")
        bubble = ChatBubble(self.chat_scroll, role, text, ts)
        bubble.pack(fill="x", pady=2)
        self._chat_widgets.append(bubble)
        # Scroll to bottom
        self.after(50, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    # ── Input handling ────────────────────────────────────────────────────────

    def _on_enter(self, event=None):
        self._on_send()

    def _on_send(self):
        text = self.input_box.get().strip()
        if not text:
            return
        self.input_box.delete(0, "end")
        self._handle_input(text)

    def _quick_action(self, command: str):
        self._handle_input(command)

    def _handle_input(self, text: str):
        if self._first_interaction:
            self._first_interaction = False
            self.after(200, self._check_on_wake)

        self._append_chat("user", text)
        self._set_status("thinking")
        self._update_context(f'"{text[:40]}..."' if len(text) > 40 else f'"{text}"')

        is_task = any(k in text.lower() for k in TASK_KEYWORDS)
        if is_task:
            threading.Thread(
                target=self._run_agent, args=(text,), daemon=True
            ).start()
        else:
            threading.Thread(
                target=self._call_claude, args=(text,), daemon=True
            ).start()

    # ── Agent runner ──────────────────────────────────────────────────────────

    def _run_agent(self, text: str):
        try:
            def status_update(msg):
                self.msg_queue.put(("status", msg))
            result = run_task(text, status_callback=status_update)
            if result and result.strip():
                self.msg_queue.put(("reply", result))
            else:
                self.msg_queue.put(("reply", "Task complete — check workflows folder for the full report."))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    # ── Claude conversation ───────────────────────────────────────────────────

    def _call_claude(self, user_text: str):
        try:
            self.conversation.append({"role": "user", "content": user_text})

            # Keep conversation manageable
            messages = self.conversation[-20:]
            # Ensure alternating roles
            valid = []
            last_role = None
            for m in messages:
                if m["role"] != last_role:
                    valid.append(m)
                    last_role = m["role"]

            # Remove system message from messages list (goes in system param)
            user_messages = [m for m in valid if m["role"] != "system"]
            if not user_messages:
                user_messages = [{"role": "user", "content": user_text}]

            msg = claude.messages.create(
                model=C_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=user_messages,
            )
            reply = msg.content[0].text if msg.content else ""

            if reply and reply.strip():
                self.conversation.append({"role": "assistant", "content": reply})
                self._save_to_memory(user_text, reply)
                self.msg_queue.put(("reply", reply))
            else:
                self.msg_queue.put(("reply", "I'm here — what do you need?"))

        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    # ── Memory ────────────────────────────────────────────────────────────────

    def _save_to_memory(self, user_text: str, reply: str):
        mem_dir = ROOT / "memory"
        mem_dir.mkdir(exist_ok=True)
        entry = {
            "ts":   datetime.now().isoformat(),
            "user": user_text,
            "tad":  reply,
        }
        with open(mem_dir / "history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ── TTS ───────────────────────────────────────────────────────────────────

    def _speak_text(self, text: str):
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    def _speak(self, text: str):
        self.speaking = True
        pause_for_tad_speaking()
        try:
            tts_engine.say(text[:300])
            tts_engine.runAndWait()
        except Exception:
            pass
        self.speaking = False
        resume_after_tad_speaking()
        self.msg_queue.put(("done_speaking", None))

    # ── Voice ─────────────────────────────────────────────────────────────────

    def _toggle_voice(self):
        if self._voice_active:
            return
        self._voice_active = True
        self.mic_btn.configure(text="⏹  Stop", text_color=RED)
        self._set_status("thinking", "listening...")

        def on_transcript(text: str):
            self.after(0, lambda: self._inject_voice(text))

        def on_error(e: Exception):
            self.after(0, self._voice_reset)

        start_listening(on_transcript=on_transcript, on_error=on_error)

    def _inject_voice(self, text: str):
        if text.strip():
            self.input_box.delete(0, "end")
            self.input_box.insert(0, text.strip())
            self._voice_reset()
            self._on_send()
        else:
            self._voice_reset()

    def _voice_reset(self):
        self._voice_active = False
        self.mic_btn.configure(text="🎙  Speak", text_color=TEXT_SEC)
        self._set_status("idle")

    def _toggle_voice_loop(self):
        active = toggle_voice_loop(
            on_transcript=lambda t: self.after(0, lambda: self._inject_voice(t)),
            on_status=lambda s, m: self.after(0, lambda: self._update_voice_loop_ui(s))
        )
        self._update_voice_loop_ui("active" if active else "idle")

    def _update_voice_loop_ui(self, state: str):
        if state == "active":
            self.voice_loop_btn.configure(
                text="🔊  Listening...", text_color=GREEN, fg_color=BG_HOVER
            )
        else:
            self.voice_loop_btn.configure(
                text="🔊  Hands-free", text_color=TEXT_SEC, fg_color=BG_HOVER
            )

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, state: str, text: str = None):
        labels = {
            "idle":     "◉  idle",
            "thinking": "◉  thinking",
            "speaking": "◉  speaking",
            "night":    "◉  building",
            "error":    "◉  error",
        }
        colors = {
            "idle":     (BG_HOVER, ACCENT),
            "thinking": (BG_HOVER, ORANGE),
            "speaking": (BG_HOVER, GREEN),
            "night":    (BG_HOVER, PURPLE),
            "error":    (BG_HOVER, RED),
        }
        fg, tc = colors.get(state, colors["idle"])
        self.status_pill.configure(
            text=labels.get(state, "◉  idle"),
            fg_color=fg, text_color=tc
        )
        self.avatar.set_state(state)

        # Update active agent dot
        agent_map = {
            "market":   ["research", "market", "scan", "opportunity"],
            "decision": ["score", "evaluate", "decide"],
            "build":    ["build", "code", "create"],
            "ceo":      ["briefing", "summary", "strategy"],
            "cseo":     ["evolve", "cseo", "fix"],
            "ops":      ["health", "ops", "check"],
        }
        if text:
            for agent, keywords in agent_map.items():
                if any(k in str(text).lower() for k in keywords):
                    self._highlight_agent(agent)
                    break

    def _highlight_agent(self, active_key: str):
        for key, dot in self.agent_labels.items():
            if key == active_key:
                dot.configure(text_color=GREEN)
            else:
                dot.configure(text_color=TEXT_DIM)

    def _update_context(self, text: str):
        self.context_label.configure(text=text)

    # ── Night mode ────────────────────────────────────────────────────────────

    def _start_night_mode(self):
        if night_is_running():
            self._append_chat("tad", "Night mode is already running — TAD is building.")
            return

        self.night_btn.configure(
            text="🌙  Building...",
            fg_color=PURPLE,
        )
        self._set_status("night")
        self._append_chat(
            "tad",
            "Night mode activated. Building everything on the priority list. "
            "Go sleep — full report ready when you wake up."
        )
        self._speak_text(
            "Night mode activated. Building while you sleep Joshua."
        )
        start_night_mode(
            status_callback=lambda msg: self.msg_queue.put(("night_status", msg))
        )

    # ── On wake check ─────────────────────────────────────────────────────────

    def _check_on_wake(self):
        def _do():
            overnight = check_overnight_report()
            if overnight and overnight.get("total_built", 0) > 0:
                self.after(0, lambda: self._show_overnight_report(overnight))
                return
            briefing = check_pending_briefing()
            if briefing:
                self.after(0, lambda: self._show_briefing_safe(briefing))
        threading.Thread(target=_do, daemon=True).start()

    def _show_overnight_report(self, report: dict):
        try:
            from tad_visual import OvernightReportDashboard
            self.after(0, lambda: OvernightReportDashboard(report))
        except Exception:
            built   = report.get("total_built", 0)
            summary = report.get("exec_summary", "")
            self._append_chat("tad", f"Overnight: built {built} items. {summary}")

        self.night_btn.configure(text="🌙  Night Mode", fg_color=ACCENT_DIM)

    def _show_briefing_safe(self, briefing: dict):
        try:
            from tad_visual import MorningBriefingDashboard
            self.after(0, lambda: MorningBriefingDashboard(briefing))
        except Exception:
            self._append_chat("tad", f"Morning briefing ready. Action: {briefing.get('action_today','')}")

    # ── Queue polling ─────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "status":
                    self._set_status("thinking", str(data))
                elif msg_type == "night_status":
                    if "complete" in str(data).lower():
                        self._set_status("idle")
                    else:
                        self._set_status("night", str(data))
                elif msg_type == "reply":
                    if data and data.strip():
                        self._append_chat("tad", data)
                        self._set_status("speaking")
                        self._speak_text(data[:300])
                elif msg_type == "done_speaking":
                    if not night_is_running():
                        self._set_status("idle")
                    self._update_context("")
                elif msg_type == "error":
                    self._set_status("error")
                    self._append_chat("tad", f"Error: {data}")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _register_hotkeys(self):
        try:
            keyboard.add_hotkey("ctrl+space", self._on_hotkey_wake)
            register_hotkey(
                on_transcript=lambda t: self.after(0, lambda: self._inject_voice(t)),
                on_status=lambda s, m: self.after(0, lambda: self._update_voice_loop_ui(s))
            )
        except Exception:
            pass

    def _on_hotkey_wake(self):
        self.after(0, self._focus_input)

    def _focus_input(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        self.input_box.focus()

    # ── Minimize / close ──────────────────────────────────────────────────────

    def _on_minimize(self, event):
        if event.widget != self:
            return
        hour = datetime.now().hour
        if (hour >= 22 or hour < 5) and not night_is_running():
            self.after(2000, self._start_night_mode)

    def _on_close(self):
        if night_is_running():
            self._append_chat(
                "tad",
                "Night mode is running — minimize instead to keep building."
            )
        else:
            self.destroy()


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)
    app = TADApp()
    app.mainloop()