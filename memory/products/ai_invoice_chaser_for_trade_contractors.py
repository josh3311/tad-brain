"""
AI Invoice Chaser for Trade Contractors
========================================
Product: Automated invoice follow-up system for small construction/trade contractors
Author: TAD Build Agent
Build Date: 2026-06-28
Version: 1.0.0

Business Logic:
- Ingests invoices (CSV or manual entry)
- Tracks payment status and days outstanding
- Generates escalating follow-up messages (polite → firm → final notice)
- Sends via email (SMTP) and SMS (Twilio)
- Logs all activity to memory/products/invoice_chaser/
- Provides CLI dashboard of outstanding invoices + revenue at risk
- Compliance-aware: avoids FDCPA-triggering language, adds state opt-out hooks

Revenue Model: SaaS subscription — contractors pay $29-79/mo based on invoice volume
"""

import os
import csv
import json
import time
import smtplib
import logging
import hashlib
import argparse
import textwrap
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# ── Optional Twilio (graceful degradation if not installed) ──────────────────
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# ── Optional Anthropic for AI message generation ────────────────────────────
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# ── Directory bootstrap ──────────────────────────────────────────────────────
BASE_DIR = Path("memory/products/invoice_chaser")
BASE_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = BASE_DIR / "activity.log"
INVOICE_DB = BASE_DIR / "invoices.json"
AUDIT_LOG  = BASE_DIR / "audit_trail.jsonl"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("invoice_chaser")


# ════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ════════════════════════════════════════════════════════════════════════════

class InvoiceStatus(str, Enum):
    DRAFT      = "draft"
    SENT       = "sent"
    OVERDUE    = "overdue"
    ESCALATED  = "escalated"
    FINAL_NOTICE = "final_notice"
    PAID       = "paid"
    WRITTEN_OFF = "written_off"


class ChaseStage(int, Enum):
    """Maps to escalation level — higher = more assertive tone."""
    FRIENDLY_REMINDER = 1   # 1-7 days overdue
    POLITE_FOLLOW_UP  = 2   # 8-14 days overdue
    FIRM_REQUEST      = 3   # 15-29 days overdue
    FINAL_NOTICE      = 4   # 30+ days overdue


@dataclass
class Contact:
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None   # E.164 format: +15551234567
    company: Optional[str] = None
    state: Optional[str] = None   # 2-letter US state for compliance hooks


@dataclass
class Invoice:
    invoice_id: str
    contractor_name: str
    client: Contact
    amount: float
    issue_date: str          # ISO 8601: YYYY-MM-DD
    due_date: str
    description: str
    status: InvoiceStatus = InvoiceStatus.SENT
    chase_count: int = 0
    last_chased: Optional[str] = None
    paid_date: Optional[str] = None
    notes: str = ""
    tags: list = field(default_factory=list)

    @property
    def days_overdue(self) -> int:
        due = datetime.fromisoformat(self.due_date)
        return max(0, (datetime.now() - due).days)

    @property
    def chase_stage(self) -> ChaseStage:
        d = self.days_overdue
        if d <= 7:
            return ChaseStage.FRIENDLY_REMINDER
        elif d <= 14:
            return ChaseStage.POLITE_FOLLOW_UP
        elif d <= 29:
            return ChaseStage.FIRM_REQUEST
        else:
            return ChaseStage.FINAL_NOTICE

    @property
    def is_actionable(self) -> bool:
        """True if invoice should be chased today."""
        if self.status in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF, InvoiceStatus.DRAFT):
            return False
        if self.days_overdue <= 0:
            return False
        if self.last_chased:
            last = datetime.fromisoformat(self.last_chased)
            cooldown = self._cooldown_days()
            if (datetime.now() - last).days < cooldown:
                return False
        return True

    def _cooldown_days(self) -> int:
        """Days between follow-ups per stage."""
        return {
            ChaseStage.FRIENDLY_REMINDER: 3,
            ChaseStage.POLITE_FOLLOW_UP:  4,
            ChaseStage.FIRM_REQUEST:      5,
            ChaseStage.FINAL_NOTICE:      7,
        }[self.chase_stage]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Invoice":
        data["status"] = InvoiceStatus(data.get("status", "sent"))
        data["client"] = Contact(**data["client"])
        return cls(**data)


# ════════════════════════════════════════════════════════════════════════════
# INVOICE DATABASE (JSON file persistence)
# ════════════════════════════════════════════════════════════════════════════

class InvoiceDatabase:
    def __init__(self, path: Path = INVOICE_DB):
        self.path = path
        self._data: dict[str, Invoice] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                self._data = {k: Invoice.from_dict(v) for k, v in raw.items()}
                log.info(f"Loaded {len(self._data)} invoices from {self.path}")
            except Exception as e:
                log.error(f"Failed to load invoice DB: {e}")
                self._data = {}

    def save(self):
        try:
            serialized = {k: v.to_dict() for k, v in self._data.items()}
            self.path.write_text(json.dumps(serialized, indent=2))
        except Exception as e:
            log.error(f"Failed to save invoice DB: {e}")

    def add(self, invoice: Invoice):
        self._data[invoice.invoice_id] = invoice
        self.save()
        log.info(f"Added invoice {invoice.invoice_id} — ${invoice.amount:.2f} from {invoice.client.name}")

    def get(self, invoice_id: str) -> Optional[Invoice]:
        return self._data.get(invoice_id)

    def all(self) -> list[Invoice]:
        return list(self._data.values())

    def mark_paid(self, invoice_id: str):
        inv = self._data.get(invoice_id)
        if inv:
            inv.status = InvoiceStatus.PAID
            inv.paid_date = datetime.now().date().isoformat()
            self.save()
            log.info(f"Invoice {invoice_id} marked PAID")
            return True
        return False

    def overdue(self) -> list[Invoice]:
        return [i for i in self._data.values() if i.days_overdue > 0
                and i.status not in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF)]

    def actionable(self) -> list[Invoice]:
        return [i for i in self._data.values() if i.is_actionable]

    def stats(self) -> dict:
        all_inv = self._data.values()
        overdue = [i for i in all_inv if i.days_overdue > 0
                   and i.status not in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF)]
        paid    = [i for i in all_inv if i.status == InvoiceStatus.PAID]
        return {
            "total_invoices": len(self._data),
            "total_outstanding": sum(i.amount for i in overdue),
            "overdue_count": len(overdue),
            "avg_days_overdue": (sum(i.days_overdue for i in overdue) / len(overdue)) if overdue else 0,
            "paid_count": len(paid),
            "paid_total": sum(i.amount for i in paid),
            "at_risk_90_plus": sum(i.amount for i in overdue if i.days_overdue >= 90),
        }


# ════════════════════════════════════════════════════════════════════════════
# COMPLIANCE LAYER
# ════════════════════════════════════════════════════════════════════════════

# States with stricter commercial debt collection rules (conservative list)
STRICT_STATES = {"CA", "NY", "TX", "IL", "WA", "MA", "NJ"}

# Banned phrases that could trigger FDCPA / state equivalents
BANNED_PHRASES = [
    "you will be sued",
    "legal action will be taken",
    "we will report to credit bureau",
    "debt collector",
    "collection agency",
    "final demand before litigation",
]

def compliance_check(message: str, client_state: Optional[str] = None) -> tuple[bool, list[str]]:
    """
    Returns (is_compliant, list_of_issues).
    Compliance note: This tool targets B2B contractor invoices.
    FDCPA primarily covers consumer debt; however, many states extend
    similar protections to commercial contexts. When in doubt, use
    soft language and always include opt-out language.
    """
    issues = []
    msg_lower = message.lower()

    for phrase in BANNED_PHRASES:
        if phrase in msg_lower:
            issues.append(f"Potentially problematic phrase detected: '{phrase}'")

    if client_state and client_state.upper() in STRICT_STATES:
        # In strict states, add a soft advisory
        if "opt out" not in msg_lower and "unsubscribe" not in msg_lower:
            issues.append(f"State {client_state} — consider adding opt-out language")

    return (len(issues) == 0, issues)


def add_compliance_footer(state: Optional[str] = None) -> str:
    base = "\n\n---\nThis is a reminder from your contractor. To stop receiving reminders, " \
           "reply STOP or email us directly."
    if state and state.upper() in STRICT_STATES:
        base += f" [Compliance notice for {state} recipients: This communication is from " \
                f"the original service provider, not a third-party collector.]"
    return base


# ════════════════════════════════════════════════════════════════════════════
# MESSAGE GENERATION
# ════════════════════════════════════════════════════════════════════════════

TEMPLATE_LIBRARY = {
    ChaseStage.FRIENDLY_REMINDER: {
        "subject": "Friendly reminder: Invoice #{invoice_id} due {due_date}",
        "body": textwrap.dedent("""\
            Hi {client_name},

            Hope your project is going well! Just a quick heads-up that Invoice #{invoice_id}
            for ${amount:.2f} ({description}) was due on {due_date}.

            If you've already sent payment, please disregard this message — and thank you!

            If not, here are your payment options:
            • Bank transfer / check payable to {contractor_name}
            • Online: [Your payment link here]

            Invoice total: ${amount:.2f}
            Days outstanding: {days_overdue}

            Thanks for your business — I really appreciate it.

            {contractor_name}
        """),
    },
    ChaseStage.POLITE_FOLLOW_UP: {
        "subject": "Follow-up: Invoice #{invoice_id} — ${amount:.2f} outstanding",
        "body": textwrap.dedent("""\
            Hi {client_name},

            I'm following up on Invoice #{invoice_id} for ${amount:.2f} ({description}),
            which was due on {due_date} and is now {days_overdue} days past due.

            I understand things get busy — I just need to make sure this doesn't slip
            through the cracks on either end.

            Could you confirm:
            1. Has payment been sent? If so, when can I expect it to clear?
            2. If there's a hold-up, can we discuss and find a solution?

            Outstanding balance: ${amount:.2f}

            I value our working relationship and want to keep things smooth.

            {contractor_name}
        """),
    },
    ChaseStage.FIRM_REQUEST: {
        "subject": "Action required: Invoice #{invoice_id} — {days_overdue} days overdue",
        "body": textwrap.dedent("""\
            Hi {client_name},

            This is my third notice regarding Invoice #{invoice_id} for ${amount:.2f}
            ({description}), now {days_overdue} days past the due date of {due_date}.

            The work has been completed and delivered as agreed. Payment of ${amount:.2f}
            is owed and overdue.

            I need to receive payment or a confirmed payment commitment within 5 business
            days. Please reply to this email with your payment timeline or arrange
            payment directly.

            Outstanding: ${amount:.2f}
            Original due: {due_date}
            Days overdue: {days_overdue}

            I'd prefer to resolve this without further escalation.

            {contractor_name}
        """),
    },
    ChaseStage.FINAL_NOTICE: {
        "subject": "FINAL NOTICE: Invoice #{invoice_id} — Immediate payment required",
        "body": textwrap.dedent("""\
            Hi {client_name},

            This is a final notice for Invoice #{invoice_id} — ${amount:.2f}
            ({description}) — now {days_overdue} days overdue.

            Despite multiple follow-ups, this invoice remains unpaid. I am now reviewing
            my options for recovering this outstanding balance, which may include filing
            a claim in small claims court or engaging a collections professional.

            To avoid additional steps, please remit payment of ${amount:.2f} in full
            within 3 business days, or contact me immediately to make arrangements.

            Outstanding: ${amount:.2f}
            Invoice date: {issue_date}
            Due date: {due_date}

            This is your final notice before I take further action.

            {contractor_name}
        """),
    },
}


def generate_message_from_template(invoice: Invoice) -> tuple[str, str]:
    """Returns (subject, body) using the built-in template library."""
    template = TEMPLATE_LIBRARY[invoice.chase_stage]
    context = {
        "invoice_id":      invoice.invoice_id,
        "client_name":     invoice.client.name,
        "contractor_name": invoice.contractor_name,
        "amount":          invoice.amount,
        "description":     invoice.description,
        "due_date":        invoice.due_date,
        "issue_date":      invoice.issue_date,
        "days_overdue":    invoice.days_overdue,
    }
    subject = template["subject"].format(**context)
    body    = template["body"].format(**context)
    body   += add_compliance_footer(invoice.client.state)
    return subject, body


def generate_message_with_ai(invoice: Invoice, api_key: Optional[str] = None) -> tuple[str, str]:
    """
    Uses Claude to generate a personalised follow-up message.
    Falls back to template if Anthropic not available or API call fails.
    """
    if not ANTHROPIC_AVAILABLE or not api_key:
        log.info("AI message generation unavailable — using template")
        return generate_message_from_template(invoice)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        stage_name = invoice.chase_stage.name.replace("_", " ").title()
        prompt = f"""You are writing a professional invoice follow-up email for a trade contractor.

Invoice details:
- Invoice ID: {invoice.invoice_id}
- Client name: {invoice.client.name}
- Client company: {invoice.client.company or 'N/A'}
- Contractor name: {invoice.contractor_name}
- Amount owed: ${invoice.amount:.2f}
- Description: {invoice.description}
- Due date: {invoice.due_date}
- Days overdue: {invoice.days_overdue}
- Follow-up stage: {stage_name} (chase #{invoice.chase_count + 1})

Write a {stage_name.lower()} email. Be professional, direct, and appropriate for the escalation level.
Do NOT use any threatening legal language or debt collector framing.
Return ONLY a JSON object with keys "subject" and "body". No other text."""

        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Extract JSON even if Claude adds prose
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        data  = json.loads(raw[start:end])
        subject = data["subject"]
        body    = data["body"] + add_compliance_footer(invoice.client.state)
        return subject, body

    except Exception as e:
        log.warning(f"AI message generation failed ({e}) — falling back to template")
        return generate_message_from_template(invoice)


def generate_sms_message(invoice: Invoice) -> str:
    """Concise SMS reminder — max 160 chars per segment."""
    stage = invoice.chase_stage
    base = (
        f"Hi {invoice.client.name.split()[0]}, "
        f"invoice #{invoice.invoice_id} for ${invoice.amount:.2f} is "
        f"{invoice.days_overdue}d overdue. "
        f"Please arrange payment. — {invoice.contractor_name}. "
        f"Reply STOP to opt out."
    )
    if stage == ChaseStage.FINAL_NOTICE:
        base = (
            f"FINAL NOTICE: Invoice #{invoice.invoice_id} ${invoice.amount:.2f} "
            f"is {invoice.days_overdue} days overdue. "
            f"Contact {invoice.contractor_name} immediately. Reply STOP to opt out."
        )
    return base[:320]  # max 2 SMS segments


# ════════════════════════════════════════════════════════════════════════════
# DELIVERY CHANNELS
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_address: str
    use_tls: bool = True


@dataclass
class SMSConfig:
    account_sid: str
    auth_token: str
    from_number: str  # E.164


def send_email(config: EmailConfig, to_address: str, subject: str, body: str) -> bool:
    """Send plain-text email. Returns True on success."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = config.from_address
        msg["To"]      = to_address
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as server:
            if config.use_tls:
                server.starttls()
            server.login(config.username, config.password)
            server.sendmail(config.from_address, to_address, msg.as_string())

        log.info(f"Email sent to {to_address} | Subject: {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        log.error(f"SMTP auth failed for {config.username} — check credentials")
    except smtplib.SMTPConnectError:
        log.error(f"SMTP connection failed to {config.smtp_host}:{config.smtp_port}")
    except Exception as e:
        log.error(f"Email send failed to {to_address}: {e}")
    return False


def send_sms(config: SMSConfig, to_number: str, message: str) -> bool:
    """Send SMS via Twilio. Returns True on success."""
    if not TWILIO_AVAILABLE:
        log.warning("Twilio not installed — SMS skipped. Run: pip install twilio")
        return False
    try:
        client = TwilioClient(config.account_sid, config.auth_token)
        result = client.messages.create(
            body=message,
            from_=config.from_number,
            to=to_number
        )
        log.info(f"SMS sent to {to_number} | SID: {result.sid}")
        return True
    except Exception as e:
        log.error(f"SMS send failed to {to_number}: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# AUDIT TRAIL
# ════════════════════════════════════════════════════════════════════════════

def write_audit_event(event_type: str, invoice: Invoice, details: dict):
    """Append an immutable audit record to the JSONL audit log."""
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": event_type,
        "invoice_id": invoice.invoice_id,
        "client_name": invoice.client.name,
        "amount": invoice.amount,
        "days_overdue": invoice.days_overdue,
        "chase_stage": invoice.chase_stage.name,
        "chase_count": invoice.chase_count,
        **details,
    }
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")


# ════════════════════════════════════════════════════════════════════════════
# CORE CHASE ENGINE
# ════════════════════════════════════════════════════════════════════════════

class InvoiceChaser:
    def __init__(
        self,
        db: InvoiceDatabase,
        email_config: Optional[EmailConfig] = None,
        sms_config: Optional[SMSConfig] = None,
        anthropic_api_key: Optional[str] = None,
        dry_run: bool = False,
    ):
        self.db    = db
        self.email = email_config
        self.sms   = sms_config
        self.ai_key = anthropic_api_key
        self.dry_run = dry_run

        if dry_run:
            log.info("⚠ DRY RUN MODE — no messages will be sent")

    def run_chase_cycle(self) -> dict:
        """
        Main entry point: finds all actionable invoices and chases them.
        Returns a summary dict.
        """
        actionable = self.db.actionable()
        log.info(f"Chase cycle started — {len(actionable)} invoices to chase")

        results = {
            "chased": 0,
            "email_sent": 0,
            "sms_sent": 0,
            "skipped_compliance": 0,
            "errors": 0,
            "total_value_chased": 0.0,
        }

        for invoice in actionable:
            try:
                outcome = self._chase_invoice(invoice)
                if outcome["sent"]:
                    results["chased"] += 1
                    results["total_value_chased"] += invoice.amount
                    if outcome.get("email"):
                        results["email_sent"] += 1
                    if outcome.get("sms"):
                        results["sms_sent"] += 1
                elif outcome.get("compliance_block"):
                    results["skipped_compliance"] += 1
            except Exception as e:
                log.error(f"Unexpected error chasing invoice {invoice.invoice_id}: {e}")
                results["errors"] += 1

        log.info(
            f"Chase cycle complete — {results['chased']} chased, "
            f"${results['total_value_chased']:,.2f} in motion"
        )
        return results

    def _chase_invoice(self, invoice: Invoice) -> dict:
        """Chase a single invoice. Returns outcome dict."""
        log.info(
            f"Chasing invoice {invoice.invoice_id} | "
            f"${invoice.amount:.2f} | {invoice.days_overdue}d overdue | "
            f"Stage: {invoice.chase_stage.name}"
        )

        # Generate message
        subject, body = generate_message_with_ai(invoice, self.ai_key)

        # Compliance gate
        ok, issues = compliance_check(body, invoice.client.state)
        if not ok:
            log.warning(f"Compliance block on {invoice.invoice_id}: {issues}")
            write_audit_event("COMPLIANCE_BLOCK", invoice, {"issues": issues})
            return {"sent": False, "compliance_block": True, "issues": issues}

        outcome = {"sent": False, "email": False, "sms": False}

        # Email
        if invoice.client.email and self.email:
            if self.dry_run:
                log.info(f"[DRY RUN] Would email {invoice.client.email}:\n{subject}\n{body[:120]}...")
                outcome["email"] = True
                outcome["sent"]  = True
            else:
                sent = send_email(self.email, invoice.client.email, subject, body)
                outcome["email"] = sent
                if sent:
                    outcome["sent"] = True

        # SMS (only stages 3+ to avoid spamming)
        if (invoice.client.phone and self.sms
                and invoice.chase_stage.value >= ChaseStage.FIRM_REQUEST.value):
            sms_text = generate_sms_message(invoice)
            if self.dry_run:
                log.info(f"[DRY RUN] Would SMS {invoice.client.phone}: {sms_text}")
                outcome["sms"]  = True
                outcome["sent"] = True
            else:
                sent = send_sms(self.sms, invoice.client.phone, sms_text)
                outcome["sms"] = sent
                if sent:
                    outcome["sent"] = True

        # Update invoice record
        if outcome["sent"] or self.dry_run:
            invoice.chase_count += 1
            invoice.last_chased  = datetime.now().isoformat()
            invoice.status = (
                InvoiceStatus.FINAL_NOTICE
                if invoice.chase_stage == ChaseStage.FINAL_NOTICE
                else InvoiceStatus.OVERDUE
                if invoice.days_overdue > 7
                else InvoiceStatus.ESCALATED
            )
            self.db.save()
            write_audit_event("CHASE_SENT", invoice, {
                "subject": subject,
                "email_sent": outcome["email"],
                "sms_sent": outcome["sms"],
                "dry_run": self.dry_run,
            })

        return outcome


# ════════════════════════════════════════════════════════════════════════════
# CSV IMPORT
# ════════════════════════════════════════════════════════════════════════════

def import_from_csv(filepath: str, contractor_name: str, db: InvoiceDatabase) -> int:
    """
    Import invoices from CSV.
    Expected columns: invoice_id, client_name, client_email, client_phone,
                      client_company, client_state, amount, issue_date,
                      due_date, description, status
    Returns number of invoices imported.
    """
    imported = 0
    try:
        with open(filepath, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    inv_id = row.get("invoice_id") or _generate_id(
                        row.get("client_name", ""), row.get("amount", "0")
                    )
                    contact = Contact(
                        name    = row.get("client_name", "Unknown"),
                        email   = row.get("client_email") or None,
                        phone   = row.get("client_phone") or None,
                        company = row.get("client_company") or None,
                        state   = row.get("client_state") or None,
                    )
                    invoice = Invoice(
                        invoice_id      = inv_id,
                        contractor_name = contractor_name,
                        client          = contact,
                        amount          = float(row.get("amount", 0)),
                        issue_date      = row.get("issue_date", datetime.now().date().isoformat()),
                        due_date        = row.get("due_date", datetime.now().date().isoformat()),
                        description     = row.get("description", "Services rendered"),
                        status          = InvoiceStatus(row.get("status", "sent")),
                    )
                    db.add(invoice)
                    imported += 1
                except Exception as e:
                    log.warning(f"Skipping CSV row (parse error): {e} | Row: {row}")
    except FileNotFoundError:
        log.error(f"CSV file not found: {filepath}")
    except Exception as e:
        log.error(f"CSV import failed: {e}")

    log.info(f"CSV import complete — {imported} invoices loaded from {filepath}")
    return imported


def _generate_id(client: str, amount: str) -> str:
    """Deterministic fallback invoice ID from client + amount + timestamp."""
    raw = f"{client}{amount}{time.time()}"
    return "INV-" + hashlib.md5(raw.encode()).hexdigest()[:8].upper()


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD / REPORTING
# ════════════════════════════════════════════════════════════════════════════

def print_dashboard(db: InvoiceDatabase):
    """CLI dashboard — prints outstanding invoice summary."""
    stats = db.stats()
    overdue = sorted(db.overdue(), key=lambda i: i.days_overdue, reverse=True)

    print("\n" + "═" * 65)
    print("  💰  AI INVOICE CHASER — OUTSTANDING RECEIVABLES DASHBOARD")
    print("═" * 65)
    print(f"  Total invoices tracked : {stats['total_invoices']}")
    print(f"  Overdue invoices       : {stats['overdue_count']}")
    print(f"  Total outstanding      : ${stats['total_outstanding']:,.2f}")
    print(f"  Avg days overdue       : {stats['avg_days_overdue']:.1f} days")
    print(f"  90+ day risk           : ${stats['at_risk_90_plus']:,.2f}")
    print(f"  Total paid (all time)  : ${stats['paid_total']:,.2f}")
    print("─" * 65)

    if not overdue:
        print("  ✅  No overdue invoices. Great payment health!")
    else:
        print(f"  {'ID':<12} {'Client':<20} {'Amount':>9}  {'Days':>5}  Stage")
        print("  " + "─" * 60)
        for inv in overdue[:20]:  # show top 20
            stage_icon = {
                ChaseStage.FRIENDLY_REMINDER: "🟢",
                ChaseStage.POLITE_FOLLOW_UP:  "🟡",
                ChaseStage.FIRM_REQUEST:      "🟠",
                ChaseStage.FINAL_NOTICE:      "🔴",
            }[inv.chase_stage]
            print(
                f"  {inv.invoice_id:<12} {inv.client.name[:20]:<20} "
                f"${inv.amount:>8,.2f}  {inv.days_overdue:>5}d  "
                f"{stage_icon} {inv.chase_stage.name}"
            )
        if len(overdue) > 20:
            print(f"  ... and {len(overdue) - 20} more")

    print("═" * 65)
    actionable = db.actionable()
    print(f"  ⚡ {len(actionable)} invoices ready to chase now")
    print(f"  📁 Audit log: {AUDIT_LOG}")
    print("═" * 65 + "\n")


def export_report(db: InvoiceDatabase) -> Path:
    """Export overdue invoice report to CSV in the products folder."""
    report_path = BASE_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    overdue = db.overdue()

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "invoice_id", "client_name", "client_email", "client_phone",
            "amount", "due_date", "days_overdue", "status", "chase_count",
            "last_chased", "stage"
        ])
        for inv in overdue:
            writer.writerow([
                inv.invoice_id,
                inv.client.name,
                inv.client.email or "",
                inv.client.phone or "",
                inv.amount,
                inv.due_date,
                inv.days_overdue,
                inv.status.value,
                inv.chase_count,
                inv.last_chased or "",
                inv.chase_stage.name,
            ])

    log.info(f"Report exported to {report_path}")
    return report_path


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="invoice_chaser",
        description="AI Invoice Chaser — automated follow-up for trade contractors"
    )
    sub = p.add_subparsers(dest="command")

    # dashboard
    sub.add_parser("dashboard", help="Show outstanding invoice dashboard")

    # add invoice manually
    add = sub.add_parser("add", help="Add a new invoice")
    add.add_argument("--id",          required=True,  help="Invoice ID (e.g. INV-001)")
    add.add_argument("--contractor",  required=True,  help="Your business name")
    add.add_argument("--client",      required=True,  help="Client name")
    add.add_argument("--email",       default=None,   help="Client email")
    add.add_argument("--phone",       default=None,   help="Client phone (E.164)")
    add.add_argument("--company",     default=None,   help="Client company")
    add.add_argument("--state",       default=None,   help="Client state (2-letter)")
    add.add_argument("--amount",      required=True,  type=float)
    add.add_argument("--due",         required=True,  help="Due date YYYY-MM-DD")
    add.add_argument("--issued",      default=None,   help="Issue date YYYY-MM-DD")
    add.add_argument("--description", default="Services rendered")

    # mark paid
    paid = sub.add_parser("paid", help="Mark invoice as paid")
    paid.add_argument("invoice_id")

    # run chase
    chase = sub.add_parser("chase", help="Run the chase engine")
    chase.add_argument("--dry-run",   action="store_true", help="Preview without sending")
    chase.add_argument("--smtp-host", default=os.getenv("SMTP_HOST", "smtp.gmail.com"))
    chase.add_argument("--smtp-port", default=int(os.getenv("SMTP_PORT", "587")), type=int)
    chase.add_argument("--smtp-user", default=os.getenv("SMTP_USER"))
    chase.add_argument("--smtp-pass", default=os.getenv("SMTP_PASS"))
    chase.add_argument("--from-email",default=os.getenv("FROM_EMAIL"))
    chase.add_argument("--twilio-sid",default=os.getenv("TWILIO_ACCOUNT_SID"))
    chase.add_argument("--twilio-token", default=os.getenv("TWILIO_AUTH_TOKEN"))
    chase.add_argument("--twilio-from",  default=os.getenv("TWILIO_FROM_NUMBER"))
    chase.add_argument("--ai-key",    default=os.getenv("ANTHROPIC_API_KEY"))

    # import CSV
    imp = sub.add_parser("import", help="Import invoices from CSV")
    imp.add_argument("filepath")
    imp.add_argument("--contractor", required=True, help="Your business name")

    # export report
    sub.add_parser("report", help="Export overdue report to CSV")

    return p


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def _seed_demo_invoices(db: InvoiceDatabase):
    """Populate the DB with realistic demo data for first-run showcase."""
    if db.all():
        return  # already seeded

    today = datetime.now().date()
    demos = [
        Invoice(
            invoice_id="INV-2024-001",
            contractor_name="Peak Electrical LLC",
            client=Contact(name="Mike Rosenberg", email="demo@example.com",
                          company="Rosenberg Builds", state="TX"),
            amount=4800.00,
            issue_date=(today - timedelta(days=45)).isoformat(),
            due_date=(today - timedelta(days=15)).isoformat(),
            description="Electrical rough-in, 3-bed new construction",
            status=InvoiceStatus.OVERDUE,
            chase_count=1,
        ),
        Invoice(
            invoice_id="INV-2024-002",
            contractor_name="Peak Electrical LLC",
            client=Contact(name="Sandra Chu", email="demo2@example.com",
                          phone="+15550001234", company="Chu Properties", state="CA"),
            amount=12_350.00,
            issue_date=(today - timedelta(days=65)).isoformat(),
            due_date=(today - timedelta(days=35)).isoformat(),
            description="Panel upgrade + EV charger install, commercial",
            status=InvoiceStatus.ESCALATED,
            chase_count=3,
        ),
        Invoice(
            invoice_id="INV-2024-003",
            contractor_name="Peak Electrical LLC",
            client=Contact(name="Tony Marchetti", email="demo3@example.com",
                          state="NY"),
            amount=950.00,
            issue_date=(today - timedelta(days=12)).isoformat(),
            due_date=(today - timedelta(days=2)).isoformat(),
            description="Emergency lighting repair",
            status=InvoiceStatus.SENT,
        ),
        Invoice(
            invoice_id="INV-2024-004",
            contractor_name="Peak Electrical LLC",
            client=Contact(name="Heritage Hotel Group", email="demo4@example.com"),
            amount=28_000.00,
            issue_date=(today - timedelta(days=110)).isoformat(),
            due_date=(today - timedelta(days=80)).isoformat(),
            description="Full hotel rewire, Phase 2",
            status=InvoiceStatus.FINAL_NOTICE,
            chase_count=6,
        ),
    ]
    for inv in demos:
        db.add(inv)
    log.info("Demo invoices seeded — run 'dashboard' to view")


def main():
    parser = build_arg_parser()
    args   = parser.parse_args()
    db     = InvoiceDatabase()

    if args.command == "dashboard" or args.command is None:
        _seed_demo_invoices(db)
        print_dashboard(db)

    elif args.command == "add":
        contact = Contact(
            name    = args.client,
            email   = args.email,
            phone   = args.phone,
            company = args.company,
            state   = args.state,
        )
        invoice = Invoice(
            invoice_id      = args.id,
            contractor_name = args.contractor,
            client          = contact,
            amount          = args.amount,
            issue_date      = args.issued or datetime.now().date().isoformat(),
            due_date        = args.due,
            description     = args.description,
        )
        db.add(invoice)
        print(f"✅ Invoice {invoice.invoice_id} added — ${invoice.amount:,.2f} due {invoice.due_date}")

    elif args.command == "paid":
        ok = db.mark_paid(args.invoice_id)
        if ok:
            print(f"✅ Invoice {args.invoice_id} marked as PAID")
        else:
            print(f"❌ Invoice {args.invoice_id} not found")

    elif args.command == "chase":
        email_cfg = None
        if args.smtp_user and args.smtp_pass and args.from_email:
            email_cfg = EmailConfig(
                smtp_host    = args.smtp_host,
                smtp_port    = args.smtp_port,
                username     = args.smtp_user,
                password     = args.smtp_pass,
                from_address = args.from_email,
            )
        else:
            log.warning("No SMTP credentials — email will be skipped. "
                       "Set SMTP_USER, SMTP_PASS, FROM_EMAIL env vars.")

        sms_cfg = None
        if args.twilio_sid and args.twilio_token and args.twilio_from:
            sms_cfg = SMSConfig(
                account_sid = args.twilio_sid,
                auth_token  = args.twilio_token,
                from_number = args.twilio_from,
            )

        chaser = InvoiceChaser(
            db               = db,
            email_config     = email_cfg,
            sms_config       = sms_cfg,
            anthropic_api_key= args.ai_key,
            dry_run          = args.dry_run,
        )
        _seed_demo_invoices(db)
        results = chaser.run_chase_cycle()
        print_dashboard(db)
        print(f"  Chase results: {results}")

    elif args.command == "import":
        n = import_from_csv(args.filepath, args.contractor, db)
        print(f"✅ Imported {n} invoices")
        print_dashboard(db)

    elif args.command == "report":
        path = export_report(db)
        print(f"✅ Report exported to {path}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()