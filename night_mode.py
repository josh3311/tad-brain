"""
TAD - Night Mode Autonomous Builder v0.6
Loop 3 fix - iterate-and-test build pattern

v0.6.1 patch (2026-06-10):
- code_executor.import_check fixed (was always failing on absolute
  Windows paths -- "C:.TAD.module" is invalid Python)
- Review gate downgraded from claude-opus-4-8 to claude-haiku-4-5
  (cost control -- Opus was burning the Anthropic balance fast)
- _plan_features fallback no longer treats the WHOLE item as one
  giant feature (this caused massive single-shot generations that
  Kimi truncated mid-string, producing endless syntax errors).
  Fallback now splits into a fixed small-step plan.
- Per-item attempt cap (MAX_ITEM_ATTEMPTS) added to run_night_mode's
  build loop -- after repeated failures on the same item it is logged
  as blocked and skipped for this run, instead of looping forever
  and burning the Kimi balance.
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

from tad_encoding import force_utf8
force_utf8()

from skills.build_agent import _generate_code
from config_providers import claude_chat

load_dotenv()

ROOT        = Path(__file__).parent
AGENTS_DIR  = ROOT / "skills"
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import code_executor

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

REVIEW_MODEL = "claude-haiku-4-5-20251001"
try:
    import anthropic
    _claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
except Exception:
    _claude = None

MONKEY_PATH  = ROOT / "THE_MONKEY.md"
REPORT_PATH  = ROOT / "memory" / "overnight_report.json"
LOG_PATH     = ROOT / "memory" / "night_log.jsonl"
PRODUCTS_DIR = ROOT / "memory" / "products"
DECISIONS_PATH = ROOT / "memory" / "decisions.json"

STOP_HOUR   = 6
_manual_mode = False

MAX_FEATURES      = 5
MAX_FIX_ROUNDS    = 3
MAX_ITEM_ATTEMPTS = 3


def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[NIGHT] {msg}")


def _past_stop_time() -> bool:
    if _manual_mode:
        return False
    return datetime.now().time() >= dtime(STOP_HOUR, 0)


# ── Approved opportunity queue ────────────────────────────────────────────────

def _load_approved_opportunities() -> tuple[list, list]:
    """Return (approved_unbuilt, full_history) from decisions.json.
    Approved = APPROVE or STRONGLY APPROVE, not yet built.
    Uses opportunity_name (decision_agent format), not 'name'.
    """
    if not DECISIONS_PATH.exists():
        return [], []
    try:
        data    = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
        history = data.get("history", [])
        approved = [
            h for h in history
            if h.get("decision") in ("APPROVE", "STRONGLY APPROVE")
            and not h.get("built")
            and h.get("opportunity_name")
        ]
        return approved, history
    except Exception as e:
        _log(f"decisions.json load error: {e}")
        return [], []


def _save_decisions(history: list):
    try:
        DECISIONS_PATH.write_text(
            json.dumps({"history": history}, indent=2), encoding="utf-8"
        )
    except Exception as e:
        _log(f"decisions.json save error: {e}")


def _build_approved_opportunity(opp: dict) -> dict:
    """Call build_agent.build() for one CEO-approved opportunity.
    Output goes to PRODUCTS_DIR so memory/products/ fills up, not ROOT."""
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)
    name = opp.get("opportunity_name", "unnamed")
    _log(f"[NIGHT] Building CEO-approved: {name} (score {opp.get('total_score', '?')}/40)")
    try:
        from skills.build_agent import build as ba_build
        result = ba_build(
            {
                "name":        name,
                "problem":     opp.get("reasoning", ""),
                "total_score": opp.get("total_score", 0),
                "scores":      opp.get("scores", {}),
                "risk_flags":  opp.get("risk_flags", []),
                "market_size": opp.get("market_size", ""),
            },
            output_dir=PRODUCTS_DIR,
        )
        return result
    except Exception as e:
        _log(f"[NIGHT] build_agent error for {name}: {e}")
        return {"status": "failed", "reason": str(e)}


def _read_monkey() -> str:
    return MONKEY_PATH.read_text(encoding="utf-8") if MONKEY_PATH.exists() else ""


def _run_cseo_evolution() -> dict:
    _log("=== CSEO Evolution cycle starting ===")
    try:
        from cseo_agent import run_evolution_cycle
        report = run_evolution_cycle()
        built  = report.get("skills_built", 0)
        _log(f"CSEO evolution complete -- {built} new skills built")

        game_changers = report.get("game_changers", [])
        if game_changers:
            _log("GAME-CHANGING DISCOVERY -- flagging for Joshua on wake")
            for gc in game_changers:
                _log(f"  -> {gc.get('gap_name', 'Unknown')}: {gc.get('description', '')}")

        return report

    except Exception as e:
        _log(f"CSEO evolution error: {e}")
        return {"status": "error", "reason": str(e), "skills_built": 0}


def _run_market_scan() -> dict:
    _log("=== Market Agent scanning for loopholes ===")
    try:
        from market_agent import run_full_scan
        report = run_full_scan()
        opps   = report.get("opportunities", [])
        _log(f"Market scan complete -- {len(opps)} opportunities found")

        if opps:
            for opp in opps[:3]:
                _log(f"  -> {opp.get('name')} (Score: {opp.get('total_score')}/40)")

        return report

    except Exception as e:
        _log(f"Market scan error: {e}")
        return {"status": "error", "reason": str(e), "opportunities": []}


def _run_ops_check() -> dict:
    _log("Ops Agent health check...")
    try:
        from ops_agent import run_full_health_check, generate_daily_summary
        health  = run_full_health_check()
        summary = generate_daily_summary()
        _log(f"Ops check complete -- {health.get('issue_count', 0)} issues")
        return {"health": health, "summary": summary}
    except Exception as e:
        _log(f"Ops check error: {e}")
        return {"status": "error", "reason": str(e)}


def _find_skill(task: str) -> dict | None:
    try:
        from skill_library import find_skill_for_task
        return find_skill_for_task(task)
    except Exception as e:
        _log(f"Skill lookup error: {e}")
        return None


def _learn_skill(task: str, result_summary: str):
    try:
        from skill_library import auto_learn_from_task
        auto_learn_from_task(task, result_summary, success=True)
    except Exception as e:
        _log(f"Skill auto-learn error: {e}")


BUILD_SYSTEM = """You are TAD's code generation engine.

RULES:
1. Output ONLY raw Python 3 code. Nothing else.
2. DO NOT write any explanation, prose, or markdown outside code blocks.
3. Start your response with either import or a docstring.
4. The code must be complete and runnable.
5. Include if __name__ == "__main__": at the bottom.
6. The module MUST support a --test mode: when run as
   `python module.py --test` it runs its own quick self-checks and
   exits 0 on pass, non-zero on fail. Self-checks must not need
   network access or API keys.
7. Build ONLY the feature you are asked for in this cycle. Keep the
   module small and testable. No speculative extras.
8. Put notes inside Python comments (#), not prose.
9. Keep the module SHORT. Prefer fewer, simpler functions over long
   ones. If you are tempted to write a long f-string or long literal,
   break it across multiple shorter lines/strings instead -- unterminated
   strings and unclosed brackets from overly long lines are the most
   common failure mode. Double-check every opening bracket/quote has
   a matching close before finishing.

VIOLATION: Returning prose instead of code is a critical failure."""


def _is_real_python(code: str) -> bool:
    markers = ["import ", "def ", "class ", "if __name__"]
    return any(m in code.strip() for m in markers)


def _extract_code_block(text: str) -> str:
    for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    # unclosed fence (truncated output) — strip the opening marker
    match = re.search(r"```(?:python)?\s*(.*)", text, re.DOTALL)
    if match and text.lstrip().startswith("```"):
        return match.group(1).strip()
    return text.strip()


def _log_kimi_retry(msg: str):
    # Brief 2026-06-12: retry events go to build_log.jsonl (shared with build_agent)
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    build_log = ROOT / "memory" / "build_log.jsonl"
    build_log.parent.mkdir(exist_ok=True)
    with open(build_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    _log(msg)


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


def _kimi(messages: list, max_tokens: int = 8000) -> str:
    """
    Single entry for kimi-k2.6 calls. Retries once at 12000 on ANY
    length finish: empty content means reasoning ate the whole budget;
    non-empty means the answer was truncated mid-stream.
    """
    resp    = _kimi_raw(messages, max_tokens)
    choice  = resp.choices[0]
    content = choice.message.content or ""
    if choice.finish_reason == "length":
        kind = "empty" if not content.strip() else f"truncated ({len(content)} chars)"
        _log_kimi_retry(f"kimi_length_retry: {kind} content at max_tokens={max_tokens}, retrying at 12000")
        resp   = _kimi_raw(messages, 12000)
        choice = resp.choices[0]
        retry_content = choice.message.content or ""
        if retry_content.strip():
            content = retry_content
        if choice.finish_reason == "length" or not content.strip():
            _log_kimi_retry(f"kimi_length_retry FAILED: still {choice.finish_reason} at 12000")
    return content


_GENERIC_FEATURE_PLAN = [
    "Core data model and the single most important calculation/logic, "
    "with a --test mode that checks that calculation on 1-2 known inputs",
    "Storage or aggregation layer on top of the core model (e.g. recording "
    "multiple entries and summarizing them), with --test checks",
    "Simple text or HTML report/output function summarizing the data, "
    "plus a small CLI demo in __main__, with --test checks",
]


def _plan_features(item_name: str, monkey_context: str) -> list[str]:
    prompt = f"""TAD PROJECT CONTEXT:
{monkey_context[:2000]}

TASK: {item_name}

Break this into 2-{MAX_FEATURES} SMALL features, ordered so each one builds
on the previous. Feature 1 must be the minimal working core. Each feature
must be independently testable. Keep each feature small enough to implement
in under ~80 lines of code.

Return ONLY a JSON array of short feature description strings:
["feature one", "feature two"]"""

    # Feature planning is reasoning, not code — use Haiku.
    # _generate_code() would inject BUILD_SYSTEM into fallback models, breaking JSON.
    try:
        raw   = claude_chat(
            "You are a project planning assistant. Always respond with valid JSON only.",
            prompt,
            max_tokens=2000,
        )
        clean = re.sub(r"```json|```", "", raw).strip()
        features = json.loads(clean)
        if isinstance(features, list) and features:
            return [str(f) for f in features[:MAX_FEATURES]]
    except Exception as e:
        _log(f"feature_planning_failed: {str(e)}")

    _log("  Using generic fallback feature plan (small steps)")
    return list(_GENERIC_FEATURE_PLAN)


def _build_feature(item_name: str, feature: str, current_code: str,
                   skill: dict | None, monkey_context: str) -> str | None:
    skill_hint = ""
    if skill:
        skill_hint = f"""
LEARNED SKILL THAT APPLIES (use it):
{skill.get('name')}: {skill.get('what_it_does', '')}
{skill.get('code_or_prompt', '')[:1000]}"""

    if current_code:
        prompt = f"""TASK: {item_name}
{skill_hint}
CURRENT MODULE (all features so far pass their tests):
{current_code}

THIS CYCLE -- add exactly ONE feature: {feature}

Return the COMPLETE updated module with this feature added and its
self-checks added to the --test mode. Do not remove or break existing
features. Output Python code only."""
    else:
        prompt = f"""TAD PROJECT CONTEXT:
{monkey_context[:2000]}

TASK: {item_name}
{skill_hint}
THIS CYCLE -- build exactly ONE feature, the minimal working core: {feature}

Write a small, complete Python module with this feature only, including
a --test self-check mode. Output Python code only."""

    for attempt in range(1, 3):
        try:
            raw  = _generate_code(prompt)
            code = _extract_code_block(raw)
            if _is_real_python(code):
                return code
            _log(f"  Attempt {attempt} returned prose -- retrying")
            prompt += "\n\nPREVIOUS ATTEMPT FAILED -- output ONLY Python code."
        except Exception as e:
            if "Connection error" in str(e) or "connection" in str(e).lower():
                _log(f"[NIGHT] All models unreachable: {str(e)} — skipping build")
                break
            raise
    return None


def _test_failure_summary(test_result: dict) -> str:
    lines = [test_result.get("message", "unknown failure")]
    for t in test_result.get("tests", []):
        if not t.get("success", True):
            stderr = (t.get("stderr") or "")[:800]
            stdout = (t.get("stdout") or "")[:400]
            lines.append(f"[{t.get('type')}] stderr: {stderr}")
            if stdout:
                lines.append(f"[{t.get('type')}] stdout: {stdout}")
    return "\n".join(lines)


def _test_and_fix(filepath: Path, code: str, item_name: str) -> bool:
    filepath.write_text(code, encoding="utf-8")

    for fix_round in range(1, MAX_FIX_ROUNDS + 2):
        result = code_executor.test_file(str(filepath))
        if result["success"]:
            _log(f"  Tests pass: {filepath.name}")
            return True

        failure = _test_failure_summary(result)
        _log(f"  Test failure round {fix_round}: {failure[:200]}")

        if fix_round > MAX_FIX_ROUNDS:
            break

        fix_prompt = f"""This Python module failed its tests.

TASK: {item_name}
TEST OUTPUT:
{failure}

CODE:
{code}

Fix the failure and return ONLY the corrected, complete Python module
(keep the --test self-check mode)."""

        try:
            raw   = _generate_code(fix_prompt)
            fixed = _extract_code_block(raw)
            if _is_real_python(fixed):
                code = fixed
                filepath.write_text(code, encoding="utf-8")
            else:
                break
        except Exception as e:
            if "Connection error" in str(e) or "connection" in str(e).lower():
                _log(f"[NIGHT] All models unreachable: {str(e)} — skipping build")
                break
            _log(f"  Fix error: {e}")
            break

    return False


def _build_and_test(item_name: str, filepath: Path, monkey_context: str) -> dict:
    skill = _find_skill(item_name)
    if skill:
        _log(f"  Using learned skill: {skill.get('name')}")

    features = _plan_features(item_name, monkey_context)
    _log(f"  Plan: {len(features)} feature(s)")
    for i, f in enumerate(features, 1):
        _log(f"    {i}. {f}")

    code  = ""
    built = []

    for feature in features:
        if _past_stop_time():
            _log("  Stop time reached mid-build -- keeping last passing version")
            break

        _log(f"  Cycle: {feature}")
        new_code = _build_feature(item_name, feature, code, skill, monkey_context)
        if not new_code:
            _log(f"  Generation failed for feature: {feature}")
            break

        if _test_and_fix(filepath, new_code, item_name):
            code = filepath.read_text(encoding="utf-8")
            built.append(feature)
        else:
            _log(f"  Feature failed tests after {MAX_FIX_ROUNDS} fixes: {feature}")
            if code:
                filepath.write_text(code, encoding="utf-8")
            else:
                filepath.unlink(missing_ok=True)
            break

    if not built:
        return {"status": "failed", "features_built": [],
                "features_planned": features, "code": ""}

    status = "success" if len(built) == len(features) else "partial"
    return {"status": status, "features_built": built,
            "features_planned": features, "code": code}


def _build_item(item_name: str, monkey_context: str) -> str:
    safe  = re.sub(r"[^a-z0-9_]", "_", item_name.lower()).strip("_")
    fpath = ROOT / f"{safe}.py"
    result = _build_and_test(item_name, fpath, monkey_context)
    return result["code"]


REVIEW_SYSTEM = """You are TAD's code reviewer -- the last gate before code is
committed to the company repo. Review for: real logic (not stubs/placeholders),
correctness bugs, dangerous operations (deleting files outside the project,
leaking secrets, unbounded loops), and whether the code plausibly does what
the task asked.

Return ONLY JSON:
{"verdict": "approve" | "reject", "reasons": ["..."], "must_fix": ["..."]}

Approve working code even if imperfect. Reject stubs, fake logic,
or anything dangerous."""


def _get_diff(filepath: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--", str(filepath)],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except Exception:
        pass
    return filepath.read_text(encoding="utf-8")


def _claude_review(item_name: str, filepath: Path, features: list[str]) -> dict:
    # Fix brief 2026-06-12 Task 3: the review gate FAILS CLOSED. Any
    # condition that prevents a real review (no key, API/credit error,
    # exception) returns verdict "error" and the caller blocks the push.
    if _claude is None or not os.getenv("ANTHROPIC_API_KEY"):
        _log("  Review FAILED -- no ANTHROPIC_API_KEY / anthropic package (blocking push)")
        return {"verdict": "error", "reasons": ["no reviewer available"],
                "must_fix": []}

    diff = _get_diff(filepath)[:12000]
    prompt = f"""TASK THE CODE MUST ACCOMPLISH: {item_name}

FEATURES BUILT THIS RUN:
{json.dumps(features, indent=2)}

DIFF / CODE TO REVIEW ({filepath.name}):
{diff}

All automated tests (syntax, import, --test run) already pass.
Review and return your JSON verdict."""

    try:
        msg = _claude.messages.create(
            model=REVIEW_MODEL,
            max_tokens=1500,
            system=REVIEW_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = next((b.text for b in msg.content if b.type == "text"), "{}")
        clean = re.sub(r"```json|```", "", raw).strip()
        data  = json.loads(clean)
        verdict = data.get("verdict", "reject")
        _log(f"  Claude review: {verdict.upper()}"
             + (f" -- {'; '.join(data.get('reasons', [])[:2])}" if verdict != "approve" else ""))
        return {"verdict": verdict,
                "reasons": data.get("reasons", []),
                "must_fix": data.get("must_fix", [])}
    except Exception as e:
        _log(f"  Review error (blocking push): {e}")
        return {"verdict": "error", "reasons": [str(e)], "must_fix": []}


def _apply_review_fixes(item_name: str, filepath: Path, must_fix: list[str]) -> bool:
    if not must_fix:
        return False
    code = filepath.read_text(encoding="utf-8")
    fix_prompt = f"""A code reviewer rejected this module. Fix ONLY these issues:
{json.dumps(must_fix, indent=2)}

TASK: {item_name}
CODE:
{code}

Return ONLY the corrected, complete Python module (keep the --test mode)."""
    try:
        raw   = _generate_code(fix_prompt)
        fixed = _extract_code_block(raw)
        if _is_real_python(fixed) and _test_and_fix(filepath, fixed, item_name):
            return True
    except Exception as e:
        if "Connection error" in str(e) or "connection" in str(e).lower():
            _log(f"[NIGHT] All models unreachable: {str(e)} — skipping build")
        else:
            _log(f"  Review-fix error: {e}")
    return False


def _git_push(item_name: str, filepath: Path | None = None):
    try:
        targets = ["THE_MONKEY.md", "memory"]
        if filepath is not None:
            targets.insert(0, str(filepath))
        subprocess.run(["git", "add", *targets],
                       cwd=ROOT, check=True, capture_output=True)
        msg = f"[night_mode] {item_name} -- {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["git", "push"], cwd=ROOT, check=True, capture_output=True)
        _log(f"  Pushed to GitHub: {item_name}")
    except subprocess.CalledProcessError as e:
        _log(f"  Git push failed: {e}")


def _get_priority_items(monkey_text: str) -> list[str]:
    items = []
    for line in monkey_text.splitlines():
        if line.strip().startswith("- [ ]"):
            item = line.strip().replace("- [ ]", "").strip()
            if item and len(item) > 5:
                items.append(item)

    build_items = [i for i in items if re.match(r"P\d+-BUILD-\d+", i)]
    other_items = [i for i in items if i not in build_items]
    return build_items + other_items


def generate_new_tasks(monkey_text: str) -> list[str]:
    _log("Priority list empty -- CSEO generating new tasks...")
    prompt = f"""TAD PROJECT CONTEXT:
{monkey_text[:3000]}

Generate 5 new high-value tasks that would most advance TAD AI
toward its mission of finding and solving AI loopholes.

Return ONLY a JSON array of task name strings.
["Task one", "Task two", "Task three"]

JSON array only."""

    # Task generation is reasoning, not code — use Haiku (fast, cheap, JSON-reliable).
    # _generate_code() carries BUILD_SYSTEM ("output ONLY Python code") which breaks
    # JSON responses in fallback models. claude_chat uses Haiku with correct framing.
    try:
        raw   = claude_chat(
            "You are a project planning assistant. Always respond with valid JSON only.",
            prompt,
            max_tokens=1000,
        )
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        _log(f"task_generation_failed: {str(e)}")
        return []


def _mark_done(item_name: str):
    if not MONKEY_PATH.exists():
        return
    text    = MONKEY_PATH.read_text(encoding="utf-8")
    today   = datetime.now().strftime("%Y-%m-%d")
    updated = text.replace(
        f"- [ ] {item_name}",
        f"- [x] {item_name} (done {today})"
    )
    MONKEY_PATH.write_text(updated, encoding="utf-8")


def _mark_blocked(item_name: str, reason: str):
    if not MONKEY_PATH.exists():
        return
    text  = MONKEY_PATH.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    target = f"- [ ] {item_name}"
    replacement = f"- [ ] {item_name} (BLOCKED {today} -- {reason[:80]} -- needs human review)"
    if target in text and "(BLOCKED" not in text:
        text = text.replace(target, replacement, 1)
        MONKEY_PATH.write_text(text, encoding="utf-8")


def run_night_mode():
    _log("=== Night mode v0.6.1 started (iterate-and-test) ===")

    # Quick health check — surface model availability at start rather than
    # discovering failures 30 minutes into builds.
    try:
        claude_chat("respond with ok", "ok", max_tokens=5)
        _log("[NIGHT] Primary model (Haiku/Sonnet) reachable — proceeding")
    except Exception as e:
        _log(f"[NIGHT] WARNING: Primary model unreachable: {str(e)}")
        _log("[NIGHT] Will attempt builds with fallback models")
        # Do NOT stop night mode — fallback chain handles this

    report = {
        "started":          datetime.now().isoformat(),
        "built":            [],
        "skipped":          [],
        "errors":           [],
        "blocked":          [],
        "cseo_evolution":   {},
        "market_scan":      {},
        "ops_health":       {},
        "game_changers":    [],
    }

    if not _past_stop_time():
        cseo_report = _run_cseo_evolution()
        report["cseo_evolution"]  = cseo_report
        report["game_changers"]   = cseo_report.get("game_changers", [])

    if not _past_stop_time():
        market_report = _run_market_scan()
        report["market_scan"] = market_report

    # ── PHASE: Build CEO-approved opportunities → memory/products/ ────────────
    # These are real market-validated ideas (APPROVE/STRONGLY APPROVE from
    # decision_agent). They must be built before any internal TAD tasks.
    # build_agent.build() handles code-gen, syntax check, and git push.
    # Output goes to PRODUCTS_DIR so products/ fills up, not ROOT.
    if not _past_stop_time():
        approved_opps, full_history = _load_approved_opportunities()
        if approved_opps:
            _log(f"[NIGHT] {len(approved_opps)} CEO-approved opportunities queued for build")
            for opp in approved_opps:
                if _past_stop_time():
                    break
                result = _build_approved_opportunity(opp)
                opp_name = opp.get("opportunity_name", "unknown")
                if result.get("status") == "success":
                    # Mark built so it won't be rebuilt next night
                    for h in full_history:
                        if h.get("opportunity_name") == opp_name:
                            h["built"]        = True
                            h["built_at"]     = datetime.now().isoformat()
                            h["build_file"]   = result.get("filename", "")
                    _save_decisions(full_history)
                    report["built"].append({
                        "item":   opp_name,
                        "file":   result.get("file", ""),
                        "source": "decisions_approved",
                        "ts":     datetime.now().isoformat(),
                    })
                    _log(f"[NIGHT] Built approved: {opp_name} → {result.get('filename')}")
                else:
                    report["errors"].append({
                        "item":   opp_name,
                        "reason": result.get("reason", "build_failed"),
                        "source": "decisions_approved",
                    })
                    _log(f"[NIGHT] Build failed for approved: {opp_name} — {result.get('reason')}")
        else:
            _log("[NIGHT] No unbuilt approved opportunities — continuing to CSEO build loop")

    item_attempts: dict[str, int] = {}

    while not _past_stop_time():
        monkey = _read_monkey()
        items  = _get_priority_items(monkey)

        items = [i for i in items if item_attempts.get(i, 0) < MAX_ITEM_ATTEMPTS]

        if not items:
            generated = generate_new_tasks(monkey)
            generated = [i for i in generated
                          if item_attempts.get(i, 0) < MAX_ITEM_ATTEMPTS]
            if not generated:
                _log("No buildable tasks left -- sleeping 30m")
                time.sleep(1800)
                continue
            items = generated

        item = items[0]
        item_attempts[item] = item_attempts.get(item, 0) + 1
        attempt_n = item_attempts[item]

        if any(x in item.lower() for x in [
            "skills/", "skill file", ".md", "skill_file",
            "write skills", "update skills"
        ]):
            _log(f"Skipping non-Python item: {item}")
            _mark_done(item)
            report["skipped"].append(item)
            continue

        _log(f"Building ({attempt_n}/{MAX_ITEM_ATTEMPTS}): {item}")

        safe  = re.sub(r"[^a-z0-9_]", "_", item.lower()).strip("_")
        fpath = ROOT / f"{safe}.py"

        result = _build_and_test(item, fpath, monkey)

        if result["status"] == "failed":
            if attempt_n >= MAX_ITEM_ATTEMPTS:
                _mark_blocked(item, "build failed after max attempts")
                report["blocked"].append({"item": item,
                                          "planned": result["features_planned"]})
                _log(f"  Blocked after {attempt_n} attempts: {item}")
            else:
                report["errors"].append({"item": item, "reason": "build_failed",
                                         "attempt": attempt_n,
                                         "planned": result["features_planned"]})
                _log(f"  Build failed (attempt {attempt_n}): {item}")
            time.sleep(15)
            continue

        review = _claude_review(item, fpath, result["features_built"])

        if review["verdict"] == "reject":
            _log("  Reviewer rejected -- one fix round")
            if _apply_review_fixes(item, fpath, review["must_fix"]):
                review = _claude_review(item, fpath, result["features_built"])

        if review["verdict"] == "reject":
            fpath.unlink(missing_ok=True)
            if attempt_n >= MAX_ITEM_ATTEMPTS:
                _mark_blocked(item, "review rejected after max attempts")
                report["blocked"].append({"item": item, "review": review["reasons"]})
                _log(f"  Blocked after {attempt_n} attempts (review): {item}")
            else:
                report["errors"].append({"item": item, "reason": "review_rejected",
                                         "attempt": attempt_n,
                                         "review": review["reasons"]})
                _log(f"  Review rejected, file removed: {item}")
            time.sleep(15)
            continue

        if review["verdict"] != "approve":
            # Review could not run (API/credit failure etc.) — FAIL CLOSED:
            # keep the file local for morning review but never push unreviewed
            # code or mark the item done.
            reason = "; ".join(review.get("reasons", []))[:200]
            _log(f"  review_failed_blocking_push: {reason} — {fpath.name} kept local, NOT pushed")
            report["errors"].append({"item": item,
                                     "reason": "review_failed_blocking_push",
                                     "attempt": attempt_n,
                                     "review": review.get("reasons", [])})
            time.sleep(15)
            continue

        if result["status"] == "success":
            _mark_done(item)
        _git_push(item, fpath)
        report["built"].append({
            "item":             item,
            "file":             str(fpath),
            "features_built":   result["features_built"],
            "features_planned": result["features_planned"],
            "build_status":     result["status"],
            "review":           review["verdict"],
            "ts":               datetime.now().isoformat(),
        })
        _log(f"  Completed ({result['status']}): {item}")

        _learn_skill(
            item,
            f"Built {fpath.name} with features: {', '.join(result['features_built'])}. "
            f"All tests passed, review: {review['verdict']}.",
        )

        time.sleep(15)

    ops_report = _run_ops_check()
    report["ops_health"] = ops_report

    _log("=== Night mode ended -- saving report ===")
    REPORT_PATH.parent.mkdir(exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    _log(f"Report saved -> {REPORT_PATH}")


_running = False


def is_running() -> bool:
    return _running


def start_night_mode(status_callback=None):
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
                status_callback("Night mode started -- CSEO evolving TAD...")
            run_night_mode()
            if status_callback:
                status_callback("Night mode complete -- report ready.")
        except Exception as e:
            _log(f"Night mode error: {e}")
            if status_callback:
                status_callback(f"Night mode error: {e}")
        finally:
            _running = False

    t = threading.Thread(target=_run, daemon=True, name="NightMode")
    t.start()


def check_overnight_report() -> dict | None:
    if REPORT_PATH.exists():
        try:
            data  = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            built = data.get("built", [])
            cseo  = data.get("cseo_evolution", {})
            market = data.get("market_scan", {})
            opps  = market.get("opportunities", [])
            game_changers = data.get("game_changers", [])
            blocked = data.get("blocked", [])

            summary = (
                f"Built {len(built)} items. "
                f"CSEO added {cseo.get('skills_built', 0)} new skills. "
                f"Market found {len(opps)} opportunities. "
                f"Skipped {len(data.get('skipped', []))}. "
                f"Errors: {len(data.get('errors', []))}. "
                f"Blocked: {len(blocked)}."
            )

            if game_changers:
                summary += f" {len(game_changers)} game-changing discovery found!"

            return {
                "total_built":    len(built),
                "total_files":    len(built),
                "exec_summary":   summary,
                "built":          built,
                "skipped":        data.get("skipped", []),
                "errors":         data.get("errors", []),
                "blocked":        blocked,
                "cseo_skills":    cseo.get("skills_built", 0),
                "opportunities":  opps,
                "game_changers":  game_changers,
                "date":           datetime.now().strftime("%Y-%m-%d"),
            }
        except Exception:
            return None
    return None


if __name__ == "__main__":
    _manual_mode = True
    run_night_mode()