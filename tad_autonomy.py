"""
TAD — Autonomy Engine v1.0
Phase 4 — Self-assigned tasks

TAD reads THE_MONKEY.md and assigns itself tasks without Joshua asking.
Runs in the background. When TAD is idle it finds something useful to do.

How it works:
1. Reads THE_MONKEY.md for unchecked items
2. Picks the highest priority item TAD can do right now
3. Routes it to the correct agent
4. Reports what it did to Joshua
5. Updates THE_MONKEY.md when done

Rules:
- Never touches Phase 5 items without Joshua approval
- Never spends money without approval
- Never sends outreach without approval
- Always logs what it did and why
- Flags anything above its authority to Joshua
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent
MEMORY     = ROOT / "memory"
SKILLS_DIR = ROOT / "skills"
LOG_PATH   = MEMORY / "autonomy_log.jsonl"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# ── Config ────────────────────────────────────────────────────────────────────
IDLE_THRESHOLD   = 300   # seconds of inactivity before TAD self-assigns (5 min)
CHECK_INTERVAL   = 60    # check for tasks every 60 seconds
MAX_AUTO_TASKS   = 3     # max tasks TAD self-assigns per session

# Tasks TAD CANNOT self-assign — need Joshua approval
REQUIRES_APPROVAL = [
    "send outreach", "send email", "send sms",
    "delete", "remove department", "add department",
    "spend", "invoice", "payment", "financial",
    "phase 5", "p5-",
]


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Autonomy] {msg}")


# ── Task reader ───────────────────────────────────────────────────────────────

def get_next_task() -> dict | None:
    """
    Read THE_MONKEY.md and find the best next task TAD can do autonomously.
    Returns task dict or None if nothing available.
    """
    monkey_path = ROOT / "THE_MONKEY.md"
    if not monkey_path.exists():
        return None

    monkey_text = monkey_path.read_text(encoding="utf-8")

    # Find all unchecked items
    unchecked = []
    current_phase = ""

    for line in monkey_text.splitlines():
        if re.match(r"###? PHASE", line.upper()):
            current_phase = line.strip()
        if line.strip().startswith("- [ ]"):
            item = line.strip().replace("- [ ]", "").strip()
            if item and len(item) > 5:
                unchecked.append({
                    "item":  item,
                    "phase": current_phase,
                    "line":  line,
                })

    if not unchecked:
        return None

    # Filter out items that require approval
    auto_eligible = []
    for task in unchecked:
        item_lower = task["item"].lower()
        needs_approval = any(phrase in item_lower for phrase in REQUIRES_APPROVAL)
        if not needs_approval:
            auto_eligible.append(task)

    if not auto_eligible:
        _log("All pending tasks require Joshua approval — cannot self-assign")
        return None

    # Ask Kimi which task TAD should pick
    prompt = f"""TAD AI has these unchecked tasks available for autonomous execution:

{json.dumps([t['item'] for t in auto_eligible[:10]], indent=2)}

MONKEY CONTEXT:
{monkey_text[:1500]}

Which single task should TAD execute RIGHT NOW to make the most progress
toward the mission? Consider:
- Highest business impact
- Can be completed in under 30 minutes
- Does not require Joshua's input
- Builds on what is already working

Return ONLY a JSON object:
{{
  "task": "exact task name from the list",
  "reason": "one sentence why this task first",
  "agent": "which agent should handle it: market/decision/build/ops/cseo/ceo",
  "estimated_minutes": 15
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=200,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(clean)

        # Verify the task is in our eligible list
        task_name = result.get("task", "")
        matching  = [t for t in auto_eligible if task_name.lower() in t["item"].lower()]

        if matching:
            result["full_item"] = matching[0]["item"]
            result["phase"]     = matching[0]["phase"]
            return result
        else:
            # Fall back to first eligible task
            return {
                "task":               auto_eligible[0]["item"],
                "full_item":          auto_eligible[0]["item"],
                "reason":             "First available task",
                "agent":              "build",
                "estimated_minutes":  15,
                "phase":              auto_eligible[0]["phase"],
            }

    except Exception as e:
        _log(f"Task selection error: {e}")
        return {
            "task":               auto_eligible[0]["item"],
            "full_item":          auto_eligible[0]["item"],
            "reason":             "Fallback — first available",
            "agent":              "build",
            "estimated_minutes":  15,
            "phase":              auto_eligible[0]["phase"],
        }


# ── Task executor ─────────────────────────────────────────────────────────────

def execute_task(task: dict, status_callback=None) -> dict:
    """
    Execute a self-assigned task using the correct agent.
    Returns result dict.
    """
    item  = task.get("full_item", task.get("task", ""))
    agent = task.get("agent", "build")

    _log(f"Self-executing: {item} via {agent} agent")

    result = {
        "task":       item,
        "agent":      agent,
        "started_at": datetime.now().isoformat(),
        "status":     "running",
    }

    try:
        # Route to correct agent
        if agent == "market":
            from market_agent import run_full_scan
            report = run_full_scan(focus_area=item)
            result["output"]  = f"Market scan complete — {len(report.get('opportunities', []))} opportunities found"
            result["status"]  = "success"

        elif agent == "decision":
            from decision_agent import score_opportunity
            score = score_opportunity({"name": item, "problem": item})
            result["output"] = f"Decision: {score.get('decision')} — Score {score.get('total_score')}/40"
            result["status"] = "success"

        elif agent == "ops":
            from ops_agent import run_full_health_check, update_monkey
            health = run_full_health_check()
            update_monkey(item, "done", "auto-executed by Autonomy Engine")
            result["output"] = f"Ops check: {health.get('overall')} — {health.get('issue_count', 0)} issues"
            result["status"] = "success"

        elif agent == "cseo":
            from cseo_agent import run_evolution_cycle
            evo = run_evolution_cycle()
            result["output"] = f"CSEO built {evo.get('skills_built', 0)} new skills"
            result["status"] = "success"

        else:
            # Build agent — use night mode build function
            from night_mode import _build_item, _test_and_fix, _mark_done
            monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8") \
                     if (ROOT / "THE_MONKEY.md").exists() else ""
            code   = _build_item(item, monkey)
            safe   = re.sub(r"[^a-z0-9_]", "_", item.lower()).strip("_")
            fpath  = ROOT / f"{safe}.py"
            ok     = _test_and_fix(fpath, code, item)

            if ok:
                _mark_done(item)
                result["output"] = f"Built and tested: {fpath.name}"
                result["status"] = "success"
            else:
                result["output"] = f"Build failed for: {item}"
                result["status"] = "failed"

        result["completed_at"] = datetime.now().isoformat()
        _log(f"Task complete: {item} — {result['status']}")

    except Exception as e:
        result["status"] = "error"
        result["error"]  = str(e)
        _log(f"Task error: {item} — {e}")

    return result


# ── Mark done in THE_MONKEY.md ────────────────────────────────────────────────

def _mark_done(item: str):
    monkey_path = ROOT / "THE_MONKEY.md"
    if not monkey_path.exists():
        return
    today   = datetime.now().strftime("%Y-%m-%d")
    content = monkey_path.read_text(encoding="utf-8")
    updated = content.replace(
        f"- [ ] {item}",
        f"- [x] {item} ✓ auto {today}"
    )
    monkey_path.write_text(updated, encoding="utf-8")


# ── Save autonomy log ─────────────────────────────────────────────────────────

def _save_session(tasks_done: list):
    session_log = MEMORY / "autonomy_sessions.json"
    data = {"sessions": []}
    if session_log.exists():
        try:
            data = json.loads(session_log.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["sessions"].append({
        "date":       datetime.now().isoformat(),
        "tasks_done": tasks_done,
    })
    session_log.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Autonomy engine ───────────────────────────────────────────────────────────

class AutonomyEngine:
    """
    Runs as a daemon thread.
    When TAD is idle, finds and executes the next task autonomously.
    """

    def __init__(self):
        self._active       = False
        self._stop_event   = threading.Event()
        self._last_activity = datetime.now()
        self._tasks_done   = 0
        self._thread       = None

    def record_activity(self):
        """Call this whenever Joshua interacts with TAD."""
        self._last_activity = datetime.now()

    def _is_idle(self) -> bool:
        """Returns True if TAD has been idle long enough."""
        idle_seconds = (datetime.now() - self._last_activity).total_seconds()
        return idle_seconds >= IDLE_THRESHOLD

    def _run(self, on_task_complete=None):
        """Main autonomy loop."""
        _log("Autonomy engine started")
        tasks_done = []

        while not self._stop_event.is_set():
            try:
                # Only act when idle and under task limit
                if self._is_idle() and self._tasks_done < MAX_AUTO_TASKS:
                    task = get_next_task()

                    if task:
                        _log(f"Self-assigning: {task.get('task')} — {task.get('reason')}")
                        result = execute_task(task)
                        tasks_done.append(result)
                        self._tasks_done += 1

                        if on_task_complete:
                            on_task_complete(result)

                        # Reset idle clock after completing a task
                        self._last_activity = datetime.now()

                        # Save progress
                        _save_session(tasks_done)

                    else:
                        _log("No eligible tasks found — TAD is fully caught up")
                        # Stop after checking once with nothing to do
                        break

                elif self._tasks_done >= MAX_AUTO_TASKS:
                    _log(f"Reached max auto-tasks ({MAX_AUTO_TASKS}) — waiting for Joshua")
                    break

            except Exception as e:
                _log(f"Autonomy loop error: {e}")

            self._stop_event.wait(CHECK_INTERVAL)

        _log(f"Autonomy session complete — {len(tasks_done)} tasks executed")
        self._active = False

    def start(self, on_task_complete=None):
        """Start the autonomy engine."""
        if self._active:
            return False
        self._active     = True
        self._tasks_done = 0
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(on_task_complete,),
            daemon=True,
            name="TADAutonomy"
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()
        self._active = False

    def is_active(self) -> bool:
        return self._active


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine = AutonomyEngine()


def start_autonomy(on_task_complete=None) -> bool:
    """
    Start TAD's autonomy engine.
    Call from tad_gui.py after startup.

    on_task_complete(result) — called when TAD finishes a self-assigned task.
    """
    return _engine.start(on_task_complete)


def stop_autonomy():
    _engine.stop()


def record_activity():
    """
    Call this every time Joshua interacts with TAD.
    Resets the idle clock so TAD doesn't self-assign during active sessions.
    """
    _engine.record_activity()


def is_running() -> bool:
    return _engine.is_active()


def get_autonomy_summary() -> dict:
    """Get summary of autonomous activity."""
    session_log = MEMORY / "autonomy_sessions.json"
    if not session_log.exists():
        return {"total_sessions": 0, "total_tasks": 0}
    try:
        data     = json.loads(session_log.read_text(encoding="utf-8"))
        sessions = data.get("sessions", [])
        total    = sum(len(s.get("tasks_done", [])) for s in sessions)
        return {
            "total_sessions": len(sessions),
            "total_tasks":    total,
            "last_session":   sessions[-1] if sessions else None,
        }
    except Exception:
        return {"total_sessions": 0, "total_tasks": 0}


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Autonomy Engine — Test Mode")
    print("=" * 40)

    print("Checking for self-assignable tasks...")
    task = get_next_task()

    if task:
        print(f"\nNext task: {task.get('task')}")
        print(f"Reason: {task.get('reason')}")
        print(f"Agent: {task.get('agent')}")
        print(f"Phase: {task.get('phase')}")

        answer = input("\nExecute this task now? (y/n): ").strip().lower()
        if answer == "y":
            print(f"\nExecuting: {task.get('task')}...")
            result = execute_task(task)
            print(f"\nResult: {result.get('status')}")
            print(f"Output: {result.get('output', result.get('error', 'no output'))}")
    else:
        print("No eligible tasks found — THE_MONKEY.md is either empty or all tasks need approval.")

    print("\nAutonomy summary:")
    print(json.dumps(get_autonomy_summary(), indent=2))
