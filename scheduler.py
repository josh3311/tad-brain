"""
TAD — Scheduler v0.3
Phase 3 — Agents wired in

Changes from v0.2:
- Market Agent runs at 3am instead of generic deep scan
- CEO Agent generates the 7am morning briefing summary
- Ops Agent runs hourly health check
- All temperatures fixed to 1 for Kimi K2
- Agents path added to sys.path
- Morning briefing now includes market opportunities + CSEO report
"""

import json
import os
import re
import sys
import subprocess
import threading
import time
from datetime import datetime, date
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

from tad_encoding import force_utf8
force_utf8()

load_dotenv()

ROOT          = Path(__file__).parent
AGENTS_DIR    = ROOT / "skills"
BRIEFING_PATH = ROOT / "memory" / "morning_briefing.json"
STATUS_PATH   = ROOT / "memory" / "scheduler_status.json"
LOG_PATH      = ROOT / "memory" / "scheduler_log.jsonl"

# Add agents to path immediately
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

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


# ── Night mode launcher ───────────────────────────────────────────────────────

def launch_night_mode():
    """Launch night_mode.py as a detached subprocess. Survives GUI close."""
    night_script = ROOT / "night_mode.py"
    if not night_script.exists():
        _log("ERROR: night_mode.py not found")
        return

    _log("Launching night mode (detached)...")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = (subprocess.CREATE_NEW_PROCESS_GROUP |
                         subprocess.DETACHED_PROCESS)

    proc = subprocess.Popen(
        [sys.executable, str(night_script)],
        cwd=str(ROOT),
        stdout=open(ROOT / "memory" / "night_stdout.log", "a"),
        stderr=open(ROOT / "memory" / "night_stderr.log", "a"),
        creationflags=creation_flags,
    )
    _log(f"Night mode launched — PID {proc.pid}")
    _save_status("night_mode_launched", {
        "ts":   datetime.now().isoformat(),
        "pid":  proc.pid,
        "date": str(date.today()),
    })


# ── 3am — Market Agent scan ───────────────────────────────────────────────────

def run_market_scan():
    """
    3am — Run Market Agent to find loopholes.
    Saves results to memory/opportunity_log.json.
    """
    _log("3AM — Market Agent scan starting...")
    try:
        from market_agent import run_full_scan
        report = run_full_scan()
        opps   = report.get("opportunities", [])
        _log(f"Market scan complete — {len(opps)} opportunities found")
        if opps:
            for opp in opps[:3]:
                _log(f"  → {opp.get('name')} (Score: {opp.get('total_score')}/40)")
        run_decision_chain(opps)
        return report
    except Exception as e:
        _log(f"Market Agent error: {e} — falling back to Kimi scan")
        return _kimi_fallback_scan()


def run_decision_chain(opportunities: list):
    """
    Market → Decision → CEO chain (THE_MONKEY.md).
    Decision Agent scores the scan's opportunities; the top approved one
    goes to the CEO Agent for a GO/KILL/ESCALATE call.
    """
    if not opportunities:
        _log("Decision chain skipped — no opportunities from market scan")
        return

    try:
        from decision_agent import score_multiple
        approved = score_multiple(opportunities)
        _log(f"Decision Agent approved {len(approved)} / {len(opportunities)} opportunities")
    except Exception as e:
        _log(f"Decision Agent error: {e}")
        return

    if not approved:
        return

    try:
        from ceo_agent import make_decision
        verdict = make_decision(approved[0], "opportunity_score")
        _log(f"CEO verdict on '{approved[0].get('opportunity_name')}': {verdict.get('decision')}")
    except Exception as e:
        _log(f"CEO Agent error: {e}")


def _kimi_fallback_scan() -> dict:
    """Fallback scan using Kimi directly if Market Agent fails."""
    monkey_text = ""
    monkey_path = ROOT / "THE_MONKEY.md"
    if monkey_path.exists():
        monkey_text = monkey_path.read_text(encoding="utf-8")[:2000]

    prompt = f"""You are TAD's market intelligence agent.

TAD mission:
{monkey_text}

Find 3 high-value AI loopholes — problems people are experiencing
that have little competition and high willingness to pay.

Return ONLY JSON:
{{
  "opportunities": [
    {{"name": "...", "problem": "...", "total_score": 0, "evidence": "..."}}
  ],
  "risk": "one key risk to watch today",
  "action_today": "TAD's #1 recommended action",
  "summary": "2 sentence summary"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=800,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        data  = json.loads(clean)
        _log("Kimi fallback scan complete")
        return data
    except Exception as e:
        _log(f"Fallback scan error: {e}")
        return {
            "opportunities": [],
            "risk":          "Check logs — market scan failed",
            "action_today":  "Run python scheduler.py to test manually",
            "summary":       "Scan failed. Check memory/scheduler_log.jsonl",
        }


# ── 7am — CEO Agent morning briefing ─────────────────────────────────────────

def build_morning_briefing():
    """
    7am — CEO Agent assembles morning briefing from all overnight data.
    Includes: builds, CSEO skills, market opportunities, financials.
    """
    _log("7AM — Building morning briefing...")

    # Pull overnight report
    overnight    = {}
    report_path  = ROOT / "memory" / "overnight_report.json"
    if report_path.exists():
        try:
            overnight = json.loads(report_path.read_text())
        except Exception:
            pass

    built_items   = overnight.get("built", [])
    cseo_report   = overnight.get("cseo_evolution", {})
    market_report = overnight.get("market_scan", {})
    game_changers = overnight.get("game_changers", [])
    night_ran     = bool(built_items or overnight.get("skipped") or overnight.get("errors"))

    # Get market opportunities
    opps = market_report.get("opportunities", [])
    if not opps:
        # Try reading from opportunity log
        opp_path = ROOT / "memory" / "opportunity_log.json"
        if opp_path.exists():
            try:
                opp_data = json.loads(opp_path.read_text())
                opps = opp_data.get("opportunities", [])[-3:]
            except Exception:
                pass

    # Try CEO Agent for summary
    ceo_summary = _get_ceo_summary(built_items, opps, cseo_report)

    # Build action item
    if game_changers:
        action = f"🚨 GAME-CHANGING DISCOVERY: {game_changers[0].get('gap_name', 'Check evolution log')}"
    elif built_items:
        action = f"Review {len(built_items)} items TAD built overnight: {', '.join(i.get('item','?') for i in built_items[:3])}"
    elif opps:
        action = f"Top opportunity ready for GO decision: {opps[0].get('name', '?')} (Score: {opps[0].get('total_score', '?')}/40)"
    else:
        action = "Review THE_MONKEY.md — pick the next Phase 3 item to build"

    briefing = {
        "date":            datetime.now().strftime("%Y-%m-%d"),
        "time":            datetime.now().strftime("%H:%M"),
        "greeting":        "Good morning, Joshua.",
        "night_mode_ran":  night_ran,
        "built_count":     len(built_items),
        "built_items":     [i.get("item", "?") for i in built_items],
        "cseo_skills":     cseo_report.get("skills_built", 0),
        "skipped":         overnight.get("skipped", []),
        "errors":          overnight.get("errors", []),
        "opportunities":   opps[:3],
        "game_changers":   game_changers,
        "action_today":    action,
        "summary":         ceo_summary,
        "full_text":       _format_briefing_text(
                               built_items, opps, cseo_report,
                               game_changers, action, night_ran
                           ),
    }

    BRIEFING_PATH.parent.mkdir(exist_ok=True)
    BRIEFING_PATH.write_text(json.dumps(briefing, indent=2))
    _log(f"Morning briefing saved → {BRIEFING_PATH}")
    return briefing


def _get_ceo_summary(built_items: list, opps: list, cseo_report: dict) -> str:
    """Ask CEO Agent or Kimi for the morning summary."""
    try:
        from ceo_agent import generate_daily_summary
        return generate_daily_summary()
    except Exception:
        pass

    # Fallback to Kimi
    prompt = f"""Write a 3-sentence morning briefing summary for Joshua, CEO of TAD AI.

Last night TAD:
- Built {len(built_items)} items
- CSEO added {cseo_report.get('skills_built', 0)} new skills
- Market found {len(opps)} opportunities

Top opportunity: {opps[0].get('name', 'none') if opps else 'none'}

Be direct and energizing. What happened, what's ready, what to focus on."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip() or ""
    except Exception as e:
        _log(f"CEO summary error: {e}")
        return f"TAD built {len(built_items)} items overnight. {len(opps)} opportunities ready for review."


def _format_briefing_text(built_items: list, opps: list,
                           cseo_report: dict, game_changers: list,
                           action: str, night_ran: bool) -> str:
    lines = []

    # Game changer alert
    if game_changers:
        lines.append("🚨 GAME-CHANGING DISCOVERY FOUND:")
        for gc in game_changers:
            lines.append(f"  → {gc.get('gap_name')}: {gc.get('description', '')}")
        lines.append("")

    # Overnight build
    if night_ran and built_items:
        lines.append(f"OVERNIGHT BUILD: TAD completed {len(built_items)} items.")
        for item in built_items[:5]:
            lines.append(f"  ✓ {item.get('item', '?')} → {item.get('file', '?')}")
    else:
        lines.append("OVERNIGHT: Night mode ran. Check memory/night_log.jsonl for details.")

    # CSEO skills
    cseo_built = cseo_report.get("skills_built", 0)
    if cseo_built:
        lines.append(f"\nCSEO EVOLUTION: {cseo_built} new skills added to TAD.")
        report_text = cseo_report.get("report_text", "")
        if report_text:
            lines.append(f"  {report_text[:200]}")

    # Market opportunities
    lines.append("\nTOP OPPORTUNITIES:")
    if opps:
        for i, opp in enumerate(opps[:3], 1):
            if isinstance(opp, dict):
                lines.append(f"  #{i} {opp.get('name', '?')} — Score: {opp.get('total_score', '?')}/40")
                lines.append(f"      {opp.get('problem', '')[:80]}")
            else:
                lines.append(f"  #{i} {opp}")
    else:
        lines.append("  No opportunities scanned yet — market scan runs at 3am")

    lines.append(f"\nYOUR #1 ACTION: {action}")
    return "\n".join(lines)


# ── Hourly Ops health check ───────────────────────────────────────────────────

def run_ops_health_check():
    """Hourly — Ops Agent checks all agent health."""
    _log("Hourly Ops health check...")
    try:
        from ops_agent import run_full_health_check, get_system_status
        health = run_full_health_check()
        status = get_system_status()
        issues = health.get("issue_count", 0)
        if issues > 0:
            _log(f"⚠️ Ops detected {issues} issue(s): {status}")
        else:
            _log(f"Ops: {status}")
        return health
    except Exception as e:
        _log(f"Ops health check error: {e}")
        return {}


# ── Scheduler loop ────────────────────────────────────────────────────────────

class TADScheduler:
    """
    Runs as daemon thread inside tad_gui.py.
    Checks clock every 60 seconds and fires tasks at scheduled times.
    Each task fires once per calendar day (except ops — runs hourly).
    """

    SCHEDULE = {
        "night_mode":  (23, 0),   # 11:00 PM → night mode
        "market_scan": ( 3, 0),   #  3:00 AM → Market Agent
        "briefing":    ( 7, 0),   #  7:00 AM → CEO morning briefing
    }

    def __init__(self):
        self._ran_today:  dict[str, str] = {}
        self._last_ops:   datetime | None = None
        self._thread:     threading.Thread | None = None
        self._stop        = threading.Event()

    def _should_run(self, task: str, hour: int, minute: int) -> bool:
        now   = datetime.now()
        today = str(date.today())
        return (now.hour == hour and
                now.minute == minute and
                self._ran_today.get(task) != today)

    def _should_run_ops(self) -> bool:
        """Ops runs every hour."""
        if self._last_ops is None:
            return True
        elapsed = (datetime.now() - self._last_ops).total_seconds()
        return elapsed >= 3600

    def _mark_ran(self, task: str):
        self._ran_today[task] = str(date.today())

    def _tick(self):
        while not self._stop.is_set():
            try:
                # Scheduled tasks
                for task, (h, m) in self.SCHEDULE.items():
                    if self._should_run(task, h, m):
                        _log(f"Firing scheduled task: {task}")
                        self._mark_ran(task)
                        if task == "night_mode":
                            threading.Thread(
                                target=launch_night_mode,
                                daemon=True
                            ).start()
                        elif task == "market_scan":
                            threading.Thread(
                                target=run_market_scan,
                                daemon=True
                            ).start()
                        elif task == "briefing":
                            threading.Thread(
                                target=build_morning_briefing,
                                daemon=True
                            ).start()

                # Hourly Ops check
                if self._should_run_ops():
                    self._last_ops = datetime.now()
                    threading.Thread(
                        target=run_ops_health_check,
                        daemon=True
                    ).start()

            except Exception as e:
                _log(f"Scheduler tick error: {e}")

            self._stop.wait(60)

    def start(self):
        self._thread = threading.Thread(
            target=self._tick,
            daemon=True,
            name="TADScheduler"
        )
        self._thread.start()
        _log("Scheduler started — night mode 11pm | market scan 3am | briefing 7am | ops every hour")

    def stop(self):
        self._stop.set()

    def force_briefing(self):
        return build_morning_briefing()


# ── Singleton + public API ────────────────────────────────────────────────────

_scheduler = TADScheduler()


def start_scheduler(status_callback=None):
    """Called once from tad_gui.py on startup."""
    _scheduler.start()
    if status_callback:
        status_callback("Scheduler started — night mode 11pm | market 3am | briefing 7am | ops hourly")


def force_briefing_now():
    return _scheduler.force_briefing()


def check_pending_briefing():
    """Return briefing data if morning briefing exists, else None."""
    if BRIEFING_PATH.exists():
        try:
            return json.loads(BRIEFING_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


if __name__ == "__main__":
    print("TAD Scheduler v0.3 — test mode")
    print("Generating morning briefing now...")
    briefing = build_morning_briefing()
    print(f"\nDate: {briefing['date']} {briefing['time']}")
    print(f"Action: {briefing['action_today']}")
    print(f"\nFull briefing:\n{briefing['full_text']}")