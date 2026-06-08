"""
TAD AI — CEO Agent Script
Chief Executive Officer — Master Decision Maker
Version: 1.0
"""

import json
import os
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT         = Path(__file__).parent.parent
MEMORY       = ROOT / "memory"
SKILL_PATH   = Path(__file__).parent / "ceo_agent.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


# ── Load skill prompt ─────────────────────────────────────────────────────────

def _load_skill() -> str:
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return ""


# ── Memory helpers ────────────────────────────────────────────────────────────

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
    path = MEMORY / filename
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _log(msg: str):
    log_path = MEMORY / "ceo_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[CEO] {msg}")


# ── Core decision engine ──────────────────────────────────────────────────────

def make_decision(report: dict, report_type: str) -> dict:
    """
    Main entry point. Takes any agent report and makes a decision.
    Returns: { decision, action, assigned_to, reasoning, escalate_to_joshua }
    """
    skill = _load_skill()
    monkey = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:2000] \
             if (ROOT / "THE_MONKEY.md").exists() else ""

    prompt = f"""INCOMING REPORT TYPE: {report_type}

REPORT DATA:
{json.dumps(report, indent=2)}

COMPANY MISSION (THE_MONKEY.md):
{monkey}

Based on this report, make your decision.
Return ONLY a JSON object with these exact keys:
{{
  "decision": "GO or KILL or ESCALATE or ASSIGN",
  "action": "exactly what happens next",
  "assigned_to": "which agent gets the next task",
  "reasoning": "2-3 sentences max explaining why",
  "escalate_to_joshua": true or false,
  "escalation_reason": "only if escalate_to_joshua is true"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or "{}"
        import re
        clean = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(clean)

        # Log the decision
        _log(f"Decision: {result.get('decision')} → {result.get('assigned_to')} | {result.get('reasoning')}")

        # Save to decisions log
        decisions = _read("decisions.json")
        if "history" not in decisions:
            decisions["history"] = []
        decisions["history"].append({
            "ts":          datetime.now().isoformat(),
            "report_type": report_type,
            "decision":    result.get("decision"),
            "assigned_to": result.get("assigned_to"),
            "reasoning":   result.get("reasoning"),
        })
        _write("decisions.json", decisions)

        return result

    except Exception as e:
        _log(f"Decision error: {e}")
        return {
            "decision":            "ERROR",
            "action":              "retry",
            "assigned_to":         "ops_agent",
            "reasoning":           f"CEO Agent encountered an error: {e}",
            "escalate_to_joshua":  False,
        }


# ── Daily briefing summary ────────────────────────────────────────────────────

def generate_daily_summary() -> str:
    """Generate CEO's daily summary for morning briefing."""
    skill    = _load_skill()
    finance  = _read("finance.json")
    leads    = _read("leads.json")
    builds   = _read("build_log.json")
    opps     = _read("opportunity_log.json")

    prompt = f"""Generate a CEO daily summary for Joshua.

CURRENT DATA:
- Finance: {json.dumps(finance)[:500]}
- Leads: {json.dumps(leads)[:500]}
- Recent builds: {json.dumps(builds)[:500]}
- Opportunities: {json.dumps(opps)[:500]}

Write a direct, honest 5-sentence summary covering:
1. What TAD accomplished yesterday
2. Current revenue status
3. Top opportunity in the pipeline
4. What TAD is doing today
5. One thing Joshua should know or decide

Speak like a smart business partner, not a corporate report."""

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
        return resp.choices[0].message.content or "No summary available."
    except Exception as e:
        return f"CEO summary error: {e}"


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — CEO Agent Test")
    print("=" * 40)

    # Test with a sample market report
    test_report = {
        "opportunity": "AI Receptionist for HVAC companies",
        "score":       32,
        "demand":      9,
        "competition": 8,
        "buildability": 8,
        "revenue_speed": 7,
        "summary": "HVAC companies miss 40% of calls during peak season. No AI solution exists targeting this niche specifically."
    }

    print("Testing decision with sample opportunity report...")
    result = make_decision(test_report, "opportunity_score")
    print(json.dumps(result, indent=2))

    print("\nTesting daily summary...")
    summary = generate_daily_summary()
    print(summary)