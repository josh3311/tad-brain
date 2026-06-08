"""
TAD — Invoice Sender v1.0
Phase 5 — Auto-invoicing after delivery

Triggered by Finance Agent after a deal closes.
Generates a professional invoice and sends it immediately.
Tracks payment status and follows up automatically.
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
    with open(MEMORY / "invoice_sender_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Invoice] {msg}")


# ── Invoice generator ─────────────────────────────────────────────────────────

def generate_invoice_text(client_name: str, client_email: str,
                           product_name: str, amount: float,
                           invoice_number: str) -> dict:
    """Generate professional invoice text."""
    due_date = (datetime.now() + timedelta(days=7)).strftime("%B %d, %Y")
    today    = datetime.now().strftime("%B %d, %Y")

    prompt = f"""Generate a professional invoice email for:

CLIENT: {client_name}
EMAIL: {client_email}
PRODUCT: {product_name}
AMOUNT: ${amount:.2f}
INVOICE #: {invoice_number}
DATE: {today}
DUE: {due_date} (Net 7)
FROM: TAD AI Solutions

Include:
- Professional invoice header
- Line item for the product
- Total amount due
- Payment instructions (bank transfer or e-transfer)
- Thank you note
- Contact for questions

Return ONLY JSON:
{{
  "subject": "Invoice #{invoice_number} — {product_name}",
  "body": "full invoice email body",
  "amount": {amount},
  "due_date": "{due_date}"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=600,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        result = json.loads(clean)
        result["invoice_number"] = invoice_number
        return result
    except Exception as e:
        _log(f"Invoice generation error: {e}")
        return {
            "subject":        f"Invoice #{invoice_number} — {product_name}",
            "body":           f"Hi {client_name},\n\nPlease find your invoice below.\n\nInvoice #: {invoice_number}\nProduct: {product_name}\nAmount Due: ${amount:.2f}\nDue Date: {due_date}\n\nThank you for your business.\n\nTAD AI Solutions",
            "amount":         amount,
            "due_date":       due_date,
            "invoice_number": invoice_number,
        }


# ── Follow-up checker ─────────────────────────────────────────────────────────

def check_unpaid_invoices() -> list:
    """Find invoices that need follow-up."""
    invoice_log = MEMORY / "invoice_log.json"
    if not invoice_log.exists():
        return []

    try:
        data     = json.loads(invoice_log.read_text(encoding="utf-8"))
        invoices = data.get("invoices", [])
        unpaid   = []
        now      = datetime.now()

        for inv in invoices:
            if inv.get("status") == "sent":
                sent_at = datetime.fromisoformat(inv.get("created_at", now.isoformat()))
                days_out = (now - sent_at).days
                if days_out >= 7:
                    inv["days_overdue"] = days_out - 7
                    unpaid.append(inv)

        return unpaid
    except Exception as e:
        _log(f"Check unpaid error: {e}")
        return []


def send_follow_up(invoice: dict) -> bool:
    """Send a payment follow-up for an overdue invoice."""
    days_overdue = invoice.get("days_overdue", 0)
    client_email = invoice.get("client_email", "")
    if not client_email:
        return False

    subject = f"Payment Reminder — Invoice #{invoice.get('invoice_number', '')}"
    if days_overdue <= 7:
        tone = "gentle"
        body = f"Hi,\n\nJust a friendly reminder that invoice #{invoice.get('invoice_number')} for ${invoice.get('amount', 0):.2f} was due {days_overdue} days ago.\n\nPlease let us know if you have any questions.\n\nTAD AI Solutions"
    else:
        tone = "firm"
        body = f"Hi,\n\nThis is a follow-up regarding invoice #{invoice.get('invoice_number')} for ${invoice.get('amount', 0):.2f}, which is now {days_overdue} days overdue.\n\nPlease arrange payment at your earliest convenience.\n\nTAD AI Solutions"

    _log(f"Sending {tone} follow-up for invoice #{invoice.get('invoice_number')} ({days_overdue} days overdue)")

    # Use delivery module to send
    try:
        from tad_delivery import send_email
        return send_email(client_email, subject, body)
    except Exception as e:
        _log(f"Follow-up send error: {e}")
        return False


# ── Main invoice sender ───────────────────────────────────────────────────────

def send_invoice(client_name: str, client_email: str,
                 product_name: str, amount: float) -> dict:
    """
    Generate and send invoice immediately after delivery.
    Returns invoice dict.
    """
    invoice_number = f"TAD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    _log(f"Sending invoice {invoice_number} to {client_name} — ${amount:.2f}")

    # Generate invoice
    invoice_content = generate_invoice_text(
        client_name, client_email,
        product_name, amount, invoice_number
    )

    # Send email
    sent = False
    try:
        from tad_delivery import send_email
        sent = send_email(
            to_email=client_email,
            subject=invoice_content.get("subject", f"Invoice #{invoice_number}"),
            body=invoice_content.get("body", ""),
        )
    except Exception as e:
        _log(f"Invoice send error: {e}")

    # Save to invoice log
    invoice = {
        "invoice_number": invoice_number,
        "client_name":    client_name,
        "client_email":   client_email,
        "product":        product_name,
        "amount":         amount,
        "due_date":       invoice_content.get("due_date", ""),
        "status":         "sent" if sent else "pending",
        "created_at":     datetime.now().isoformat(),
        "email_sent":     sent,
    }

    invoice_log = MEMORY / "invoice_log.json"
    data        = {"invoices": []}
    if invoice_log.exists():
        try:
            data = json.loads(invoice_log.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["invoices"].append(invoice)
    invoice_log.write_text(json.dumps(data, indent=2), encoding="utf-8")

    _log(f"Invoice {invoice_number}: {'sent' if sent else 'saved to pending'}")
    return invoice


def run_follow_ups() -> int:
    """Check and send follow-ups for all overdue invoices. Returns count sent."""
    unpaid = check_unpaid_invoices()
    if not unpaid:
        _log("No overdue invoices — all good")
        return 0

    _log(f"Found {len(unpaid)} overdue invoices")
    sent = 0
    for inv in unpaid:
        if send_follow_up(inv):
            sent += 1
    return sent


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Invoice Sender — Test Mode")
    print("=" * 40)

    name    = input("Client name: ").strip() or "Test Client"
    email   = input("Client email: ").strip() or "test@example.com"
    product = input("Product name: ").strip() or "AI Receptionist"
    amount  = float(input("Amount ($): ").strip() or "297")

    print(f"\nSending invoice to {name} ({email}) for ${amount:.2f}...")
    invoice = send_invoice(name, email, product, amount)

    print(f"\nInvoice #: {invoice['invoice_number']}")
    print(f"Status:    {invoice['status']}")
    print(f"Due:       {invoice['due_date']}")

    print("\nChecking for overdue invoices...")
    count = run_follow_ups()
    print(f"Follow-ups sent: {count}")
