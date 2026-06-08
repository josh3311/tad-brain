"""
TAD — Night Mode Autonomous Builder v0.5
Phase 3 — CSEO Agent wired in

Changes from v0.4:
- CSEO Agent runs first every night (evolution cycle)
- CSEO identifies gaps and builds new skills automatically
- Build loop reads Phase 3 roadmap items from THE_MONKEY.md
- Market Agent runs at 3am scan window
- Ops Agent logs everything and updates THE_MONKEY.md
- Evolution report included in overnight report
- Game-changing discoveries flag Joshua via report
"""

import json
import os
import re
import sys
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, time as dtime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Agent path setup (must be before any agent imports) ──────────────────────
ROOT        = Path(__file__).parent
AGENTS_DIR  = ROOT / "skills"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))

# ── Kimi client ───────────────────────────────────────────────────────────────
client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# ── Paths ─────────────────────────────────────────────────────────────────────
MONKEY_PATH = ROOT / "THE_MONKEY.md"
REPORT_PATH = ROOT / "memory" / "overnight_report.json"
LOG_PATH    = ROOT / "memory" / "night_log.jsonl"

STOP_HOUR   = 6   # stop loop at 6:00 AM

# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[NIGHT] {msg}")


def _past_stop_time() -> bool:
    return datetime.now().time() >= dtime(STOP_HOUR, 0)


def _read_monkey() -> str:
    return MONKEY_PATH.read_text(encoding="utf-8") if MONKEY_PATH.exists() else ""


# ── CSEO Evolution phase ──────────────────────────────────────────────────────

def _run_cseo_evolution() -> dict:
    """
    Run the CSEO Agent evolution cycle at the start of night mode.
    Returns evolution report.
    """
    _log("=== CSEO Evolution cycle starting ===")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from cseo_agent import run_evolution_cycle
        report = run_evolution_cycle()
        built  = report.get("skills_built", 0)
        _log(f"CSEO evolution complete — {built} new skills built")

        # Check for game changers
        game_changers = report.get("game_changers", [])
        if game_changers:
            _log(f"🚨 GAME-CHANGING DISCOVERY — flagging for Joshua on wake")
            for gc in game_changers:
                _log(f"  → {gc.get('gap_name', 'Unknown')}: {gc.get('description', '')}")

        return report

    except Exception as e:
        _log(f"CSEO evolution error: {e}")
        return {"status": "error", "reason": str(e), "skills_built": 0}


# ── Market scan phase ─────────────────────────────────────────────────────────

def _run_market_scan() -> dict:
    """
    Run Market Agent scan during night mode.
    Returns scan report with top opportunities.
    """
    _log("=== Market Agent scanning for loopholes ===")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from market_agent import run_full_scan
        report = run_full_scan()
        opps   = report.get("opportunities", [])
        _log(f"Market scan complete — {len(opps)} opportunities found")

        if opps:
            for opp in opps[:3]:
                _log(f"  → {opp.get('name')} (Score: {opp.get('total_score')}/40)")

        return report

    except Exception as e:
        _log(f"Market scan error: {e}")
        return {"status": "error", "reason": str(e), "opportunities": []}


# ── Ops health check ──────────────────────────────────────────────────────────

def _run_ops_check() -> dict:
    """Run Ops Agent health check."""
    _log("Ops Agent health check...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from ops_agent import run_full_health_check, generate_daily_summary
        health  = run_full_health_check()
        summary = generate_daily_summary()
        _log(f"Ops check complete — {health.get('issue_count', 0)} issues")
        return {"health": health, "summary": summary}
    except Exception as e:
        _log(f"Ops check error: {e}")
        return {"status": "error", "reason": str(e)}


# ── Code generation helpers ───────────────────────────────────────────────────

BUILD_SYSTEM = """You are TAD's code generation engine.

RULES:
1. Output ONLY raw Python 3 code. Nothing else.
2. DO NOT write any explanation, prose, or markdown outside code blocks.
3. Start your response with either import or a docstring.
4. The code must be complete and runnable.
5. Include if __name__ == "__main__": at the bottom.
6. Put notes inside Python comments (#), not prose.

VIOLATION: Returning prose instead of code is a critical failure."""


def _is_real_python(code: str) -> bool:
    markers = ["import ", "def ", "class ", "if __name__"]
    return any(m in code.strip() for m in markers)


def _extract_code_block(text: str) -> str:
    for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return text.strip()


def _skeleton_fallback(item_name: str) -> str:
    safe = re.sub(r"[^a-z0-9_]", "_", item_name.lower())
    return f'''"""
TAD — {item_name}
Auto-generated skeleton.
"""

def main():
    print("{item_name} skeleton — implement logic here.")

if __name__ == "__main__":
    main()
'''


def _build_item(item_name: str, monkey_context: str) -> str:
    """Generate real Python code for a priority item."""
    prompt = f"""TAD PROJECT CONTEXT:
{monkey_context[:3000]}

TASK: Write a complete, runnable Python module for: {item_name}

Requirements:
- Real Python code only
- Importable as module AND runnable standalone
- Proper docstring, imports, if __name__ == "__main__" block
- No placeholder TODOs — write actual logic
- Production quality

Output Python code only."""

    for attempt in range(1, 4):
        _log(f"  Build attempt {attempt}/3 for '{item_name}'")
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": BUILD_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=1,
                max_tokens=2500,
            )
            raw  = resp.choices[0].message.content or ""
            code = _extract_code_block(raw)

            if _is_real_python(code):
                _log(f"  ✓ Real Python on attempt {attempt}")
                return code
            else:
                _log(f"  ✗ Attempt {attempt} returned prose — retrying")
                prompt += "\n\nPREVIOUS ATTEMPT FAILED — output ONLY Python code."

        except Exception as e:
            _log(f"  Kimi error attempt {attempt}: {e}")
            time.sleep(5)

    _log(f"  All attempts failed for '{item_name}' — using skeleton")
    return _skeleton_fallback(item_name)


def _test_and_fix(filepath: Path, code: str, item_name: str) -> bool:
    """Syntax check and fix loop. Returns True if passing."""
    filepath.write_text(code, encoding="utf-8")

    for fix_round in range(1, 4):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(filepath)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            _log(f"  ✓ Syntax OK: {filepath.name}")
            return True

        error = result.stderr.strip()
        _log(f"  Syntax error round {fix_round}: {error}")

        fix_prompt = f"""Fix this Python syntax error:
ERROR: {error}
CODE: {code}
Return ONLY corrected Python code."""

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": BUILD_SYSTEM},
                    {"role": "user",   "content": fix_prompt},
                ],
                temperature=1,
                max_tokens=2500,
            )
            fixed = _extract_code_block(resp.choices[0].message.content or "")
            if _is_real_python(fixed):
                code = fixed
                filepath.write_text(code, encoding="utf-8")
            else:
                break
        except Exception as e:
            _log(f"  Fix error: {e}")
            break

    return False


def _git_push(item_name: str):
    """Push to GitHub after each successful build."""
    try:
        subprocess.run(["git", "add", "."], cwd=ROOT, check=True, capture_output=True)
        msg = f"[night_mode] {item_name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True, capture_output=True)
        _log(f"  ✓ Pushed to GitHub: {item_name}")
    except subprocess.CalledProcessError as e:
        _log(f"  Git push failed: {e}")


# ── Priority list reader ──────────────────────────────────────────────────────

def _get_priority_items(monkey_text: str) -> list[str]:
    """Extract unchecked items from Phase 3 roadmap in THE_MONKEY.md."""
    items = []
    in_phase3 = False

    for line in monkey_text.splitlines():
        # Enter Phase 3 section
        if "PHASE 3" in line.upper():
            in_phase3 = True
        # Exit on next phase
        elif in_phase3 and re.match(r"###? PHASE [4-9]", line.upper()):
            in_phase3 = False

        if in_phase3 and line.strip().startswith("- [ ]"):
            item = line.strip().replace("- [ ]", "").strip()
            if item:
                items.append(item)

    # Fallback — any unchecked item anywhere
    if not items:
        for line in monkey_text.splitlines():
            if line.strip().startswith("- [ ]"):
                item = line.strip().replace("- [ ]", "").strip()
                if item and len(item) > 5:
                    items.append(item)

    return items


def generate_new_tasks(monkey_text: str) -> list[str]:
    """Generate new tasks when priority list is empty."""
    _log("Priority list empty — CSEO generating new tasks...")
    prompt = f"""TAD PROJECT CONTEXT:
{monkey_text[:3000]}

Generate 5 new high-value tasks that would most advance TAD AI
toward its mission of finding and solving AI loopholes.

Return ONLY a JSON array of task name strings.
["Task one", "Task two", "Task three"]

JSON array only."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=500,
        )
        raw   = resp.choices[0].message.content or "[]"
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        _log(f"Task generation error: {e}")
        return [
            "tad_opportunity_scorer",
            "tad_lead_finder",
            "tad_client_outreach",
            "tad_revenue_tracker",
            "tad_skill_gap_analyzer",
        ]


def _mark_done(item_name: str):
    """Mark item done in THE_MONKEY.md."""
    if not MONKEY_PATH.exists():
        return
    text    = MONKEY_PATH.read_text(encoding="utf-8")
    today   = datetime.now().strftime("%Y-%m-%d")
    updated = text.replace(
        f"- [ ] {item_name}",
        f"- [x] {item_name} ✓ {today}"
    )
    MONKEY_PATH.write_text(updated, encoding="utf-8")


# ── Main night mode loop ──────────────────────────────────────────────────────

def run_night_mode():
    _log("=== Night mode v0.5 started ===")

    report = {
        "started":          datetime.now().isoformat(),
        "built":            [],
        "skipped":          [],
        "errors":           [],
        "cseo_evolution":   {},
        "market_scan":      {},
        "ops_health":       {},
        "game_changers":    [],
    }

    # ── PHASE 1: CSEO Evolution (runs first every night) ──────────────────────
    if not _past_stop_time():
        cseo_report = _run_cseo_evolution()
        report["cseo_evolution"]  = cseo_report
        report["game_changers"]   = cseo_report.get("game_changers", [])

    # ── PHASE 2: Market Scan ───────────────────────────────────────────────────
    if not _past_stop_time():
        market_report = _run_market_scan()
        report["market_scan"] = market_report

    # ── PHASE 3: Build loop — priority items from THE_MONKEY.md ───────────────
    while not _past_stop_time():
        monkey = _read_monkey()
        items  = _get_priority_items(monkey)

        if not items:
            items = generate_new_tasks(monkey)
            if not items:
                _log("No tasks found — sleeping 30m")
                time.sleep(1800)
                continue

        item = items[0]
        _log(f"Building: {item}")

        safe  = re.sub(r"[^a-z0-9_]", "_", item.lower()).strip("_")
        fpath = ROOT / f"{safe}.py"

        code = _build_item(item, monkey)
        ok   = _test_and_fix(fpath, code, item)

        if ok:
            _mark_done(item)
            _git_push(item)
            report["built"].append({
                "item":      item,
                "file":      str(fpath),
                "ts":        datetime.now().isoformat(),
            })
            _log(f"  ✓ Completed: {item}")
        else:
            report["errors"].append(item)
            _log(f"  ✗ Build failed: {item}")

        time.sleep(30)

    # ── PHASE 4: Ops health check before shutdown ──────────────────────────────
    ops_report = _run_ops_check()
    report["ops_health"] = ops_report

    # ── Save full overnight report ─────────────────────────────────────────────
    _log("=== Night mode ended — saving report ===")
    REPORT_PATH.parent.mkdir(exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _log(f"Report saved → {REPORT_PATH}")


# ── Public API (called by tad_gui.py) ─────────────────────────────────────────

_running = False


def is_running() -> bool:
    return _running


def start_night_mode(status_callback=None):
    """Launch night mode in background thread."""
    global _running
    if _running:
        if status_callback:
            status_callback("Night mode already running.")
        return

    def _run():
        global _running
        _running = True
        try:
            if status_callback:
                status_callback("Night mode started — CSEO evolving TAD...")
            run_night_mode()
            if status_callback:
                status_callback("Night mode complete — report ready.")
        except Exception as e:
            _log(f"Night mode error: {e}")
            if status_callback:
                status_callback(f"Night mode error: {e}")
        finally:
            _running = False

    t = threading.Thread(target=_run, daemon=True, name="NightMode")
    t.start()


def check_overnight_report() -> dict | None:
    """Return overnight report for tad_gui.py on first interaction."""
    if REPORT_PATH.exists():
        try:
            data  = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            built = data.get("built", [])
            cseo  = data.get("cseo_evolution", {})
            market = data.get("market_scan", {})
            opps  = market.get("opportunities", [])
            game_changers = data.get("game_changers", [])

            summary = (
                f"Built {len(built)} items. "
                f"CSEO added {cseo.get('skills_built', 0)} new skills. "
                f"Market found {len(opps)} opportunities. "
                f"Skipped {len(data.get('skipped', []))}. "
                f"Errors: {len(data.get('errors', []))}."
            )

            if game_changers:
                summary += f" 🚨 {len(game_changers)} game-changing discovery found!"

            return {
                "total_built":    len(built),
                "total_files":    len(built),
                "exec_summary":   summary,
                "built":          built,
                "skipped":        data.get("skipped", []),
                "errors":         data.get("errors", []),
                "cseo_skills":    cseo.get("skills_built", 0),
                "opportunities":  opps,
                "game_changers":  game_changers,
                "date":           datetime.now().strftime("%Y-%m-%d"),
            }
        except Exception:
            return None
    return None


if __name__ == "__main__":
    run_night_mode()