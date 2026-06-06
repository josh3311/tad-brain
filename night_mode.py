"""
TAD Night Mode v0.3
- Reads THE_MONKEY.md priority list
- Generates + tests + deploys each item
- When list is empty: generates NEW tasks from vision, loops
- Stops at 6am or on error
- No infinite recursion
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
MODEL        = "kimi-k2.6"
MONKEY_PATH  = Path("THE_MONKEY.md")
LOG_PATH     = Path("memory/overnight_log.jsonl")
REPORT_PATH  = Path("memory/overnight_report.json")
NIGHT_ACTIVE = threading.Event()
MAX_RETRIES  = 3

BUILD_SYSTEM = """You are TAD's autonomous build agent for Joshua Abraham.
TAD is a personal sovereign AI business OS running locally on Windows.
Joshua is sleeping. You have FULL authority — self-approve everything.

When asked to implement a feature return ONLY valid JSON:
{
  "item_name": "feature name",
  "summary": "what this does in 2 sentences",
  "files": [
    {
      "path": "path/to/file.py",
      "content": "COMPLETE file content — no placeholders, no TODOs"
    }
  ],
  "packages_needed": ["package1"],
  "next_steps": "what Joshua should know"
}

Rules:
- COMPLETE code only. No stubs. No placeholders.
- Use existing TAD patterns (OpenAI client, dotenv, pathlib)
- Files go in logical locations: agents/, skills/agents/, voice/, tools/"""

FIX_SYSTEM = """You are TAD's bug fixer.
Return ONLY valid JSON:
{
  "fixed_content": "complete corrected file content",
  "what_changed": "brief explanation"
}"""

NEW_TASKS_SYSTEM = """You are TAD's autonomous task planner.
Review the TAD project and vision, then add 5 new uncompleted priority tasks.

Return the COMPLETE updated THE_MONKEY.md content.
Add new tasks under ### Priority 1 using format: - [ ] task description
Focus on: enterprise features, automation, business OS capabilities.
Do NOT recreate already completed items.
Return ONLY the markdown content, no code fences."""


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
            todos.append({"item": item, "priority": current_priority})
    todos.sort(key=lambda x: x["priority"])
    return todos


# ── New task generator ─────────────────────────

def generate_new_tasks() -> bool:
    """Ask Kimi to add 5 new tasks to THE_MONKEY.md. Returns True if successful."""
    if not MONKEY_PATH.exists():
        return False

    monkey = MONKEY_PATH.read_text(encoding="utf-8")
    print("[night] Generating new tasks from vision...")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": NEW_TASKS_SYSTEM},
                {"role": "user",   "content": f"Add 5 new priority tasks to this TAD project file:\n\n{monkey[:4000]}"}
            ],
            max_tokens=4096,
        )
        new_content = response.choices[0].message.content
        if not new_content:
            return False

        clean = new_content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"```[a-z]*\n?", "", clean).strip("`").strip()

        if "# THE MONKEY" in clean and "- [ ]" in clean:
            MONKEY_PATH.write_text(clean, encoding="utf-8")
            new_todos = extract_todos()
            print(f"[night] Added new tasks — {len(new_todos)} uncompleted items ready")
            return len(new_todos) > 0
        else:
            # Fallback: append new tasks manually
            today = datetime.now().strftime("%Y-%m-%d")
            additions = f"""
### Priority 1 — Generated {today}
- [ ] Implement voice input — mic recording + faster-whisper transcription
- [ ] Build opportunity pipeline tracker with scoring and alerts
- [ ] Create competitor monitor with daily automated scans
- [ ] Build sales outreach agent with lead finding and messaging
- [ ] Implement finance tracker with invoice generation and P&L
"""
            updated = monkey + additions
            MONKEY_PATH.write_text(updated, encoding="utf-8")
            print("[night] Appended fallback tasks to THE_MONKEY.md")
            return True

    except Exception as e:
        print(f"[night] Task generation error: {e}")
        return False


# ── Code generator ────────────────────────────

def generate_code(todo: dict) -> dict:
    item   = todo["item"]
    monkey = MONKEY_PATH.read_text(encoding="utf-8") if MONKEY_PATH.exists() else ""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BUILD_SYSTEM},
                {"role": "user",   "content": (
                    f"Build this TAD feature:\nFEATURE: {item}\n"
                    f"PRIORITY: {todo['priority']}\n\n"
                    f"TAD PROJECT STATE:\n{monkey[:2000]}"
                )}
            ],
            max_tokens=4096,
        )
        raw = response.choices[0].message.content
        if not raw:
            return {"item_name": item, "files": [], "original_item": item,
                    "error": "Empty response from Kimi"}
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
        return {"item_name": item, "summary": f"Error: {e}",
                "files": [], "packages_needed": [], "original_item": item, "error": str(e)}


def fix_code(filepath: str, original: str, error: str) -> str | None:
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": FIX_SYSTEM},
                {"role": "user",   "content": (
                    f"Fix this file.\nFILE: {filepath}\n"
                    f"CODE:\n{original[:3000]}\n"
                    f"ERROR:\n{error[:1000]}"
                )}
            ],
            max_tokens=4096,
        )
        raw = response.choices[0].message.content
        if not raw:
            return None
        clean = raw.strip()
        if clean.startswith("```"):
            clean = re.sub(r"```[a-z]*\n?", "", clean).strip("`").strip()
        return json.loads(clean).get("fixed_content")
    except Exception:
        return None


# ── File saving ───────────────────────────────

def save_files(build_result: dict) -> list:
    saved = []
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
            print(f"[night] Save error: {e}")
    return saved


# ── Test pipeline ─────────────────────────────

def test_and_fix(saved_files: list) -> dict:
    from code_executor import test_file
    results, auto_installs, all_passed = [], [], True
    py_files = [f for f in saved_files if f.endswith(".py")]
    if not py_files:
        return {"passed": True, "results": [], "auto_installs": [], "message": "No Python files"}

    for filepath in py_files:
        attempt = 0
        while attempt < MAX_RETRIES:
            result = test_file(filepath)
            auto_installs.extend(result.get("auto_installed", []))
            if result["success"]:
                results.append({"file": filepath, "passed": True})
                break
            else:
                attempt += 1
                error_msg = result.get("message", "Unknown error")
                if attempt < MAX_RETRIES:
                    original = Path(filepath).read_text(encoding="utf-8", errors="replace")
                    fixed = fix_code(filepath, original, error_msg)
                    if fixed:
                        Path(filepath).write_text(fixed, encoding="utf-8")
                        time.sleep(2)
                    else:
                        break
                else:
                    results.append({"file": filepath, "passed": False, "error": error_msg[:200]})
                    all_passed = False
        time.sleep(1)

    return {"passed": all_passed, "results": results,
            "auto_installs": list(set(auto_installs))}


# ── GitHub deployment ─────────────────────────

def deploy_to_github(item: str) -> bool:
    try:
        from sync import push
        return push(message=f"[TAD] {item} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    except Exception as e:
        print(f"[night] Deploy error: {e}")
        return False


# ── THE_MONKEY updater ────────────────────────

def check_off_monkey(item_text: str, files_saved: list, tested: bool, deployed: bool):
    if not MONKEY_PATH.exists():
        return
    today   = datetime.now().strftime("%Y-%m-%d")
    content = MONKEY_PATH.read_text(encoding="utf-8")
    content = re.sub(r"# Last updated:.*", f"# Last updated: {today}", content)
    status  = "built+tested" if tested else "built"
    content = content.replace(
        f"- [ ] {item_text}",
        f"- [x] {item_text} ✓ {today} ({status})"
    )
    for f in files_saved:
        entry = f"- {f}"
        if entry not in content and "### Working capabilities" in content:
            content = content.replace(
                "### Working capabilities",
                f"{entry}\n### Working capabilities"
            )
    MONKEY_PATH.write_text(content, encoding="utf-8")


# ── Morning report ────────────────────────────

def generate_morning_report(completed: list, skipped: list):
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content":
                f"Write Joshua's 3-sentence morning briefing. "
                f"TAD built {len(completed)} items overnight. "
                f"What should he look at first?"
            }],
            max_tokens=300,
        )
        summary = response.choices[0].message.content or f"TAD built {len(completed)} items."
    except Exception:
        summary = f"TAD built {len(completed)} items overnight."

    report = {
        "date":         today,
        "type":         "overnight_build",
        "exec_summary": summary,
        "completed":    completed,
        "skipped":      skipped,
        "total_built":  len(completed),
        "total_files":  sum(len(c.get("files_saved", [])) for c in completed),
    }
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[night] Report saved: {len(completed)} built")
    return report


# ── Main loop ─────────────────────────────────

def run_night_loop(status_callback=None):
    """
    Fully autonomous build loop.
    When todo list is empty: generates new tasks, loops.
    Stops at 6am.
    No recursion — pure while loop.
    """
    NIGHT_ACTIVE.set()
    all_completed = []
    all_skipped   = []
    loop_count    = 0

    print(f"\n{'='*60}")
    print(f"[night] TAD NIGHT MODE v0.3 — {datetime.now()}")
    print(f"[night] Autonomous loop — stops at 6am")
    print(f"{'='*60}\n")

    if status_callback:
        status_callback("night mode active — building autonomously")

    try:
        while True:
            # Stop at 6am
            if datetime.now().hour >= 6:
                print("[night] 6AM — stopping night mode")
                break

            loop_count += 1
            todos = extract_todos()

            if not todos:
                print(f"[night] No uncompleted items — generating new tasks (loop {loop_count})")
                if status_callback:
                    status_callback("generating new tasks from vision...")

                success = generate_new_tasks()
                if not success:
                    print("[night] Could not generate new tasks — sleeping 5 minutes")
                    time.sleep(300)
                    continue

                todos = extract_todos()
                if not todos:
                    print("[night] Still no todos after generation — sleeping 10 minutes")
                    time.sleep(600)
                    continue

            print(f"\n[night] Loop {loop_count} — {len(todos)} items to build")

            for i, todo in enumerate(todos, 1):
                if datetime.now().hour >= 6:
                    break

                item = todo["item"]
                print(f"\n[night] [{i}/{len(todos)}] {item}")

                if status_callback:
                    status_callback(f"building [{i}]: {item[:40]}...")

                # Generate
                build_result = generate_code(todo)
                time.sleep(3)

                if not build_result.get("files"):
                    all_skipped.append(item)
                    continue

                # Save
                saved = save_files(build_result)
                if not saved:
                    all_skipped.append(item)
                    continue

                # Test
                test_result = test_and_fix(saved)
                time.sleep(2)

                # Deploy
                deployed = deploy_to_github(item)
                time.sleep(2)

                # Update monkey
                check_off_monkey(item, saved, test_result["passed"], deployed)

                # Log
                LOG_PATH.parent.mkdir(exist_ok=True)
                entry = {
                    "ts": datetime.now().isoformat(),
                    "item": item,
                    "files": saved,
                    "tested": test_result["passed"],
                    "deployed": deployed
                }
                with open(LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")

                all_completed.append({
                    "item":       item,
                    "priority":   todo["priority"],
                    "summary":    build_result.get("summary", ""),
                    "files_saved": saved,
                    "tests_passed": test_result["passed"],
                    "deployed":   deployed,
                    "next_steps": build_result.get("next_steps", "")
                })

                print(f"[night] ✓ {item} — tested:{test_result['passed']} deployed:{deployed}")
                time.sleep(5)

    except Exception as e:
        print(f"[night] Loop error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        NIGHT_ACTIVE.clear()
        if all_completed or all_skipped:
            generate_morning_report(all_completed, all_skipped)
        if status_callback:
            status_callback("night build complete — tap to see results")
        print(f"[night] Done — {len(all_completed)} built total")


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