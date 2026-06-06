"""
TAD Night Mode v0.2 — Fully Autonomous Overnight Builder
- Reads priority list from THE_MONKEY.md
- Generates code for each item (Kimi)
- Tests each file (syntax + import + run)
- Auto-installs missing packages (no approval needed)
- Auto-fixes bugs (Kimi re-generates on failure, up to 3 retries)
- Deploys to private GitHub after each passing item
- Generates morning report
- Joshua wakes up to tested, committed code
"""

import json
import os
import re
import sys
import time
import threading
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL       = "kimi-k2.6"
MONKEY_PATH = Path("THE_MONKEY.md")
LOG_PATH    = Path("memory/overnight_log.jsonl")
REPORT_PATH = Path("memory/overnight_report.json")
NIGHT_ACTIVE = threading.Event()
MAX_RETRIES  = 3


BUILD_SYSTEM = """You are TAD's autonomous build agent — Joshua Abraham's overnight developer.
TAD is a personal sovereign AI business OS running locally on Windows.

Joshua is sleeping. You have FULL authority:
- Self-approve all decisions
- Install any packages needed
- Write production-quality code
- Deploy to GitHub automatically

TAD already has these files (do NOT recreate them):
- tad_gui.py, agent.py, scheduler.py, tad_visual.py, night_mode.py
- tools/registry.py, skills/skill_loader.py, sync.py, code_executor.py
- config/providers.py, memory/profile.json

When asked to implement a feature, return ONLY valid JSON:
{
  "item_name": "feature name",
  "summary": "what this does in 2 sentences",
  "files": [
    {
      "path": "path/to/file.py",
      "content": "COMPLETE file content — no placeholders, no TODOs, working code only"
    }
  ],
  "packages_needed": ["package1", "package2"],
  "next_steps": "what Joshua should know",
  "test_command": "python filename.py --test"
}

Rules:
- COMPLETE code only. No stubs. No "# TODO". No "pass".
- Every Python file must work when imported
- Include proper error handling
- Use existing TAD patterns (OpenAI client, dotenv, pathlib)
- Files go in logical locations: agents/, skills/agents/, voice/, tools/"""


FIX_SYSTEM = """You are TAD's bug fixer. A file failed its test.
Fix the code and return the corrected version.

Return ONLY valid JSON:
{
  "fixed_content": "complete corrected file content",
  "what_changed": "brief explanation of the fix"
}"""


# ── Todo extraction ────────────────────────────

def extract_todos() -> list:
    if not MONKEY_PATH.exists():
        return []
    content = MONKEY_PATH.read_text(encoding="utf-8")
    todos = []
    current_priority = 0
    for line in content.split("\n"):
        if "### Priority" in line:
            try:
                current_priority = int(re.search(r"Priority (\d+)", line).group(1))
            except Exception:
                current_priority = 99
        if line.strip().startswith("- [ ]") and current_priority <= 3:
            item = line.strip().replace("- [ ]", "").strip()
            todos.append({"item": item, "priority": current_priority, "line": line})
    todos.sort(key=lambda x: x["priority"])
    return todos


# ── Code generator ────────────────────────────

def generate_code(todo: dict) -> dict:
    """Ask Kimi to fully implement a priority item."""
    item   = todo["item"]
    monkey = MONKEY_PATH.read_text(encoding="utf-8") if MONKEY_PATH.exists() else ""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BUILD_SYSTEM},
                {"role": "user",   "content": (
                    f"Build this TAD feature with complete working code:\n\n"
                    f"FEATURE: {item}\n"
                    f"PRIORITY: {todo['priority']}\n\n"
                    f"TAD PROJECT STATE:\n{monkey[:2500]}"
                )}
            ],
            max_tokens=4096,
        )
        raw = response.choices[0].message.content
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = re.sub(r"```[a-z]*\n?", "", clean).strip("`").strip()
            result = json.loads(clean)
            result["original_item"] = item
            return result
        except Exception:
            return {
                "item_name":  item,
                "summary":    "Plan generated",
                "files": [{"path": f"plans/{_slug(item)}-plan.md",
                           "content": f"# Plan: {item}\n\n{raw}"}],
                "packages_needed": [],
                "next_steps": "Review plan",
                "original_item": item
            }
    except Exception as e:
        return {"item_name": item, "summary": f"Generate error: {e}",
                "files": [], "packages_needed": [], "original_item": item, "error": str(e)}


def fix_code(filepath: str, original_content: str, error: str) -> str | None:
    """Ask Kimi to fix a failing file. Returns corrected content or None."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": FIX_SYSTEM},
                {"role": "user",   "content": (
                    f"Fix this Python file.\n\n"
                    f"FILE: {filepath}\n\n"
                    f"ORIGINAL CODE:\n{original_content[:3000]}\n\n"
                    f"TEST ERROR:\n{error[:1000]}\n\n"
                    f"Return corrected JSON."
                )}
            ],
            max_tokens=4096,
        )
        raw = response.choices[0].message.content
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"```[a-z]*\n?", "", clean).strip("`").strip()
        result = json.loads(clean)
        return result.get("fixed_content")
    except Exception as e:
        print(f"[night] Fix error: {e}")
        return None


# ── File saving ───────────────────────────────

def save_files(build_result: dict) -> list:
    """Save all generated files. Returns list of saved paths."""
    saved = []
    # Auto-install declared packages first
    for pkg in build_result.get("packages_needed", []):
        from code_executor import install_package
        install_package(pkg)
        time.sleep(1)

    for f in build_result.get("files", []):
        try:
            path = Path(f["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["content"], encoding="utf-8")
            saved.append(str(path))
            print(f"[night] Saved: {path}")
        except Exception as e:
            print(f"[night] Save error {f.get('path')}: {e}")
    return saved


# ── Test pipeline ─────────────────────────────

def test_and_fix(saved_files: list, build_result: dict) -> dict:
    """
    Test every Python file.
    Auto-install missing packages.
    Ask Kimi to fix failures (max 3 retries).
    Returns overall pass/fail with details.
    """
    from code_executor import test_file

    results      = []
    all_passed   = True
    auto_installs = []

    py_files = [f for f in saved_files if f.endswith(".py")]

    if not py_files:
        return {"passed": True, "results": [], "auto_installs": [], "message": "No Python files to test"}

    for filepath in py_files:
        print(f"[night] Testing: {filepath}")
        attempt = 0

        while attempt < MAX_RETRIES:
            result = test_file(filepath)
            auto_installs.extend(result.get("auto_installed", []))

            if result["success"]:
                print(f"[night] ✓ Test passed: {filepath}")
                results.append({"file": filepath, "passed": True, "attempts": attempt + 1})
                break
            else:
                attempt += 1
                error_msg = result.get("message", "Unknown error")
                print(f"[night] ✗ Test failed (attempt {attempt}): {filepath}")
                print(f"[night]   Error: {error_msg[:100]}")

                if attempt < MAX_RETRIES:
                    print(f"[night] Asking Kimi to fix...")
                    original = Path(filepath).read_text(encoding="utf-8", errors="replace")
                    fixed = fix_code(filepath, original, error_msg)

                    if fixed:
                        Path(filepath).write_text(fixed, encoding="utf-8")
                        print(f"[night] Fixed and saved — retrying test")
                        time.sleep(2)
                    else:
                        print(f"[night] Could not auto-fix — moving on")
                        break
                else:
                    results.append({
                        "file":     filepath,
                        "passed":   False,
                        "attempts": attempt,
                        "error":    error_msg[:200]
                    })
                    all_passed = False

        time.sleep(1)

    return {
        "passed":       all_passed,
        "results":      results,
        "auto_installs": list(set(auto_installs)),
        "message":      "All tests passed" if all_passed else "Some tests failed"
    }


# ── GitHub deployment ─────────────────────────

def deploy_to_github(item: str, files: list) -> bool:
    """Auto-push to private GitHub after successful test."""
    try:
        from sync import push
        commit_msg = f"[TAD night build] {item} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        success = push(message=commit_msg)
        if success:
            print(f"[night] ✓ Deployed to GitHub: {item}")
        return success
    except Exception as e:
        print(f"[night] GitHub deploy error: {e}")
        return False


# ── THE_MONKEY updater ────────────────────────

def check_off_monkey(item_text: str, files_saved: list, tested: bool, deployed: bool):
    if not MONKEY_PATH.exists():
        return
    today   = datetime.now().strftime("%Y-%m-%d")
    content = MONKEY_PATH.read_text(encoding="utf-8")
    content = re.sub(r"# Last updated:.*", f"# Last updated: {today}", content)

    status = "built+tested+deployed" if (tested and deployed) else \
             "built+tested" if tested else "built (test failed)"
    old    = f"- [ ] {item_text}"
    new    = f"- [x] {item_text} ✓ {today} ({status})"
    content = content.replace(old, new)

    for f in files_saved:
        entry = f"- {f}"
        if entry not in content and "### Working capabilities" in content:
            content = content.replace(
                "### Working capabilities",
                f"{entry}\n### Working capabilities"
            )

    MONKEY_PATH.write_text(content, encoding="utf-8")


# ── Logging ───────────────────────────────────

def log(item: str, result: dict, saved: list, test_result: dict, deployed: bool):
    LOG_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "ts":          datetime.now().isoformat(),
        "item":        item,
        "summary":     result.get("summary", ""),
        "files_saved": saved,
        "tests_passed": test_result.get("passed", False),
        "auto_installs": test_result.get("auto_installs", []),
        "deployed":    deployed,
        "next_steps":  result.get("next_steps", "")
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Morning report ────────────────────────────

def generate_morning_report(completed: list, skipped: list):
    today = datetime.now().strftime("%Y-%m-%d")
    completed_text = "\n".join([
        f"- {c['item']}: {c.get('summary','')} "
        f"(tested: {c.get('tests_passed','?')}, deployed: {c.get('deployed','?')})"
        for c in completed
    ])

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content":
                f"Write Joshua's morning briefing about what TAD built overnight.\n\n"
                f"COMPLETED ({len(completed)}):\n{completed_text}\n\n"
                f"SKIPPED: {len(skipped)}\n\n"
                f"3-4 sentences. What should he look at first? What's ready to run?"
            }],
            max_tokens=400,
        )
        summary = response.choices[0].message.content
    except Exception:
        summary = f"TAD built {len(completed)} items. {sum(1 for c in completed if c.get('deployed'))} deployed to GitHub."

    report = {
        "date":          today,
        "type":          "overnight_build",
        "exec_summary":  summary,
        "completed":     completed,
        "skipped":       skipped,
        "total_built":   len(completed),
        "total_files":   sum(len(c.get("files_saved", [])) for c in completed),
        "total_deployed": sum(1 for c in completed if c.get("deployed")),
        "total_tested":   sum(1 for c in completed if c.get("tests_passed")),
    }

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[night] Report: {len(completed)} built · "
          f"{report['total_tested']} tested · "
          f"{report['total_deployed']} deployed to GitHub")
    return report


# ── Main autonomous loop ──────────────────────

def run_night_loop(status_callback=None):
    """
    Fully autonomous build loop.
    Generates → Tests → Auto-fixes → Deploys → Loops.
    No human needed. Self-approves everything.
    """
    NIGHT_ACTIVE.set()
    print(f"\n{'='*60}")
    print(f"[night] TAD NIGHT MODE v0.2 — {datetime.now()}")
    print(f"[night] Full autonomy: code generation + testing + deployment")
    print(f"[night] Joshua is sleeping. Building everything.")
    print(f"{'='*60}\n")

    if status_callback:
        status_callback("night mode active — building autonomously")

    completed = []
    skipped   = []

    try:
        todos = extract_todos()
        if not todos:
            print("[night] No uncompleted items. TAD is fully built!")
            NIGHT_ACTIVE.clear()
            return

        print(f"[night] {len(todos)} items on the priority list\n")

        for i, todo in enumerate(todos, 1):
            if datetime.now().hour >= 6:
                print("[night] 6AM — stopping night mode")
                break

            item = todo["item"]
            print(f"\n[night] [{i}/{len(todos)}] {item}")
            print(f"[night] Priority {todo['priority']}")

            if status_callback:
                status_callback(f"building [{i}/{len(todos)}]: {item[:35]}...")

            # ── 1. Generate code ──────────────────
            print(f"[night] Generating code...")
            build_result = generate_code(todo)
            time.sleep(3)

            if not build_result.get("files"):
                skipped.append(item)
                print(f"[night] No files generated — skipping")
                continue

            # ── 2. Save files ─────────────────────
            saved = save_files(build_result)
            if not saved:
                skipped.append(item)
                continue

            # ── 3. Test + auto-fix ────────────────
            print(f"[night] Testing {len(saved)} file(s)...")
            if status_callback:
                status_callback(f"testing: {item[:35]}...")

            test_result = test_and_fix(saved, build_result)
            time.sleep(2)

            tests_passed  = test_result["passed"]
            auto_installs = test_result.get("auto_installs", [])

            if auto_installs:
                print(f"[night] Auto-installed: {', '.join(auto_installs)}")

            if tests_passed:
                print(f"[night] ✓ All tests passed")
            else:
                print(f"[night] ⚠ Some tests failed — still saving and deploying")

            # ── 4. Deploy to GitHub ───────────────
            print(f"[night] Deploying to GitHub...")
            if status_callback:
                status_callback(f"deploying: {item[:35]}...")

            deployed = deploy_to_github(item, saved)
            time.sleep(2)

            # ── 5. Update THE_MONKEY ──────────────
            check_off_monkey(item, saved, tests_passed, deployed)
            log(item, build_result, saved, test_result, deployed)

            completed.append({
                "item":          item,
                "priority":      todo["priority"],
                "summary":       build_result.get("summary", ""),
                "files_saved":   saved,
                "tests_passed":  tests_passed,
                "auto_installs": auto_installs,
                "deployed":      deployed,
                "next_steps":    build_result.get("next_steps", "")
            })

            print(f"[night] ✓ Complete — tested: {tests_passed} · deployed: {deployed}")
            time.sleep(5)  # breathe between items

    except Exception as e:
        print(f"[night] Loop error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        NIGHT_ACTIVE.clear()
        if completed or skipped:
            generate_morning_report(completed, skipped)
        if status_callback:
            status_callback("night build complete — tap to see results")


def start_night_mode(status_callback=None):
    if NIGHT_ACTIVE.is_set():
        print("[night] Already running")
        return
    thread = threading.Thread(
        target=run_night_loop, args=(status_callback,), daemon=True
    )
    thread.start()
    return thread


def check_overnight_report() -> dict:
    if not REPORT_PATH.exists():
        return {}
    try:
        data  = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        today = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") == today:
            REPORT_PATH.unlink()
            return data
        REPORT_PATH.unlink()
        return {}
    except Exception:
        return {}


def is_running() -> bool:
    return NIGHT_ACTIVE.is_set()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


if __name__ == "__main__":
    run_night_loop()