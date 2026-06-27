"""
TAD AI — Decision Agent Script
Chief Decision Officer — Ruthless Opportunity Filter
Version: 1.0
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
import anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
SKILL_PATH = Path(__file__).parent / "decision_agent.md"

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL  = "claude-haiku-4-5-20251001"

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
try:
    from skills.agent_soul import _get_agent_context, _log_history, _check_learned_skills
except ImportError:
    def _get_agent_context(n): return ""
    def _log_history(n, e): pass
    def _check_learned_skills(kws): return []


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
    log_path = MEMORY / "decision_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    try:
        print(f"[DECISION] {msg}")
    except UnicodeEncodeError:
        print(f"[DECISION] {msg}".encode("ascii", "replace").decode())


# Startup heartbeat — ops health check reads decision_log.jsonl; the agent
# only logs when scoring runs, but scoring only happens when the market scan
# finds opportunities. Without this ping, ops flags the agent as silent even
# though it's loaded and ready.
_log("Decision Agent loaded — ready to score")


# ── Core scoring engine ───────────────────────────────────────────────────────

def score_opportunity(opportunity: dict) -> dict:
    """
    Score an opportunity on 4 criteria.
    Returns full score card with decision.
    """
    skill = _load_skill()

    prompt = f"""OPPORTUNITY TO SCORE:
{json.dumps(opportunity, indent=2)}

Score this opportunity on all 4 criteria.
Be ruthless. Use evidence from the opportunity data provided.

Return ONLY a JSON object:
{{
  "opportunity_name": "name of the opportunity",
  "scores": {{
    "demand": 0,
    "competition": 0,
    "buildability": 0,
    "revenue_speed": 0
  }},
  "total_score": 0,
  "decision": "STRONGLY APPROVE or APPROVE or CONDITIONAL or KILL",
  "reasoning": "2-3 sentences explaining the decision",
  "risk_flags": ["any hidden risks to watch"],
  "market_size": "estimated total addressable market",
  "kill_reason": "only if decision is KILL — specific reason"
}}

Remember:
- 35-40 → STRONGLY APPROVE
- 28-34 → APPROVE  
- 20-27 → CONDITIONAL
- below 20 → KILL

Return JSON only."""

    try:
        _ctx = _get_agent_context("decision")
        _sys_prompt = ((_ctx + "\n\n") if _ctx else "") + skill + "\n\nAlways respond with valid JSON only."
        # Run competitive/analysis learned skills before scoring
        try:
            from skills.agent_soul import execute_learned_skill
            relevant = _check_learned_skills([
                "competitive", "analysis", "win", "loss", "scoring", "intelligence",
            ])
            competitive_insight = ""
            if relevant:
                _log(f"Running learned skill: {relevant[0]}")
                result = execute_learned_skill(
                    relevant[0],
                    {"opportunity": opportunity.get("name", "unknown"), "task": "competitive_analysis"},
                )
                if result and result.strip() not in ("None", "") \
                        and "failed" not in result.lower() and "not found" not in result.lower() \
                        and "no known entry" not in result.lower():
                    competitive_insight = f"\n\nCompetitive analysis from learned skill:\n{result[:300]}"
                    _log(f"Competitive insight added from {relevant[0]}")
            if competitive_insight:
                prompt += competitive_insight
        except Exception as _e:
            _log(f"Competitive skill skipped: {_e}")

        msg = claude.messages.create(
            model=MODEL,
            max_tokens=600,
            system=_sys_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        raw   = msg.content[0].text or "{}"
        clean = re.sub(r"```(?:json)?\n?", "", raw).strip().lstrip("`").strip()
        result, _ = json.JSONDecoder().raw_decode(clean)

        # Add timestamp
        result["scored_at"] = datetime.now().isoformat()

        # Save to decisions log
        decisions = _read("decisions.json")
        if "history" not in decisions:
            decisions["history"] = []
        decisions["history"].append(result)
        _write("decisions.json", decisions)

        # If killed — save to graveyard
        if result.get("decision") == "KILL":
            killed = _read("killed_opportunities.json")
            if "opportunities" not in killed:
                killed["opportunities"] = []
            killed["opportunities"].append({
                "name":        result.get("opportunity_name"),
                "kill_reason": result.get("kill_reason"),
                "score":       result.get("total_score"),
                "killed_at":   datetime.now().isoformat(),
            })
            _write("killed_opportunities.json", killed)
            _log(f"KILLED: {result.get('opportunity_name')} — Score: {result.get('total_score')}/40")
        else:
            _log(f"{result.get('decision')}: {result.get('opportunity_name')} — Score: {result.get('total_score')}/40")

        _log_history("decision", {
            "action":      "score",
            "opportunity": result.get("opportunity_name"),
            "decision":    result.get("decision"),
            "score":       result.get("total_score"),
        })
        return result

    except Exception as e:
        _log(f"Scoring error: {e}")
        return {
            "decision":    "ERROR",
            "total_score": 0,
            "reasoning":   f"Decision Agent error: {e}",
        }


def score_multiple(opportunities: list) -> list:
    """
    Score a list of opportunities.
    Returns only approved ones sorted by score descending.
    """
    _log(f"Scoring {len(opportunities)} opportunities...")
    results = []

    for opp in opportunities:
        result = score_opportunity(opp)
        results.append(result)

    # Return only approved, sorted by score
    approved = [
        r for r in results
        if r.get("decision") in ["STRONGLY APPROVE", "APPROVE"]
    ]
    approved.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    _log(f"Approved: {len(approved)} / {len(opportunities)}")
    return approved


def get_decision_stats() -> dict:
    """Return stats on all decisions made so far."""
    decisions = _read("decisions.json")
    history   = decisions.get("history", [])
    killed    = _read("killed_opportunities.json")

    approved  = [d for d in history if d.get("decision") in ["STRONGLY APPROVE", "APPROVE"]]
    killed_count = len(killed.get("opportunities", []))

    return {
        "total_scored":    len(history),
        "total_approved":  len(approved),
        "total_killed":    killed_count,
        "approval_rate":   f"{(len(approved)/len(history)*100):.1f}%" if history else "0%",
        "top_approved":    approved[0] if approved else None,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Decision Agent Test")
    print("=" * 40)

    # Test with two sample opportunities
    test_opps = [
        {
            "name": "AI Receptionist for HVAC companies",
            "problem": "HVAC companies miss 40% of calls during peak season. No proper AI solution exists.",
            "demand": 9,
            "competition": 8,
            "buildability": 8,
            "revenue_speed": 7,
            "total_score": 32,
            "evidence": "Reddit r/HVAC — dozens of posts about missed calls costing revenue",
            "why_no_competition": "Generic AI receptionists exist but none target HVAC specifically"
        },
        {
            "name": "AI that writes LinkedIn posts",
            "problem": "People want more LinkedIn engagement",
            "demand": 4,
            "competition": 2,
            "buildability": 8,
            "revenue_speed": 5,
            "total_score": 19,
            "evidence": "Vague — many tools already do this",
            "why_no_competition": "Actually very saturated"
        }
    ]

    print("Scoring opportunities...")
    results = score_multiple(test_opps)
    print(f"\nApproved opportunities: {len(results)}")
    for r in results:
        print(f"\n{r.get('opportunity_name')} — {r.get('decision')} ({r.get('total_score')}/40)")
        print(f"Reasoning: {r.get('reasoning')}")

    print("\nDecision stats:")
    print(json.dumps(get_decision_stats(), indent=2))