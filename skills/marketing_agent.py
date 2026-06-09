"""
TAD AI — Marketing Agent Script
Chief Revenue Officer — Lead Finder and Deal Closer
Version: 1.0
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
import anthropic
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
SKILL_PATH = Path(__file__).parent / "marketing_agent.md"

# Kimi for code generation
kimi = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
KIMI_MODEL = "kimi-k2.6"

# Claude for reasoning and JSON
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL  = "claude-haiku-4-5-20251001"


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
    log_path = MEMORY / "marketing_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[CRO] {msg}")


def _get_killed_leads() -> list:
    killed = _read("killed_leads.json")
    return [l.get("contact", "") for l in killed.get("leads", [])]


# ── Lead generation ───────────────────────────────────────────────────────────

def find_leads(product: dict, count: int = 10) -> list:
    """
    Find people already experiencing the problem this product solves.
    Returns list of qualified leads.
    """
    skill        = _load_skill()
    killed_leads = _get_killed_leads()

    prompt = f"""PRODUCT BUILT:
{json.dumps(product, indent=2)}

Find {count} highly qualified leads — real people or businesses
who are CURRENTLY experiencing the exact problem this product solves.

For each lead provide:
- name: business or person name
- type: type of business
- contact: email or LinkedIn URL if findable
- problem_evidence: specific quote or post where they described the problem
- source: where you found them (Reddit, LinkedIn, Twitter, Google)
- urgency: how urgently do they need this (1-10)
- fit_score: how well does this product solve their problem (1-10)

EXCLUDED LEADS (never include these):
{json.dumps(killed_leads[:20])}

Return ONLY a JSON array of {count} leads.
Only include leads with fit_score >= 7.
Real leads only — no made up contacts."""

    try:
        resp = claude.messages.create(model=MODEL, max_tokens=2000, system=skill, messages=[{"role": "user", "content": prompt}])
        raw   = msg.content[0].text or "[]"
        clean = re.sub(r"```json|```", "", raw).strip()
        leads = json.loads(clean)

        # Add metadata to each lead
        for lead in leads:
            lead["id"]            = f"lead_{datetime.now().strftime('%Y%m%d%H%M%S')}_{leads.index(lead)}"
            lead["status"]        = "new"
            lead["product"]       = product.get("name", "")
            lead["found_date"]    = datetime.now().isoformat()
            lead["follow_up_count"] = 0
            lead["messages"]      = []

        _log(f"Found {len(leads)} qualified leads for {product.get('name')}")
        return leads

    except Exception as e:
        _log(f"Lead generation error: {e}")
        return []


# ── Outreach message generation ───────────────────────────────────────────────

def craft_message(lead: dict, product: dict, follow_up_number: int = 0) -> str:
    """
    Generate a personalized outreach message for a specific lead.
    follow_up_number: 0 = first message, 1 = first follow up, 2 = second follow up
    """
    skill = _load_skill()

    message_type = {
        0: "first outreach message",
        1: "first follow up (3 days after no response)",
        2: "second follow up (7 days after no response)",
        3: "final follow up (14 days — last attempt)",
    }.get(follow_up_number, "follow up message")

    prompt = f"""LEAD:
{json.dumps(lead, indent=2)}

PRODUCT:
{json.dumps(product, indent=2)}

Write a {message_type} for this lead.

RULES:
- Reference something SPECIFIC about their situation
- Under 5 sentences for first message
- Lead with their problem, not your product
- End with one clear call to action
- Sound like a human, not a bot
- Never use corporate language

Use this formula:
"I noticed [specific thing about them].
Most [their business type] struggle with [exact problem].
We built something that [specific result in their terms].
Would a quick call this week make sense?"

Return ONLY the message text. No subject line. No explanation."""

    try:
        resp = claude.messages.create(model=MODEL, max_tokens=200, system=skill, messages=[{"role": "user", "content": prompt}])
        return msg.content[0].text.strip() or ""
    except Exception as e:
        _log(f"Message craft error: {e}")
        return ""


# ── Lead management ───────────────────────────────────────────────────────────

def save_leads(leads: list):
    """Save leads to memory/leads.json."""
    leads_data = _read("leads.json")
    if "leads" not in leads_data:
        leads_data["leads"] = []
    leads_data["leads"].extend(leads)
    _write("leads.json", leads_data)
    _log(f"Saved {len(leads)} leads to memory/leads.json")


def log_outreach(lead_id: str, message: str, channel: str):
    """Log every outreach message sent."""
    outreach = _read("outreach_log.json")
    if "messages" not in outreach:
        outreach["messages"] = []
    outreach["messages"].append({
        "lead_id":   lead_id,
        "message":   message,
        "channel":   channel,
        "sent_at":   datetime.now().isoformat(),
        "status":    "sent",
    })
    _write("outreach_log.json", outreach)


def mark_closed(lead: dict, deal_value: float):
    """Mark a lead as closed and report to Finance Agent."""
    # Update lead status
    leads_data = _read("leads.json")
    for l in leads_data.get("leads", []):
        if l.get("id") == lead.get("id"):
            l["status"]      = "closed"
            l["closed_date"] = datetime.now().isoformat()
            l["deal_value"]  = deal_value
    _write("leads.json", leads_data)

    # Save to closed deals
    closed = _read("closed_deals.json")
    if "deals" not in closed:
        closed["deals"] = []
    deal = {
        "lead":        lead,
        "value":       deal_value,
        "closed_date": datetime.now().isoformat(),
        "product":     lead.get("product", ""),
    }
    closed["deals"].append(deal)
    _write("closed_deals.json", closed)

    _log(f"DEAL CLOSED: {lead.get('name')} — ${deal_value}")
    return deal


def mark_cold(lead: dict):
    """Mark a lead as cold after 3 failed follow ups."""
    killed = _read("killed_leads.json")
    if "leads" not in killed:
        killed["leads"] = []
    killed["leads"].append({
        "contact":   lead.get("contact", ""),
        "name":      lead.get("name", ""),
        "killed_at": datetime.now().isoformat(),
        "reason":    "no_response_after_3_followups",
    })
    _write("killed_leads.json", killed)
    _log(f"Lead marked cold: {lead.get('name')}")


# ── Pipeline summary ──────────────────────────────────────────────────────────

def get_pipeline_summary() -> dict:
    """Weekly pipeline summary for CEO Agent."""
    leads_data = _read("leads.json")
    closed     = _read("closed_deals.json")
    leads      = leads_data.get("leads", [])

    new_leads      = [l for l in leads if l.get("status") == "new"]
    contacted      = [l for l in leads if l.get("status") == "contacted"]
    in_convo       = [l for l in leads if l.get("status") == "in_conversation"]
    closed_deals   = closed.get("deals", [])
    total_revenue  = sum(d.get("value", 0) for d in closed_deals)

    return {
        "summary_date":   datetime.now().isoformat(),
        "new_leads":      len(new_leads),
        "contacted":      len(contacted),
        "in_conversation": len(in_convo),
        "closed_deals":   len(closed_deals),
        "total_revenue":  total_revenue,
        "pipeline_value": len(in_convo) * 500,  # estimated average deal
        "top_lead":       in_convo[0] if in_convo else None,
    }


# ── Full outreach cycle ───────────────────────────────────────────────────────

def run_outreach_cycle(product: dict) -> dict:
    """
    Full outreach cycle for a completed product.
    Find leads → craft messages → log everything → return summary.
    """
    _log(f"=== Starting outreach cycle for: {product.get('name')} ===")

    leads = find_leads(product, count=10)
    if not leads:
        _log("No qualified leads found")
        return {"status": "no_leads", "product": product.get("name")}

    save_leads(leads)

    messages_crafted = []
    for lead in leads:
        message = craft_message(lead, product, follow_up_number=0)
        if message:
            log_outreach(lead["id"], message, "email")
            messages_crafted.append({
                "lead":    lead.get("name"),
                "message": message,
            })

    _log(f"Outreach cycle complete: {len(leads)} leads, {len(messages_crafted)} messages crafted")

    return {
        "status":           "complete",
        "product":          product.get("name"),
        "leads_found":      len(leads),
        "messages_crafted": len(messages_crafted),
        "leads":            leads,
        "messages":         messages_crafted,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Marketing Agent Test")
    print("=" * 40)

    test_product = {
        "name":     "HVAC Call Screener",
        "problem":  "HVAC companies miss 40% of calls during peak season",
        "solution": "AI receptionist that screens, logs and responds to missed calls 24/7",
        "price":    "$297/month",
    }

    print("Running outreach cycle...")
    result = run_outreach_cycle(test_product)
    print(f"\nLeads found: {result.get('leads_found')}")
    print(f"Messages crafted: {result.get('messages_crafted')}")

    if result.get("messages"):
        print(f"\nSample message for first lead:")
        print(result["messages"][0].get("message"))

    print("\nPipeline summary:")
    print(json.dumps(get_pipeline_summary(), indent=2))