"""
AI Invoice Chaser for Trade Contractors
========================================
Product: Automated invoice follow-up system for small construction/trade contractors
Target: ~2.8M US/Canada trade contractors losing $15-40K/yr to unpaid invoices
Revenue Model: SaaS subscription ($49-149/mo) + optional SMS add-on

Architecture:
- InvoiceChaser: Core engine — loads invoices, determines follow-up strategy, sends messages
- EscalationEngine: Decides tone/channel based on days overdue + client history
- MessageComposer: Generates professional, legally compliant follow-up messages
- DeliveryEngine: Sends via SendGrid (email) + Twilio (SMS) with fallback logging
- ReportEngine: Produces daily contractor dashboard (console + JSON)

Compliance Notes:
- Messages stay informational (invoice reminders), not debt-collection demands
- Avoids FDCPA-triggering language (we are not a debt collector, we are a billing tool)
- State-specific soft-caps: no threatening language, no contact before 8AM / after 9PM
- All contact timestamps logged for audit trail

Author: TAD Build Agent
Built: 2026-06-28
"""

import os
import json
import logging
import hashlib
import smtplib
import time
import re
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
LOG_DIR = Path("memory/invoice_chaser")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "invoice_chaser.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("InvoiceChaser")

# ─────────────────────────────────────────────
# ENUMS & CONSTANTS
# ─────────────────────────────────────────────

class InvoiceStatus(Enum):
    PENDING   = "pending"
    OVERDUE   = "overdue"
    PAID      = "paid"
    DISPUTED  = "disputed"
    ESCALATED = "escalated"
    WRITTEN_OFF = "written_off"


class ContactChannel(Enum):
    EMAIL = "email"
    SMS   = "sms"
    BOTH  = "both"


class EscalationLevel(Enum):
    REMINDER    = 1   # 1-7 days overdue  — friendly nudge
    FOLLOW_UP   = 2   # 8-21 days         — firmer, asks for confirmation
    FINAL_NOTICE = 3  # 22-45 days        — formal, mentions next steps
    HOLD        = 4   # 45+ days          — flag for contractor decision


ESCALATION_THRESHOLDS = {
    EscalationLevel.REMINDER:     (1, 7),
    EscalationLevel.FOLLOW_UP:    (8, 21),
    EscalationLevel.FINAL_NOTICE: (22, 45),
    EscalationLevel.HOLD:         (46, 9999),
}

# Safe contact hours (local time assumed; UTC used here for MVP)
CONTACT_HOUR_START = 8   # 8 AM
CONTACT_HOUR_END   = 20  # 8 PM

# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class Client:
    client_id: str
    name: str
    email: Optional[str]
    phone: Optional[str]          # E.164 format: +15550001234
    preferred_channel: ContactChannel = ContactChannel.EMAIL
    dispute_flag: bool = False
    total_paid_historical: float = 0.0
    avg_days_to_pay: int = 0


@dataclass
class Invoice:
    invoice_id: str
    client: Client
    contractor_name: str
    amount: float
    currency: str
    issue_date: datetime
    due_date: datetime
    description: str
    status: InvoiceStatus = InvoiceStatus.PENDING
    paid_date: Optional[datetime] = None
    contact_log: list = field(default_factory=list)  # list of ContactEvent dicts
    escalation_level: EscalationLevel = EscalationLevel.REMINDER

    @property
    def days_overdue(self) -> int:
        if self.status == InvoiceStatus.PAID:
            return 0
        now = datetime.now(timezone.utc)
        due = self.due_date.replace(tzinfo=timezone.utc) if self.due_date.tzinfo is None else self.due_date
        delta = (now - due).days
        return max(0, delta)

    @property
    def is_overdue(self) -> bool:
        return self.days_overdue > 0

    @property
    def amount_display(self) -> str:
        return f"{self.currency} {self.amount:,.2f}"

    def log_contact(self, channel: ContactChannel, message_type: str, success: bool, note: str = ""):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channel": channel.value,
            "message_type": message_type,
            "success": success,
            "note": note,
        }
        self.contact_log.append(event)
        log.info(
            f"[{self.invoice_id}] Contact logged — "
            f"channel={channel.value} type={message_type} success={success}"
        )


# ─────────────────────────────────────────────
# MESSAGE COMPOSER
# ─────────────────────────────────────────────

class MessageComposer:
    """
    Generates legally safe, professional invoice follow-up messages.
    Tone escalates automatically. No FDCPA-triggering language.
    """

    SUBJECT_TEMPLATES = {
        EscalationLevel.REMINDER:     "Friendly reminder — Invoice #{invoice_id} due {due_date}",
        EscalationLevel.FOLLOW_UP:    "Invoice #{invoice_id} — Payment not yet received",
        EscalationLevel.FINAL_NOTICE: "Action needed — Invoice #{invoice_id} is {days_overdue} days past due",
        EscalationLevel.HOLD:         "Invoice #{invoice_id} — Please contact us today",
    }

    def _format_date(self, dt: datetime) -> str:
        return dt.strftime("%B %d, %Y")

    def compose_email(self, invoice: Invoice) -> dict:
        """Returns dict with 'subject' and 'body' (HTML string)."""
        level = invoice.escalation_level
        subject = self.SUBJECT_TEMPLATES[level].format(
            invoice_id=invoice.invoice_id,
            due_date=self._format_date(invoice.due_date),
            days_overdue=invoice.days_overdue,
        )
        body = self._build_email_body(invoice, level)
        return {"subject": subject, "body": body}

    def _build_email_body(self, invoice: Invoice, level: EscalationLevel) -> str:
        client_name = invoice.client.name.split()[0]  # first name
        contractor  = invoice.contractor_name
        inv_id      = invoice.invoice_id
        amount      = invoice.amount_display
        due_str     = self._format_date(invoice.due_date)
        desc        = invoice.description
        days_over   = invoice.days_overdue

        opening_map = {
            EscalationLevel.REMINDER: (
                f"Hi {client_name},<br><br>"
                f"Hope your project is going well! This is a friendly reminder that "
                f"invoice <strong>#{inv_id}</strong> for <strong>{amount}</strong> "
                f"({desc}) was due on <strong>{due_str}</strong>."
            ),
            EscalationLevel.FOLLOW_UP: (
                f"Hi {client_name},<br><br>"
                f"I wanted to follow up on invoice <strong>#{inv_id}</strong> "
                f"for <strong>{amount}</strong> ({desc}), which was due {due_str}. "
                f"We haven't received payment yet and wanted to make sure everything is in order."
            ),
            EscalationLevel.FINAL_NOTICE: (
                f"Dear {client_name},<br><br>"
                f"This is an important notice regarding invoice <strong>#{inv_id}</strong> "
                f"for <strong>{amount}</strong> ({desc}). "
                f"As of today, this invoice is <strong>{days_over} days past due</strong>. "
                f"We need to resolve this promptly to keep your account in good standing."
            ),
            EscalationLevel.HOLD: (
                f"Dear {client_name},<br><br>"
                f"We have been unable to collect payment for invoice <strong>#{inv_id}</strong> "
                f"totaling <strong>{amount}</strong>. This account requires your immediate attention. "
                f"Please contact us directly to arrange payment or discuss your situation."
            ),
        }

        cta_map = {
            EscalationLevel.REMINDER: (
                "If you've already sent payment, please disregard this message — and thank you!<br><br>"
                "If you have any questions about this invoice, reply to this email and I'll help you right away."
            ),
            EscalationLevel.FOLLOW_UP: (
                "Please arrange payment at your earliest convenience or reply to let us know "
                "if there is an issue we can help resolve. If payment has already been sent, "
                "please share the confirmation so we can update our records."
            ),
            EscalationLevel.FINAL_NOTICE: (
                "Please arrange payment within the next <strong>7 business days</strong>. "
                "If you are experiencing difficulty, contact us immediately — we may be able to arrange "
                "a payment plan. Continued non-payment may result in additional action."
            ),
            EscalationLevel.HOLD: (
                "Please call or email us within <strong>48 hours</strong> to discuss this matter. "
                "Failure to respond may require us to pursue other remedies available to us."
            ),
        }

        html = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: auto;">
        <div style="border-left: 4px solid #F5A623; padding-left: 16px; margin-bottom: 24px;">
            <h2 style="color: #F5A623; margin: 0;">Invoice Follow-Up</h2>
            <p style="margin: 4px 0; font-size: 13px; color: #888;">from {contractor}</p>
        </div>
        <p>{opening_map[level]}</p>
        <table style="background:#f9f9f9; border-radius:8px; padding:16px; width:100%; margin:16px 0;">
            <tr><td style="color:#888; font-size:13px;">Invoice #</td><td><strong>{inv_id}</strong></td></tr>
            <tr><td style="color:#888; font-size:13px;">Amount Due</td><td><strong style="color:#d9534f;">{amount}</strong></td></tr>
            <tr><td style="color:#888; font-size:13px;">Due Date</td><td>{due_str}</td></tr>
            <tr><td style="color:#888; font-size:13px;">Description</td><td>{desc}</td></tr>
        </table>
        <p>{cta_map[level]}</p>
        <hr style="border:none; border-top:1px solid #eee; margin:24px 0;">
        <p style="font-size:12px; color:#aaa;">
            This is an automated billing reminder from {contractor}. 
            To stop receiving these reminders, please reply with "PAID" or contact us directly.<br>
            This message is not a demand for payment from a debt collection agency.
        </p>
        </body></html>
        """
        return html.strip()

    def compose_sms(self, invoice: Invoice) -> str:
        """Returns SMS body (≤160 chars for single segment)."""
        level   = invoice.escalation_level
        inv_id  = invoice.invoice_id
        amount  = invoice.amount_display
        contractor = invoice.contractor_name[:20]

        sms_map = {
            EscalationLevel.REMINDER: (
                f"Hi, this is {contractor}. Friendly reminder: Invoice #{inv_id} "
                f"for {amount} is due. Reply PAID if sent. Thx!"
            ),
            EscalationLevel.FOLLOW_UP: (
                f"{contractor}: Invoice #{inv_id} ({amount}) is overdue. "
                f"Please arrange payment or call us. Reply PAID if settled."
            ),
            EscalationLevel.FINAL_NOTICE: (
                f"FINAL NOTICE from {contractor}: Invoice #{inv_id} ({amount}) "
                f"urgently overdue. Contact us today to avoid further action."
            ),
            EscalationLevel.HOLD: (
                f"{contractor}: Invoice #{inv_id} ({amount}) requires immediate "
                f"attention. Please call us within 48hrs."
            ),
        }
        msg = sms_map[level]
        return msg[:320]  # Twilio concat limit; keep reasonable


# ─────────────────────────────────────────────
# ESCALATION ENGINE
# ─────────────────────────────────────────────

class EscalationEngine:
    """
    Determines the correct escalation level and contact channel
    for each invoice based on days overdue, dispute status, and history.
    """

    def determine_level(self, invoice: Invoice) -> EscalationLevel:
        if invoice.client.dispute_flag:
            log.info(f"[{invoice.invoice_id}] Dispute flag active — holding escalation")
            return EscalationLevel.HOLD

        days = invoice.days_overdue
        for level, (lo, hi) in ESCALATION_THRESHOLDS.items():
            if lo <= days <= hi:
                return level
        return EscalationLevel.HOLD

    def should_contact_now(self) -> bool:
        """Enforce safe contact hours (8AM-8PM UTC as MVP proxy)."""
        hour = datetime.now(timezone.utc).hour
        return CONTACT_HOUR_START <= hour < CONTACT_HOUR_END

    def days_since_last_contact(self, invoice: Invoice) -> int:
        if not invoice.contact_log:
            return 9999
        last_ts = invoice.contact_log[-1]["timestamp"]
        last_dt = datetime.fromisoformat(last_ts)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - last_dt
        return delta.days

    def contact_frequency_ok(self, invoice: Invoice) -> bool:
        """
        Respect contact frequency limits by escalation level.
        Reminder: every 3 days | Follow-up: every 4 days | Final/Hold: every 7 days
        """
        level = invoice.escalation_level
        freq_map = {
            EscalationLevel.REMINDER:     3,
            EscalationLevel.FOLLOW_UP:    4,
            EscalationLevel.FINAL_NOTICE: 7,
            EscalationLevel.HOLD:         7,
        }
        min_days = freq_map.get(level, 7)
        days_since = self.days_since_last_contact(invoice)
        ok = days_since >= min_days
        if not ok:
            log.debug(
                f"[{invoice.invoice_id}] Skipping — contacted {days_since}d ago, "
                f"min interval {min_days}d"
            )
        return ok


# ─────────────────────────────────────────────
# DELIVERY ENGINE
# ─────────────────────────────────────────────

class DeliveryEngine:
    """
    Sends messages via email (SMTP/SendGrid-compatible) and SMS (Twilio).
    Falls back to file-based mock delivery when credentials are absent.
    All sends are logged to memory/invoice_chaser/sent_log.jsonl.
    """

    SENT_LOG = LOG_DIR / "sent_log.jsonl"

    def __init__(self):
        self.smtp_host     = os.getenv("SMTP_HOST", "")
        self.smtp_port     = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user     = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email    = os.getenv("FROM_EMAIL", "billing@yourcompany.com")

        self.twilio_sid    = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.twilio_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from   = os.getenv("TWILIO_FROM_NUMBER", "")

        self.mock_mode = not bool(self.smtp_host and self.smtp_user)
        if self.mock_mode:
            log.warning(
                "DeliveryEngine running in MOCK MODE — "
                "set SMTP_HOST/SMTP_USER/SMTP_PASSWORD env vars for live delivery"
            )

    # ── EMAIL ──────────────────────────────────

    def send_email(self, to_address: str, subject: str, html_body: str,
                   invoice_id: str, contractor_name: str) -> bool:
        if self.mock_mode:
            return self._mock_send("email", to_address, subject, invoice_id)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{contractor_name} Billing <{self.from_email}>"
        msg["To"]      = to_address
        msg["X-Invoice-ID"] = invoice_id
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, [to_address], msg.as_string())
            self._log_sent("email", to_address, subject, invoice_id, True)
            log.info(f"[{invoice_id}] Email sent → {to_address}")
            return True
        except smtplib.SMTPException as exc:
            log.error(f"[{invoice_id}] Email failed → {to_address}: {exc}")
            self._log_sent("email", to_address, subject, invoice_id, False, str(exc))
            return False
        except Exception as exc:
            log.error(f"[{invoice_id}] Unexpected email error: {exc}")
            self._log_sent("email", to_address, subject, invoice_id, False, str(exc))
            return False

    # ── SMS ────────────────────────────────────

    def send_sms(self, to_number: str, body: str, invoice_id: str) -> bool:
        if not to_number or not re.match(r"^\+\d{10,15}$", to_number):
            log.warning(f"[{invoice_id}] Invalid phone number '{to_number}' — skipping SMS")
            return False

        if self.mock_mode or not self.twilio_sid:
            return self._mock_send("sms", to_number, body, invoice_id)

        try:
            # Lazy import so package is optional in email-only deployments
            from twilio.rest import Client as TwilioClient  # type: ignore
            client = TwilioClient(self.twilio_sid, self.twilio_token)
            message = client.messages.create(
                body=body,
                from_=self.twilio_from,
                to=to_number,
            )
            self._log_sent("sms", to_number, body[:50], invoice_id, True, message.sid)
            log.info(f"[{invoice_id}] SMS sent → {to_number} (sid={message.sid})")
            return True
        except ImportError:
            log.warning(f"[{invoice_id}] Twilio not installed — falling back to mock SMS")
            return self._mock_send("sms", to_number, body, invoice_id)
        except Exception as exc:
            log.error(f"[{invoice_id}] SMS failed → {to_number}: {exc}")
            self._log_sent("sms", to_number, body[:50], invoice_id, False, str(exc))
            return False

    # ── HELPERS ────────────────────────────────

    def _mock_send(self, channel: str, destination: str, content: str,
                   invoice_id: str) -> bool:
        mock_path = LOG_DIR / f"mock_{channel}_{invoice_id}.txt"
        mock_path.write_text(
            f"MOCK {channel.upper()} DELIVERY\n"
            f"To: {destination}\n"
            f"Invoice: {invoice_id}\n"
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
            f"Content:\n{content}\n",
            encoding="utf-8",
        )
        self._log_sent(channel, destination, content[:80], invoice_id, True, "MOCK")
        log.info(f"[{invoice_id}] Mock {channel} saved → {mock_path.name}")
        return True

    def _log_sent(self, channel: str, destination: str, content_preview: str,
                  invoice_id: str, success: bool, note: str = ""):
        record = {
            "ts":         datetime.now(timezone.utc).isoformat(),
            "invoice_id": invoice_id,
            "channel":    channel,
            "to":         destination,
            "preview":    content_preview[:80],
            "success":    success,
            "note":       note,
        }
        with open(self.SENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


# ─────────────────────────────────────────────
# REPORT ENGINE
# ─────────────────────────────────────────────

class ReportEngine:
    """
    Generates daily contractor dashboard:
    - Total AR outstanding
    - Overdue breakdown by escalation level
    - Recent contacts sent
    - Paid this week
    """

    REPORT_DIR = LOG_DIR / "reports"

    def __init__(self):
        self.REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, invoices: list[Invoice]) -> dict:
        now        = datetime.now(timezone.utc)
        week_ago   = now - timedelta(days=7)

        total_outstanding  = 0.0
        total_overdue      = 0.0
        paid_this_week     = 0.0
        overdue_by_level   = {lvl.name: {"count": 0, "amount": 0.0} for lvl in EscalationLevel}
        contacts_sent_today = 0

        for inv in invoices:
            if inv.status == InvoiceStatus.PAID:
                if inv.paid_date and inv.paid_date >= week_ago:
                    paid_this_week += inv.amount
                continue

            if inv.status in (InvoiceStatus.WRITTEN_OFF, InvoiceStatus.DISPUTED):
                continue

            total_outstanding += inv.amount

            if inv.is_overdue:
                total_overdue += inv.amount
                lvl_name = inv.escalation_level.name
                overdue_by_level[lvl_name]["count"]  += 1
                overdue_by_level[lvl_name]["amount"] += inv.amount

            # Count today's contacts
            for event in inv.contact_log:
                ts = datetime.fromisoformat(event["timestamp"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if (now - ts).total_seconds() < 86400 and event["success"]:
                    contacts_sent_today += 1

        report = {
            "generated_at":         now.isoformat(),
            "total_outstanding":     round(total_outstanding, 2),
            "total_overdue":         round(total_overdue, 2),
            "paid_this_week":        round(paid_this_week, 2),
            "overdue_by_level":      overdue_by_level,
            "contacts_sent_today":   contacts_sent_today,
            "total_invoices":        len(invoices),
        }

        report_file = self.REPORT_DIR / f"report_{now.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        log.info(f"Report saved → {report_file}")
        return report

    def print_dashboard(self, report: dict):
        w = 58
        sep = "─" * w

        def money(v): return f"${v:,.2f}"
        def pct(a, b): return f"({100*a/b:.1f}%)" if b else ""

        print(f"\n{'═'*w}")
        print(f"  📊  AI INVOICE CHASER — CONTRACTOR DASHBOARD")
        print(f"  Generated: {report['generated_at'][:19]} UTC")
        print(f"{'═'*w}")
        print(f"  Total AR Outstanding : {money(report['total_outstanding'])}")
        print(f"  Overdue (at risk)    : {money(report['total_overdue'])} "
              f"{pct(report['total_overdue'], report['total_outstanding'])}")
        print(f"  Paid This Week       : {money(report['paid_this_week'])}")
        print(f"  Contacts Sent Today  : {report['contacts_sent_today']}")
        print(f"  Total Invoices       : {report['total_invoices']}")
        print(sep)
        print("  Overdue Breakdown:")
        for level, data in report["overdue_by_level"].items():
            if data["count"] > 0:
                bar_len = min(20, int(data["count"] * 3))
                bar = "█" * bar_len
                print(f"    {level:<14} {bar:<20} {data['count']:>3} inv  {money(data['amount'])}")
        print(f"{'═'*w}\n")


# ─────────────────────────────────────────────
# INVOICE PERSISTENCE
# ─────────────────────────────────────────────

class InvoiceStore:
    """
    Simple JSON-file persistence for invoice state.
    Production upgrade: swap for PostgreSQL / SQLite.
    """

    DATA_FILE = LOG_DIR / "invoices.json"

    def save(self, invoices: list[Invoice]):
        def serialize(inv: Invoice) -> dict:
            d = asdict(inv)
            d["status"]           = inv.status.value
            d["escalation_level"] = inv.escalation_level.value
            d["issue_date"]       = inv.issue_date.isoformat()
            d["due_date"]         = inv.due_date.isoformat()
            d["paid_date"]        = inv.paid_date.isoformat() if inv.paid_date else None
            d["client"]["preferred_channel"] = inv.client.preferred_channel.value
            return d

        with open(self.DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([serialize(i) for i in invoices], f, indent=2)
        log.info(f"Saved {len(invoices)} invoices → {self.DATA_FILE}")

    def load(self) -> list[Invoice]:
        if not self.DATA_FILE.exists():
            return []
        with open(self.DATA_FILE, encoding="utf-8") as f:
            raw = json.load(f)

        invoices = []
        for d in raw:
            try:
                c_raw = d["client"]
                client = Client(
                    client_id=c_raw["client_id"],
                    name=c_raw["name"],
                    email=c_raw.get("email"),
                    phone=c_raw.get("phone"),
                    preferred_channel=ContactChannel(c_raw.get("preferred_channel", "email")),
                    dispute_flag=c_raw.get("dispute_flag", False),
                    total_paid_historical=c_raw.get("total_paid_historical", 0.0),
                    avg_days_to_pay=c_raw.get("avg_days_to_pay", 0),
                )
                inv = Invoice(
                    invoice_id=d["invoice_id"],
                    client=client,
                    contractor_name=d["contractor_name"],
                    amount=d["amount"],
                    currency=d.get("currency", "USD"),
                    issue_date=datetime.fromisoformat(d["issue_date"]),
                    due_date=datetime.fromisoformat(d["due_date"]),
                    description=d["description"],
                    status=InvoiceStatus(d["status"]),
                    paid_date=datetime.fromisoformat(d["paid_date"]) if d.get("paid_date") else None,
                    contact_log=d.get("contact_log", []),
                    escalation_level=EscalationLevel(d.get("escalation_level", 1)),
                )
                invoices.append(inv)
            except (KeyError, ValueError) as exc:
                log.error(f"Failed to deserialize invoice: {exc} — skipping")

        log.info(f"Loaded {len(invoices)} invoices from {self.DATA_FILE}")
        return invoices


# ─────────────────────────────────────────────
# CORE ENGINE
# ─────────────────────────────────────────────

class InvoiceChaser:
    """
    Main orchestrator.
    Call .run(invoices) to process all eligible overdue invoices.
    """

    def __init__(self):
        self.escalation  = EscalationEngine()
        self.composer    = MessageComposer()
        self.delivery    = DeliveryEngine()
        self.reporter    = ReportEngine()
        self.store       = InvoiceStore()

    def run(self, invoices: list[Invoice]) -> dict:
        """
        Process all invoices:
        1. Determine escalation level
        2. Check contact eligibility
        3. Compose + send messages
        4. Log all actions
        5. Persist updated state
        6. Return report
        """
        log.info(f"─── InvoiceChaser run started — {len(invoices)} invoices ───")

        if not self.escalation.should_contact_now():
            hour = datetime.now(timezone.utc).hour
            log.warning(
                f"Current hour {hour} UTC is outside safe contact window "
                f"({CONTACT_HOUR_START}:00–{CONTACT_HOUR_END}:00). "
                f"No messages sent this cycle."
            )
            return self.reporter.generate(invoices)

        contacted = 0
        skipped   = 0
        errors    = 0

        for inv in invoices:
            if inv.status in (InvoiceStatus.PAID, InvoiceStatus.WRITTEN_OFF):
                skipped += 1
                continue

            if inv.client.dispute_flag:
                log.info(f"[{inv.invoice_id}] Dispute flag — skipping")
                skipped += 1
                continue

            if not inv.is_overdue:
                log.debug(f"[{inv.invoice_id}] Not yet overdue — skipping")
                skipped += 1
                continue

            # Determine escalation level
            inv.escalation_level = self.escalation.determine_level(inv)
            inv.status = InvoiceStatus.OVERDUE

            # Check frequency gate
            if not self.escalation.contact_frequency_ok(inv):
                skipped += 1
                continue

            # Compose messages
            email_msg = self.composer.compose_email(inv)
            sms_body  = self.composer.compose_sms(inv)

            channel   = inv.client.preferred_channel
            success   = False

            try:
                if channel in (ContactChannel.EMAIL, ContactChannel.BOTH):
                    if inv.client.email:
                        ok = self.delivery.send_email(
                            to_address=inv.client.email,
                            subject=email_msg["subject"],
                            html_body=email_msg["body"],
                            invoice_id=inv.invoice_id,
                            contractor_name=inv.contractor_name,
                        )
                        inv.log_contact(
                            ContactChannel.EMAIL,
                            inv.escalation_level.name,
                            ok,
                            note=email_msg["subject"],
                        )
                        success = success or ok
                    else:
                        log.warning(f"[{inv.invoice_id}] No email on file for {inv.client.name}")

                if channel in (ContactChannel.SMS, ContactChannel.BOTH):
                    if inv.client.phone:
                        ok = self.delivery.send_sms(
                            to_number=inv.client.phone,
                            body=sms_body,
                            invoice_id=inv.invoice_id,
                        )
                        inv.log_contact(
                            ContactChannel.SMS,
                            inv.escalation_level.name,
                            ok,
                            note=sms_body[:60],
                        )
                        success = success or ok
                    else:
                        log.warning(f"[{inv.invoice_id}] No phone on file for {inv.client.name}")

            except Exception as exc:
                log.error(f"[{inv.invoice_id}] Unexpected error during contact: {exc}")
                inv.log_contact(channel, "ERROR", False, str(exc))
                errors += 1
                continue

            if success:
                contacted += 1
            else:
                errors += 1

            # Respect rate limits between sends
            time.sleep(0.5)

        self.store.save(invoices)

        report = self.reporter.generate(invoices)
        log.info(
            f"─── Run complete — contacted={contacted} skipped={skipped} errors={errors} ───"
        )
        return report

    def mark_paid(self, invoices: list[Invoice], invoice_id: str) -> bool:
        """Mark an invoice as paid (call this from your payment webhook)."""
        for inv in invoices:
            if inv.invoice_id == invoice_id:
                inv.status    = InvoiceStatus.PAID
                inv.paid_date = datetime.now(timezone.utc)
                self.store.save(invoices)
                log.info(f"[{invoice_id}] Marked as PAID ✓")
                return True
        log.warning(f"Invoice {invoice_id} not found for mark_paid")
        return False

    def add_invoice(self, invoices: list[Invoice], invoice: Invoice) -> list[Invoice]:
        """Add a new invoice and persist."""
        invoices.append(invoice)
        self.store.save(invoices)
        log.info(f"Invoice {invoice.invoice_id} added for {invoice.client.name}")
        return invoices


# ─────────────────────────────────────────────
# DEMO DATA
# ─────────────────────────────────────────────

def _build_demo_invoices() -> list[Invoice]:
    """Create a realistic set of demo invoices spanning all escalation levels."""
    now = datetime.now(timezone.utc)

    def make_invoice(inv_id, client_name, email, phone, amount,
                     days_overdue, description, channel=ContactChannel.EMAIL,
                     dispute=False, status=InvoiceStatus.OVERDUE):
        due = now - timedelta(days=days_overdue)
        issue = due - timedelta(days=30)
        client = Client(
            client_id=hashlib.md5(client_name.encode()).hexdigest()[:8],
            name=client_name,
            email=email,
            phone=phone,
            preferred_channel=channel,
            dispute_flag=dispute,
        )
        return Invoice(
            invoice_id=inv_id,
            client=client,
            contractor_name="Apex Plumbing & HVAC LLC",
            amount=amount,
            currency="USD",
            issue_date=issue,
            due_date=due,
            description=description,
            status=status,
        )

    invoices = [
        # Reminder tier (1-7 days)
        make_invoice("INV-2401", "Marcus Bellamy",    "marcus@bellamyhomes.com",    "+15554010001", 4_200.00,  3,  "Bathroom rough-in & water heater install"),
        make_invoice("INV-2402", "Sandra Kowalczyk",  "sandra@kowalczykLLC.com",    "+15554010002", 1_850.50,  5,  "Emergency pipe repair — 38 Oak St",       ContactChannel.BOTH),
        # Follow-up tier (8-21 days)
        make_invoice("INV-2390", "Heritage Build Co", "ap@heritagebuild.com",       "+15554010003", 12_400.00, 14, "New construction plumbing — Phase 2",     ContactChannel.BOTH),
        make_invoice("INV-2388", "Ray Morales",       "rmorales@moralesprops.com",  None,           3_600.00,  10, "Boiler replacement & zone valves"),
        # Final notice tier (22-45 days)
        make_invoice("INV-2370", "Greenfield Dev",    "finance@greenfielddev.com",  "+15554010005", 28_750.00, 30, "Commercial HVAC install — Unit B",        ContactChannel.EMAIL),
        make_invoice("INV-2365", "Tommy Vu",          "tommyvu@gmail.com",          "+15554010006", 890.00,    25, "Drain cleaning & camera inspection"),
        # Hold tier (46+ days)
        make_invoice("INV-2310", "Pioneer Rentals",   "billing@pioneerrentals.net", None,           7_500.00,  60, "Full plumbing re-pipe — 4 units",         ContactChannel.EMAIL),
        # Dispute — should be held
        make_invoice("INV-2350", "Clay Whitmore",     "clay@whitmorebuild.com",     "+15554010008", 5_200.00,  18, "Sump pump install & waterproofing",       ContactChannel.BOTH, dispute=True),
        # Already paid — should be skipped
        make_invoice("INV-2200", "Laura Dunne",       "laura@dunnehomes.com",       None,           2_100.00,   0, "Kitchen sink & disposal install",
                     status=InvoiceStatus.PAID),
    ]

    # Mark the paid one properly
    invoices[-1].paid_date = now - timedelta(days=2)
    invoices[-1].status    = InvoiceStatus.PAID

    return invoices


# ─────────────────────────────────────────────
# MAIN ENTRYPOINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "═"*60)
    print("  🔧  AI INVOICE CHASER — Trade Contractor Edition")
    print("  TAD Build Agent | 2026-06-28")
    print("  Mode: DEMO (mock delivery)")
    print("═"*60)

    chaser   = InvoiceChaser()
    reporter = ReportEngine()

    # ── Load or seed invoices ──────────────────
    stored = chaser.store.load()
    if stored:
        invoices = stored
        log.info(f"Loaded {len(invoices)} existing invoices from store")
    else:
        invoices = _build_demo_invoices()
        log.info("No stored invoices found — using demo dataset")
        chaser.store.save(invoices)

    # ── Run the chaser ─────────────────────────
    print("\n[1/3] Running invoice chaser...\n")
    report = chaser.run(invoices)

    # ── Print dashboard ────────────────────────
    print("\n[2/3] Generating dashboard...\n")
    reporter.print_dashboard(report)

    # ── Show sent log summary ──────────────────
    print("[3/3] Recent contact log:\n")
    sent_log = DeliveryEngine.SENT_LOG
    if sent_log.exists():
        lines = sent_log.read_text(encoding="utf-8").strip().splitlines()
        recent = lines[-10:] if len(lines) > 10 else lines
        for line in recent:
            try:
                rec = json.loads(line)
                status_icon = "✅" if rec["success"] else "❌"
                print(
                    f"  {status_icon} [{rec['ts'][:16]}] "
                    f"{rec['channel'].upper():<5} → {rec['to']:<32} "
                    f"inv={rec['invoice_id']}"
                )
            except json.JSONDecodeError:
                pass
    else:
        print("  No sent log found (first run?)")

    print("\n" + "─"*60)
    print("  ✓ Build complete. Next steps:")
    print("    1. Set SMTP_HOST / SMTP_USER / SMTP_PASSWORD env vars for live email")
    print("    2. Set TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER for SMS")
    print("    3. Connect your invoicing source (QuickBooks API, CSV import, webhook)")
    print("    4. Schedule this script via cron or cloud scheduler (once/day at 9AM)")
    print("    5. Wire mark_paid() to your payment processor webhook")
    print("─"*60 + "\n")