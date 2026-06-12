"""
TAD — User Research Skill
Adapted from cookiy-ai/user-research-skill (MIT) for TAD's Decision and
Marketing agents. Reimplements the useful concepts locally on Claude Haiku
— no Cookiy platform API (paid service, no key) required.

Extracted components:
1. Synthetic user feedback (from cookiy-study-synthetic-user.md concept):
   generate AI personas matching a target profile and collect their
   reaction to an opportunity → demand signal for the Decision Agent
   before it scores, and objection list for the Marketing Agent's pitches.
2. Participant targeting logic (from qualitative-research-planner.md):
   behavior-first screening questions (2-4 max, screen-out first,
   no yes/no) → lead qualification criteria for the Marketing Agent.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_providers import claude_json  # noqa: E402

MEMORY   = ROOT / "memory"
LOG_PATH = MEMORY / "user_research_log.jsonl"


def _log(msg: str):
    LOG_PATH.parent.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(), "msg": msg}) + "\n")
    try:
        print(f"[RESEARCH] {msg}")
    except UnicodeEncodeError:
        print(f"[RESEARCH] {msg}".encode("ascii", "replace").decode())


def synthetic_feedback(opportunity: dict, persona_count: int = 3) -> dict:
    """
    TAD use case: before the Decision Agent scores an opportunity, get
    synthetic feedback from AI personas matching the target customer.
    Adds a demand-validation signal beyond the Market Agent's evidence,
    and gives the Marketing Agent a ready-made objection list.

    Returns: {"personas": [...], "avg_willingness_to_pay": 1-10,
              "top_objections": [...], "would_buy_count": int, "summary": str}
    """
    system = (
        "You are a user research moderator running synthetic-user interviews. "
        "You simulate realistic, skeptical target customers — not cheerleaders. "
        "Specific incidents and real-world objections beat generic praise."
    )
    user = f"""OPPORTUNITY:
{json.dumps(opportunity, indent=2)}

Simulate {persona_count} distinct synthetic users from this opportunity's
target market reacting to the proposed solution. Each persona must have a
realistic job, context, and at least one genuine objection.

Return JSON:
{{
  "personas": [
    {{
      "name": "first name + role, e.g. 'Dana, HVAC dispatch manager'",
      "context": "1 sentence on their situation and current workaround",
      "reaction": "2 sentences, honest first reaction",
      "willingness_to_pay": 1-10,
      "would_buy": true/false,
      "objection": "their strongest objection"
    }}
  ],
  "summary": "2 sentences: overall demand signal and the dominant objection"
}}"""

    _log(f"Synthetic feedback: {persona_count} personas for "
         f"'{opportunity.get('name', '?')}'")
    raw = claude_json(system, user, max_tokens=1500)
    try:
        data = json.loads(raw)
    except Exception as e:
        _log(f"Synthetic feedback parse error: {e}")
        return {"personas": [], "error": str(e), "raw": raw[:300]}

    personas = data.get("personas", [])
    wtps     = [p.get("willingness_to_pay", 0) for p in personas]
    result = {
        "personas":               personas,
        "avg_willingness_to_pay": round(sum(wtps) / len(wtps), 1) if wtps else 0,
        "would_buy_count":        sum(1 for p in personas if p.get("would_buy")),
        "top_objections":         [p.get("objection") for p in personas if p.get("objection")],
        "summary":                data.get("summary", ""),
        "generated_at":           datetime.now().isoformat(),
    }
    _log(f"Feedback: avg WTP {result['avg_willingness_to_pay']}/10, "
         f"{result['would_buy_count']}/{len(personas)} would buy")
    return result


def build_screening_criteria(target_profile: str) -> dict:
    """
    TAD use case: turn a fuzzy target-customer description into lead
    qualification criteria for the Marketing Agent — who to contact and
    2-4 behavior-first screening questions to qualify them.

    Follows the planner's targeting rules: behaviors over demographics,
    screen-out questions first, no yes/no questions, max 4 questions.
    """
    system = (
        "You are a research recruitment specialist. You target participants "
        "by BEHAVIOR and domain knowledge, never demographic checkboxes. "
        "Screening rules: 2-4 questions max, disqualifying questions first, "
        "never yes/no (use specific options/quantities/timeframes instead)."
    )
    user = f"""TARGET PROFILE (may be vague):
{target_profile}

Return JSON:
{{
  "ideal_lead": "1 sentence behavioral definition (what they DO, not who they are)",
  "where_to_find": ["2-3 specific channels/communities where these people are"],
  "screening_questions": [
    {{
      "question": "the question text with specific answer options",
      "qualifies_if": "which answers qualify the lead",
      "purpose": "screen-out or articulacy"
    }}
  ],
  "criteria_too_narrow": true/false,
  "narrowness_note": "if true, 1 sentence on how to relax the criteria"
}}"""

    _log(f"Building screening criteria for: {target_profile[:80]}")
    raw = claude_json(system, user, max_tokens=1000)
    try:
        data = json.loads(raw)
    except Exception as e:
        _log(f"Screening criteria parse error: {e}")
        return {"error": str(e), "raw": raw[:300]}

    # Enforce the planner's hard cap of 4 questions
    qs = data.get("screening_questions", [])
    if len(qs) > 4:
        data["screening_questions"] = qs[:4]
    data["generated_at"] = datetime.now().isoformat()
    return data


if __name__ == "__main__":
    print("TAD User Research — self test")
    opp = {
        "name": "AI invoice-chaser for trade contractors",
        "problem": ("Small contractors lose hours chasing unpaid invoices; "
                    "no AI tool targets this niche."),
        "price_point": "$49/mo",
    }
    fb = synthetic_feedback(opp, persona_count=2)
    print(json.dumps(fb, indent=2)[:1500])
    crit = build_screening_criteria(
        "small trade contractors who struggle with late-paying clients"
    )
    print(json.dumps(crit, indent=2)[:1200])
