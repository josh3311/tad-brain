"""
TAD GUI v0.5 — JARVIS + Joshua face + Green/Purple theme
- Green + Purple color scheme (from abstract reference)
- 3D-style animated face (inspired by Joshua's features)
- Live transcription with edit before send
- Input blocked while TAD is thinking
- Shows live work-in-progress in chat
- Smooth idle animations (blink, breathe, pulse)
- Larger, cleaner layout
"""

import customtkinter as ctk
import threading
import os, sys, json, queue, math, random
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic
import tkinter as tk

from tad_encoding import force_utf8
force_utf8()

from memory_tools import MEMORY_TOOL_SCHEMA, call_memory_tool
from agent import run_task
from scheduler import start_scheduler, check_pending_briefing
from night_mode import start_night_mode, check_overnight_report, is_running as night_is_running
from voice_input import start_listening
from voice_loop import register_hotkey, toggle_voice_loop
from voice_loop import pause_for_tad_speaking, resume_after_tad_speaking
import pyttsx3
import keyboard

load_dotenv()
ROOT    = Path(__file__).parent
claude  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
C_MODEL = "claude-haiku-4-5-20251001"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Color palette: Purple + Green (from abstract reference) ──────────────────
BG_DEEP    = "#06030f"   # deepest space
BG_BASE    = "#0a0618"   # main bg
BG_SURFACE = "#110e22"   # panels
BG_CARD    = "#160f2a"   # cards
BG_HOVER   = "#1e1640"   # hover
NEON_GREEN = "#00e87a"   # bright neon green
NEON_PURP  = "#9d4edd"   # vivid purple
MID_GREEN  = "#00b35c"   # mid green
MID_PURP   = "#6a0dad"   # mid purple
GLOW_GREEN = "#00ff88"   # glow green
GLOW_PURP  = "#bf5fff"   # glow purple
TEXT_PRI   = "#f0eeff"   # primary text
TEXT_SEC   = "#8b80aa"   # secondary
TEXT_DIM   = "#3d3558"   # dimmed
BORDER     = "#1e1640"   # borders
ORANGE     = "#ff9f43"   # thinking
RED        = "#ff4757"   # error
WHITE      = "#ffffff"


def _load_memory() -> str:
    profile_path = ROOT / "memory/profile.json"
    history_path = ROOT / "memory/history.jsonl"
    monkey_path  = ROOT / "THE_MONKEY.md"
    parts = [
        "You are TAD — Joshua's sovereign AI business agent. "
        "Casual, direct, smart. Never corporate. Address Joshua by name. "
        "Keep responses concise unless detail is asked for. "
        "Always know your project state. Never ask Joshua to re-explain TAD. "
        "You have a read_memory_file tool with read-only access to memory/. "
        "For 'what happened', 'what was built', 'what did you decide' or "
        "spend questions, call it on session_report.md, decision_log.jsonl, "
        "ceo_log.jsonl, metrics.json or pii_audit.jsonl and answer from the "
        "real contents — never claim you have no access to logs."
    ]
    if profile_path.exists():
        try:
            p = json.loads(profile_path.read_text(encoding="utf-8"))
            parts.append(f"USER: {p.get('name','Joshua')} | Goals: {', '.join(p.get('goals',[]))}")
        except Exception: pass
    if history_path.exists():
        try:
            lines = history_path.read_text(encoding="utf-8").strip().splitlines()
            last5 = lines[-5:] if len(lines) >= 5 else lines
            snippets = []
            for line in last5:
                e = json.loads(line)
                snippets.append(f"  {e['user']} → {e['tad'][:60]}")
            if snippets:
                parts.append("RECENT:\n" + "\n".join(snippets))
        except Exception: pass
    if monkey_path.exists():
        parts.append("\nPROJECT STATE:\n" + monkey_path.read_text(encoding="utf-8")[:1500])
    return "\n".join(parts)


SYSTEM_PROMPT = _load_memory()

tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 175)
voices = tts_engine.getProperty("voices")
if len(voices) > 1:
    tts_engine.setProperty("voice", voices[1].id)

# Only these EXPLICIT phrases trigger the agent pipeline
# Everything else goes to Claude conversation
TASK_KEYWORDS = [
    "run a market scan", "market scan", "run cseo", "cseo evolution",
    "run a full", "health check", "ops check",
    "score this opportunity", "go or no go", "should we build",
    "p&l report", "profit and loss", "invoice client",
    "find leads", "send outreach", "build me a", "build a script",
    "ceo briefing", "morning briefing", "daily briefing",
    "find opportunities", "scan for loopholes", "run the market",
    "evolve tad", "fix all broken",
]


# ── Animated Blob Background (from abstract reference) ────────────────────────

class BlobBackground(tk.Canvas):
    """
    Animated green/purple gradient blobs floating in the background.
    Reverse-engineered from the abstract reference image.
    """

    def __init__(self, parent, width, height, **kwargs):
        super().__init__(parent, width=width, height=height,
                        bg=BG_DEEP, highlightthickness=0, **kwargs)
        self.w = width
        self.h = height
        self._blobs = []
        self._init_blobs()
        self._animate()

    def _init_blobs(self):
        # Green and purple blobs of varying sizes
        configs = [
            (0.15, 0.85, 90,  NEON_GREEN, MID_GREEN),
            (0.05, 0.65, 70,  NEON_PURP,  MID_PURP),
            (0.45, 0.95, 110, MID_GREEN,  NEON_GREEN),
            (0.75, 0.80, 80,  NEON_PURP,  GLOW_PURP),
            (0.90, 0.60, 60,  NEON_GREEN, MID_GREEN),
            (0.30, 0.70, 50,  GLOW_PURP,  NEON_PURP),
            (0.60, 0.55, 45,  MID_GREEN,  NEON_GREEN),
        ]
        for fx, fy, size, c1, c2 in configs:
            self._blobs.append({
                "x":     self.w * fx,
                "y":     self.h * fy,
                "size":  size,
                "c1":    c1,
                "c2":    c2,
                "phase": random.uniform(0, math.pi * 2),
                "drift": random.uniform(0.1, 0.3),
            })

    def _animate(self):
        self.delete("all")
        for b in self._blobs:
            b["phase"] += 0.02
            wobble = math.sin(b["phase"]) * 8
            x = b["x"] + math.cos(b["phase"] * 0.5) * 15
            y = b["y"] + wobble
            s = b["size"] + math.sin(b["phase"] * 0.7) * 6

            # Layered ovals for 3D gradient effect (dark to bright)
            for i, stipple in [(s*1.3, "gray12"), (s*1.1, "gray25"),
                              (s*0.9, "gray50"), (s*0.6, "gray75")]:
                self.create_oval(
                    x - i, y - i*0.7, x + i, y + i*0.7,
                    fill=b["c1"], outline="", stipple=stipple
                )
            # Bright core
            self.create_oval(
                x - s*0.4, y - s*0.3, x + s*0.4, y + s*0.3,
                fill=b["c2"], outline="", stipple="gray50"
            )

        self.after(60, self._animate)


# ── TAD Face Canvas ───────────────────────────────────────────────────────────

class TADFace(tk.Canvas):
    """
    Animated JARVIS-style face inspired by Joshua's features.
    Dark complexion, round face, short hair, goatee, expressive eyes.
    Runs idle animations: blink, breathe, pulse ring.
    """

    def __init__(self, parent, size=160, **kwargs):
        # Remove bg from kwargs to avoid duplicate argument
        kwargs.pop("bg", None)
        super().__init__(parent, width=size, height=size,
                        bg=BG_BASE, highlightthickness=0, **kwargs)
        self.size     = size
        self.cx       = size // 2
        self.cy       = size // 2 + 4
        self.r        = size // 2 - 8
        self.state    = "idle"

        # Animation state
        self._blink_open   = True
        self._breath_phase = 0.0
        self._ring_angle   = 0
        self._idle_timer   = None
        self._anim_running = False
        self._particles    = []

        self._init_particles()
        self._start_animation()

    def _init_particles(self):
        """Small floating particles around the face."""
        for _ in range(6):
            self._particles.append({
                "x":     self.cx + random.randint(-self.r, self.r),
                "y":     self.cy + random.randint(-self.r, self.r),
                "vx":    random.uniform(-0.3, 0.3),
                "vy":    random.uniform(-0.5, -0.1),
                "life":  random.uniform(0.3, 1.0),
                "size":  random.randint(1, 3),
            })

    def _ring_color(self):
        return {
            "idle":     NEON_GREEN,
            "thinking": ORANGE,
            "speaking": NEON_PURP,
            "night":    GLOW_PURP,
            "error":    RED,
        }.get(self.state, NEON_GREEN)

    def set_state(self, state: str):
        self.state = state

    def _start_animation(self):
        if not self._anim_running:
            self._anim_running = True
            self._animate()

    def _animate(self):
        self._breath_phase += 0.05
        self._ring_angle   = (self._ring_angle + 3) % 360

        # Random blink
        if random.random() < 0.008:
            self._blink_open = False
            self.after(120, self._reopen_eyes)

        # Update particles
        for p in self._particles:
            p["x"]    += p["vx"]
            p["y"]    += p["vy"]
            p["life"] -= 0.008
            if p["life"] <= 0:
                p.update({
                    "x":    self.cx + random.randint(-30, 30),
                    "y":    self.cy + self.r//2,
                    "vx":   random.uniform(-0.3, 0.3),
                    "vy":   random.uniform(-0.5, -0.1),
                    "life": random.uniform(0.5, 1.0),
                    "size": random.randint(1, 3),
                })

        self._draw()
        self._idle_timer = self.after(40, self._animate)

    def _reopen_eyes(self):
        self._blink_open = True

    def _draw(self):
        self.delete("all")
        cx, cy, r = self.cx, self.cy, self.r
        color     = self._ring_color()

        # ── Background glow ────────────────────────────────────────────────
        breath = math.sin(self._breath_phase) * 0.15 + 0.85
        glow_r = int(r * 1.35 * breath)

        # Outer glow rings
        for i, alpha in [(glow_r+12, "gray12"), (glow_r+6, "gray25")]:
            self.create_oval(cx-i, cy-i, cx+i, cy+i,
                            outline=color, width=1,
                            fill=BG_BASE, stipple=alpha)

        # ── Main ring ─────────────────────────────────────────────────────
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                        outline=color, width=3, fill="#0e0a1e")

        # Spinning arc (always, speed varies by state)
        arc_speed = 8 if self.state == "thinking" else 3
        self._ring_angle = (self._ring_angle + (arc_speed - 3)) % 360
        extent = 90 if self.state == "thinking" else 60
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                       start=self._ring_angle, extent=extent,
                       outline=GLOW_GREEN if self.state != "thinking" else ORANGE,
                       width=4, style="arc")

        # Opposite arc
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                       start=(self._ring_angle+180)%360, extent=30,
                       outline=GLOW_PURP, width=2, style="arc")

        # ── Face base (dark complexion — rounder, fuller) ─────────────────
        face_r = int(r * 0.76)
        fw = int(face_r * 1.05)   # slightly wider
        fh = int(face_r * 1.15)   # slightly taller (oval face)
        # Deep skin tone with 3D shading
        self.create_oval(cx-fw, cy-fh, cx+fw, cy+fh,
                        fill="#2e1d12", outline="#1a0f0a", width=2)
        # 3D highlight catch (top-left light source)
        self.create_arc(cx-fw+4, cy-fh+2, cx+4, cy+4,
                       start=50, extent=90,
                       outline="#4a3020", width=4, style="arc")
        # Cheek highlights (gives roundness)
        self.create_oval(cx-fw+8, cy-2, cx-fw+24, cy+16,
                        fill="#3a2418", outline="", stipple="gray50")
        self.create_oval(cx+fw-24, cy-2, cx+fw-8, cy+16,
                        fill="#3a2418", outline="", stipple="gray50")

        # ── Hair (fuller top fade, like the photo) ────────────────────────
        hair_w = fw + 4
        hair_h = fh + 8
        # Main hair mass — taller crown
        self.create_arc(cx-hair_w, cy-hair_h,
                       cx+hair_w, cy+hair_h-10,
                       start=10, extent=160,
                       fill="#080404", outline="#080404")
        # Hair texture lines (curls hint)
        for hx in range(-3, 4):
            tx = cx + hx * 12
            self.create_arc(tx-6, cy-fh-6, tx+6, cy-fh+10,
                           start=20, extent=140,
                           outline="#1a1010", width=1, style="arc")
        # Fade line at temples
        self.create_arc(cx-fw, cy-fh+4, cx+fw, cy-fh+24,
                       start=20, extent=140,
                       outline="#241510", width=3, style="arc")

        # ── Eyes (wider set, like the photo) ──────────────────────────────
        ey    = cy - int(fh * 0.18)
        ew, eh = 15, 9
        ex_l  = cx - int(fw * 0.42)
        ex_r  = cx + int(fw * 0.18)

        for ex in [ex_l, ex_r]:
            # Eye white / iris bg
            self.create_oval(ex, ey, ex+ew, ey+eh,
                            fill="#0d0d1a", outline=color, width=1)
            if self._blink_open:
                # Iris
                iris_x = ex + ew//2 - 4
                iris_y = ey + eh//2 - 4
                self.create_oval(iris_x, iris_y,
                                iris_x+8, iris_y+8,
                                fill=color, outline="")
                # Pupil
                self.create_oval(iris_x+2, iris_y+2,
                                iris_x+5, iris_y+5,
                                fill=BG_DEEP, outline="")
                # Glow reflection
                self.create_oval(iris_x+1, iris_y+1,
                                iris_x+3, iris_y+3,
                                fill="#ffffff", outline="")
            else:
                # Blink — closed line
                mid_y = ey + eh//2
                self.create_line(ex+2, mid_y, ex+ew-2, mid_y,
                                fill=color, width=2)

        # ── Eyebrows ──────────────────────────────────────────────────────
        brow_y = ey - 6
        if self.state == "thinking":
            # Furrowed brows
            self.create_line(ex_l-1, brow_y+2, ex_l+ew+1, brow_y-1,
                            fill="#4a3020", width=3, smooth=True)
            self.create_line(ex_r-1, brow_y-1, ex_r+ew+1, brow_y+2,
                            fill="#4a3020", width=3, smooth=True)
        else:
            self.create_line(ex_l-1, brow_y, ex_l+ew+1, brow_y,
                            fill="#2a1a10", width=3)
            self.create_line(ex_r-1, brow_y, ex_r+ew+1, brow_y,
                            fill="#2a1a10", width=3)

        # ── Nose ──────────────────────────────────────────────────────────
        nx, ny = cx - 3, cy + 4
        self.create_line(nx, ny-6, nx+1, ny+4,
                        fill="#2a1810", width=2)
        self.create_arc(nx-5, ny, nx+11, ny+8,
                       start=200, extent=140,
                       style="arc", outline="#2a1810", width=1)

        # ── Mouth / expression ────────────────────────────────────────────
        my = cy + int(face_r * 0.38)

        if self.state == "idle":
            # Fuller lips, slight smile
            self.create_oval(cx-14, my-3, cx+14, my+9,
                            fill="#5a2a25", outline="#3a1815", width=1)
            self.create_line(cx-13, my+3, cx+13, my+3,
                            fill="#2a1010", width=2)
        elif self.state == "speaking":
            # Open mouth + animated
            phase = math.sin(self._breath_phase * 4)
            h = int(8 + phase * 4)
            self.create_oval(cx-10, my-2, cx+10, my+h,
                            fill="#0a0505", outline="#4a3020", width=2)
            # Teeth hint
            self.create_line(cx-7, my+2, cx+7, my+2,
                            fill="#cccccc", width=1)
        elif self.state == "thinking":
            # Pursed lips
            self.create_line(cx-10, my+2, cx+10, my+2,
                            fill="#4a3020", width=2)
        elif self.state == "error":
            self.create_arc(cx-14, my, cx+14, my+12,
                           start=20, extent=140,
                           style="arc", outline=RED, width=2)
        elif self.state == "night":
            self.create_arc(cx-14, my-4, cx+14, my+10,
                           start=210, extent=120,
                           style="arc", outline=NEON_PURP, width=2)

        # ── Goatee / facial hair ──────────────────────────────────────────
        beard_y = my + 6
        self.create_arc(cx-10, beard_y, cx+10, beard_y+10,
                       start=0, extent=180,
                       fill="#0a0505", outline="#0a0505")

        # Mustache
        must_y = my - 6
        self.create_arc(cx-10, must_y, cx, must_y+5,
                       start=180, extent=170,
                       style="arc", outline="#1a0f0a", width=2)
        self.create_arc(cx, must_y, cx+10, must_y+5,
                       start=350, extent=170,
                       style="arc", outline="#1a0f0a", width=2)

        # ── HUD elements (JARVIS overlay) ─────────────────────────────────
        # Corner brackets
        b = r + 6
        bracket_len = 12
        bracket_color = color
        # Top-left
        self.create_line(cx-b, cy-b, cx-b+bracket_len, cy-b,
                        fill=bracket_color, width=1)
        self.create_line(cx-b, cy-b, cx-b, cy-b+bracket_len,
                        fill=bracket_color, width=1)
        # Top-right
        self.create_line(cx+b, cy-b, cx+b-bracket_len, cy-b,
                        fill=bracket_color, width=1)
        self.create_line(cx+b, cy-b, cx+b, cy-b+bracket_len,
                        fill=bracket_color, width=1)
        # Bottom-left
        self.create_line(cx-b, cy+b, cx-b+bracket_len, cy+b,
                        fill=bracket_color, width=1)
        self.create_line(cx-b, cy+b, cx-b, cy+b-bracket_len,
                        fill=bracket_color, width=1)
        # Bottom-right
        self.create_line(cx+b, cy+b, cx+b-bracket_len, cy+b,
                        fill=bracket_color, width=1)
        self.create_line(cx+b, cy+b, cx+b, cy+b-bracket_len,
                        fill=bracket_color, width=1)

        # Scan line (thinking state)
        if self.state == "thinking":
            scan_y = cy - r + int((self._ring_angle / 360) * (r * 2))
            scan_y = max(cy - r + 5, min(cy + r - 5, scan_y))
            self.create_line(cx-r+5, scan_y, cx+r-5, scan_y,
                            fill=ORANGE, width=1, stipple="gray50")

        # ── Floating particles ────────────────────────────────────────────
        for p in self._particles:
            alpha = int(p["life"] * 255)
            x, y, s = int(p["x"]), int(p["y"]), p["size"]
            dist = math.sqrt((x-cx)**2 + (y-cy)**2)
            if dist < r + 20:
                self.create_oval(x-s, y-s, x+s, y+s,
                                fill=NEON_GREEN if p["life"] > 0.5 else NEON_PURP,
                                outline="")


# ── Chat message widget ───────────────────────────────────────────────────────

class ChatMessage(ctk.CTkFrame):

    def __init__(self, parent, role: str, text: str, ts: str,
                 on_edit=None, **kwargs):
        is_user = (role == "user")
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._text    = text
        self._on_edit = on_edit
        self._is_user = is_user

        bubble = ctk.CTkFrame(
            self,
            fg_color=BG_CARD if is_user else "transparent",
            corner_radius=14,
            border_width=1 if not is_user else 0,
            border_color=BORDER,
        )
        if is_user:
            bubble.pack(anchor="e", padx=(80, 8), pady=3)
        else:
            bubble.pack(anchor="w", padx=(8, 80), pady=3)

        # Role + action row
        top_row = ctk.CTkFrame(bubble, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(10, 2))

        ctk.CTkLabel(
            top_row,
            text="you" if is_user else "◈ TAD",
            font=("Segoe UI", 10, "bold"),
            text_color=MID_GREEN if is_user else NEON_PURP,
        ).pack(side="left")

        # Copy button
        copy_btn = ctk.CTkButton(
            top_row, text="⎘", width=24, height=20,
            font=("Segoe UI", 10),
            fg_color="transparent", hover_color=BG_HOVER,
            text_color=TEXT_DIM, corner_radius=4,
            command=self._copy_text
        )
        copy_btn.pack(side="right")

        # Edit button (user messages only)
        if is_user and on_edit:
            edit_btn = ctk.CTkButton(
                top_row, text="✎", width=24, height=20,
                font=("Segoe UI", 10),
                fg_color="transparent", hover_color=BG_HOVER,
                text_color=TEXT_DIM, corner_radius=4,
                command=self._edit_message
            )
            edit_btn.pack(side="right", padx=(0, 4))

        # Message text
        ctk.CTkLabel(
            bubble,
            text=text,
            font=("Segoe UI", 13),
            text_color=TEXT_PRI,
            wraplength=400,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(0, 4))

        # Timestamp
        ctk.CTkLabel(
            bubble,
            text=ts,
            font=("Segoe UI", 9),
            text_color=TEXT_DIM,
        ).pack(anchor="e", padx=14, pady=(0, 8))

    def _copy_text(self):
        self.clipboard_clear()
        self.clipboard_append(self._text)

    def _edit_message(self):
        if self._on_edit:
            self._on_edit(self._text)


class WorkingIndicator(ctk.CTkFrame):
    """Shows what TAD is actively working on."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._dots     = 0
        self._label    = None
        self._timer    = None
        self._visible  = False

    def show(self, text: str = "thinking"):
        self._visible = True
        if self._label:
            self._label.destroy()

        self._frame = ctk.CTkFrame(
            self,
            fg_color=BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=NEON_PURP,
        )
        self._frame.pack(anchor="w", padx=(8, 80), pady=3)

        self._label = ctk.CTkLabel(
            self._frame,
            text=f"◈ TAD  ·  {text}",
            font=("Segoe UI", 12),
            text_color=NEON_PURP,
        )
        self._label.pack(padx=14, pady=10)
        self._animate(text)

    def update_text(self, text: str):
        if self._label and self._visible:
            self._label.configure(text=f"◈ TAD  ·  {text}")

    def _animate(self, base: str):
        if not self._visible:
            return
        self._dots = (self._dots + 1) % 4
        dots = "." * self._dots
        if self._label:
            self._label.configure(text=f"◈ TAD  ·  {base}{dots}")
        self._timer = self.after(400, lambda: self._animate(base))

    def hide(self):
        self._visible = False
        if self._timer:
            self.after_cancel(self._timer)
        if hasattr(self, "_frame"):
            self._frame.destroy()


# ── Main App ──────────────────────────────────────────────────────────────────

class TADApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("TAD — sovereign agent")
        self.geometry("900x920")
        self.minsize(780, 720)
        self.configure(fg_color=BG_DEEP)

        self.conversation       = []
        self.msg_queue          = queue.Queue()
        self.speaking           = False
        self._first_interaction = True
        self._voice_active      = False
        self._thinking          = False   # blocks input while processing

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
        # ── Top bar ───────────────────────────────────────────────────────
        topbar = ctk.CTkFrame(self, fg_color=BG_SURFACE,
                              corner_radius=0, height=50)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        ctk.CTkLabel(
            topbar, text="◈  TAD",
            font=("Segoe UI", 15, "bold"),
            text_color=NEON_GREEN
        ).pack(side="left", padx=20)

        ctk.CTkLabel(
            topbar, text="sovereign agent  ·  claude haiku + kimi k2",
            font=("Segoe UI", 10),
            text_color=TEXT_DIM
        ).pack(side="left", padx=4)

        self.status_pill = ctk.CTkLabel(
            topbar, text="◉  idle",
            fg_color=BG_HOVER, text_color=NEON_GREEN,
            corner_radius=20, font=("Segoe UI", 11),
            padx=14, pady=4
        )
        self.status_pill.pack(side="right", padx=20)

        # ── Main layout ───────────────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        main.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(main, fg_color=BG_SURFACE,
                               corner_radius=0, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        chat_col = ctk.CTkFrame(main, fg_color=BG_BASE, corner_radius=0)
        chat_col.pack(side="left", fill="both", expand=True)
        self._build_chat(chat_col)

    def _build_sidebar(self, p):
        # Face
        face_frame = ctk.CTkFrame(p, fg_color="transparent")
        face_frame.pack(fill="x", pady=(20, 0))

        self.face = TADFace(face_frame, size=160)
        self.face.pack(anchor="center")

        ctk.CTkLabel(
            face_frame, text="T  A  D",
            font=("Segoe UI", 17, "bold"),
            text_color=NEON_GREEN
        ).pack(pady=(10, 2))

        self.face_subtitle = ctk.CTkLabel(
            face_frame, text="always running",
            font=("Segoe UI", 10),
            text_color=TEXT_DIM
        )
        self.face_subtitle.pack()

        ctk.CTkFrame(p, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=14)

        # ── Agents section ────────────────────────────────────────────────
        # WHAT THIS DOES: shows which AI agent is currently active
        ctk.CTkLabel(p, text="AGENTS",
                    font=("Segoe UI", 9, "bold"),
                    text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(0, 6))

        self.agent_dots = {}
        agents = [
            ("market",   "Market",   "Scans loopholes + opportunities"),
            ("decision", "Decision", "Scores + kills weak ideas"),
            ("build",    "Build",    "Codes and ships products"),
            ("ceo",      "CEO",      "GO/NO-GO decisions"),
            ("cseo",     "CSEO",     "Self-evolves TAD overnight"),
            ("ops",      "Ops",      "Hourly system health check"),
        ]
        for key, label, tooltip in agents:
            row = ctk.CTkFrame(p, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)

            ctk.CTkLabel(row, text=label,
                        font=("Segoe UI", 11),
                        text_color=TEXT_SEC).pack(side="left")

            dot = ctk.CTkLabel(row, text="●",
                              font=("Segoe UI", 10),
                              text_color=TEXT_DIM)
            dot.pack(side="right")
            self.agent_dots[key] = dot

        ctk.CTkFrame(p, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=14)

        # ── Quick actions ─────────────────────────────────────────────────
        # WHAT THIS DOES: one-click commands to the most common tasks
        ctk.CTkLabel(p, text="ACTIONS",
                    font=("Segoe UI", 9, "bold"),
                    text_color=TEXT_DIM).pack(anchor="w", padx=16, pady=(0, 6))

        actions = [
            ("⟳  Market Scan",   "run a market scan and find the best opportunity right now"),
            ("◈  CEO Briefing",   "give me today's CEO briefing summary"),
            ("⚡  Ops Check",     "run a full system health check"),
            ("◎  CSEO Evolve",   "run cseo evolution cycle and fix all broken things"),
            ("$  P&L Report",    "generate a full profit and loss report"),
        ]
        for label, cmd in actions:
            btn = ctk.CTkButton(
                p, text=label,
                font=("Segoe UI", 11), height=30,
                fg_color="transparent",
                hover_color=BG_HOVER,
                text_color=TEXT_SEC, anchor="w",
                corner_radius=6,
                command=lambda c=cmd: self._quick_action(c)
            )
            btn.pack(fill="x", padx=8, pady=1)

        ctk.CTkFrame(p, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=14)

        # Dashboard button — opens visual command center
        self._dashboard_btn = ctk.CTkButton(
            p, text="⬡  Dashboard",
            font=("Segoe UI", 11, "bold"), height=36,
            fg_color="#0a1a20",
            hover_color="#112a30",
            text_color="#1ecfaa",
            border_color="#1ecfaa",
            border_width=1,
            corner_radius=8,
            command=self._open_dashboard
        )
        self._dashboard_btn.pack(fill="x", padx=12, pady=(0, 4))

        # Night mode button
        # WHAT THIS DOES: starts autonomous build mode — TAD works all night
        self.night_btn = ctk.CTkButton(
            p, text="🌙  Night Mode",
            font=("Segoe UI", 12, "bold"), height=40,
            fg_color=MID_PURP,
            hover_color=NEON_PURP,
            text_color=WHITE,
            corner_radius=10,
            command=self._start_night_mode
        )
        self.night_btn.pack(fill="x", padx=12, pady=4)

    def _build_chat(self, p):
        # Chat header
        header = ctk.CTkFrame(p, fg_color="transparent", height=44)
        header.pack(fill="x", padx=20, pady=(12, 0))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="Chat",
                    font=("Segoe UI", 14, "bold"),
                    text_color=TEXT_PRI).pack(side="left")

        self.ctx_label = ctk.CTkLabel(
            header, text="",
            font=("Segoe UI", 10),
            text_color=TEXT_DIM
        )
        self.ctx_label.pack(side="right")

        # Scrollable chat
        # WHAT THIS DOES: all conversation history between you and TAD
        self.chat_scroll = ctk.CTkScrollableFrame(
            p, fg_color="transparent",
            scrollbar_button_color=BG_SURFACE,
        )
        self.chat_scroll.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        # Welcome
        self._sys_msg(
            "TAD online.  Market scan ready.  "
            "Type below or press Ctrl+M for hands-free voice."
        )

        # Working indicator (shows live progress)
        # WHAT THIS DOES: shows exactly what TAD is doing while you wait
        self.working = WorkingIndicator(self.chat_scroll)
        self.working.pack(fill="x")

        # ── Input panel ───────────────────────────────────────────────────
        # WHAT THIS DOES: everything below the chat — input, transcription, buttons
        input_panel = ctk.CTkFrame(p, fg_color=BG_SURFACE,
                                   corner_radius=14,
                                   border_width=1, border_color=BORDER)
        input_panel.pack(fill="x", padx=14, pady=12)

        # Live transcription display
        # WHAT THIS DOES: shows what Whisper heard — EDIT THIS before sending
        transcript_header = ctk.CTkFrame(input_panel, fg_color="transparent")
        self._transcript_header = transcript_header

        ctk.CTkLabel(
            transcript_header,
            text="🎙  Whisper heard this — edit before sending:",
            font=("Segoe UI", 10),
            text_color=NEON_GREEN,
        ).pack(side="left", padx=4)

        ctk.CTkButton(
            transcript_header,
            text="✕ discard",
            font=("Segoe UI", 10),
            width=70, height=22,
            fg_color="transparent",
            hover_color=BG_HOVER,
            text_color=RED,
            corner_radius=4,
            command=self._discard_transcript,
        ).pack(side="right", padx=4)

        self.transcript_box = ctk.CTkTextbox(
            input_panel,
            height=70,
            font=("Segoe UI", 13),
            fg_color=BG_DEEP,
            text_color=TEXT_PRI,
            border_color=NEON_GREEN,
            border_width=2,
            corner_radius=8,
            wrap="word",
        )
        # Hidden by default — shows when voice captures something
        self._transcript_visible = False

        # Main input row
        input_row = ctk.CTkFrame(input_panel, fg_color="transparent")
        input_row.pack(fill="x", padx=12, pady=(12, 6))

        self.input_box = ctk.CTkEntry(
            input_row,
            placeholder_text="Message TAD...",
            font=("Segoe UI", 13),
            fg_color=BG_BASE,
            border_color=BORDER,
            text_color=TEXT_PRI,
            placeholder_text_color=TEXT_DIM,
            corner_radius=8, height=42,
        )
        self.input_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_box.bind("<Return>", self._on_enter)
        self.transcript_box.bind("<Return>", self._on_transcript_enter)

        # Button row
        btn_row = ctk.CTkFrame(input_panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        # SEND button — disabled while thinking
        self.send_btn = ctk.CTkButton(
            btn_row, text="Send  ↵",
            font=("Segoe UI", 12, "bold"), height=38, width=110,
            fg_color=NEON_GREEN,
            hover_color=MID_GREEN,
            text_color=BG_DEEP,
            corner_radius=8,
            command=self._on_send
        )
        self.send_btn.pack(side="right")

        self.vloop_btn = ctk.CTkButton(
            btn_row, text="🔊  Hands-free",
            font=("Segoe UI", 11), height=38,
            fg_color=BG_HOVER, hover_color=BG_CARD,
            text_color=TEXT_SEC, corner_radius=8,
            command=self._toggle_voice_loop
        )
        self.vloop_btn.pack(side="right", padx=(0, 8))

        self.mic_btn = ctk.CTkButton(
            btn_row, text="🎙  Speak",
            font=("Segoe UI", 11), height=38,
            fg_color=BG_HOVER, hover_color=BG_CARD,
            text_color=TEXT_SEC, corner_radius=8,
            command=self._toggle_voice
        )
        self.mic_btn.pack(side="right", padx=(0, 8))

    # ── Chat helpers ──────────────────────────────────────────────────────────

    def _sys_msg(self, text: str):
        ctk.CTkLabel(
            self.chat_scroll, text=text,
            font=("Segoe UI", 11),
            text_color=TEXT_DIM,
            wraplength=500, justify="center",
        ).pack(pady=(16, 8))

    def _append_chat(self, role: str, text: str):
        if not text or not text.strip():
            return
        ts  = datetime.now().strftime("%H:%M")
        # Save to chat history
        self._save_chat_message(role, text, ts)

        def on_edit(original_text):
            self.input_box.delete(0, "end")
            self.input_box.insert(0, original_text)
            self.input_box.focus()

        msg = ChatMessage(
            self.chat_scroll, role, text, ts,
            on_edit=on_edit if role == "user" else None
        )
        msg.pack(fill="x", pady=2)
        self.after(60, lambda: self.chat_scroll._parent_canvas.yview_moveto(1.0))

    def _save_chat_message(self, role: str, text: str, ts: str):
        """Save every message to chat history."""
        history_dir = ROOT / "memory" / "chat_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        path  = history_dir / f"chat_{today}.jsonl"
        entry = {"ts": ts, "date": today, "role": role, "text": text}
        with open(path, "a", encoding="utf-8") as f:
            import json as _json
            f.write(_json.dumps(entry) + "\n")

    # ── Input handling ────────────────────────────────────────────────────────

    def _on_enter(self, event=None):
        if not self._thinking:
            self._on_send()

    def _on_transcript_enter(self, event=None):
        """Press Enter in transcript box to send it."""
        self._send_transcript()
        return "break"  # prevent newline in textbox

    def _on_send(self):
        if self._thinking:
            return
        text = self.input_box.get().strip()
        if not text:
            return
        self.input_box.delete(0, "end")
        self._handle_input(text)

    def _quick_action(self, cmd: str):
        if not self._thinking:
            self._handle_input(cmd)

    def _handle_input(self, text: str):
        if self._first_interaction:
            self._first_interaction = False
            self.after(200, self._check_on_wake)

        self._append_chat("user", text)
        self._lock_input()  # block more input while thinking
        self._set_status("thinking", text[:50])

        is_task = any(k in text.lower() for k in TASK_KEYWORDS)
        if is_task:
            self.working.show("routing to agent")
            threading.Thread(
                target=self._run_agent, args=(text,), daemon=True
            ).start()
        else:
            self.working.show("thinking")
            threading.Thread(
                target=self._call_claude, args=(text,), daemon=True
            ).start()

    def _lock_input(self):
        """Block all input while TAD is processing."""
        self._thinking = True
        self.send_btn.configure(
            state="disabled", fg_color=BG_HOVER,
            text_color=TEXT_DIM, text="thinking..."
        )
        self.input_box.configure(state="disabled")
        self.mic_btn.configure(state="disabled")

    def _unlock_input(self):
        """Re-enable input after TAD finishes."""
        self._thinking = False
        self.send_btn.configure(
            state="normal", fg_color=NEON_GREEN,
            text_color=BG_DEEP, text="Send  ↵"
        )
        self.input_box.configure(state="normal")
        self.mic_btn.configure(state="normal")
        self.input_box.focus()

    # ── Agent & Claude calls ──────────────────────────────────────────────────

    def _run_agent(self, text: str):
        try:
            def status_cb(msg):
                self.msg_queue.put(("status", msg))
            result = run_task(text, status_callback=status_cb)
            reply  = result if result and result.strip() else "Done — check workflows for full report."
            self.msg_queue.put(("reply", reply))

            # Pick up any chart/report queued by agent.py and hand it to
            # the main thread for display.
            try:
                from agent import get_last_visual
                visual = get_last_visual()
                if visual:
                    self.msg_queue.put(("visual", visual))
            except Exception as e:
                print(f"[gui] visual fetch error: {e}")
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _call_claude(self, user_text: str):
        try:
            self.conversation.append({"role": "user", "content": user_text})
            msgs = self.conversation[-20:]
            # Ensure alternating roles
            valid, last = [], None
            for m in msgs:
                if m["role"] != last:
                    valid.append(m)
                    last = m["role"]
            user_msgs = [m for m in valid if m["role"] != "system"]
            if not user_msgs:
                user_msgs = [{"role": "user", "content": user_text}]

            # Tool-use loop: lets Claude read memory/ files (read-only)
            # before answering "what happened" style questions.
            reply = ""
            for _ in range(5):
                msg = claude.messages.create(
                    model=C_MODEL, max_tokens=1024,
                    system=SYSTEM_PROMPT, messages=user_msgs,
                    tools=MEMORY_TOOL_SCHEMA,
                )
                if msg.stop_reason != "tool_use":
                    reply = "".join(
                        b.text for b in msg.content if b.type == "text"
                    )
                    break
                user_msgs = user_msgs + [{"role": "assistant", "content": msg.content}]
                results = []
                for block in msg.content:
                    if block.type != "tool_use":
                        continue
                    self.msg_queue.put(("status", f"reading memory/{block.input.get('filename', '')}"))
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     call_memory_tool(block.name, block.input),
                    })
                user_msgs = user_msgs + [{"role": "user", "content": results}]

            if reply and reply.strip():
                self.conversation.append({"role": "assistant", "content": reply})
                self._save_memory(user_text, reply)
                self.msg_queue.put(("reply", reply))
            else:
                self.msg_queue.put(("reply", "I'm here — what do you need?"))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _save_memory(self, user: str, reply: str):
        mem = ROOT / "memory"
        mem.mkdir(exist_ok=True)
        entry = {"ts": datetime.now().isoformat(), "user": user, "tad": reply}
        with open(mem / "history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # ── Voice ─────────────────────────────────────────────────────────────────

    def _toggle_voice(self):
        if self._voice_active or self._thinking:
            return
        self._voice_active = True
        self.mic_btn.configure(text="⏹  Stop", text_color=RED)
        self._set_status("thinking", "listening...")

        # Show live transcript box
        self._show_transcript_box()

        def on_transcript(text: str):
            self.after(0, lambda: self._on_transcript(text))

        def on_error(e):
            self.after(0, self._voice_done)

        start_listening(on_transcript=on_transcript, on_error=on_error)

    def _show_transcript_box(self):
        if not self._transcript_visible:
            self._transcript_header.pack(fill="x", padx=12, pady=(8, 2), before=self.send_btn.master)
            self.transcript_box.pack(fill="x", padx=12, pady=(0, 4), before=self.send_btn.master)
            self._transcript_visible = True
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("end", "🎙 Listening...")

    def _on_transcript(self, text: str):
        """
        Show transcript in editable box.
        NOTHING sends automatically — user reviews and hits Send.
        """
        self._voice_done()

        if not text or not text.strip():
            self._hide_transcript_box()
            return

        # Show transcript in the edit box
        self._show_transcript_box()
        self.transcript_box.configure(state="normal")
        self.transcript_box.delete("1.0", "end")
        self.transcript_box.insert("end", text.strip())

        # Move focus to transcript box so user can edit immediately
        self.transcript_box.focus()
        self.transcript_box.mark_set("insert", "end")

        # Update send button to use transcript
        self.send_btn.configure(
            text="Send transcript  ↵",
            command=self._send_transcript
        )
        self._set_status("idle", "Review your message — edit then Send")

    def _send_transcript(self):
        """Send the (possibly edited) transcript manually."""
        text = self.transcript_box.get("1.0", "end").strip()
        self._hide_transcript_box()
        # Restore normal send button
        self.send_btn.configure(
            text="Send  ↵",
            command=self._on_send
        )
        if text:
            self._handle_input(text)

    def _hide_transcript_box(self):
        if self._transcript_visible:
            self._transcript_header.pack_forget()
            self.transcript_box.pack_forget()
            self._transcript_visible = False

    def _discard_transcript(self):
        """Throw away the transcript and start fresh."""
        self._hide_transcript_box()
        self.send_btn.configure(text="Send  ↵", command=self._on_send)
        self._set_status("idle")

    def _voice_done(self):
        self._voice_active = False
        self.mic_btn.configure(text="🎙  Speak", text_color=TEXT_SEC)
        self._set_status("idle")

    def _toggle_voice_loop(self):
        if self._thinking:
            return
        active = toggle_voice_loop(
            on_transcript=lambda t: self.after(0, lambda: self._on_transcript(t)),
            on_status=lambda s, m: self.after(0, lambda: self._vloop_ui(s))
        )
        self._vloop_ui("active" if active else "idle")

    def _vloop_ui(self, state: str):
        if state == "active":
            self.vloop_btn.configure(text="🔊  Listening...", text_color=NEON_GREEN)
        else:
            self.vloop_btn.configure(text="🔊  Hands-free", text_color=TEXT_SEC)

    # ── Status & face ─────────────────────────────────────────────────────────

    def _set_status(self, state: str, text: str = ""):
        labels = {
            "idle":     "◉  idle",
            "thinking": "◉  thinking",
            "speaking": "◉  speaking",
            "night":    "◉  building",
            "error":    "◉  error",
        }
        colors = {
            "idle":     (BG_HOVER, NEON_GREEN),
            "thinking": (BG_HOVER, ORANGE),
            "speaking": (BG_HOVER, NEON_PURP),
            "night":    (BG_HOVER, GLOW_PURP),
            "error":    (BG_HOVER, RED),
        }
        fg, tc = colors.get(state, colors["idle"])
        self.status_pill.configure(text=labels.get(state, "◉  idle"),
                                   fg_color=fg, text_color=tc)
        self.face.set_state(state)
        if text:
            self.ctx_label.configure(text=text[:60])
            self.face_subtitle.configure(
                text=text[:30] + "..." if len(text) > 30 else text,
                text_color=tc
            )
        else:
            self.face_subtitle.configure(text="always running", text_color=TEXT_DIM)
            self.ctx_label.configure(text="")

        # Highlight active agent
        agent_keywords = {
            "market":   ["market","scan","loophole","opportunity"],
            "decision": ["score","evaluate","decision"],
            "build":    ["build","code","create"],
            "ceo":      ["briefing","strategy","ceo"],
            "cseo":     ["cseo","evolve","evolution"],
            "ops":      ["ops","health","check"],
        }
        for agent, keywords in agent_keywords.items():
            if any(k in text.lower() for k in keywords):
                for key, dot in self.agent_dots.items():
                    dot.configure(text_color=NEON_GREEN if key == agent else TEXT_DIM)
                break

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def _open_dashboard(self):
        try:
            import sys as _sys
            _sys.path.insert(0, str(ROOT))
            from tad_command_center import open_command_center
            open_command_center(parent=self, root_path=ROOT)
        except Exception as e:
            self._append_chat("system", f"Dashboard error: {e}")

    # ── Night mode ────────────────────────────────────────────────────────────

    def _start_night_mode(self):
        if night_is_running():
            self._append_chat("tad", "Night mode already running — TAD is building.")
            return
        self.night_btn.configure(text="🌙  Building...", fg_color=GLOW_PURP)
        self._set_status("night")
        self._append_chat("tad",
            "Night mode on. Building everything on the priority list. "
            "Go sleep — full report ready when you wake up.")
        self._speak_text("Night mode activated. Building while you sleep Joshua.")
        start_night_mode(
            status_callback=lambda msg: self.msg_queue.put(("night_status", msg))
        )

    # ── On-wake check ─────────────────────────────────────────────────────────

    def _check_on_wake(self):
        def _do():
            overnight = check_overnight_report()
            if overnight and overnight.get("total_built", 0) > 0:
                self.after(0, lambda: self._show_overnight(overnight))
                return
            briefing = check_pending_briefing()
            if briefing:
                self.after(0, lambda: self._show_briefing(briefing))
        threading.Thread(target=_do, daemon=True).start()

    def _show_overnight(self, report: dict):
        try:
            from tad_visual import OvernightReportDashboard
            self.after(0, lambda: OvernightReportDashboard(report))
        except Exception:
            self._append_chat("tad",
                f"Overnight: {report.get('total_built',0)} items built. "
                f"{report.get('exec_summary','')}")
        self.night_btn.configure(text="🌙  Night Mode", fg_color=MID_PURP)

    def _show_briefing(self, briefing: dict):
        try:
            from tad_visual import MorningBriefingDashboard
            self.after(0, lambda: MorningBriefingDashboard(briefing))
        except Exception:
            self._append_chat("tad",
                f"Morning briefing: {briefing.get('action_today','')}")

    def _show_visual(self, visual: dict):
        """Open a chart or report popup. Called on the main thread from
        _poll_queue after agent.get_last_visual() returns something."""
        kind = visual.get("kind")
        data = visual.get("data")
        try:
            if kind == "market":
                from tad_dashboard import show_market_chart
                show_market_chart(data)
            elif kind == "finance":
                from tad_dashboard import show_pnl_chart
                show_pnl_chart(data)
            elif kind == "ops":
                from tad_dashboard import show_ops_chart
                show_ops_chart(data)
            elif kind == "report":
                from tad_visual import show_research_report
                show_research_report(visual.get("text", ""), visual.get("user_input", ""))
        except Exception as e:
            print(f"[gui] show_visual error: {e}")

    # ── TTS ───────────────────────────────────────────────────────────────────

    def _speak_text(self, text: str):
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    def _speak(self, text: str):
        self.speaking = True
        pause_for_tad_speaking()
        try:
            tts_engine.say(text[:400])
            tts_engine.runAndWait()
        except Exception:
            pass
        self.speaking = False
        resume_after_tad_speaking()
        self.msg_queue.put(("done_speaking", None))

    # ── Queue poll ────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()

                if msg_type == "status":
                    self.working.update_text(str(data)[:60])
                    self._set_status("thinking", str(data))

                elif msg_type == "night_status":
                    if "complete" in str(data).lower():
                        self._set_status("idle")
                        self.working.hide()
                    else:
                        self._set_status("night", str(data))
                        self.working.update_text(str(data)[:60])

                elif msg_type == "reply":
                    self.working.hide()
                    self._unlock_input()
                    if data and data.strip():
                        self._append_chat("tad", data)
                        self._set_status("speaking")
                        self._speak_text(data[:400])

                elif msg_type == "visual":
                    self._show_visual(data)

                elif msg_type == "done_speaking":
                    if not night_is_running():
                        self._set_status("idle")

                elif msg_type == "error":
                    self.working.hide()
                    self._unlock_input()
                    self._set_status("error")
                    self._append_chat("tad", f"Error: {data}")

        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _register_hotkeys(self):
        try:
            keyboard.add_hotkey("ctrl+space", lambda: self.after(0, self._focus_input))
            register_hotkey(
                on_transcript=lambda t: self.after(0, lambda: self._on_transcript(t)),
                on_status=lambda s, m: self.after(0, lambda: self._vloop_ui(s))
            )
        except Exception:
            pass

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
            self._append_chat("tad",
                "Night mode still running — minimize instead to keep building.")
        else:
            self.destroy()


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not found in .env")
        sys.exit(1)
    app = TADApp()
    app.mainloop()