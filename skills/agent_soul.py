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


def _get_agent_context(agent_name: str) -> str:
    """
    Build a concise identity context string for prepending to Claude system prompts.
    Returns empty string if identity not found — agent works exactly as before.
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
    Find skill files in skills/learned/ whose names match any task keyword.
    Returns list of matching stem names.
    """
    learned = ROOT / "skills" / "learned"
    if not learned.exists():
        return []
    results = []
    for skill_file in learned.glob("*.md"):
        name = skill_file.stem.replace("_", " ").lower()
        if any(kw.lower() in name for kw in task_keywords):
            results.append(skill_file.stem)
    return results
