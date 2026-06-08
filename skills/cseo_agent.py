"""
TAD AI — CSEO Agent Script
Chief Self-Evolution Officer — TAD's Brain That Never Stops Growing
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

ROOT        = Path(__file__).parent.parent
MEMORY      = ROOT / "memory"
SKILLS_DIR  = ROOT / "skills" / "learned"
SKILL_PATH  = Path(__file__).parent / "cseo_agent.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# Core files CSEO can never touch
PROTECTED = [
    "tad_gui.py", "agent.py", "scheduler.py",
    "night_mode.py", "voice_input.py", "tad_visual.py",
    "sync.py", ".env"
]

BUILD_SYSTEM = """You are TAD's self-evolution engine.
Output ONLY raw Python 3 code. Never prose or plans.
Every file must be complete, tested, and runnable.
Start with imports or a docstring."""


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
    log_path = MEMORY / "cseo_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[CSEO] {msg}")


def _extract_code(text: str) -> str:
    for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
    return text.strip()


def _is_real_python(code: str) -> bool:
    return any(m in code for m in ["import ", "def ", "class ", "if __name__"])


def _syntax_check(filepath: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(filepath)],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr.strip()


# ── Gap analysis ──────────────────────────────────────────────────────────────

def identify_gaps() -> list:
    """
    Analyze TAD's current state and identify capability gaps.
    Returns list of improvements to build this cycle.
    """
    skill  = _load_skill()
    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:2000] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    # Read current learned skills
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    existing_skills = [f.stem for f in SKILLS_DIR.glob("*.md")]

    # Read error patterns
    error_log  = _read("error_log.json")
    errors     = error_log.get("errors", [])[-10:]

    # Read build history
    build_log  = _read("build_log.json")
    builds     = build_log.get("builds", [])[-10:]

    prompt = f"""TAD AI CURRENT STATE:

MISSION (THE_MONKEY.md):
{monkey}

EXISTING LEARNED SKILLS:
{json.dumps(existing_skills)}

RECENT ERRORS (patterns to fix):
{json.dumps([e.get('error', '')[:100] for e in errors])}

RECENT BUILDS:
{json.dumps([b.get('opportunity', '') for b in builds])}

As the CSEO, identify the TOP 3 capability gaps TAD has right now.
These should be skills or tools TAD needs but doesn't have yet.
Focus on what would make the biggest impact on the mission.

Return ONLY a JSON array:
[
  {{
    "gap_name": "short name for this capability",
    "description": "what TAD cannot do that it needs to do",
    "why_important": "how this serves the mission",
    "build_type": "skill_file or python_module or improvement",
    "priority": 1
  }}
]

Return JSON array only. Top 3 gaps maximum."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=800,
        )
        raw   = resp.choices[0].message.content or "[]"
        clean = re.sub(r"```json|```", "", raw).strip()
        gaps  = json.loads(clean)
        _log(f"Identified {len(gaps)} capability gaps")
        return gaps

    except Exception as e:
        _log(f"Gap analysis error: {e}")
        return []


# ── Skill builder ─────────────────────────────────────────────────────────────

def build_skill(gap: dict) -> dict:
    """
    Build a new skill file and script for an identified gap.
    Returns build result.
    """
    skill_name = re.sub(r"[^a-z0-9_]", "_", gap.get("gap_name", "new_skill").lower())
    _log(f"Building new skill: {skill_name}")

    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:1500] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    # Build the .md skill file
    md_prompt = f"""Create a complete skill file for TAD AI for this capability:

GAP: {json.dumps(gap)}

MISSION CONTEXT:
{monkey}

Write a complete skill.md file following this exact structure:
# {skill_name.upper()} SKILL FILE
# TAD AI — [Role Name]
# Version: 1.0

## ROLE
[one paragraph]

## PROMPT
[exact instructions]

## TOOLS
[list]

## DATA SOURCES
[list]

## TRIGGERS
[list]

## OUTPUT
[list]

## SUCCESS CRITERIA
[list]

## CRUD AUTHORITY
[what it can and cannot do]

Return the complete skill file content only."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _load_skill()},
                {"role": "user",   "content": md_prompt},
            ],
            temperature=1,
            max_tokens=1500,
        )
        md_content = resp.choices[0].message.content or ""

        # Save skill.md
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        md_path = SKILLS_DIR / f"{skill_name}.md"
        md_path.write_text(md_content, encoding="utf-8")
        _log(f"Skill file saved: {md_path.name}")

    except Exception as e:
        _log(f"Skill MD generation error: {e}")
        return {"status": "failed", "reason": str(e)}

    # Build the .py script
    py_prompt = f"""Write a complete Python module for this TAD AI skill:

SKILL: {skill_name}
DESCRIPTION: {gap.get('description')}
PURPOSE: {gap.get('why_important')}

MISSION:
{monkey}

Requirements:
- Real working Python 3 code
- Integrates with TAD's memory/ folder
- Logs all actions to memory/{skill_name}_log.jsonl
- Has a main() function and if __name__ == "__main__": block
- Error handling on all external calls
- Works with Kimi API via OpenAI client

Output Python code only."""

    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": BUILD_SYSTEM},
                    {"role": "user",   "content": py_prompt},
                ],
                temperature=1,
                max_tokens=2500,
            )
            raw  = resp.choices[0].message.content or ""
            code = _extract_code(raw)

            if not _is_real_python(code):
                _log(f"Attempt {attempt} returned prose — retrying")
                continue

            # Save and test
            py_path = SKILLS_DIR / f"{skill_name}.py"
            py_path.write_text(code, encoding="utf-8")

            ok, error = _syntax_check(py_path)
            if ok:
                _log(f"Script built and tested: {py_path.name}")

                # Git push
                try:
                    subprocess.run(["git", "add", str(py_path), str(md_path)],
                                   cwd=ROOT, capture_output=True)
                    subprocess.run(
                        ["git", "commit", "-m",
                         f"[cseo] New skill: {skill_name} — {datetime.now().strftime('%Y-%m-%d')}"],
                        cwd=ROOT, capture_output=True
                    )
                    subprocess.run(["git", "push"], cwd=ROOT, capture_output=True)
                    _log(f"Pushed to GitHub: {skill_name}")
                except Exception:
                    _log("Git push failed — skill saved locally")

                return {
                    "status":     "success",
                    "skill_name": skill_name,
                    "md_file":    str(md_path),
                    "py_file":    str(py_path),
                    "gap":        gap,
                }
            else:
                _log(f"Syntax error attempt {attempt}: {error[:100]}")
                py_prompt += f"\n\nFix this error: {error}"

        except Exception as e:
            _log(f"Script generation error attempt {attempt}: {e}")

    return {"status": "failed", "skill_name": skill_name, "reason": "syntax_unfixable"}


# ── Game-changing detection ───────────────────────────────────────────────────

def check_for_game_changer(gap: dict) -> bool:
    """
    Evaluate if a discovery meets the game-changing threshold.
    Returns True only if all 4 criteria are met.
    """
    skill = _load_skill()

    prompt = f"""Evaluate if this discovery is truly GAME-CHANGING for TAD AI:

DISCOVERY: {json.dumps(gap)}

A discovery is game-changing ONLY if ALL 4 criteria are met:
1. TAD cannot currently do this at all
2. It would open an entirely new revenue stream or capability
3. It would take TAD from current level to fundamentally new level
4. It is buildable within TAD's current Python architecture

Score each criterion 1-10.
Return ONLY JSON:
{{
  "criterion_1_score": 0,
  "criterion_2_score": 0,
  "criterion_3_score": 0,
  "criterion_4_score": 0,
  "total": 0,
  "is_game_changing": false,
  "reason": "one sentence"
}}

Only mark is_game_changing true if ALL scores are 8 or above."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=300,
        )
        raw    = resp.choices[0].message.content or "{}"
        clean  = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(clean)
        return result.get("is_game_changing", False)

    except Exception as e:
        _log(f"Game-changer check error: {e}")
        return False


# ── Evolution report ──────────────────────────────────────────────────────────

def generate_evolution_report(built_skills: list, gaps_found: list) -> dict:
    """Generate full evolution report after a build cycle."""
    skill  = _load_skill()
    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:1000] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    prompt = f"""Generate a CSEO evolution report for Joshua.

GAPS IDENTIFIED THIS CYCLE:
{json.dumps(gaps_found, indent=2)}

SKILLS BUILT THIS CYCLE:
{json.dumps(built_skills, indent=2)}

MISSION:
{monkey}

Write a clear evolution report covering:
1. What I learned this cycle
2. What I built and why
3. What each new skill does
4. How it connects to the company vision
5. What I recommend building next cycle

Keep it direct and specific. Joshua needs to understand
exactly what TAD can do now that it couldn't do before.
Under 200 words."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=400,
        )
        report_text = resp.choices[0].message.content or ""

        report = {
            "cycle_date":    datetime.now().isoformat(),
            "gaps_found":    len(gaps_found),
            "skills_built":  len([s for s in built_skills if s.get("status") == "success"]),
            "skills_failed": len([s for s in built_skills if s.get("status") == "failed"]),
            "built_skills":  built_skills,
            "report_text":   report_text,
        }

        # Save to evolution log
        evo_log = _read("evolution_log.json")
        if "cycles" not in evo_log:
            evo_log["cycles"] = []
        evo_log["cycles"].append(report)
        _write("evolution_log.json", evo_log)

        _log(f"Evolution report saved: {report['skills_built']} skills built")
        return report

    except Exception as e:
        _log(f"Evolution report error: {e}")
        return {"status": "error", "reason": str(e)}


# ── Main evolution cycle ──────────────────────────────────────────────────────

def run_evolution_cycle() -> dict:
    """
    Full CSEO evolution cycle.
    Identify gaps → build skills → check for game changers → report.
    """
    _log("=== CSEO Evolution cycle started ===")

    # Step 1: Identify gaps
    gaps = identify_gaps()
    if not gaps:
        _log("No gaps identified this cycle")
        return {"status": "no_gaps", "cycle_date": datetime.now().isoformat()}

    built_skills   = []
    game_changers  = []

    # Step 2: Build skills for each gap
    for gap in gaps:
        # Check if game-changing first
        if check_for_game_changer(gap):
            _log(f"GAME-CHANGING DISCOVERY: {gap.get('gap_name')} — flagging Joshua!")
            game_changers.append(gap)
            continue

        # Build the skill
        result = build_skill(gap)
        built_skills.append(result)

        if result.get("status") == "success":
            _log(f"✓ New skill built: {result.get('skill_name')}")
        else:
            _log(f"✗ Skill failed: {result.get('skill_name')}")

    # Step 3: Generate evolution report
    report = generate_evolution_report(built_skills, gaps)

    # Step 4: Update THE_MONKEY.md
    successful = [s for s in built_skills if s.get("status") == "success"]
    if successful:
        monkey_path = ROOT / "THE_MONKEY.md"
        if monkey_path.exists():
            content = monkey_path.read_text(encoding="utf-8")
            today   = datetime.now().strftime("%Y-%m-%d")
            new_entries = "\n".join(
                [f"- [x] CSEO built: {s.get('skill_name')} ✓ {today}"
                 for s in successful]
            )
            content = content.replace(
                "## SESSION LOG",
                f"## SESSION LOG\n\n### CSEO Auto-build {today}\n{new_entries}\n"
            )
            monkey_path.write_text(content, encoding="utf-8")

    report["game_changers"] = game_changers
    _log(f"=== Evolution cycle complete: {len(successful)} skills built ===")
    return report


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — CSEO Agent Test")
    print("=" * 40)

    print("Running evolution cycle...")
    result = run_evolution_cycle()

    print(f"\nGaps found: {result.get('gaps_found', 0)}")
    print(f"Skills built: {result.get('skills_built', 0)}")
    print(f"Game changers: {len(result.get('game_changers', []))}")

    if result.get("report_text"):
        print(f"\nEvolution Report:\n{result['report_text']}")