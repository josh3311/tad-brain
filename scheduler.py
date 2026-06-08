"""
TAD — Scheduler v0.2
Runs silently in the background as a daemon thread from tad_gui.py.

Schedule:
  11:00 PM → launches night_mode.py as a subprocess (runs until 6am)
   3:00 AM → deep scan (silent market/opportunity scan)
   7:00 AM → morning briefing saved to memory/morning_briefing.json

Changes from v0.1:
  - Adds night mode launcher at 11pm
  - Night mode runs as a DETACHED subprocess so it survives GUI close
  - Adds run_status tracking so TAD can report what ran overnight
  - Fixes morning briefing actually populating with real content
"""

import json
import os
import sys
import subprocess
import threading
import time
from datetime import datetime, date
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT         = Path(__file__).parent
BRIEFING_PATH = ROOT / "memory" / "morning_briefing.json"
STATUS_PATH   = ROOT / "memory" / "scheduler_status.json"
LOG_PATH      = ROOT / "memory" / "scheduler_log.jsonl"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Scheduler] {msg}")


def _save_status(key: str, value):
    status = {}
    if STATUS_PATH.exists():
        try:
            status = json.loads(STATUS_PATH.read_text())
        except Exception:
            pass
    status[key] = value
    STATUS_PATH.write_text(json.dumps(status, indent=2))


# ── Tasks ─────────────────────────────────────────────────────────────────────

def launch_night_mode():
    """
    Launch night_mode.py as a fully detached subprocess.
    Survives GUI close. Writes its own log and report.
    """
    night_script = ROOT / "night_mode.py"
    if not night_script.exists():
        _log("ERROR: night_mode.py not found — cannot launch night mode")
        return

    _log("Launching night mode (detached subprocess)...")

    # Windows: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
    # so it keeps running even if the terminal / GUI closes
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    proc = subprocess.Popen(
        [sys.executable, str(night_script)],
        cwd=str(ROOT),
        stdout=open(ROOT / "memory" / "night_stdout.log", "a"),
        stderr=open(ROOT / "memory" / "night_stderr.log", "a"),
        creationflags=creation_flags,
    )

    _log(f"Night mode launched — PID {proc.pid}")
    _save_status("night_mode_launched", {
        "ts": datetime.now().isoformat(),
        "pid": proc.pid,
        "date": str(date.today()),
    })


def run_deep_scan():
    """3am — scan for opportunities and save to briefing."""
    _log("3AM deep scan starting...")

    monkey_text = ""
    monkey_path = ROOT / "THE_MONKEY.md"
    if monkey_path.exists():
        monkey_text = monkey_path.read_text(encoding="utf-8")[:2000]

    prompt = f"""You are TAD's research agent running a pre-dawn opportunity scan for Joshua.

TAD project context:
{monkey_text}

Scan for:
1. Top 3 high-value opportunities Joshua should know about today (market, tech, business)
2. One key risk or threat to watch
3. TAD's #1 recommended action for Joshua today

Be specific and direct. Joshua is an aspiring AI/cloud architect and entrepreneur.
Format as JSON with keys: opportunities (list), risk (string), action_today (string), summary (string)
Return ONLY valid JSON."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or "{}"
        import re
        clean = re.sub(r"```json|```", "", raw).strip()
        data  = json.loads(clean)
        _log("Deep scan complete")
        return data
    except Exception as e:
        _log(f"Deep scan error: {e}")
        return {
            "opportunities": ["Check TAD project status", "Review overnight builds"],
            "risk": "Night mode may not have run — verify scheduler logs",
            "action_today": "Review memory/night_log.jsonl and morning_briefing.json",
            "summary": "Scan encountered an error. Check logs.",
        }


def build_morning_briefing():
    """7am — assemble morning briefing from overnight data + deep scan."""
    _log("Building 7AM morning briefing...")

    # Pull overnight report if exists
    overnight = {}
    report_path = ROOT / "memory" / "overnight_report.json"
    if report_path.exists():
        try:
            overnight = json.loads(report_path.read_text())
        except Exception:
            pass

    # Pull deep scan
    scan = run_deep_scan()

    # Check scheduler status
    status = {}
    if STATUS_PATH.exists():
        try:
            status = json.loads(STATUS_PATH.read_text())
        except Exception:
            pass

    built_items  = overnight.get("built", [])
    skipped      = overnight.get("skipped", [])
    errors       = overnight.get("errors", [])
    night_ran    = bool(built_items or skipped or errors)

    # Build action item
    if built_items:
        action = f"Review {len(built_items)} new files TAD built overnight: {', '.join(i.get('item','?') for i in built_items[:3])}"
    elif not night_ran:
        action = scan.get("action_today", "Review THE_MONKEY.md and pick a priority to build today")
    else:
        action = scan.get("action_today", "Review TAD logs and continue building")

    briefing = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "greeting": f"Good morning, Joshua.",
        "night_mode_ran": night_ran,
        "built_count": len(built_items),
        "built_items": [i.get("item", "?") for i in built_items],
        "skipped": skipped,
        "errors": errors,
        "opportunities": scan.get("opportunities", []),
        "risk": scan.get("risk", ""),
        "action_today": action,
        "summary": scan.get("summary", ""),
        "full_text": _format_briefing_text(built_items, scan, night_ran),
    }

    BRIEFING_PATH.parent.mkdir(exist_ok=True)
    BRIEFING_PATH.write_text(json.dumps(briefing, indent=2))
    _log(f"Morning briefing saved → {BRIEFING_PATH}")
    return briefing


def _format_briefing_text(built_items: list, scan: dict, night_ran: bool) -> str:
    lines = []

    if night_ran and built_items:
        lines.append(f"OVERNIGHT BUILD: TAD completed {len(built_items)} items.")
        for item in built_items[:5]:
            lines.append(f"  ✓ {item.get('item', '?')} → {item.get('file', '?')}")
    else:
        lines.append("OVERNIGHT: Night mode did not run or built nothing.")
        lines.append("To enable: make sure scheduler.py is running and it is past 11pm.")

    lines.append("")
    lines.append("TOP OPPORTUNITIES:")
    for opp in scan.get("opportunities", []):
        lines.append(f"  • {opp}")

    lines.append("")
    lines.append(f"WATCH: {scan.get('risk', 'N/A')}")
    lines.append("")
    lines.append(f"YOUR #1 ACTION: {scan.get('action_today', 'N/A')}")

    return "\n".join(lines)


# ── Scheduler loop ────────────────────────────────────────────────────────────

class TADScheduler:
    """
    Runs as a daemon thread inside tad_gui.py.
    Checks the clock every 60 seconds and fires tasks at their scheduled times.
    Each task fires once per calendar day.
    """

    SCHEDULE = {
        "night_mode": (23, 0),   # 11:00 PM
        "deep_scan":  ( 3, 0),   #  3:00 AM
        "briefing":   ( 7, 0),   #  7:00 AM
    }

    def __init__(self):
        self._ran_today: dict[str, str] = {}   # task → date string
        self._thread: threading.Thread | None  = None
        self._stop = threading.Event()

    def _should_run(self, task: str, hour: int, minute: int) -> bool:
        now = datetime.now()
        today = str(date.today())
        last_ran = self._ran_today.get(task)
        return (now.hour == hour and now.minute == minute and last_ran != today)

    def _mark_ran(self, task: str):
        self._ran_today[task] = str(date.today())

    def _tick(self):
        while not self._stop.is_set():
            try:
                for task, (h, m) in self.SCHEDULE.items():
                    if self._should_run(task, h, m):
                        _log(f"Firing scheduled task: {task}")
                        self._mark_ran(task)
                        if task == "night_mode":
                            threading.Thread(target=launch_night_mode, daemon=True).start()
                        elif task == "deep_scan":
                            threading.Thread(target=run_deep_scan, daemon=True).start()
                        elif task == "briefing":
                            threading.Thread(target=build_morning_briefing, daemon=True).start()
            except Exception as e:
                _log(f"Scheduler tick error: {e}")

            self._stop.wait(60)   # check every minute

    def start(self):
        """Call this from tad_gui.py __init__ to start the scheduler."""
        self._thread = threading.Thread(target=self._tick, daemon=True, name="TADScheduler")
        self._thread.start()
        _log("Scheduler started — night mode at 11pm, deep scan at 3am, briefing at 7am")

    def stop(self):
        self._stop.set()

    def force_briefing(self):
        """Call this to generate briefing right now (for testing)."""
        return build_morning_briefing()


# ── Singleton ─────────────────────────────────────────────────────────────────
_scheduler = TADScheduler()

def start_scheduler(status_callback=None):
    """Called once from tad_gui.py on startup. status_callback is optional."""
    _scheduler.start()
    if status_callback:
        status_callback("Scheduler started — night mode at 11pm, deep scan at 3am, briefing at 7am")

def force_briefing_now():
    """For testing — generate briefing immediately regardless of time."""
    return _scheduler.force_briefing()

def check_pending_briefing():
    """Return briefing data if a morning briefing is waiting, else None."""
    if BRIEFING_PATH.exists():
        try:
            return json.loads(BRIEFING_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


if __name__ == "__main__":
    # Test mode — generate briefing immediately
    print("TAD Scheduler — test mode")
    print("Generating morning briefing now...")
    briefing = build_morning_briefing()
    print(json.dumps(briefing, indent=2))