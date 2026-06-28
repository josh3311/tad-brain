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

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
try:
    from skills.agent_soul import _get_agent_context, _log_history
except ImportError:
    def _get_agent_context(n): return ""
    def _log_history(n, e): pass

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
8. Keep the module under ~250 lines. Prefer fewer, simpler functions —
   a small working module beats a large truncated one.

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
    # unclosed fence (truncated output) — strip the opening marker so the
    # syntax check fails on the real code, not on the ``` line
    match = re.search(r"```(?:python)?\s*(.*)", text, re.DOTALL)
    if match and text.lstrip().startswith("```"):
        return match.group(1).strip()
    return text.strip()


def _is_real_python(code: str) -> bool:
    markers = ["import ", "def ", "class ", "if __name__"]
    return any(m in code for m in markers)


# kimi-k2.6 is a reasoning model: with thinking ON, chain-of-thought
# consumes max_tokens BEFORE answer tokens emit (verified 2026-06-12:
# 12000 tokens fully spent on reasoning, content=""). Thinking is
# disabled for code-gen; the API then requires temperature=0.6.
KIMI_NO_THINK = {"thinking": {"type": "disabled"}}


def _kimi_raw(messages: list, max_tokens: int):
    try:
        return client.chat.completions.create(
            model=MODEL, messages=messages,
            temperature=0.6, max_tokens=max_tokens,
            extra_body=KIMI_NO_THINK,
        )
    except Exception as e:
        # model variant without thinking control — fall back to old call
        _log(f"kimi no-think rejected ({str(e)[:100]}) — falling back to thinking mode")
        return client.chat.completions.create(
            model=MODEL, messages=messages,
            temperature=1, max_tokens=max_tokens,
        )


def _kimi_call(messages: list, max_tokens: int = 8000) -> str:
    """
    Single entry for kimi-k2.6 code-gen. Retries once at 12000 on ANY
    length finish: empty content means reasoning ate the whole budget;
    non-empty means the answer was truncated mid-stream (may still
    compile by luck — never trust it). Retries logged to build_log.jsonl.
    """
    resp    = _kimi_raw(messages, max_tokens)
    choice  = resp.choices[0]
    content = choice.message.content or ""
    if choice.finish_reason == "length":
        kind = "empty" if not content.strip() else f"truncated ({len(content)} chars)"
        _log(f"kimi_length_retry: {kind} content at max_tokens={max_tokens}, retrying at 12000")
        resp   = _kimi_raw(messages, 12000)
        choice = resp.choices[0]
        retry_content = choice.message.content or ""
        if retry_content.strip():
            content = retry_content
        if choice.finish_reason == "length" or not content.strip():
            _log(f"kimi_length_retry FAILED: still {choice.finish_reason} at 12000")
    return content


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


# ── Resilient multi-model code generation ────────────────────────────────────

def _generate_code(prompt: str, max_tokens: int = 8000) -> str:
    """
    Resilient code generation with silent fallback chain.
    Priority: Claude Sonnet → Kimi K2.6 → MiniMax M3 → DeepSeek V4 Pro.
    Logs which model succeeded to build_log.jsonl for cost tracking.
    Only returns empty string if ALL four models fail — never fabricates.
    """
    import sys
    sys.path.insert(0, str(ROOT))
    from config_providers import claude_build, minimax_code, deepseek_code

    # Kimi uses _kimi_call which handles the no-think mode and length retry.
    def _kimi_wrapper(p: str, mt: int) -> str:
        return _kimi_call([
            {"role": "system", "content": BUILD_SYSTEM},
            {"role": "user",   "content": p},
        ], mt)

    attempts = [
        ("claude-sonnet", claude_build),
        ("kimi-k2.6",     _kimi_wrapper),
        ("minimax-m3",    minimax_code),
        ("deepseek-v4",   deepseek_code),
    ]
    for model_name, fn in attempts:
        try:
            result = fn(prompt, max_tokens)
            if result and result.strip():
                _log(f"Code generated via {model_name}")
                return result
            _log(f"{model_name} returned empty — trying next model")
        except Exception as e:
            _log(f"{model_name} failed: {str(e)} — trying next model")
    _log("all_code_models_failed — build cannot proceed")
    return ""


# ── Truncation detection and continuation ────────────────────────────────────

def _is_truncated(code: str) -> bool:
    """
    Detect code that got cut off mid-stream.
    Truncated code always causes syntax errors but the root cause
    is output limit, not bad generation — continuation fixes it.
    """
    import ast
    code = code.strip()
    if not code:
        return False
    # Unclosed triple-quote strings
    if code.count('"""') % 2 != 0:
        return True
    if code.count("'''") % 2 != 0:
        return True
    # Unclosed string literals (single or double quote)
    try:
        ast.parse(code)
    except SyntaxError as e:
        msg = str(e).lower()
        if any(phrase in msg for phrase in [
            "eol while scanning string",
            "eof while scanning",
            "unterminated string",
            "unexpected eof",
        ]):
            return True
    lines = [l for l in code.split('\n') if l.strip()]
    if not lines:
        return False
    last = lines[-1].strip()
    # Last line is a continuation character or open bracket
    if last.endswith(('\\', ',', '(', '[', '{')):
        return True
    # Last line is a partial keyword with no body
    if last.endswith(':') and not any(
        last.startswith(k) for k in
        ('class ', 'def ', 'if ', 'else:', 'elif ', 'for ',
         'while ', 'try:', 'except', 'finally:', 'with ')
    ):
        return True
    return False


def _continue_truncated(original_prompt: str,
                        partial_code: str,
                        max_tokens: int = 16000) -> str:
    """
    Ask the model to continue from where it got cut off.
    Combines original + continuation into one complete module.
    """
    _log("[BUILD] Output truncated — requesting continuation")
    continuation_prompt = f"""You were writing a Python module and
your output was cut off before you finished.

Here is everything you wrote so far:
{partial_code}

Continue writing the Python code from EXACTLY where you stopped.
Output ONLY the remaining code — do NOT repeat what is already
written above. Start from the next line after the cut-off point.
Complete the module including the if __name__ == '__main__': block
and --test mode if not already present."""

    try:
        continuation = _generate_code(continuation_prompt, max_tokens)
        continuation = _extract_code(continuation)
        if continuation and _is_real_python(continuation):
            combined = partial_code.rstrip() + '\n' + continuation.lstrip()
            _log(f"[BUILD] Continuation added {len(continuation)} chars")
            return combined
    except Exception as e:
        _log(f"[BUILD] Continuation failed: {e}")
    return partial_code


# ── Code generation ───────────────────────────────────────────────────────────

def generate_code(opportunity: dict, filename: str) -> str | None:
    """
    Ask Kimi to generate real Python code for the opportunity.
    Returns code string or None after 3 failed attempts.
    """
    skill = _load_skill()
    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:1500] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    _ctx = _get_agent_context("build")
    prompt = f"""{(_ctx + chr(10) + chr(10)) if _ctx else ""}TAD PROJECT CONTEXT:
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
            raw  = _generate_code(prompt, max_tokens=16000)
            code = _extract_code(raw)

            if _is_truncated(code):
                code = _continue_truncated(prompt, code)
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
        raw  = _generate_code(fix_prompt, max_tokens=32000)
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

def _plan_architecture(opportunity: dict, output_dir: Path) -> dict:
    """
    Generate a full project blueprint before any code is written.
    Saves ARCHITECTURE.md to the product output directory.
    Returns architecture dict that guides the build.
    """
    from config_providers import claude_json as _claude_json
    name    = opportunity.get("name", "unknown")
    problem = opportunity.get("problem", "")
    score   = opportunity.get("total_score", 0)

    ci       = opportunity.get("complaint_intelligence", {})
    who      = ci.get("who", "")
    language = ci.get("their_language", "")
    resonant = ci.get("resonant_solution", "")

    prompt = f"""You are TAD's senior software architect.
Plan the complete architecture for this MVP product.

PRODUCT: {name}
PROBLEM BEING SOLVED: {problem}
TARGET USER: {who if who else 'AI developers and teams'}
WHAT RESONATES WITH THEM: {resonant if resonant else 'clear, working solution'}
THEIR LANGUAGE: {language if language else 'technical'}
OPPORTUNITY SCORE: {score}/40

Return ONLY valid JSON — no preamble, no explanation:
{{
  "entry_point": "main file e.g. main.py",
  "files": [
    {{
      "name": "filename.py",
      "purpose": "one sentence: what this file does",
      "depends_on": []
    }}
  ],
  "data_model": "key data structures in 1-2 sentences",
  "mvp_scope": "what the MVP does — 2 sentences max",
  "done_criteria": "how we know the build is complete",
  "build_order": ["file1.py", "file2.py"]
}}

IMPORTANT: Keep MVP scope tight — maximum 2 files for overnight build.
One file is better. Complexity kills overnight builds."""

    try:
        raw  = _claude_json(
            "You are a software architect. Return only valid JSON.",
            prompt,
            max_tokens=1500,
        )
        import json as _json
        arch = _json.loads(raw) if isinstance(raw, str) else raw

        output_dir.mkdir(parents=True, exist_ok=True)
        arch_lines = [
            f"# {name} — Architecture Plan",
            f"Generated: {datetime.now().isoformat()}",
            "",
            "## MVP Scope",
            arch.get("mvp_scope", ""),
            "",
            "## Target User",
            who if who else "AI developers and teams",
            "",
            "## Files",
        ]
        for f in arch.get("files", []):
            arch_lines.append(f"\n### {f['name']}")
            arch_lines.append(f["purpose"])
            if f.get("depends_on"):
                arch_lines.append(f"Depends on: {', '.join(f['depends_on'])}")
        arch_lines += [
            "",
            "## Data Model",
            arch.get("data_model", ""),
            "",
            "## Done Criteria",
            arch.get("done_criteria", ""),
        ]
        arch_path = output_dir / "ARCHITECTURE.md"
        arch_path.write_text("\n".join(arch_lines), encoding="utf-8")
        _log(f"[BUILD] Architecture planned -> {arch_path}")
        _log(f"[BUILD] MVP: {arch.get('mvp_scope', '')[:80]}")
        return arch

    except Exception as e:
        _log(f"[BUILD] Architecture planning failed: {e} — using default")
        return {
            "entry_point": "main.py",
            "files": [{"name": "main.py",
                       "purpose": "main product module",
                       "depends_on": []}],
            "data_model": "standard Python data structures",
            "mvp_scope": problem[:100],
            "done_criteria": "module runs without errors with --test mode",
            "build_order": ["main.py"],
        }


def _save_checkpoint(output_dir: Path, feature_name: str,
                     code: str, features_done: list):
    """Save build progress after each successful feature."""
    checkpoint = {
        "ts":                     datetime.now().isoformat(),
        "last_completed_feature": feature_name,
        "features_done":          features_done,
        "features_done_count":    len(features_done),
        "code_length":            len(code),
    }
    cp_path = output_dir / "progress.json"
    try:
        cp_path.write_text(
            json.dumps(checkpoint, indent=2), encoding="utf-8"
        )
        _log(f"[BUILD] Checkpoint saved: {len(features_done)} features done")
    except Exception as e:
        _log(f"[BUILD] Checkpoint save failed: {e}")


def _load_checkpoint(output_dir: Path) -> dict:
    """Load previous build progress if it exists."""
    cp_path = output_dir / "progress.json"
    if cp_path.exists():
        try:
            data = json.loads(cp_path.read_text(encoding="utf-8"))
            _log(f"[BUILD] Checkpoint found: "
                 f"{data.get('features_done_count', 0)} features previously done")
            return data
        except Exception:
            pass
    return {}


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

    # Step 0: Plan architecture before writing any code
    arch = _plan_architecture(opportunity, output_dir)

    # Generate code
    code = generate_code(opportunity, filename)
    if not code:
        _log(f"Code generation failed for {name}")
        return {"status": "failed", "reason": "generation_failed", "file": filename}

    # Write file
    filepath.write_text(code, encoding="utf-8")
    _log(f"[BUILD] Output written to: {filepath.resolve()}")

    # Test and fix loop
    for fix_round in range(1, 4):
        ok, error = _syntax_check(filepath)
        if ok:
            _log(f"Syntax check passed on round {fix_round}")
            _save_checkpoint(output_dir, name, code, [name])
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
        "mvp_scope":   arch.get("mvp_scope", ""),
    }
    _save_build_result(result)
    _log_history("build", {
        "action":  "build_complete",
        "product": name,
        "file":    filename,
        "pushed":  pushed,
    })
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