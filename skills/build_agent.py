"""
TAD AI — Build Agent Script
Chief Technology Officer — Code Builder and Shipper
Version: 1.0
"""

import json
import os
import re
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
SKILL_PATH = Path(__file__).parent / "build_agent.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# Core TAD files that can never be deleted or overwritten
PROTECTED_FILES = [
    "tad_gui.py", "agent.py", "scheduler.py",
    "night_mode.py", "voice_input.py", "tad_visual.py",
    "sync.py", "THE_MONKEY.md", ".env"
]

BUILD_SYSTEM = """You are TAD's code generation engine — the CTO.

ABSOLUTE RULES:
1. Output ONLY raw Python 3 code. Nothing else.
2. Never write prose, plans, or explanations outside of code comments.
3. Start your response with either import or a docstring.
4. Every file must be complete and runnable.
5. Include if __name__ == "__main__": at the bottom.
6. Use proper error handling on all external calls.
7. Add logging to memory/ folder for every major action.

VIOLATION: Returning a plan or prose instead of code is a critical failure."""


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


def _write_memory(filename: str, data: dict):
    MEMORY.mkdir(exist_ok=True)
    (MEMORY / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _log(msg: str):
    log_path = MEMORY / "build_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[BUILD] {msg}")


def _is_protected(filepath: Path) -> bool:
    return filepath.name in PROTECTED_FILES


def _extract_code(text: str) -> str:
    """Pull code from markdown fences if present."""
    for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return text.strip()


def _is_real_python(code: str) -> bool:
    markers = ["import ", "def ", "class ", "if __name__"]
    return any(m in code for m in markers)


# ── Syntax and execution testing ──────────────────────────────────────────────

def _syntax_check(filepath: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(filepath)],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr.strip()


def _auto_install(error: str) -> bool:
    """Try to install missing package from error message."""
    match = re.search(r"No module named '(\w+)'", error)
    if match:
        package = match.group(1)
        _log(f"Auto-installing: {package}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, text=True
        )
        return result.returncode == 0
    return False


# ── Code generation ───────────────────────────────────────────────────────────

def generate_code(opportunity: dict, filename: str) -> str | None:
    """
    Ask Kimi to generate real Python code for the opportunity.
    Returns code string or None after 3 failed attempts.
    """
    skill = _load_skill()
    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:1500] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    prompt = f"""TAD PROJECT CONTEXT:
{monkey}

APPROVED OPPORTUNITY TO BUILD:
{json.dumps(opportunity, indent=2)}

TARGET FILENAME: {filename}

Write a complete, production-quality Python module for this opportunity.
Requirements:
- Real working code with actual business logic
- Proper imports, functions, classes as needed
- Error handling on all external calls
- Logging to memory/ folder
- Runnable standalone with if __name__ == "__main__":
- No placeholder comments — write actual working logic

Output the Python code directly. Start with imports or docstring."""

    for attempt in range(1, 4):
        _log(f"Code generation attempt {attempt}/3 for {filename}")
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": BUILD_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=1,
                max_tokens=3000,
            )
            raw  = resp.choices[0].message.content or ""
            code = _extract_code(raw)

            if _is_real_python(code):
                _log(f"Real Python code generated on attempt {attempt}")
                return code
            else:
                _log(f"Attempt {attempt} returned prose — retrying")
                prompt += "\n\nPREVIOUS ATTEMPT FAILED — output ONLY Python code."

        except Exception as e:
            _log(f"Generation error attempt {attempt}: {e}")

    _log(f"All 3 generation attempts failed for {filename}")
    return None


def fix_code(code: str, error: str, filename: str) -> str | None:
    """Ask Kimi to fix a syntax or runtime error."""
    fix_prompt = f"""This Python file has an error:

FILENAME: {filename}
ERROR: {error}

CODE:
{code}

Fix the error and return ONLY the corrected Python code.
No explanation. Start with imports or docstring."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BUILD_SYSTEM},
                {"role": "user",   "content": fix_prompt},
            ],
            temperature=1,
            max_tokens=3000,
        )
        raw  = resp.choices[0].message.content or ""
        code = _extract_code(raw)
        return code if _is_real_python(code) else None
    except Exception as e:
        _log(f"Fix attempt error: {e}")
        return None


# ── Git push ──────────────────────────────────────────────────────────────────

def _git_push(filepath: Path, message: str) -> bool:
    try:
        subprocess.run(["git", "add", str(filepath)],
                       cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message],
                       cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push"],
                       cwd=ROOT, check=True, capture_output=True)
        _log(f"Pushed to GitHub: {filepath.name}")
        return True
    except subprocess.CalledProcessError as e:
        _log(f"Git push failed: {e}")
        return False


# ── Update THE_MONKEY.md ──────────────────────────────────────────────────────

def _mark_done(item_name: str):
    monkey_path = ROOT / "THE_MONKEY.md"
    if not monkey_path.exists():
        return
    text = monkey_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    updated = text.replace(
        f"- [ ] {item_name}",
        f"- [x] {item_name} ✓ {today}"
    )
    monkey_path.write_text(updated, encoding="utf-8")


# ── Main build function ───────────────────────────────────────────────────────

def build(opportunity: dict, output_dir: Path = None) -> dict:
    """
    Full build cycle for one approved opportunity.
    Returns build result dict.
    """
    if output_dir is None:
        output_dir = ROOT

    name     = opportunity.get("name", "unnamed_module")
    filename = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_") + ".py"
    filepath = output_dir / filename

    # Safety check
    if _is_protected(filepath):
        _log(f"BLOCKED: Cannot overwrite protected file {filename}")
        return {"status": "blocked", "reason": "protected file", "file": filename}

    _log(f"=== Building: {name} → {filename} ===")

    # Generate code
    code = generate_code(opportunity, filename)
    if not code:
        _log(f"Code generation failed for {name}")
        return {"status": "failed", "reason": "generation_failed", "file": filename}

    # Write file
    filepath.write_text(code, encoding="utf-8")

    # Test and fix loop
    for fix_round in range(1, 4):
        ok, error = _syntax_check(filepath)
        if ok:
            _log(f"Syntax check passed on round {fix_round}")
            break

        _log(f"Syntax error round {fix_round}: {error}")

        # Try auto-install first
        if "No module named" in error:
            if _auto_install(error):
                continue

        # Ask Kimi to fix
        fixed = fix_code(code, error, filename)
        if fixed:
            code = fixed
            filepath.write_text(code, encoding="utf-8")
        else:
            _log(f"Fix attempt {fix_round} failed")
    else:
        # All fix attempts exhausted
        _log(f"Could not fix {filename} after 3 attempts — flagging to Ops")
        result = {
            "status":    "failed",
            "reason":    "unfixable_syntax_error",
            "file":      filename,
            "error":     error,
            "timestamp": datetime.now().isoformat(),
        }
        _save_build_result(result)
        return result

    # Push to GitHub
    commit_msg = f"[build_agent] {name} — {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    pushed = _git_push(filepath, commit_msg)

    # Mark done in THE_MONKEY.md
    _mark_done(name)

    # Save result
    result = {
        "status":      "success",
        "opportunity": name,
        "file":        str(filepath),
        "filename":    filename,
        "pushed":      pushed,
        "timestamp":   datetime.now().isoformat(),
    }
    _save_build_result(result)
    _log(f"=== Build complete: {filename} ===")
    return result


def _save_build_result(result: dict):
    build_log = _read("build_log.json")
    if "builds" not in build_log:
        build_log["builds"] = []
    build_log["builds"].append(result)
    _write_memory("build_log.json", build_log)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Build Agent Test")
    print("=" * 40)

    test_opportunity = {
        "name": "hvac_call_screener",
        "problem": "HVAC companies miss 40% of calls during peak season",
        "demand": 9,
        "competition": 8,
        "buildability": 8,
        "revenue_speed": 7,
        "total_score": 32,
        "evidence": "Reddit r/HVAC multiple posts about missed revenue from missed calls",
    }

    import tempfile
    test_dir = Path(tempfile.mkdtemp())
    print(f"Building to test directory: {test_dir}")

    result = build(test_opportunity, output_dir=test_dir)
    print(json.dumps(result, indent=2))