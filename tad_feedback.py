"""
TAD — Feedback Engine v1.0
Phase 5 — Collect client feedback and update skill files

After delivery, TAD follows up with the client to collect feedback.
Uses that feedback to improve skill files automatically via CSEO Agent.
Closes the learning loop — every client makes TAD smarter.
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent
MEMORY     = ROOT / "memory"
SKILLS_DIR = ROOT / "skills"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    with open(MEMORY / "feedback_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Feedback] {msg}")


# ── Feedback request ──────────────────────────────────────────────────────────

def generate_feedback_email(client_name: str, product_name: str) -> dict:
    """Generate a feedback request email."""
    prompt = f"""Write a friendly feedback request email.

CLIENT: {client_name}
PRODUCT: {product_name}
SENT: 3 days after delivery

Ask for:
1. Is the product working well?
2. What could be better?
3. Would they recommend us? (NPS 1-10)
4. Any features they wish it had?

Keep it under 100 words. Casual and warm.
Include a simple reply instruction: "Just reply to this email with your thoughts"

Return ONLY JSON:
{{
  "subject": "Quick question about your {product_name}",
  "body": "email body"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=300,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        _log(f"Feedback email error: {e}")
        return {
            "subject": f"Quick question about your {product_name}",
            "body":    f"Hi {client_name},\n\nHope everything is working well with your {product_name}!\n\nJust reply to this email with any feedback — what's working, what could be better, or any features you'd love to see.\n\nThanks!\nTAD AI Team",
        }


def request_feedback(client_name: str, client_email: str,
                     product_name: str, delivery_id: str = "") -> dict:
    """Send feedback request email to client."""
    _log(f"Requesting feedback from {client_name}")

    email_content = generate_feedback_email(client_name, product_name)

    sent = False
    try:
        from tad_delivery import send_email
        sent = send_email(
            to_email=client_email,
            subject=email_content.get("subject", ""),
            body=email_content.get("body", ""),
        )
    except Exception as e:
        _log(f"Feedback email send error: {e}")

    record = {
        "client_name":  client_name,
        "client_email": client_email,
        "product":      product_name,
        "delivery_id":  delivery_id,
        "requested_at": datetime.now().isoformat(),
        "email_sent":   sent,
        "status":       "requested",
        "response":     None,
    }

    _save_feedback(record)
    _log(f"Feedback request {'sent' if sent else 'queued'} for {client_name}")
    return record


# ── Feedback processing ───────────────────────────────────────────────────────

def process_feedback(client_name: str, feedback_text: str,
                     product_name: str) -> dict:
    """
    Process client feedback and extract actionable insights.
    Updates skill files via CSEO Agent.
    """
    _log(f"Processing feedback from {client_name}")

    prompt = f"""Analyze this client feedback for TAD AI's product team.

CLIENT: {client_name}
PRODUCT: {product_name}
FEEDBACK: {feedback_text}

Extract:
1. Sentiment (positive/neutral/negative)
2. NPS score if mentioned (1-10)
3. What worked well
4. What needs improvement
5. Feature requests
6. Actionable improvements for the product

Return ONLY JSON:
{{
  "sentiment": "positive/neutral/negative",
  "nps_score": null,
  "worked_well": ["item 1", "item 2"],
  "needs_improvement": ["item 1"],
  "feature_requests": ["feature 1"],
  "skill_updates": ["specific improvement to make to skill files"],
  "priority": "high/medium/low"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=400,
        )
        raw     = resp.choices[0].message.content or "{}"
        clean   = re.sub(r"```json|```", "", raw).strip()
        analysis = json.loads(clean)
        _log(f"Feedback analyzed: {analysis.get('sentiment')} — NPS: {analysis.get('nps_score')}")
        return analysis
    except Exception as e:
        _log(f"Feedback analysis error: {e}")
        return {"sentiment": "unknown", "priority": "medium"}


def apply_feedback_to_skills(analysis: dict, product_name: str):
    """
    Use CSEO Agent to update skill files based on feedback.
    This closes the learning loop.
    """
    skill_updates = analysis.get("skill_updates", [])
    if not skill_updates:
        return

    _log(f"Applying {len(skill_updates)} skill updates from feedback...")

    # Find the relevant skill file
    skill_name = re.sub(r"[^a-z0-9_]", "_", product_name.lower())
    skill_path = SKILLS_DIR / "learned" / f"{skill_name}.md"

    if not skill_path.exists():
        # Try to find closest matching skill
        learned_skills = list((SKILLS_DIR / "learned").glob("*.md")) if (SKILLS_DIR / "learned").exists() else []
        if not learned_skills:
            _log("No learned skills to update — feedback saved for CSEO")
            return
        skill_path = learned_skills[-1]

    try:
        existing = skill_path.read_text(encoding="utf-8")
        today    = datetime.now().strftime("%Y-%m-%d")

        update_section = f"\n\n## CLIENT FEEDBACK UPDATES — {today}\n"
        for update in skill_updates:
            update_section += f"- {update}\n"

        skill_path.write_text(existing + update_section, encoding="utf-8")
        _log(f"Skill file updated: {skill_path.name}")

    except Exception as e:
        _log(f"Skill update error: {e}")


def _save_feedback(record: dict):
    """Save feedback record to memory."""
    log_path = MEMORY / "feedback_log.json"
    data     = {"feedback": []}
    if log_path.exists():
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["feedback"].append(record)
    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Full feedback loop ────────────────────────────────────────────────────────

def run_feedback_loop(client_name: str, client_email: str,
                      product_name: str, feedback_text: str = None) -> dict:
    """
    Complete feedback loop:
    Request → Receive → Analyze → Update Skills → Log

    If feedback_text is provided, skips the request step.
    """
    if not feedback_text:
        # Request feedback
        return request_feedback(client_name, client_email, product_name)

    # Process received feedback
    analysis = process_feedback(client_name, feedback_text, product_name)

    # Apply to skill files
    apply_feedback_to_skills(analysis, product_name)

    # Save full record
    record = {
        "client_name":   client_name,
        "client_email":  client_email,
        "product":       product_name,
        "feedback_text": feedback_text,
        "analysis":      analysis,
        "received_at":   datetime.now().isoformat(),
        "status":        "processed",
    }
    _save_feedback(record)

    _log(f"Feedback loop complete for {client_name} — skills updated")
    return record


def get_feedback_stats() -> dict:
    """Return feedback statistics across all clients."""
    log_path = MEMORY / "feedback_log.json"
    if not log_path.exists():
        return {"total": 0, "avg_nps": 0}

    try:
        data     = json.loads(log_path.read_text(encoding="utf-8"))
        feedback = data.get("feedback", [])
        nps_scores = [
            f.get("analysis", {}).get("nps_score")
            for f in feedback
            if f.get("analysis", {}).get("nps_score")
        ]
        avg_nps = sum(nps_scores) / len(nps_scores) if nps_scores else 0

        sentiments = {}
        for f in feedback:
            s = f.get("analysis", {}).get("sentiment", "unknown")
            sentiments[s] = sentiments.get(s, 0) + 1

        return {
            "total":      len(feedback),
            "avg_nps":    round(avg_nps, 1),
            "sentiments": sentiments,
            "processed":  len([f for f in feedback if f.get("status") == "processed"]),
        }
    except Exception:
        return {"total": 0, "avg_nps": 0}


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Feedback Engine — Test Mode")
    print("=" * 40)

    name    = input("Client name: ").strip() or "Mike Johnson"
    email   = input("Client email: ").strip() or "mike@example.com"
    product = input("Product name: ").strip() or "HVAC AI Receptionist"

    print("\n1. Test feedback request (sends email)")
    print("2. Test feedback processing (analyze text)")
    choice = input("Choice (1/2): ").strip()

    if choice == "1":
        result = request_feedback(name, email, product)
        print(f"\nRequest status: {result.get('status')}")
        print(f"Email sent: {result.get('email_sent')}")

    elif choice == "2":
        feedback = input("\nEnter sample feedback text: ").strip()
        if not feedback:
            feedback = "The product works great! It answers our calls automatically. Would love a feature to send automatic follow-up texts. NPS: 9/10"

        result = run_feedback_loop(name, email, product, feedback)
        print(f"\nSentiment: {result.get('analysis', {}).get('sentiment')}")
        print(f"NPS: {result.get('analysis', {}).get('nps_score')}")
        print(f"Skill updates: {result.get('analysis', {}).get('skill_updates')}")

    print("\nFeedback stats:")
    print(json.dumps(get_feedback_stats(), indent=2))
