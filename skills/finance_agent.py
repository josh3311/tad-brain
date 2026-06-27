"""
TAD AI — Finance Agent Script
Chief Finance Officer — Money Tracker and Invoicer
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
SKILL_PATH = Path(__file__).parent / "finance_agent.md"

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
try:
    from skills.agent_soul import _get_agent_context, _log_history
except ImportError:
    def _get_agent_context(n): return ""
    def _log_history(n, e): pass

# Kimi for code generation
kimi = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
KIMI_MODEL = "kimi-k2.6"

# Claude for reasoning and JSON
claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL  = "claude-haiku-4-5-20251001"

# Revenue milestones to flag Joshua
MILESTONES = [1000, 5000, 10000, 25000, 50000, 100000]


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
    log_path = MEMORY / "finance_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[CFO] {msg}")


# ── Invoice generation ────────────────────────────────────────────────────────

def generate_invoice(deal: dict) -> dict:
    """
    Generate a professional invoice for a closed deal.
    Returns invoice dict with all details.
    """
    skill = _load_skill()
    invoice_number = f"TAD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    due_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    prompt = f"""Generate a professional invoice for this deal:
{json.dumps(deal, indent=2)}

Return ONLY a JSON object:
{{
  "invoice_number": "{invoice_number}",
  "client_name": "client name",
  "client_email": "client email if available",
  "product": "product name",
  "description": "one line description of what was delivered",
  "amount": 0.00,
  "currency": "USD",
  "issued_date": "{datetime.now().strftime('%Y-%m-%d')}",
  "due_date": "{due_date}",
  "payment_terms": "Net 7",
  "invoice_text": "full professional invoice text ready to send as email body"
}}"""

    try:
        _ctx = _get_agent_context("finance")
        _sys_prompt = ((_ctx + "\n\n") if _ctx else "") + skill
        resp = claude.messages.create(model=MODEL, max_tokens=600, system=_sys_prompt, messages=[{"role": "user", "content": prompt}])
        raw    = resp.content[0].text or "{}"
        clean  = re.sub(r"```(?:json)?\n?", "", raw).strip().lstrip("`").strip()
        invoice, _ = json.JSONDecoder().raw_decode(clean)
        invoice["status"]     = "sent"
        invoice["created_at"] = datetime.now().isoformat()

        # Save to invoice log
        invoice_log = _read("invoice_log.json")
        if "invoices" not in invoice_log:
            invoice_log["invoices"] = []
        invoice_log["invoices"].append(invoice)
        _write("invoice_log.json", invoice_log)

        _log(f"Invoice generated: {invoice_number} — ${invoice.get('amount')}")
        _log_history("finance", {
            "action":  "invoice",
            "client":  deal.get("client_name") or deal.get("client", ""),
            "amount":  invoice.get("amount"),
            "invoice": invoice_number,
        })
        return invoice

    except Exception as e:
        _log(f"Invoice generation error: {e}")
        return {}


def mark_invoice_paid(invoice_number: str, amount: float):
    """Mark an invoice as paid and update the ledger."""
    invoice_log = _read("invoice_log.json")
    for inv in invoice_log.get("invoices", []):
        if inv.get("invoice_number") == invoice_number:
            inv["status"]   = "paid"
            inv["paid_at"]  = datetime.now().isoformat()
            inv["paid_amount"] = amount
    _write("invoice_log.json", invoice_log)

    # Update master ledger
    record_revenue(amount, f"Invoice {invoice_number} paid")
    _log(f"Invoice paid: {invoice_number} — ${amount}")


# ── Revenue and expense tracking ──────────────────────────────────────────────

def record_revenue(amount: float, source: str, product: str = ""):
    """Record a revenue entry and check milestones."""
    finance = _read("finance.json")
    if "revenue" not in finance:
        finance["revenue"] = []
    if "expenses" not in finance:
        finance["expenses"] = []

    finance["revenue"].append({
        "amount":    amount,
        "source":    source,
        "product":   product,
        "date":      datetime.now().isoformat(),
    })
    _write("finance.json", finance)

    # Check milestones
    total = sum(r.get("amount", 0) for r in finance["revenue"])
    _check_milestones(total)
    _log(f"Revenue recorded: ${amount} from {source}. Total: ${total:.2f}")


def record_expense(amount: float, category: str, description: str):
    """Record an expense entry."""
    finance = _read("finance.json")
    if "expenses" not in finance:
        finance["expenses"] = []

    finance["expenses"].append({
        "amount":      amount,
        "category":    category,
        "description": description,
        "date":        datetime.now().isoformat(),
    })
    _write("finance.json", finance)

    # Check if expenses exceed 30% of revenue
    total_revenue  = sum(r.get("amount", 0) for r in finance.get("revenue", []))
    total_expenses = sum(e.get("amount", 0) for e in finance["expenses"])
    if total_revenue > 0:
        expense_ratio = total_expenses / total_revenue
        if expense_ratio > 0.30:
            _log(f"WARNING: Expenses at {expense_ratio*100:.1f}% of revenue — flagging CEO")

    _log(f"Expense recorded: ${amount} — {category}: {description}")


def _check_milestones(total_revenue: float):
    """Check if a revenue milestone has been hit."""
    milestones = _read("revenue_milestones.json")
    hit = milestones.get("hit", [])

    for milestone in MILESTONES:
        if total_revenue >= milestone and milestone not in hit:
            hit.append(milestone)
            milestones["hit"] = hit
            _write("revenue_milestones.json", milestones)
            _log(f"🎉 MILESTONE HIT: ${milestone:,} — flagging Joshua!")


# ── P&L Report ────────────────────────────────────────────────────────────────

def generate_pnl(period: str = "monthly") -> dict:
    """Generate Profit and Loss report."""
    finance  = _read("finance.json")
    revenue  = finance.get("revenue", [])
    expenses = finance.get("expenses", [])

    # Filter by period
    if period == "monthly":
        cutoff = datetime.now().replace(day=1).isoformat()
        revenue  = [r for r in revenue  if r.get("date", "") >= cutoff]
        expenses = [e for e in expenses if e.get("date", "") >= cutoff]

    total_revenue  = sum(r.get("amount", 0) for r in revenue)
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    net_profit     = total_revenue - total_expenses
    margin         = (net_profit / total_revenue * 100) if total_revenue > 0 else 0

    # Revenue by product
    by_product = {}
    for r in revenue:
        product = r.get("product", "unknown")
        by_product[product] = by_product.get(product, 0) + r.get("amount", 0)

    # Expenses by category
    by_category = {}
    for e in expenses:
        cat = e.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + e.get("amount", 0)

    pnl = {
        "period":          period,
        "generated_at":    datetime.now().isoformat(),
        "total_revenue":   round(total_revenue, 2),
        "total_expenses":  round(total_expenses, 2),
        "net_profit":      round(net_profit, 2),
        "profit_margin":   f"{margin:.1f}%",
        "revenue_by_product":  by_product,
        "expenses_by_category": by_category,
        "transactions":    len(revenue),
    }

    _log(f"P&L generated: Revenue ${total_revenue:.2f} | Expenses ${total_expenses:.2f} | Profit ${net_profit:.2f}")
    return pnl


def generate_balance_sheet() -> dict:
    """Generate monthly balance sheet."""
    finance  = _read("finance.json")
    invoices = _read("invoice_log.json")

    total_revenue  = sum(r.get("amount", 0) for r in finance.get("revenue", []))
    total_expenses = sum(e.get("amount", 0) for e in finance.get("expenses", []))

    # Accounts receivable — sent but unpaid invoices
    unpaid = [
        inv for inv in invoices.get("invoices", [])
        if inv.get("status") == "sent"
    ]
    accounts_receivable = sum(inv.get("amount", 0) for inv in unpaid)

    balance_sheet = {
        "generated_at":        datetime.now().isoformat(),
        "total_revenue":       round(total_revenue, 2),
        "total_expenses":      round(total_expenses, 2),
        "net_profit":          round(total_revenue - total_expenses, 2),
        "accounts_receivable": round(accounts_receivable, 2),
        "unpaid_invoices":     len(unpaid),
        "cash_position":       round(total_revenue - total_expenses, 2),
    }

    _log(f"Balance sheet generated: Net profit ${balance_sheet['net_profit']:.2f}")
    return balance_sheet


def get_financial_summary() -> dict:
    """Quick financial summary for CEO morning briefing."""
    pnl      = generate_pnl("monthly")
    invoices = _read("invoice_log.json")
    unpaid   = [i for i in invoices.get("invoices", []) if i.get("status") == "sent"]

    return {
        "monthly_revenue":  pnl.get("total_revenue"),
        "monthly_profit":   pnl.get("net_profit"),
        "profit_margin":    pnl.get("profit_margin"),
        "unpaid_invoices":  len(unpaid),
        "outstanding":      sum(i.get("amount", 0) for i in unpaid),
        "top_product":      max(pnl.get("revenue_by_product", {}).items(),
                               key=lambda x: x[1], default=("none", 0)),
    }


# ── Deal closed handler ───────────────────────────────────────────────────────

def handle_closed_deal(deal: dict) -> dict:
    """
    Full pipeline when Marketing Agent closes a deal.
    Generate invoice → send → record revenue → check milestones.
    """
    _log(f"=== Deal closed: {deal.get('lead', {}).get('name', 'Unknown')} ===")

    invoice = generate_invoice(deal)
    if invoice:
        record_revenue(
            amount=deal.get("value", 0),
            source=f"Deal: {deal.get('lead', {}).get('name', 'Unknown')}",
            product=deal.get("product", ""),
        )
        _log(f"Invoice sent and revenue recorded for ${deal.get('value', 0)}")

    return {
        "status":  "processed",
        "invoice": invoice,
        "deal":    deal,
    }


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Finance Agent Test")
    print("=" * 40)

    # Test with a sample closed deal
    test_deal = {
        "lead": {
            "name":    "Johnson HVAC Services",
            "contact": "mike@johnsonhvac.com",
            "type":    "HVAC Company",
        },
        "value":   297.00,
        "product": "HVAC Call Screener",
    }

    print("Processing closed deal...")
    result = handle_closed_deal(test_deal)
    print(f"Invoice: {result.get('invoice', {}).get('invoice_number')}")

    print("\nGenerating P&L...")
    pnl = generate_pnl()
    print(json.dumps(pnl, indent=2))

    print("\nFinancial summary:")
    print(json.dumps(get_financial_summary(), indent=2))