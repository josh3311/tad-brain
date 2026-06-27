"""
TAD — Visual Command Center  (tad_command_center.py)
Non-blocking Toplevel window. Opens alongside tad_gui.py.
All animation via after() — zero background threads for UI.
READ-ONLY: never writes to any agent file.
"""

import json
import math
import tkinter as tk
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent

# ── Design tokens — deep navy glassmorphism ────────────────────────────────────
BG        = "#010c18"   # deepest ocean floor
CARD_BG   = "#071c2e"   # glass panel surface
CARD_BG2  = "#041422"   # deeper glass (inset)
MUTED     = "#0d2e48"   # very muted navy
DIM       = "#2a5070"   # dim text
MID       = "#4a7a98"   # mid navy text
BRIGHT    = "#d4eef8"   # cold white — primary text
ERR_RED   = "#e83a50"   # crimson
TEAL      = "#00ccbb"   # liquid teal — primary brand (matches tad_gui)
PURPLE    = "#4a3acc"   # deep blue-violet — secondary

AGENTS = [
    ("market",    "#38bdf8", "Market Scout",    "LOOPHOLE DISCOVERY"),
    ("decision",  "#f59e0b", "Decision Agent",  "OPPORTUNITY SCORING"),
    ("ceo",       "#c084fc", "CEO Agent",        "STRATEGIC DIRECTION"),
    ("build",     "#34d399", "Build Agent",      "CODE GENERATION"),
    ("marketing", "#f472b6", "Marketing Agent",  "LEAD GENERATION"),
    ("finance",   "#a78bfa", "Finance Agent",    "REVENUE TRACKING"),
    ("ops",       "#1ecfaa", "Ops Agent",        "SYSTEM MONITORING"),
    ("cseo",      "#7c5cfc", "CSEO Agent",       "SELF-EVOLUTION"),
]

PIPELINE = [
    ("Scan",    "market"),
    ("Score",   "decision"),
    ("Approve", "ceo"),
    ("Build",   "build"),
    ("Pitch",   "marketing"),
    ("Invoice", "finance"),
]

# Which face items should blink (agent_key → list of item keys in _face_items)
EYE_KEYS = {
    "market":    ["eye_l", "eye_r"],
    "decision":  ["eye_l", "eye_r"],
    "ceo":       ["eye_l", "eye_r"],
    "build":     ["eye_l", "eye_r"],
    "marketing": ["dot1", "dot2"],
    "finance":   ["dollar"],
    "ops":       ["eye_l", "eye_r"],
    "cseo":      ["infinity"],
}


# ── Data helpers ───────────────────────────────────────────────────────────────

def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _tail_jsonl(path, n=10):
    """Read last n JSONL entries efficiently via backward seek."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            seek_to = max(0, size - n * 300)
            f.seek(seek_to)
            tail = f.read()
        lines = tail.decode("utf-8", errors="replace").splitlines()
        if seek_to > 0:
            lines = lines[1:]  # drop potentially truncated first line
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                    if len(entries) >= n:
                        break
                except Exception:
                    pass
        return list(reversed(entries))
    except Exception:
        return []


def _last_log_entry(agent_name):
    path = ROOT / "memory" / f"{agent_name}_log.jsonl"
    entries = _tail_jsonl(path, 1)
    if entries:
        e = entries[0]
        return e.get("ts", ""), e.get("msg", "")
    return None, ""


def _hours_since(ts_str):
    if not ts_str:
        return 9999
    try:
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now() - ts).total_seconds() / 3600
    except Exception:
        return 9999


def _darken(hex_color, factor=0.25):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(int(r * factor), int(g * factor), int(b * factor))


def _lighten(hex_color, factor=0.3):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#{:02x}{:02x}{:02x}".format(
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )


# ── CommandCenter ──────────────────────────────────────────────────────────────

class CommandCenter:

    def __init__(self, parent=None, root_path=None):
        global ROOT
        if root_path:
            ROOT = Path(root_path)

        self.win = tk.Toplevel(parent) if parent else tk.Tk()
        self.win.title("TAD — Command Center")
        self.win.geometry("920x780")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        try:
            self.win.attributes("-alpha", 0.97)
        except Exception:
            pass

        # ── State ──────────────────────────────────────────────────────────────
        self._stopped       = False
        self._bg_canvas     = None
        self._scanline_id   = None
        self._scanline_y    = 0
        self._face_canvases = {}   # agent_key → Canvas
        self._face_holders  = {}   # agent_key → holder Frame
        self._face_items    = {}   # agent_key → {item_name: canvas_id}
        self._ring_angle    = {a[0]: i * 45 for i, a in enumerate(AGENTS)}
        self._float_tick    = 0.0
        self._dot_widgets   = {}   # agent_key → (Canvas, oval_id)
        self._status_labels = {}   # agent_key → tk.Label
        self._log_labels    = {}   # agent_key → tk.Label
        self._metric_labels = {}   # key → tk.Label
        self._comms_text    = None
        self._last_comms    = []
        self._pipeline_info = {}   # stage_label → (circ, dot_id, txt_id, color)
        self._queue_frame   = None
        self._error_frame   = None
        self._error_label   = None
        self._error_shown   = False
        self._last_error_id = None
        self._clock_label   = None
        self._live_dot      = None
        self._live_on       = True

        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._setup_ui()
        self._start_animations()
        self._refresh_data()

    # ── UI assembly ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # Background canvas (grid overlay + scanline)
        self._bg_canvas = tk.Canvas(
            self.win, bg=BG, highlightthickness=0, bd=0, width=920, height=780
        )
        self._bg_canvas.place(x=0, y=0)
        grid_color = "#08182e"
        for x in range(0, 920, 40):
            self._bg_canvas.create_line(x, 0, x, 780, fill=grid_color, width=1)
        for y in range(0, 780, 40):
            self._bg_canvas.create_line(0, y, 920, y, fill=grid_color, width=1)
        # Ambient depth orbs — simulate light refraction in deep ocean
        for (ox, oy, radius, orb_color) in [
            (160, 650, 190, "#002a48"), (780, 180, 150, "#00302a"), (460, 760, 130, "#001e38"),
        ]:
            self._bg_canvas.create_oval(
                ox - radius, oy - radius, ox + radius, oy + radius,
                fill=orb_color, outline="", stipple="gray25"
            )
        self._scanline_id = self._bg_canvas.create_line(
            0, 0, 920, 0, fill=TEAL, width=1, stipple="gray12"
        )

        # Content frame (sits above the background canvas)
        self._main = tk.Frame(self.win, bg=BG)
        self._main.place(x=0, y=0, width=920, height=780)

        self._create_top_bar()
        self._create_agent_grid()
        self._create_pipeline_bar()
        self._create_bottom_row()
        self._create_product_queue()
        self._create_error_panel()

    def _create_top_bar(self):
        bar = tk.Frame(self._main, bg="#050f1c", height=52)
        bar.pack(fill=tk.X, padx=0)
        bar.pack_propagate(False)

        # Left: logo mark + title
        left = tk.Frame(bar, bg="#050f1c")
        left.pack(side=tk.LEFT, padx=14, pady=8)

        logo_c = tk.Canvas(left, width=30, height=30, bg="#050f1c",
                            highlightthickness=0, bd=0)
        logo_c.pack(side=tk.LEFT, padx=(0, 10))
        logo_c.create_rectangle(2, 2, 28, 28, fill="#041a2a", outline=TEAL, width=1)
        logo_c.create_text(15, 15, text="T", fill=TEAL, font=("Helvetica", 16, "bold"))

        tk.Label(left, text="TAD — COMMAND CENTER", bg="#050f1c",
                  fg=BRIGHT, font=("Helvetica", 12, "bold")).pack(side=tk.LEFT)

        # Right: night badge + live dot + clock
        right = tk.Frame(bar, bg="#050f1c")
        right.pack(side=tk.RIGHT, padx=14)

        tk.Label(right, text="◉ NIGHT MODE", bg="#041018",
                  fg=PURPLE, font=("Helvetica", 8, "bold"),
                  padx=8, pady=3).pack(side=tk.LEFT, padx=(0, 8))

        live_f = tk.Frame(right, bg="#031818", padx=8, pady=3)
        live_f.pack(side=tk.LEFT, padx=(0, 12))
        self._live_dot = tk.Label(live_f, text="●", bg="#031818",
                                   fg=TEAL, font=("Helvetica", 9))
        self._live_dot.pack(side=tk.LEFT)
        tk.Label(live_f, text=" LIVE", bg="#031818",
                  fg=TEAL, font=("Helvetica", 8, "bold")).pack(side=tk.LEFT)

        self._clock_label = tk.Label(right, bg="#050f1c", fg=MID,
                                      font=("Courier", 11))
        self._clock_label.pack(side=tk.LEFT)
        self._tick_clock()

    def _create_agent_grid(self):
        grid_f = tk.Frame(self._main, bg=BG)
        grid_f.pack(fill=tk.X, padx=12, pady=(4, 0))
        for col in range(4):
            grid_f.columnconfigure(col, weight=1, minsize=218)

        for i, (key, color, name, role) in enumerate(AGENTS):
            row, col = divmod(i, 4)
            card = self._create_agent_card(grid_f, key, color, name, role)
            card.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")

    def _create_agent_card(self, parent, key, color, name, role):
        # Outer frame: colored top border (2px) + card body
        outer = tk.Frame(parent, bg=color, padx=0, pady=0)
        tk.Frame(outer, bg=color, height=2).pack(fill=tk.X)
        card = tk.Frame(outer, bg=CARD_BG, padx=10, pady=8)
        card.pack(fill=tk.BOTH, expand=True)

        # Top row: face canvas + name/role stack
        top_row = tk.Frame(card, bg=CARD_BG)
        top_row.pack(fill=tk.X)

        holder = tk.Frame(top_row, bg=CARD_BG, width=56, height=58)
        holder.pack(side=tk.LEFT, padx=(0, 8))
        holder.pack_propagate(False)
        face_c = tk.Canvas(holder, width=52, height=52, bg=CARD_BG,
                            highlightthickness=0, bd=0)
        face_c.place(x=2, y=3)
        self._face_canvases[key] = face_c
        self._face_holders[key]  = holder

        items = self._draw_face(key, face_c, color)
        self._face_items[key] = items

        name_f = tk.Frame(top_row, bg=CARD_BG)
        name_f.pack(side=tk.LEFT, fill=tk.X, expand=True, anchor="center")
        tk.Label(name_f, text=name.upper(), bg=CARD_BG, fg=color,
                  font=("Helvetica", 8, "bold")).pack(anchor="w")
        tk.Label(name_f, text=role, bg=CARD_BG, fg=DIM,
                  font=("Helvetica", 7)).pack(anchor="w")

        # Status row: dot + label
        status_row = tk.Frame(card, bg=CARD_BG)
        status_row.pack(fill=tk.X, pady=(5, 0))
        dot_c = tk.Canvas(status_row, width=8, height=8, bg=CARD_BG,
                           highlightthickness=0, bd=0)
        dot_c.pack(side=tk.LEFT)
        dot_id = dot_c.create_oval(1, 1, 7, 7, fill=MUTED, outline="")
        self._dot_widgets[key] = (dot_c, dot_id)

        status_lbl = tk.Label(status_row, text="loading…", bg=CARD_BG,
                               fg=DIM, font=("Helvetica", 7))
        status_lbl.pack(side=tk.LEFT, padx=(3, 0))
        self._status_labels[key] = status_lbl

        # Last log line
        log_lbl = tk.Label(card, text="—", bg=CARD_BG, fg=DIM,
                            font=("Courier", 7), anchor="w",
                            wraplength=196, justify=tk.LEFT)
        log_lbl.pack(fill=tk.X, pady=(2, 0))
        self._log_labels[key] = log_lbl

        # Hover: brighten top border
        def on_enter(e, o=outer, c=color):
            try:
                o.configure(bg=_lighten(c, 0.35))
            except tk.TclError:
                pass

        def on_leave(e, o=outer, c=color):
            try:
                o.configure(bg=c)
            except tk.TclError:
                pass

        for w in [card, top_row, name_f, status_row, log_lbl]:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        card.bind("<Button-1>", lambda e, k=key, c=color, n=name: self._show_detail(k, c, n))
        return outer

    def _draw_face(self, key, canvas, color):
        cx, cy = 26, 26
        dk = _darken(color, 0.18)
        items = {}

        items["bg"] = canvas.create_oval(4, 4, 48, 48, fill=dk, outline="")

        if key == "market":
            items["eye_l"] = canvas.create_oval(16, 18, 21, 23, fill=color, outline="")
            items["eye_r"] = canvas.create_oval(31, 18, 36, 23, fill=color, outline="")
            items["smile"] = canvas.create_arc(16, 24, 36, 38, start=200, extent=140,
                                               style=tk.ARC, outline=color, width=2)
        elif key == "decision":
            items["eye_l"] = canvas.create_rectangle(15, 19, 22, 25, fill=color, outline="")
            items["eye_r"] = canvas.create_rectangle(30, 19, 37, 25, fill=color, outline="")
            items["brow_l"] = canvas.create_line(14, 14, 23, 18, fill=color, width=2)
            items["brow_r"] = canvas.create_line(29, 18, 38, 14, fill=color, width=2)
            items["mouth"]  = canvas.create_line(19, 33, 33, 33, fill=color, width=2)
        elif key == "ceo":
            pts = [18, 22, 22, 13, 26, 19, 30, 13, 34, 22, 18, 22]
            items["crown"]  = canvas.create_polygon(pts, fill=color, outline="")
            items["eye_l"]  = canvas.create_oval(18, 26, 23, 31, fill=color, outline="")
            items["eye_r"]  = canvas.create_oval(29, 26, 34, 31, fill=color, outline="")
        elif key == "build":
            items["body"]   = canvas.create_rectangle(16, 14, 36, 38,
                                                       fill="", outline=color, width=2)
            items["line1"]  = canvas.create_line(19, 20, 33, 20, fill=color, width=1)
            items["line2"]  = canvas.create_line(19, 25, 29, 25, fill=color, width=1)
            items["line3"]  = canvas.create_line(19, 30, 31, 30, fill=color, width=1)
            items["eye_l"]  = canvas.create_rectangle(18, 15, 22, 18, fill=color, outline="")
            items["eye_r"]  = canvas.create_rectangle(30, 15, 34, 18, fill=color, outline="")
        elif key == "marketing":
            items["wave"]  = canvas.create_arc(12, 20, 40, 40, start=0, extent=180,
                                               style=tk.ARC, outline=color, width=2)
            items["dot1"]  = canvas.create_oval(17, 12, 22, 17, fill=color, outline="")
            items["dot2"]  = canvas.create_oval(27, 9, 32, 14, fill=color, outline="")
            items["dot3"]  = canvas.create_oval(37, 13, 42, 18, fill=color, outline="")
        elif key == "finance":
            items["dollar"] = canvas.create_text(cx, cy, text="$", fill=color,
                                                  font=("Helvetica", 20, "bold"))
            items["vline"]  = canvas.create_line(cx, 9, cx, 43, fill=color, width=2)
        elif key == "ops":
            items["ring_m"]  = canvas.create_oval(10, 10, 42, 42, fill="",
                                                   outline=color, width=1)
            items["cross_h"] = canvas.create_line(10, 26, 42, 26, fill=color, width=1)
            items["cross_v"] = canvas.create_line(26, 10, 26, 42, fill=color, width=1)
            items["dot_n"]   = canvas.create_oval(24, 4, 28, 8, fill=color, outline="")
            items["eye_l"]   = canvas.create_oval(20, 23, 25, 27, fill=color, outline="")
            items["eye_r"]   = canvas.create_oval(27, 23, 32, 27, fill=color, outline="")
        elif key == "cseo":
            items["infinity"] = canvas.create_text(cx, cy + 1, text="∞", fill=color,
                                                    font=("Helvetica", 22, "bold"))
            items["center"]   = canvas.create_oval(24, 24, 28, 28, fill=color, outline="")

        # Rotating rings (drawn last so they appear on top)
        items["ring_inner"] = canvas.create_arc(
            8, 8, 44, 44, start=0, extent=240, style=tk.ARC,
            outline=color, width=1.5
        )
        items["ring_outer"] = canvas.create_arc(
            2, 2, 50, 50, start=45, extent=295, style=tk.ARC,
            outline=color, width=1, dash=(5, 5)
        )
        return items

    def _create_pipeline_bar(self):
        bar = tk.Frame(self._main, bg="#040f1e", height=52)
        bar.pack(fill=tk.X, padx=12, pady=(4, 0))
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg="#040f1e")
        inner.pack(expand=True)

        color_map = {a[0]: a[1] for a in AGENTS}
        for i, (label, agent) in enumerate(PIPELINE):
            color = color_map.get(agent, PURPLE)

            circ = tk.Canvas(inner, width=40, height=40, bg="#040f1e",
                              highlightthickness=0, bd=0)
            circ.pack(side=tk.LEFT)
            dot_id = circ.create_oval(3, 3, 37, 37, fill="#081828",
                                       outline=MUTED, width=2)
            txt_id = circ.create_text(20, 20, text=label[:3].upper(),
                                       fill=DIM, font=("Helvetica", 7, "bold"))
            self._pipeline_info[label] = (circ, dot_id, txt_id, color)

            if i < len(PIPELINE) - 1:
                arrow = tk.Canvas(inner, width=26, height=40, bg="#040f1e",
                                   highlightthickness=0, bd=0)
                arrow.pack(side=tk.LEFT)
                arrow.create_line(4, 20, 20, 20, fill=MUTED, width=1.5,
                                   arrow=tk.LAST, arrowshape=(5, 7, 3))

    def _create_bottom_row(self):
        row = tk.Frame(self._main, bg=BG)
        row.pack(fill=tk.X, padx=12, pady=(4, 0))
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)

        # Metrics (left)
        metrics_f = tk.Frame(row, bg=CARD_BG, padx=12, pady=10)
        metrics_f.grid(row=0, column=0, padx=(0, 3), sticky="nsew")

        tk.Label(metrics_f, text="METRICS", bg=CARD_BG, fg=TEAL,
                  font=("Helvetica", 8, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5)
        )

        metric_defs = [
            ("scans_tonight", "Scans tonight",  "0"),
            ("go_verdicts",   "GO verdicts",     "0"),
            ("skills_built",  "Skills built",    "0"),
            ("api_spend",     "API spend",        "$0.00"),
        ]
        for i, (mkey, mlabel, default) in enumerate(metric_defs):
            r, c = divmod(i, 2)
            cell = tk.Frame(metrics_f, bg=CARD_BG2, padx=8, pady=5)
            cell.grid(row=r + 1, column=c, padx=2, pady=2, sticky="nsew")
            metrics_f.columnconfigure(c, weight=1)
            val_lbl = tk.Label(cell, text=default, bg=CARD_BG2, fg=BRIGHT,
                                font=("Helvetica", 18, "bold"))
            val_lbl.pack(anchor="w")
            tk.Label(cell, text=mlabel, bg=CARD_BG2, fg=DIM,
                      font=("Helvetica", 7)).pack(anchor="w")
            self._metric_labels[mkey] = val_lbl

        # Comms feed (right)
        comms_f = tk.Frame(row, bg=CARD_BG, pady=8)
        comms_f.grid(row=0, column=1, padx=(3, 0), sticky="nsew")

        tk.Label(comms_f, text="AGENT COMMS", bg=CARD_BG, fg=TEAL,
                  font=("Helvetica", 8, "bold"), padx=10).pack(anchor="w", pady=(0, 3))

        self._comms_text = tk.Text(
            comms_f, bg="#04111e", fg=MID,
            font=("Courier", 7), height=8, wrap=tk.WORD,
            relief=tk.FLAT, bd=0, state=tk.DISABLED, padx=6, pady=4,
        )
        self._comms_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        color_map = {a[0]: a[1] for a in AGENTS}
        for akey, acolor in color_map.items():
            self._comms_text.tag_config(f"a_{akey}", foreground=acolor)
        self._comms_text.tag_config("ts", foreground=DIM)

    def _create_product_queue(self):
        frame = tk.Frame(self._main, bg=BG)
        frame.pack(fill=tk.X, padx=12, pady=(5, 4))

        tk.Label(frame, text="PRODUCT QUEUE", bg=BG, fg=TEAL,
                  font=("Helvetica", 8, "bold")).pack(anchor="w", pady=(0, 3))

        self._queue_frame = tk.Frame(frame, bg=BG)
        self._queue_frame.pack(fill=tk.X)

    def _create_error_panel(self):
        self._error_frame = tk.Frame(self._main, bg="#0a0f1e", padx=12, pady=8)
        # Not packed — shown on demand via pack(fill=X)

        tk.Label(self._error_frame, text="⚠ SYSTEM ALERT", bg="#0a0f1e",
                  fg=ERR_RED, font=("Helvetica", 9, "bold")).pack(anchor="w")
        self._error_label = tk.Label(
            self._error_frame, text="", bg="#0a0f1e", fg="#e0d0d8",
            font=("Helvetica", 8), wraplength=880, justify=tk.LEFT
        )
        self._error_label.pack(anchor="w", pady=(3, 5))
        tk.Button(self._error_frame, text="Dismiss", bg="#180a14",
                   fg=ERR_RED, relief=tk.FLAT, font=("Helvetica", 8),
                   padx=10, pady=2,
                   command=self._dismiss_error).pack(anchor="e")

    # ── Animations ─────────────────────────────────────────────────────────────

    def _start_animations(self):
        self._animate_rings()
        self._animate_scanline()
        self._animate_float()
        self._animate_status_dots()
        self._animate_live_dot()
        # Staggered blinks per agent
        for i, (key, color, *_) in enumerate(AGENTS):
            self._schedule(2000 + i * 700, lambda k=key, c=color: self._blink(k, c))

    def _schedule(self, delay, fn):
        if self._stopped:
            return
        try:
            self.win.after(delay, fn)
        except tk.TclError:
            pass

    def _animate_rings(self):
        if self._stopped:
            return
        for key, color, *_ in AGENTS:
            canvas = self._face_canvases.get(key)
            items  = self._face_items.get(key, {})
            inner_id = items.get("ring_inner")
            outer_id = items.get("ring_outer")
            if canvas is None or inner_id is None:
                continue
            angle = self._ring_angle[key]
            try:
                canvas.itemconfig(inner_id, start=angle % 360)
                canvas.itemconfig(outer_id, start=(360 - int(angle * 0.65)) % 360)
            except tk.TclError:
                return
            self._ring_angle[key] = (angle + 3) % 360
        self._schedule(50, self._animate_rings)

    def _animate_scanline(self):
        if self._stopped:
            return
        self._scanline_y = (self._scanline_y + 14) % 800
        try:
            self._bg_canvas.coords(
                self._scanline_id,
                0, self._scanline_y, 920, self._scanline_y
            )
        except tk.TclError:
            return
        self._schedule(140, self._animate_scanline)

    def _animate_float(self):
        if self._stopped:
            return
        self._float_tick += 0.06
        for i, (key, *_) in enumerate(AGENTS):
            canvas = self._face_canvases.get(key)
            if canvas is None:
                continue
            offset = int(3 * math.sin(self._float_tick + i * 0.42))
            try:
                canvas.place(x=2, y=3 + offset)
            except tk.TclError:
                return
        self._schedule(50, self._animate_float)

    def _animate_status_dots(self):
        if self._stopped:
            return
        health = _read_json(ROOT / "memory" / "system_health.json")
        agents_health = health.get("agents", {})
        color_map = {a[0]: a[1] for a in AGENTS}
        pulse_on = int(self._float_tick * 10) % 2 == 0  # reuse float_tick for pulse phase

        for key, (dot_c, dot_id) in self._dot_widgets.items():
            status = agents_health.get(key, {}).get("status", "unknown")
            color  = color_map.get(key, PURPLE)
            try:
                if status == "healthy":
                    fill = color if pulse_on else _darken(color, 0.5)
                    dot_c.itemconfig(dot_id, fill=fill)
                elif status == "silent":
                    dot_c.itemconfig(dot_id, fill=ERR_RED)
                else:
                    dot_c.itemconfig(dot_id, fill=MUTED)
            except tk.TclError:
                return
        self._schedule(500, self._animate_status_dots)

    def _animate_live_dot(self):
        if self._stopped:
            return
        self._live_on = not self._live_on
        try:
            self._live_dot.config(fg=TEAL if self._live_on else _darken(TEAL, 0.4))
        except tk.TclError:
            return
        self._schedule(800, self._animate_live_dot)

    def _tick_clock(self):
        if self._stopped:
            return
        try:
            self._clock_label.config(text=datetime.now().strftime("%H:%M:%S"))
        except tk.TclError:
            return
        self._schedule(1000, self._tick_clock)

    def _blink(self, key, color):
        """Flash eyes closed for 160ms, then reschedule."""
        if self._stopped:
            return
        canvas = self._face_canvases.get(key)
        items  = self._face_items.get(key, {})
        eye_keys = EYE_KEYS.get(key, [])
        if canvas is None or not eye_keys:
            self._schedule(3500, lambda: self._blink(key, color))
            return

        closed_color = _darken(color, 0.12)

        def close_eyes():
            if self._stopped:
                return
            for ek in eye_keys:
                iid = items.get(ek)
                if iid is None:
                    continue
                try:
                    canvas.itemconfig(iid, fill=closed_color)
                except tk.TclError:
                    pass

        def open_eyes():
            if self._stopped:
                return
            for ek in eye_keys:
                iid = items.get(ek)
                if iid is None:
                    continue
                try:
                    canvas.itemconfig(iid, fill=color)
                except tk.TclError:
                    pass
            # Schedule next blink
            import random
            self._schedule(random.randint(3000, 7000), lambda: self._blink(key, color))

        close_eyes()
        self._schedule(160, open_eyes)

    # ── Data refresh ───────────────────────────────────────────────────────────

    def _refresh_data(self):
        if self._stopped:
            return
        try:
            self._refresh_agent_cards()
            self._refresh_pipeline()
            self._refresh_metrics()
            self._refresh_comms()
            self._refresh_product_queue()
            self._check_errors()
        except Exception:
            pass
        self._schedule(5000, self._refresh_data)

    def _refresh_agent_cards(self):
        health = _read_json(ROOT / "memory" / "system_health.json")
        agents_health = health.get("agents", {})
        color_map = {a[0]: a[1] for a in AGENTS}

        for key, *_ in AGENTS:
            ts, msg = _last_log_entry(key)
            status  = agents_health.get(key, {}).get("status", "—")
            color   = color_map.get(key, PURPLE)

            lbl = self._status_labels.get(key)
            if lbl:
                try:
                    if status == "healthy":
                        lbl.config(text="● active", fg=color)
                    elif status == "silent":
                        lbl.config(text="⊗ silent", fg=ERR_RED)
                    elif status == "no_activity":
                        lbl.config(text="◌ idle", fg=MUTED)
                    else:
                        lbl.config(text="— unknown", fg=DIM)
                except tk.TclError:
                    return

            log_lbl = self._log_labels.get(key)
            if log_lbl and msg:
                short = (msg[:54] + "…") if len(msg) > 54 else msg
                try:
                    log_lbl.config(text=short)
                except tk.TclError:
                    return

    def _refresh_pipeline(self):
        for label, agent_key in PIPELINE:
            info = self._pipeline_info.get(label)
            if info is None:
                continue
            circ, dot_id, txt_id, color = info
            ts, _ = _last_log_entry(agent_key)
            hours = _hours_since(ts)
            try:
                if hours <= 2:
                    circ.itemconfig(dot_id, fill=_darken(color, 0.35), outline=color)
                    circ.itemconfig(txt_id, fill=color)
                else:
                    circ.itemconfig(dot_id, fill="#12122a", outline=MUTED)
                    circ.itemconfig(txt_id, fill=DIM)
            except tk.TclError:
                return

    def _refresh_metrics(self):
        today = date.today()

        # Scans: count today's market log entries
        market_entries = _tail_jsonl(ROOT / "memory" / "market_log.jsonl", 50)
        scans = sum(
            1 for e in market_entries
            if e.get("ts", "").startswith(today.isoformat())
        )

        # GO verdicts from decisions.json
        decisions = _read_json(ROOT / "memory" / "decisions.json")
        go_count  = sum(
            1 for h in decisions.get("history", [])
            if h.get("decision") == "GO"
        )

        # Skills built today
        learned_dir = ROOT / "skills" / "learned"
        skills_today = 0
        if learned_dir.exists():
            for f in learned_dir.glob("*.py"):
                try:
                    from datetime import datetime as _dt
                    mtime = _dt.fromtimestamp(f.stat().st_mtime)
                    if mtime.date() == today:
                        skills_today += 1
                except Exception:
                    pass

        # API spend
        cost_data = _read_json(ROOT / "memory" / "session_cost.json")
        spend = cost_data.get("total_cost", cost_data.get("total", 0))
        spend_str = f"${spend:.2f}" if isinstance(spend, (int, float)) else "$—"

        vals = {
            "scans_tonight": str(scans) if scans else "0",
            "go_verdicts":   str(go_count),
            "skills_built":  str(skills_today),
            "api_spend":     spend_str,
        }
        for mkey, val in vals.items():
            lbl = self._metric_labels.get(mkey)
            if lbl:
                try:
                    lbl.config(text=val)
                except tk.TclError:
                    return

    def _refresh_comms(self):
        all_entries = []
        for key, *_ in AGENTS:
            path = ROOT / "memory" / f"{key}_log.jsonl"
            for entry in _tail_jsonl(path, 4):
                entry["_agent"] = key
                all_entries.append(entry)

        all_entries.sort(key=lambda e: e.get("ts", ""))
        last10 = all_entries[-10:]

        if last10 == self._last_comms:
            return
        self._last_comms = last10

        try:
            self._comms_text.config(state=tk.NORMAL)
            self._comms_text.delete("1.0", tk.END)
            for entry in last10:
                akey = entry.get("_agent", "")
                ts   = entry.get("ts", "")[:19].replace("T", " ")
                msg  = entry.get("msg", "")[:78]
                self._comms_text.insert(tk.END, ts + " ", "ts")
                self._comms_text.insert(tk.END, f"[{akey.upper()}] ", f"a_{akey}")
                self._comms_text.insert(tk.END, msg + "\n")
            self._comms_text.config(state=tk.DISABLED)
            self._comms_text.see(tk.END)
        except tk.TclError:
            pass

    def _refresh_product_queue(self):
        if self._queue_frame is None:
            return
        try:
            for w in self._queue_frame.winfo_children():
                w.destroy()
        except tk.TclError:
            return

        decisions = _read_json(ROOT / "memory" / "decisions.json")
        approved  = [
            h for h in decisions.get("history", [])
            if h.get("decision") in ("APPROVE", "STRONGLY APPROVE")
            and h.get("opportunity_name")
        ]
        approved.sort(key=lambda h: h.get("total_score", 0), reverse=True)

        for opp in approved[:5]:
            name   = opp.get("opportunity_name", "Unknown")
            score  = opp.get("total_score", 0)
            built  = opp.get("built", False)

            if built:
                s_txt, s_col, pill_bg = "DONE", TEAL, "#05201a"
            else:
                s_txt, s_col, pill_bg = "QUEUED", PURPLE, "#100828"

            card = tk.Frame(self._queue_frame, bg="#071520", padx=8, pady=5)
            card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3), expand=True)

            # Score ring
            ring_c = tk.Canvas(card, width=36, height=36, bg="#071520",
                                highlightthickness=0)
            ring_c.pack(side=tk.LEFT, padx=(0, 7))
            ring_color = TEAL if score >= 30 else "#f59e0b"
            ring_c.create_oval(2, 2, 34, 34, fill=_darken(ring_color, 0.3),
                                outline=ring_color, width=2)
            ring_c.create_text(18, 18, text=str(score), fill=ring_color,
                                font=("Helvetica", 11, "bold"))

            info_f = tk.Frame(card, bg="#071520")
            info_f.pack(side=tk.LEFT, fill=tk.X, expand=True)
            short = (name[:34] + "…") if len(name) > 34 else name
            tk.Label(info_f, text=short, bg="#071520", fg=BRIGHT,
                      font=("Helvetica", 8, "bold")).pack(anchor="w")
            tk.Label(info_f, text=s_txt, bg=pill_bg, fg=s_col,
                      font=("Helvetica", 7, "bold"), padx=5, pady=1
                      ).pack(anchor="w", pady=(2, 0))

    def _check_errors(self):
        error_data = _read_json(ROOT / "memory" / "error_log.json")
        errors     = error_data.get("errors", [])
        unresolved = [e for e in errors
                      if not e.get("resolved") and not e.get("interpreted")]
        if not unresolved:
            if self._error_shown:
                try:
                    self._error_frame.pack_forget()
                    self._error_shown = False
                    self._last_error_id = None
                except tk.TclError:
                    pass
            return

        err      = unresolved[0]
        err_id   = err.get("ts", "") + err.get("error", "")[:40]
        err_text = err.get("error", "Unknown error")

        if err_id == self._last_error_id:
            return  # already showing this one
        self._last_error_id = err_id

        explanation = self._explain_error(err_text)
        try:
            self._error_label.config(text=explanation)
            if not self._error_shown:
                self._error_frame.pack(fill=tk.X, padx=12, pady=(4, 0))
                self._error_shown = True
        except tk.TclError:
            pass

    def _explain_error(self, raw_error):
        try:
            import sys as _sys
            _sys.path.insert(0, str(ROOT / "skills"))
            from tad_error_interpreter import interpret_error
            return interpret_error(raw_error)
        except Exception:
            return f"Error detected. Raw: {raw_error[:120]}"

    def _dismiss_error(self):
        try:
            self._error_frame.pack_forget()
            self._error_shown = False
            self._last_error_id = None
        except tk.TclError:
            pass
        # Mark as interpreted so it won't re-surface
        try:
            path = ROOT / "memory" / "error_log.json"
            data = _read_json(path)
            changed = False
            for e in data.get("errors", []):
                if not e.get("resolved") and not e.get("interpreted"):
                    e["interpreted"] = True
                    changed = True
            if changed:
                path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ── Detail popup ───────────────────────────────────────────────────────────

    def _show_detail(self, agent_key, color, name):
        try:
            popup = tk.Toplevel(self.win)
        except tk.TclError:
            return
        popup.title(f"{name} — Last activity")
        popup.geometry("440x300")
        popup.configure(bg=BG)
        try:
            popup.grab_set()
        except tk.TclError:
            pass

        tk.Label(popup, text=name.upper(), bg=BG, fg=color,
                  font=("Helvetica", 11, "bold")).pack(pady=(14, 4))

        txt = tk.Text(popup, bg="#040e1a", fg=BRIGHT, font=("Courier", 8),
                      relief=tk.FLAT, bd=0, padx=10, pady=6)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        txt.tag_config("ts", foreground=DIM)

        path = ROOT / "memory" / f"{agent_key}_log.jsonl"
        for entry in _tail_jsonl(path, 5):
            ts  = entry.get("ts", "")[:19].replace("T", " ")
            msg = entry.get("msg", "")
            txt.insert(tk.END, ts + "  ", "ts")
            txt.insert(tk.END, msg + "\n")
        txt.config(state=tk.DISABLED)

        tk.Button(popup, text="Close", bg="#061020", fg=MID, relief=tk.FLAT,
                   font=("Helvetica", 8), padx=14, pady=3,
                   command=popup.destroy).pack(pady=(0, 10))

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def _on_close(self):
        self._stopped = True
        try:
            self.win.destroy()
        except Exception:
            pass


# ── Module-level singleton + public API ────────────────────────────────────────

_instance: "CommandCenter | None" = None


def open_command_center(parent=None, root_path=None):
    """
    Open the Command Center or bring it to front if already open.
    Positions 30px offset from the parent window.
    """
    global _instance
    try:
        if _instance is not None and _instance.win.winfo_exists():
            _instance.win.lift()
            _instance.win.focus_force()
            return _instance
    except Exception:
        _instance = None

    _instance = CommandCenter(parent=parent, root_path=root_path)

    if parent:
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            _instance.win.geometry(f"920x780+{px + 30}+{py + 30}")
        except Exception:
            pass

    return _instance


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    cc = open_command_center(root)
    root.mainloop()
