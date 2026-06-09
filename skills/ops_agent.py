"""
TAD AI — Ops Agent Script
Chief of Operations — System Health and Log Manager
Version: 1.0
"""

import json
import os
import sys
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import anthropic
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
SKILL_PATH = Path(__file__).parent / "ops_agent.md"

# Kimi for code generation
kimi = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
KIMI_MODEL = "kimi-k2.6"

# Claude for reasoning and JSON
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL  = "claude-haiku-4-5-20251001"

# Expected activity windows for each agent (hours)
AGENT_WINDOWS = {
    "market_agent":    {"check_hour": 5,  "window_hours": 26},
    "build_agent":     {"check_hour": 6,  "window_hours": 26},
    "finance_agent":   {"check_hour": 8,  "window_hours": 170},
    "cseo_agent":      {"check_hour": 6,  "window_hours": 26},
    "decision_agent":  {"check_hour": 6,  "window_hours": 48},
    "marketing_agent": {"check_hour": 9,  "window_hours": 48},
    "ceo_agent":       {"check_hour": 7,  "window_hours": 26},
}

# Log files for each agent
AGENT_LOGS = {
    "market_agent":    "market_log.jsonl",
    "build_agent":     "build_log.jsonl",
    "finance_agent":   "finance_log.jsonl",
    "cseo_agent":      "cseo_log.jsonl",
    "decision_agent":  "decision_log.jsonl",
    "marketing_agent": "marketing_log.jsonl",
    "ceo_agent":       "ceo_log.jsonl",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""


def _read(filename: str) -> dict:
    path = MEMORY / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write(filename: str, data: dict):
    MEMORY.mkdir(exist_ok=True)
    (MEMORY / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _log(msg: str):
    log_path = MEMORY / "ops_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[OPS] {msg}")


# ── Health checks ─────────────────────────────────────────────────────────────

def check_agent_health(agent_name: str) -> dict:
    """Check if an agent has logged activity within its expected window."""
    log_file = AGENT_LOGS.get(agent_name)
    if not log_file:
        return {"agent": agent_name, "status": "unknown", "reason": "no log file defined"}

    log_path = MEMORY / log_file
    if not log_path.exists():
        return {
            "agent":  agent_name,
            "status": "no_activity",
            "reason": "log file does not exist yet",
        }

    try:
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return {"agent": agent_name, "status": "no_activity", "reason": "empty log"}

        last_entry = json.loads(lines[-1])
        last_ts    = datetime.fromisoformat(last_entry.get("ts", "2000-01-01"))
        window     = AGENT_WINDOWS.get(agent_name, {}).get("window_hours", 48)
        cutoff     = datetime.now() - timedelta(hours=window)

        if last_ts >= cutoff:
            return {
                "agent":       agent_name,
                "status":      "healthy",
                "last_active": last_ts.isoformat(),
                "last_msg":    last_entry.get("msg", ""),
            }
        else:
            hours_silent = (datetime.now() - last_ts).total_seconds() / 3600
            return {
                "agent":         agent_name,
                "status":        "silent",
                "last_active":   last_ts.isoformat(),
                "hours_silent":  round(hours_silent, 1),
                "reason":        f"No activity for {hours_silent:.1f} hours",
            }

    except Exception as e:
        return {"agent": agent_name, "status": "error", "reason": str(e)}


def run_full_health_check() -> dict:
    """Check health of all agents and save report."""
    _log("Running full system health check...")
    results = {}
    issues  = []

    for agent in AGENT_LOGS.keys():
        result = check_agent_health(agent)
        results[agent] = result
        if result.get("status") not in ["healthy", "no_activity"]:
            issues.append(result)

    # Check memory files
    critical_files = [
        "history.jsonl", "profile.json",
        "morning_briefing.json", "finance.json",
    ]
    file_health = {}
    for f in critical_files:
        path = MEMORY / f
        file_health[f] = "ok" if path.exists() else "missing"
        if not path.exists():
            issues.append({"file": f, "status": "missing"})

    health_report = {
        "checked_at":   datetime.now().isoformat(),
        "agents":       results,
        "files":        file_health,
        "issues":       issues,
        "overall":      "healthy" if not issues else "issues_detected",
        "issue_count":  len(issues),
    }

    _write("system_health.json", health_report)
    _log(f"Health check complete — {len(issues)} issues found")

    if issues:
        _log(f"Issues: {[i.get('agent', i.get('file', 'unknown')) for i in issues]}")

    return health_report


# ── Error logging ─────────────────────────────────────────────────────────────

def log_error(agent: str, error: str, severity: str = "medium"):
    """Log an error from any agent."""
    error_log = _read("error_log.json")
    if "errors" not in error_log:
        error_log["errors"] = []

    entry = {
        "agent":    agent,
        "error":    error,
        "severity": severity,
        "logged_at": datetime.now().isoformat(),
        "resolved": False,
    }
    error_log["errors"].append(entry)
    _write("error_log.json", error_log)
    _log(f"Error logged [{severity}] from {agent}: {error[:100]}")

    if severity == "critical":
        _log(f"CRITICAL ERROR — escalating to Joshua")


# ── CRUD logging ──────────────────────────────────────────────────────────────

def log_crud(agent: str, action: str, target_file: str, details: str = ""):
    """Log every CRUD action taken by any agent."""
    crud_log = _read("crud_log.json")
    if "actions" not in crud_log:
        crud_log["actions"] = []

    crud_log["actions"].append({
        "agent":       agent,
        "action":      action,
        "target_file": target_file,
        "details":     details,
        "timestamp":   datetime.now().isoformat(),
    })
    _write("crud_log.json", crud_log)


# ── THE_MONKEY.md updater ─────────────────────────────────────────────────────

def update_monkey(item: str, status: str, notes: str = ""):
    """Update THE_MONKEY.md when a task is completed or status changes."""
    monkey_path = ROOT / "THE_MONKEY.md"
    if not monkey_path.exists():
        _log("THE_MONKEY.md not found — cannot update")
        return

    content = monkey_path.read_text(encoding="utf-8")
    today   = datetime.now().strftime("%Y-%m-%d")

    if status == "done":
        content = content.replace(
            f"- [ ] {item}",
            f"- [x] {item} ✓ {today}{' — ' + notes if notes else ''}"
        )
    elif status == "in_progress":
        content = content.replace(
            f"- [ ] {item}",
            f"- [~] {item} (in progress {today})"
        )

    # Update last updated date
    import re
    content = re.sub(r"# Last updated:.*", f"# Last updated: {today}", content)
    monkey_path.write_text(content, encoding="utf-8")
    _log(f"THE_MONKEY.md updated: {item} → {status}")
    log_crud("ops_agent", "UPDATE", "THE_MONKEY.md", f"{item} marked {status}")


# ── Log archiving ─────────────────────────────────────────────────────────────

def archive_old_logs(days: int = 30):
    """Archive log files older than specified days."""
    archive_dir = MEMORY / "archive"
    archive_dir.mkdir(exist_ok=True)
    cutoff = datetime.now() - timedelta(days=days)
    archived = []

    for log_file in MEMORY.glob("*.jsonl"):
        try:
            stat = log_file.stat()
            modified = datetime.fromtimestamp(stat.st_mtime)
            if modified < cutoff:
                dest = archive_dir / f"{log_file.stem}_{modified.strftime('%Y%m%d')}.jsonl"
                shutil.copy2(log_file, dest)
                archived.append(log_file.name)
                _log(f"Archived: {log_file.name}")
        except Exception as e:
            _log(f"Archive error for {log_file.name}: {e}")

    return archived


# ── Daily summary ─────────────────────────────────────────────────────────────

def generate_daily_summary() -> dict:
    """Consolidate all agent activity into a daily summary."""
    summary = {
        "date":          datetime.now().strftime("%Y-%m-%d"),
        "generated_at":  datetime.now().isoformat(),
        "agent_activity": {},
        "errors":        [],
        "crud_actions":  0,
        "builds":        0,
        "deals":         0,
        "revenue":       0,
    }

    # Count activity per agent
    for agent, log_file in AGENT_LOGS.items():
        path = MEMORY / log_file
        if path.exists():
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            today = datetime.now().strftime("%Y-%m-%d")
            today_lines = [l for l in lines if today in l]
            summary["agent_activity"][agent] = len(today_lines)

    # Count errors today
    error_log = _read("error_log.json")
    today = datetime.now().strftime("%Y-%m-%d")
    summary["errors"] = [
        e for e in error_log.get("errors", [])
        if today in e.get("logged_at", "")
    ]

    # Count CRUD actions
    crud_log = _read("crud_log.json")
    summary["crud_actions"] = len([
        a for a in crud_log.get("actions", [])
        if today in a.get("timestamp", "")
    ])

    # Count builds today
    build_log = _read("build_log.json")
    summary["builds"] = len([
        b for b in build_log.get("builds", [])
        if today in b.get("timestamp", "") and b.get("status") == "success"
    ])

    # Revenue today
    finance = _read("finance.json")
    summary["revenue"] = sum(
        r.get("amount", 0) for r in finance.get("revenue", [])
        if today in r.get("date", "")
    )

    _write("daily_summary.json", summary)
    _log(f"Daily summary generated: {summary['builds']} builds, ${summary['revenue']:.2f} revenue")
    return summary


def get_system_status() -> str:
    """Quick status string for TAD GUI or morning briefing."""
    health = _read("system_health.json")
    issues = health.get("issue_count", 0)
    overall = health.get("overall", "unknown")

    if overall == "healthy":
        return "All systems healthy ✓"
    else:
        return f"⚠️ {issues} issue(s) detected — check memory/system_health.json"


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Ops Agent Test")
    print("=" * 40)

    print("Running full health check...")
    health = run_full_health_check()
    print(f"Overall: {health.get('overall')}")
    print(f"Issues: {health.get('issue_count')}")

    print("\nGenerating daily summary...")
    summary = generate_daily_summary()
    print(f"Agent activity: {summary.get('agent_activity')}")
    print(f"Builds today: {summary.get('builds')}")
    print(f"Revenue today: ${summary.get('revenue'):.2f}")

    print("\nSystem status:")
    print(get_system_status())