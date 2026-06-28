"""
TAD — Agent Soul Module  (skills/agent_soul.py)
Persistent identity, toolset, and history for every agent.
All agents import from this module — never breaks if file is missing.
"""

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
AGENTS_DIR = ROOT / "memory" / "agents"


# ── Identity ───────────────────────────────────────────────────────────────────

def _load_identity(agent_name: str) -> dict:
    """Load agent's soul from memory/agents/{name}/identity.json."""
    path = AGENTS_DIR / agent_name / "identity.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_agent_context(agent_name: str, complaint_intel: dict = None) -> str:
    """
    Build a concise identity context string for prepending to Claude system prompts.
    Returns empty string if identity not found — agent works exactly as before.
    Includes complaint intelligence when provided (product/build/market tasks).
    """
    identity = _load_identity(agent_name)
    if not identity:
        return ""

    name     = identity.get("name", agent_name)
    mindset  = identity.get("mindset", "")
    rules    = identity.get("decision_rules", [])
    recent   = _get_recent_history(agent_name, n=3)

    parts = [f"You are {name}."]
    if mindset:
        parts.append(f"Mindset: {mindset}")
    if rules:
        parts.append("Decision rules: " + " | ".join(rules[:3]))
    if recent and recent != "No history yet.":
        parts.append(f"Recent actions:\n{recent}")

    if complaint_intel and complaint_intel.get("who"):
        parts.append(
            "\n=== COMPLAINT INTELLIGENCE ===\n"
            f"WHO suffers this: {complaint_intel.get('who')}\n"
            f"What they tried: {complaint_intel.get('tried_and_failed')}\n"
            f"What relief looks like: {complaint_intel.get('resonant_solution')}\n"
            f"Their exact language: {complaint_intel.get('their_language')}\n"
            "=== END COMPLAINT INTELLIGENCE ==="
        )

    return "\n".join(parts)


# ── History ────────────────────────────────────────────────────────────────────

def _get_recent_history(agent_name: str, n: int = 5) -> str:
    """Return last n history entries as a readable string."""
    path = AGENTS_DIR / agent_name / "history.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    e = json.loads(line)
                    ts    = e.get("ts", "")[:16].replace("T", " ")
                    action = e.get("action", "")
                    # Pick the most informative field
                    detail = (
                        e.get("opportunity") or e.get("skill_name") or
                        e.get("top_pick") or e.get("verdict") or
                        e.get("product") or ""
                    )
                    entries.append(f"  {ts} {action}" + (f": {detail}" if detail else ""))
                    if len(entries) >= n:
                        break
                except Exception:
                    pass
        if not entries:
            return "No history yet."
        return "\n".join(reversed(entries))
    except Exception:
        return "No history yet."


def _log_history(agent_name: str, entry: dict):
    """Append a significant action to memory/agents/{name}/history.jsonl."""
    path = AGENTS_DIR / agent_name / "history.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry["ts"] = datetime.now().isoformat()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # history is non-critical — never break agent on failure


# ── Skills awareness ──────────────────────────────────────────────────────────

def _check_learned_skills(task_keywords: list) -> list:
    """
    Find .py skill files in skills/learned/ whose names match any task keyword.
    Returns list of matching stem names (excludes broken skills).
    """
    learned = ROOT / "skills" / "learned"
    if not learned.exists():
        return []
    # Load registry to filter out broken skills
    registry_path = ROOT / "memory" / "skill_registry.json"
    broken = set()
    try:
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
        broken = {s["name"] for s in reg.get("skills", []) if s.get("broken")}
    except Exception:
        pass
    results = []
    for skill_file in learned.glob("*.py"):   # was *.md — skills are .py files
        name = skill_file.stem.replace("_", " ").lower()
        if skill_file.stem in broken:
            continue
        if any(kw.lower() in name for kw in task_keywords):
            results.append(skill_file.stem)
    return results


def execute_learned_skill(skill_name: str, context: dict = None) -> str:
    """
    Import and run a learned skill by name.
    Tries entry points in priority order: run → execute → analyze → main → generate.
    Returns skill output as string, or an error message — never raises.
    """
    import importlib.util
    import sys as _sys

    learned = ROOT / "skills" / "learned"
    skill_path = learned / f"{skill_name}.py"
    if not skill_path.exists():
        return f"Skill {skill_name} not found"

    try:
        spec   = importlib.util.spec_from_file_location(skill_name, skill_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for fn_name in ["run", "execute", "analyze", "main", "generate"]:
            if hasattr(module, fn_name):
                fn = getattr(module, fn_name)
                try:
                    result = fn(context) if context else fn()
                except TypeError:
                    result = fn()
                _update_skill_usage(skill_name)
                return str(result)[:500]

        return f"Skill {skill_name} has no known entry point (run/execute/analyze/main/generate)"

    except Exception as e:
        return f"Skill {skill_name} failed: {str(e)[:120]}"


def _update_skill_usage(skill_name: str):
    """Increment use_count and set last_used in skill_registry.json."""
    registry_path = ROOT / "memory" / "skill_registry.json"
    if not registry_path.exists():
        return
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for skill in registry.get("skills", []):
            if skill["name"] == skill_name:
                skill["use_count"] = skill.get("use_count", 0) + 1
                skill["last_used"] = datetime.now().isoformat()
                break
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    except Exception:
        pass  # registry update is non-critical
