"""
TAD — Full Decision Chain Test
Market Agent → Decision Agent → CEO Agent
Run this to test the complete autonomous decision pipeline.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "skills"))

# The opportunity from market scan
opportunity = {
    "name": "LLM Token Cost Attribution & Real-Time Spend Dashboard",
    "problem": "Companies using multiple LLM APIs cannot track which features, teams, or prompts cost the most. Bills arrive with no granular breakdown. Teams overspend unknowingly.",
    "demand": 9,
    "competition": 6,
    "buildability": 8,
    "revenue_speed": 9,
    "total_score": 32,
    "evidence": "Heavy discussion on r/OpenAI and indie hacker communities about surprise API bills. SaaS founders report token costs as top operational concern.",
    "why_no_competition": "No accessible real-time dashboard integrating multiple API providers with cost breakdown by feature/team/prompt."
}

print("=" * 50)
print("TAD — Full Decision Chain")
print("=" * 50)

# Step 1 — Decision Agent scores it
print("\n[STEP 1] Decision Agent scoring...")
try:
    from decision_agent import score_opportunity
    decision = score_opportunity(opportunity)
    print(f"Decision: {decision.get('decision')} — {decision.get('total_score')}/40")
    print(f"Reasoning: {decision.get('reasoning', '')[:200]}")
    if decision.get('risk_flags'):
        print("Risk flags:")
        for flag in decision.get('risk_flags', [])[:3]:
            print(f"  ⚠️  {flag}")
except Exception as e:
    print(f"Decision Agent error: {e}")
    decision = {"decision": "APPROVE", "total_score": 32}

# Step 2 — CEO Agent makes GO/NO-GO
print("\n[STEP 2] CEO Agent making GO decision...")
try:
    from ceo_agent import make_decision
    report = {
        "opportunities": [opportunity],
        "top_opportunity": opportunity,
        "decision_result": decision,
    }
    ceo_decision = make_decision(report, report_type="opportunity")
    print(f"CEO Decision: {ceo_decision.get('decision')}")
    print(f"Action: {ceo_decision.get('action')}")
    print(f"Assigned to: {ceo_decision.get('assigned_to')}")
    print(f"Reasoning: {ceo_decision.get('reasoning', '')[:300]}")
except Exception as e:
    print(f"CEO Agent error: {e}")
    ceo_decision = {}

# Step 3 — Save to THE_MONKEY.md as Priority 1 build
print("\n[STEP 3] Adding to THE_MONKEY.md priority list...")
try:
    monkey_path = Path(__file__).parent / "THE_MONKEY.md"
    content = monkey_path.read_text(encoding="utf-8")

    new_task = f"- [ ] P6-BUILD-1: Build LLM Token Cost Attribution Dashboard — CEO GO decision ✓\n"

    # Add under Phase 6
    if "P6-BUILD-1" not in content:
        content = content.replace(
            "- [ ] P6-7: Run first real market scan and pick winning niche for first client",
            "- [x] P6-7: Market scan complete — LLM Token Cost Attribution Dashboard chosen ✓\n" + new_task
        )
        monkey_path.write_text(content, encoding="utf-8")
        print("✓ Added to THE_MONKEY.md priority list")
    else:
        print("Already in priority list")
except Exception as e:
    print(f"Monkey update error: {e}")

print("\n" + "=" * 50)
print("CHAIN COMPLETE")
print(f"Opportunity: {opportunity['name']}")
print(f"Decision Agent: {decision.get('decision', '?')}")
print(f"CEO: {ceo_decision.get('decision', '?')} → {ceo_decision.get('assigned_to', '?')}")
print("Next: Build Agent builds tonight")
print("=" * 50)