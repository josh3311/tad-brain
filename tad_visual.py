"""
TAD Visual Dashboard System
Launches popup windows for briefings, reports, and execution plans.
TAD stays small. Visuals open in separate windows.
Close when done. TAD keeps running.
"""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
import threading
import pyttsx3
import json
from pathlib import Path
from datetime import datetime


# ── TTS for narration ─────────────────────────
_tts = pyttsx3.init()
_tts.setProperty("rate", 170)
voices = _tts.getProperty("voices")
if len(voices) > 1:
    _tts.setProperty("voice", voices[1].id)


def _speak_async(text: str):
    """Speak text in background thread."""
    def _run():
        try:
            _tts.say(text[:500])
            _tts.runAndWait()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


# ── Base popup window ─────────────────────────

class TADPopup(ctk.CTkToplevel):
    """Base class for all TAD popup windows."""

    def __init__(self, title: str, width: int = 900, height: int = 650):
        super().__init__()
        self.title(f"TAD — {title}")
        self.geometry(f"{width}x{height}+100+80")
        self.configure(fg_color="#0d0d0f")
        self.resizable(True, True)
        self._build_base(title)

    def _build_base(self, title: str):
        # Top bar
        top = ctk.CTkFrame(self, fg_color="#141418", corner_radius=0, height=48)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(
            top, text=f"TAD  ·  {title}",
            font=("Courier", 13), text_color="#7f77dd"
        ).pack(side="left", padx=16)

        ctk.CTkLabel(
            top, text=datetime.now().strftime("%Y-%m-%d  %H:%M"),
            font=("Courier", 11), text_color="#444455"
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            top, text="✕  close", width=90, height=30,
            font=("Courier", 11), fg_color="#2a1e10",
            hover_color="#3a2e20", text_color="#ef9f27",
            corner_radius=6, command=self.destroy
        ).pack(side="right", padx=16, pady=8)

        # Scrollable content area
        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="#0d0d0f", corner_radius=0
        )
        self.scroll.pack(fill="both", expand=True, padx=0, pady=0)


# ── Morning Briefing Dashboard ────────────────

class MorningBriefingDashboard(TADPopup):
    """
    Opens at 7AM with:
    - Top 3 opportunities (visual score cards)
    - Hidden gem of the day
    - Competitor gaps
    - Action for today
    - Voice narration
    """

    def __init__(self, briefing_data: dict):
        super().__init__("Morning Briefing", width=960, height=700)
        self.briefing = briefing_data
        self._build_content()
        # Speak the summary after 1 second
        self.after(1000, lambda: _speak_async(
            f"Good morning Joshua. {briefing_data.get('summary', 'Your morning briefing is ready.')}"
        ))

    def _build_content(self):
        b = self.briefing
        pad = {"padx": 24, "pady": 8}

        # Header
        ctk.CTkLabel(
            self.scroll,
            text=f"Good morning, Joshua.",
            font=("Courier", 20, "bold"), text_color="#e0e0f0"
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            self.scroll,
            text=f"Here is what TAD found overnight.  {datetime.now().strftime('%A, %B %d %Y')}",
            font=("Courier", 12), text_color="#444455"
        ).pack(anchor="w", padx=24, pady=(0, 20))

        # ── Opportunities ──
        self._section_header("Top Opportunities Right Now")
        for i, opp in enumerate(b.get("opportunities", []), 1):
            self._opportunity_card(opp, i)

        # ── Hidden gem ──
        if b.get("hidden_gem"):
            self._section_header("Hidden Gem of the Day")
            self._gem_card(b["hidden_gem"])

        # ── Competitor gaps ──
        if b.get("competitor_gaps"):
            self._section_header("What Competitors Are Missing")
            for gap in b["competitor_gaps"]:
                self._gap_card(gap)

        # ── Score chart ──
        if b.get("opportunities"):
            self._section_header("Opportunity Score Chart")
            self._score_chart(b["opportunities"])

        # ── Today's action ──
        if b.get("action_today"):
            self._action_card(b["action_today"])

        # ── Raw briefing text ──
        self._section_header("Full Briefing")
        self._text_block(b.get("raw", "No briefing text available."))

        # Close button at bottom
        ctk.CTkButton(
            self.scroll, text="Done — close briefing",
            font=("Courier", 13), height=44,
            fg_color="#1e1a30", hover_color="#2a2440",
            text_color="#afa9ec", corner_radius=8,
            command=self.destroy
        ).pack(fill="x", padx=24, pady=24)

    def _section_header(self, text: str):
        ctk.CTkLabel(
            self.scroll, text=text,
            font=("Courier", 14, "bold"), text_color="#afa9ec"
        ).pack(anchor="w", padx=24, pady=(20, 6))

    def _opportunity_card(self, opp: dict, rank: int):
        card = ctk.CTkFrame(
            self.scroll, fg_color="#111115",
            border_color="#2a2a3a", border_width=1,
            corner_radius=10
        )
        card.pack(fill="x", padx=24, pady=6)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(14, 4))

        rank_colors = ["#ef9f27", "#7f77dd", "#1d9e75"]
        rc = rank_colors[rank - 1] if rank <= 3 else "#555"

        ctk.CTkLabel(
            top_row, text=f"#{rank}",
            font=("Courier", 18, "bold"), text_color=rc,
            width=40
        ).pack(side="left")

        ctk.CTkLabel(
            top_row, text=opp.get("name", "Opportunity"),
            font=("Courier", 14, "bold"), text_color="#e0e0f0"
        ).pack(side="left", padx=8)

        score = opp.get("score", 0)
        score_color = "#1d9e75" if score >= 7 else "#ef9f27" if score >= 5 else "#e24b4a"
        ctk.CTkLabel(
            top_row, text=f"  {score}/10",
            font=("Courier", 14, "bold"), text_color=score_color
        ).pack(side="right")

        ctk.CTkLabel(
            card, text=opp.get("why", ""),
            font=("Courier", 11), text_color="#8a8a9e",
            wraplength=780, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 8))

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=16, pady=(0, 14))

        ctk.CTkLabel(
            meta,
            text=f"⏱ {opp.get('time_to_revenue', 'unknown')}",
            font=("Courier", 11), text_color="#534AB7"
        ).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(
            meta,
            text=f"feasibility: {opp.get('feasibility', '?')}/10",
            font=("Courier", 11), text_color="#444455"
        ).pack(side="left")

    def _gem_card(self, gem: dict):
        card = ctk.CTkFrame(
            self.scroll, fg_color="#0a1a10",
            border_color="#1d9e75", border_width=1,
            corner_radius=10
        )
        card.pack(fill="x", padx=24, pady=6)

        ctk.CTkLabel(
            card, text=f"💎  {gem.get('name', 'Hidden Gem')}",
            font=("Courier", 14, "bold"), text_color="#1d9e75"
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            card, text=gem.get("why_overlooked", ""),
            font=("Courier", 11), text_color="#8a8a9e",
            wraplength=780, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _gap_card(self, gap: str):
        card = ctk.CTkFrame(
            self.scroll, fg_color="#100a1a",
            border_color="#534AB7", border_width=1,
            corner_radius=8
        )
        card.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(
            card, text=f"⚡  {gap}",
            font=("Courier", 11), text_color="#afa9ec",
            wraplength=800, justify="left"
        ).pack(anchor="w", padx=16, pady=12)

    def _score_chart(self, opportunities: list):
        """Simple horizontal bar chart using canvas."""
        canvas_frame = ctk.CTkFrame(
            self.scroll, fg_color="#111115",
            border_color="#1e1e28", border_width=1,
            corner_radius=10
        )
        canvas_frame.pack(fill="x", padx=24, pady=6)

        canvas = tk.Canvas(
            canvas_frame, bg="#111115",
            height=len(opportunities) * 48 + 20,
            highlightthickness=0
        )
        canvas.pack(fill="x", padx=16, pady=16)

        bar_colors = ["#ef9f27", "#7f77dd", "#1d9e75", "#534AB7", "#e24b4a"]
        max_width = 600

        for i, opp in enumerate(opportunities):
            y = i * 48 + 24
            score = opp.get("score", 5)
            bar_w = int((score / 10) * max_width)
            color = bar_colors[i % len(bar_colors)]

            # Label
            canvas.create_text(
                4, y, text=opp.get("name", "")[:30],
                anchor="w", fill="#8a8a9e",
                font=("Courier", 10)
            )
            # Background bar
            canvas.create_rectangle(
                4, y + 14, max_width + 4, y + 34,
                fill="#1e1e28", outline=""
            )
            # Score bar
            canvas.create_rectangle(
                4, y + 14, bar_w + 4, y + 34,
                fill=color, outline=""
            )
            # Score text
            canvas.create_text(
                bar_w + 10, y + 24,
                text=f"{score}/10",
                anchor="w", fill=color,
                font=("Courier", 10, "bold")
            )

    def _action_card(self, action: str):
        card = ctk.CTkFrame(
            self.scroll, fg_color="#0a1020",
            border_color="#ef9f27", border_width=2,
            corner_radius=10
        )
        card.pack(fill="x", padx=24, pady=12)

        ctk.CTkLabel(
            card, text="Your #1 Action Today",
            font=("Courier", 13, "bold"), text_color="#ef9f27"
        ).pack(anchor="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            card, text=action,
            font=("Courier", 12), text_color="#e0e0f0",
            wraplength=800, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _text_block(self, text: str):
        box = ctk.CTkTextbox(
            self.scroll, height=200,
            font=("Courier", 11), fg_color="#0a0a0d",
            text_color="#8a8a9e", border_color="#1e1e28",
            border_width=1, corner_radius=8, wrap="word",
            state="normal"
        )
        box.pack(fill="x", padx=24, pady=6)
        box.insert("end", text)
        box.configure(state="disabled")


# ── Research Report Dashboard ─────────────────

class ResearchDashboard(TADPopup):
    """Opens when TAD completes a research task."""

    def __init__(self, report_text: str, query: str):
        super().__init__("Research Report", width=920, height=680)
        self.report = report_text
        self.query = query
        self._build_content()
        self.after(800, lambda: _speak_async(
            f"Research complete. Here is what TAD found on: {query[:100]}"
        ))

    def _build_content(self):
        ctk.CTkLabel(
            self.scroll,
            text="Research Complete",
            font=("Courier", 18, "bold"), text_color="#e0e0f0"
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            self.scroll, text=f"Query: {self.query[:80]}",
            font=("Courier", 11), text_color="#534AB7"
        ).pack(anchor="w", padx=24, pady=(0, 16))

        # Full report
        box = ctk.CTkTextbox(
            self.scroll, height=480,
            font=("Courier", 11), fg_color="#0a0a0d",
            text_color="#c0c0d0", border_color="#1e1e28",
            border_width=1, corner_radius=8, wrap="word",
            state="normal"
        )
        box.pack(fill="x", padx=24, pady=6)
        box.insert("end", self.report)
        box.configure(state="disabled")

        # Action buttons
        btn_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=16)

        ctk.CTkButton(
            btn_row, text="Save to workflows",
            font=("Courier", 12), height=40,
            fg_color="#1a2820", hover_color="#2a3830",
            text_color="#1d9e75", corner_radius=8,
            command=self._save_report
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_row, text="Close",
            font=("Courier", 12), height=40,
            fg_color="#1e1e28", hover_color="#2a2a38",
            text_color="#888899", corner_radius=8,
            command=self.destroy
        ).pack(side="left")

    def _save_report(self):
        today = datetime.now().strftime("%Y-%m-%d-%H%M")
        path = Path(f"workflows/report-{today}.md")
        path.parent.mkdir(exist_ok=True)
        path.write_text(self.report, encoding="utf-8")
        _speak_async("Report saved to workflows folder.")


# ── Approval Gate popup ───────────────────────

class ApprovalGate(TADPopup):
    """
    TAD pauses and asks Joshua to approve a big decision.
    Shows what TAD wants to do, why, and waits for yes/no.
    """

    def __init__(self, action: str, reasoning: str,
                 on_approve, on_reject):
        super().__init__("Decision Required", width=700, height=400)
        self.on_approve = on_approve
        self.on_reject = on_reject
        self._build_content(action, reasoning)
        self.after(500, lambda: _speak_async(
            f"Joshua, TAD needs your approval. {action[:150]}"
        ))

    def _build_content(self, action: str, reasoning: str):
        ctk.CTkLabel(
            self.scroll,
            text="TAD needs your approval",
            font=("Courier", 16, "bold"), text_color="#ef9f27"
        ).pack(anchor="w", padx=24, pady=(24, 8))

        ctk.CTkLabel(
            self.scroll, text="Proposed action:",
            font=("Courier", 11), text_color="#555566"
        ).pack(anchor="w", padx=24, pady=(8, 2))

        ctk.CTkLabel(
            self.scroll, text=action,
            font=("Courier", 13, "bold"), text_color="#e0e0f0",
            wraplength=620, justify="left"
        ).pack(anchor="w", padx=24, pady=(0, 12))

        ctk.CTkLabel(
            self.scroll, text="Why TAD recommends this:",
            font=("Courier", 11), text_color="#555566"
        ).pack(anchor="w", padx=24, pady=(4, 2))

        ctk.CTkLabel(
            self.scroll, text=reasoning,
            font=("Courier", 11), text_color="#8a8a9e",
            wraplength=620, justify="left"
        ).pack(anchor="w", padx=24, pady=(0, 24))

        btn_row = ctk.CTkFrame(self.scroll, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=8)

        ctk.CTkButton(
            btn_row, text="✓  Approve — TAD execute",
            font=("Courier", 13, "bold"), height=48, width=280,
            fg_color="#1a2820", hover_color="#2a3830",
            text_color="#1d9e75", corner_radius=8,
            command=self._approve
        ).pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            btn_row, text="✕  Reject",
            font=("Courier", 13), height=48, width=140,
            fg_color="#2a1010", hover_color="#3a2020",
            text_color="#e24b4a", corner_radius=8,
            command=self._reject
        ).pack(side="left")

    def _approve(self):
        self.destroy()
        if self.on_approve:
            threading.Thread(target=self.on_approve, daemon=True).start()

    def _reject(self):
        self.destroy()
        if self.on_reject:
            self.on_reject()


# ── Launch helpers ────────────────────────────

def show_morning_briefing(briefing_data: dict):
    """Call from scheduler when 7AM briefing is ready."""
    def _launch():
        win = MorningBriefingDashboard(briefing_data)
        win.mainloop()
    threading.Thread(target=_launch, daemon=True).start()


def show_research_report(report_text: str, query: str):
    """Call from agent after research task completes."""
    def _launch():
        win = ResearchDashboard(report_text, query)
        win.mainloop()
    threading.Thread(target=_launch, daemon=True).start()


def show_approval_gate(action: str, reasoning: str,
                       on_approve=None, on_reject=None):
    """Call when TAD needs Joshua's approval for a big move."""
    def _launch():
        win = ApprovalGate(action, reasoning, on_approve, on_reject)
        win.mainloop()
    threading.Thread(target=_launch, daemon=True).start()


# ── Test / preview ────────────────────────────

if __name__ == "__main__":
    root = ctk.CTk()
    root.withdraw()  # hide root

    sample = {
        "summary": "Good morning Joshua. Three strong opportunities identified overnight.",
        "opportunities": [
            {
                "name": "AI Voice Agents for Dental Practices",
                "score": 9,
                "why": "Dental offices miss 30% of calls. A booking voice agent pays for itself in one month.",
                "time_to_revenue": "2-3 weeks",
                "feasibility": 9
            },
            {
                "name": "AI Workflow Automation for Law Firms",
                "score": 8,
                "why": "Document review and client intake are still 100% manual at 80% of small firms.",
                "time_to_revenue": "3-4 weeks",
                "feasibility": 7
            },
            {
                "name": "AI Content Pipeline for Real Estate Agents",
                "score": 7,
                "why": "Agents need weekly listings content but hate writing. Full automation for $500/month.",
                "time_to_revenue": "1-2 weeks",
                "feasibility": 9
            },
        ],
        "hidden_gem": {
            "name": "AI Receptionist for HVAC Companies",
            "why_overlooked": "Everyone builds for law and dental. HVAC has seasonal call spikes, zero AI penetration, and owners are desperate."
        },
        "competitor_gaps": [
            "Generic AI agencies charge $5K+ for basic automations SMBs could get for $500/month",
            "Most voice AI tools require technical setup — businesses need a done-for-you solution",
        ],
        "action_today": "Pick one niche from the top 3 above. Call two local businesses today and ask if they miss calls. That is your market validation.",
        "raw": "Full briefing details would appear here from the overnight scan..."
    }

    dash = MorningBriefingDashboard(sample)
    dash.mainloop()


# ── Overnight Report Dashboard ────────────────

class OvernightReportDashboard(TADPopup):
    """
    Shows everything TAD built overnight.
    Opens automatically on first interaction after night mode.
    """

    def __init__(self, report: dict):
        super().__init__("Overnight Build Report", width=960, height=720)
        self.report = report
        self._build_content()
        self.after(800, lambda: _speak_async(
            f"Good morning Joshua. TAD built {report.get('total_built', 0)} items overnight. "
            f"{report.get('exec_summary', '')[:150]}"
        ))

    def _build_content(self):
        r = self.report

        # Header
        ctk.CTkLabel(self.scroll,
            text="Good morning, Joshua.",
            font=("Courier", 20, "bold"), text_color="#e0e0f0"
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(self.scroll,
            text=f"TAD worked overnight.  {r.get('date', '')}",
            font=("Courier", 12), text_color="#444455"
        ).pack(anchor="w", padx=24, pady=(0, 4))

        # Stats row
        stats = ctk.CTkFrame(self.scroll, fg_color="#111115",
                             border_color="#1e1e28", border_width=1, corner_radius=10)
        stats.pack(fill="x", padx=24, pady=(8, 16))
        stats_row = ctk.CTkFrame(stats, fg_color="transparent")
        stats_row.pack(fill="x", padx=20, pady=16)

        for label, value, color in [
            ("Items built",   str(r.get("total_built", 0)),  "#1d9e75"),
            ("Files created", str(r.get("total_files", 0)),  "#afa9ec"),
            ("Items skipped", str(len(r.get("skipped", []))), "#ef9f27"),
        ]:
            col = ctk.CTkFrame(stats_row, fg_color="transparent")
            col.pack(side="left", expand=True)
            ctk.CTkLabel(col, text=value,
                font=("Courier", 28, "bold"), text_color=color).pack()
            ctk.CTkLabel(col, text=label,
                font=("Courier", 11), text_color="#555566").pack()

        # Executive summary
        if r.get("exec_summary"):
            sum_card = ctk.CTkFrame(self.scroll, fg_color="#0a1020",
                                    border_color="#534AB7", border_width=1, corner_radius=10)
            sum_card.pack(fill="x", padx=24, pady=(0, 16))
            ctk.CTkLabel(sum_card, text="TAD's summary",
                font=("Courier", 11), text_color="#534AB7"
            ).pack(anchor="w", padx=16, pady=(12, 4))
            ctk.CTkLabel(sum_card, text=r["exec_summary"],
                font=("Courier", 12), text_color="#e0e0f0",
                wraplength=880, justify="left"
            ).pack(anchor="w", padx=16, pady=(0, 14))

        # Completed items
        completed = r.get("completed", [])
        if completed:
            ctk.CTkLabel(self.scroll, text=f"What TAD built ({len(completed)})",
                font=("Courier", 14, "bold"), text_color="#1d9e75"
            ).pack(anchor="w", padx=24, pady=(8, 6))

            for item in completed:
                card = ctk.CTkFrame(self.scroll, fg_color="#0a1a10",
                                    border_color="#1d4a28", border_width=1, corner_radius=8)
                card.pack(fill="x", padx=24, pady=4)

                top = ctk.CTkFrame(card, fg_color="transparent")
                top.pack(fill="x", padx=14, pady=(10, 4))
                ctk.CTkLabel(top, text=f"✓  {item.get('item', '')}",
                    font=("Courier", 13, "bold"), text_color="#1d9e75"
                ).pack(side="left")
                ctk.CTkLabel(top, text=f"P{item.get('priority', '?')}",
                    font=("Courier", 10), text_color="#1d4a28"
                ).pack(side="right")

                if item.get("summary"):
                    ctk.CTkLabel(card, text=item["summary"],
                        font=("Courier", 11), text_color="#8a8a9e",
                        wraplength=880, justify="left"
                    ).pack(anchor="w", padx=14, pady=(0, 4))

                if item.get("files_saved"):
                    files_text = "  ".join(item["files_saved"])
                    ctk.CTkLabel(card, text=f"📄 {files_text}",
                        font=("Courier", 10), text_color="#534AB7",
                        wraplength=880, justify="left"
                    ).pack(anchor="w", padx=14, pady=(0, 4))

                if item.get("next_steps"):
                    ctk.CTkLabel(card, text=f"→ {item['next_steps']}",
                        font=("Courier", 10), text_color="#ef9f27",
                        wraplength=880, justify="left"
                    ).pack(anchor="w", padx=14, pady=(0, 10))

        # Skipped items
        skipped = r.get("skipped", [])
        if skipped:
            ctk.CTkLabel(self.scroll, text=f"Skipped ({len(skipped)})",
                font=("Courier", 13, "bold"), text_color="#ef9f27"
            ).pack(anchor="w", padx=24, pady=(16, 6))
            for item in skipped:
                ctk.CTkLabel(self.scroll, text=f"  ○  {item}",
                    font=("Courier", 11), text_color="#555566"
                ).pack(anchor="w", padx=24)

        # Close button
        ctk.CTkButton(self.scroll, text="Got it — close report",
            font=("Courier", 13), height=44,
            fg_color="#1a2820", hover_color="#2a3830",
            text_color="#1d9e75", corner_radius=8,
            command=self.destroy
        ).pack(fill="x", padx=24, pady=24)