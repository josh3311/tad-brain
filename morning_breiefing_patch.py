"""
TAD — Morning Briefing Dashboard Patch
Apply to tad_visual.py → MorningBriefingDashboard

PROBLEM: Full Briefing section shows empty box
ROOT CAUSE: The text widget isn't reading briefing["full_text"]

FIND this section in MorningBriefingDashboard (inside _build_ui or similar):
    # Full briefing text area  
    self.briefing_text = tk.Text(...)
    self.briefing_text.pack(...)

REPLACE the populate logic with this:
"""

# ── Drop-in populate method for MorningBriefingDashboard ─────────────────────
# Find your existing populate / load_briefing method and replace it with this:

POPULATE_METHOD = '''
    def _load_briefing(self):
        """Load and display briefing data from memory/morning_briefing.json"""
        briefing_path = Path("memory/morning_briefing.json")

        if not briefing_path.exists():
            self._show_no_data()
            return

        try:
            data = json.loads(briefing_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._show_no_data(f"Error reading briefing: {e}")
            return

        # ── Header ──────────────────────────────────────────────────────
        date_str = data.get("date", "")
        time_str = data.get("time", "")
        self.date_label.config(text=f"TAD  ·  Morning Briefing  {date_str}  {time_str}")

        # ── Action card ──────────────────────────────────────────────────
        action = data.get("action_today", "Review THE_MONKEY.md and pick a build priority.")
        self.action_label.config(text=action)

        # ── Full briefing text ───────────────────────────────────────────
        full_text = data.get("full_text", "")

        # Fallback: build from parts if full_text missing
        if not full_text:
            parts = []
            if data.get("night_mode_ran"):
                count = data.get("built_count", 0)
                parts.append(f"OVERNIGHT: TAD built {count} items.")
                for item in data.get("built_items", [])[:5]:
                    parts.append(f"  ✓ {item}")
            else:
                parts.append("OVERNIGHT: Night mode did not run.")
                parts.append("Check that scheduler.py started and it was past 11pm.")

            opps = data.get("opportunities", [])
            if opps:
                parts.append("")
                parts.append("TOP OPPORTUNITIES:")
                for o in opps:
                    parts.append(f"  • {o}")

            risk = data.get("risk", "")
            if risk:
                parts.append(f"\\nWATCH: {risk}")

            full_text = "\\n".join(parts)

        # Write to text widget
        self.briefing_text.config(state="normal")
        self.briefing_text.delete("1.0", "end")
        self.briefing_text.insert("1.0", full_text if full_text else "No briefing content available.\\n\\nRun: python scheduler.py to generate one now.")
        self.briefing_text.config(state="disabled")

    def _show_no_data(self, msg: str = ""):
        fallback = "No morning briefing found.\\n\\n"
        fallback += "To generate one now, run:\\n  python scheduler.py\\n\\n"
        fallback += "To enable automatic briefings:\\n"
        fallback += "  Make sure scheduler.start_scheduler() is called in tad_gui.py __init__"
        if msg:
            fallback += f"\\n\\nError: {msg}"

        self.briefing_text.config(state="normal")
        self.briefing_text.delete("1.0", "end")
        self.briefing_text.insert("1.0", fallback)
        self.briefing_text.config(state="disabled")
'''

print("Patch ready — paste POPULATE_METHOD into MorningBriefingDashboard class")
print("Also ensure these imports exist at top of tad_visual.py:")
print("  import json")
print("  from pathlib import Path")