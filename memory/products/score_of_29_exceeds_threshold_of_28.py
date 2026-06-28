"""
TradeCollect AI — Invoice Collection Engine for Trade Contractors
=================================================================
Production module: score_of_29_exceeds_threshold_of_28.py
Product path:      memory/products/score_of_29_exceeds_threshold_of_28.py

Business problem:
    Trade contractors (plumbers, electricians, HVAC, roofers, painters) lose
    an estimated 5–8 % of annual revenue to unpaid or severely late invoices.
    No dominant AI solution owns this niche.  TradeCollect AI automates the
    entire collection workflow:

        1.  Ingest unpaid invoices (CSV / dict list)
        2.  Score each debtor's payment-risk (ML-lite heuristic model)
        3.  Generate a personalised, escalating chase sequence
            (friendly reminder → firm notice → final demand → referral)
        4.  Dispatch messages via email (SMTP) or SMS (Twilio stub)
        5.  Log every action and outcome to memory/trade_collect/
        6.  Produce a daily collection summary report (JSON + human-readable)

CEO: Joshua Abraham  |  TAD Build Agent  |  2026-06-28
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import random
import smtplib
import string
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Directory bootstrap
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent  # …/memory/products/ → project root
LOG_DIR = BASE_DIR / "memory" / "trade_collect"
LOG_DIR.mkdir(parents=True, exist_ok=True)

PRODUCTS_DIR = BASE_DIR / "memory" / "products"
PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_log_file = LOG_DIR / f"trade_collect_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(_log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("TradeCollect")


# ---------------------------------------------------------------------------
# Enums & constants
# ---------------------------------------------------------------------------
class CollectionStage(str, Enum):
    FRIENDLY = "friendly_reminder"
    FIRM     = "firm_notice"
    FINAL    = "final_demand"
    REFERRAL = "referral_agency"
    PAID     = "paid"
    DISPUTED = "disputed"


STAGE_DAYS: Dict[CollectionStage, int] = {
    CollectionStage.FRIENDLY:  7,
    CollectionStage.FIRM:     14,
    CollectionStage.FINAL:    21,
    CollectionStage.REFERRAL: 30,
}

RISK_THRESHOLDS = {
    "low":    (0.00, 0.35),
    "medium": (0.35, 0.65),
    "high":   (0.65, 1.00),
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class Invoice:
    invoice_id:     str
    client_name:    str
    client_email:   str
    client_phone:   str
    amount_due:     float
    issue_date:     str           # ISO-8601
    due_date:       str           # ISO-8601
    trade_type:     str           # e.g. plumbing, electrical
    notes:          str = ""
    # Runtime fields (populated by engine)
    days_overdue:   int = 0
    risk_score:     float = 0.0
    risk_label:     str = "unknown"
    stage:          CollectionStage = CollectionStage.FRIENDLY
    contact_log:    List[Dict] = field(default_factory=list)
    paid_date:      Optional[str] = None
    disputed:       bool = False

    @property
    def uid(self) -> str:
        """Stable short UID for logging."""
        return hashlib.md5(self.invoice_id.encode()).hexdigest()[:8].upper()

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["stage"] = self.stage.value
        return d


# ---------------------------------------------------------------------------
# Risk scorer  (heuristic model — no external ML dependency)
# ---------------------------------------------------------------------------
class RiskScorer:
    """
    Scores 0–1 (higher = more likely to remain unpaid).
    Factors:
      - Days overdue               (weight 0.40)
      - Invoice amount bracket     (weight 0.25)  large bills → higher risk
      - Prior contact attempts     (weight 0.20)  more attempts → higher risk
      - Trade type risk profile    (weight 0.15)
    """

    TRADE_RISK: Dict[str, float] = {
        "roofing":      0.72,
        "landscaping":  0.65,
        "painting":     0.60,
        "hvac":         0.55,
        "electrical":   0.45,
        "plumbing":     0.42,
        "carpentry":    0.50,
        "general":      0.55,
    }

    def score(self, inv: Invoice) -> Tuple[float, str]:
        # --- days overdue factor ---
        if inv.days_overdue <= 0:
            day_factor = 0.0
        elif inv.days_overdue <= 7:
            day_factor = 0.15
        elif inv.days_overdue <= 14:
            day_factor = 0.35
        elif inv.days_overdue <= 30:
            day_factor = 0.60
        elif inv.days_overdue <= 60:
            day_factor = 0.80
        else:
            day_factor = 1.00

        # --- amount factor ---
        if inv.amount_due < 500:
            amt_factor = 0.20
        elif inv.amount_due < 2_000:
            amt_factor = 0.40
        elif inv.amount_due < 10_000:
            amt_factor = 0.65
        else:
            amt_factor = 0.90

        # --- prior contact factor ---
        attempts = len(inv.contact_log)
        contact_factor = min(1.0, attempts / 5)

        # --- trade type factor ---
        trade_key = inv.trade_type.lower().strip()
        trade_factor = self.TRADE_RISK.get(trade_key, 0.55)

        raw = (
            0.40 * day_factor
            + 0.25 * amt_factor
            + 0.20 * contact_factor
            + 0.15 * trade_factor
        )
        score = max(0.0, min(1.0, raw))

        label = "low"
        for lbl, (lo, hi) in RISK_THRESHOLDS.items():
            if lo <= score < hi:
                label = lbl
                break

        return round(score, 4), label


# ---------------------------------------------------------------------------
# Message generator
# ---------------------------------------------------------------------------
class MessageGenerator:
    """
    Generates stage-appropriate, personalised collection messages.
    No LLM dependency — uses curated templates with variable substitution.
    """

    TEMPLATES: Dict[CollectionStage, Dict[str, str]] = {
        CollectionStage.FRIENDLY: {
            "subject": "Friendly Reminder: Invoice #{invoice_id} — {amount_due_fmt} Due",
            "body": (
                "Hi {client_name},\n\n"
                "I hope everything is going well!  This is a quick, friendly reminder "
                "that Invoice #{invoice_id} for {amount_due_fmt} was due on {due_date}.\n\n"
                "If you've already sent payment, please disregard this message.  "
                "Otherwise, we'd appreciate settlement at your earliest convenience.\n\n"
                "Payment details:\n"
                "  Invoice:  #{invoice_id}\n"
                "  Amount:   {amount_due_fmt}\n"
                "  Due date: {due_date}\n\n"
                "Feel free to reply to this message if you have any questions.\n\n"
                "Thanks so much for your business!\n\n{sender_name}\n{trade_type} Services"
            ),
        },
        CollectionStage.FIRM: {
            "subject": "OVERDUE NOTICE: Invoice #{invoice_id} — {amount_due_fmt}",
            "body": (
                "Dear {client_name},\n\n"
                "Our records show that Invoice #{invoice_id} for {amount_due_fmt}, "
                "which was due on {due_date}, remains unpaid.  This is now "
                "{days_overdue} days overdue.\n\n"
                "Please arrange payment immediately to avoid further action.  "
                "If there is a dispute or difficulty, please contact us today so "
                "we can work towards a resolution.\n\n"
                "Invoice reference: #{invoice_id}\n"
                "Outstanding balance: {amount_due_fmt}\n"
                "Days overdue: {days_overdue}\n\n"
                "Regards,\n{sender_name}\n{trade_type} Services"
            ),
        },
        CollectionStage.FINAL: {
            "subject": "FINAL DEMAND: Invoice #{invoice_id} — Immediate Action Required",
            "body": (
                "Dear {client_name},\n\n"
                "Despite previous reminders, Invoice #{invoice_id} for {amount_due_fmt} "
                "remains unpaid after {days_overdue} days.\n\n"
                "THIS IS OUR FINAL NOTICE.  If full payment is not received within "
                "7 days, we will have no choice but to refer this debt to a "
                "collection agency and/or pursue legal remedies, which may result in "
                "additional costs being added to the outstanding balance.\n\n"
                "To avoid this outcome, please make payment immediately:\n"
                "  Amount owed: {amount_due_fmt}\n"
                "  Reference:   Invoice #{invoice_id}\n\n"
                "Sincerely,\n{sender_name}\n{trade_type} Services"
            ),
        },
        CollectionStage.REFERRAL: {
            "subject": "Debt Referral Notice: Invoice #{invoice_id}",
            "body": (
                "Dear {client_name},\n\n"
                "As you have not responded to our previous notices regarding "
                "Invoice #{invoice_id} for {amount_due_fmt} ({days_overdue} days overdue), "
                "your account has been referred to our collections partner.\n\n"
                "You will be contacted separately.  This referral may affect your "
                "credit standing.  To resolve this directly with us, you must make "
                "full payment within 48 hours.\n\n"
                "{sender_name}\n{trade_type} Services"
            ),
        },
    }

    def __init__(self, sender_name: str = "TradeCollect Services"):
        self.sender_name = sender_name

    def generate(self, inv: Invoice) -> Dict[str, str]:
        template = self.TEMPLATES.get(inv.stage)
        if not template:
            return {"subject": "", "body": ""}

        ctx = {
            "invoice_id":     inv.invoice_id,
            "client_name":    inv.client_name,
            "amount_due_fmt": f"${inv.amount_due:,.2f}",
            "due_date":       inv.due_date,
            "days_overdue":   inv.days_overdue,
            "sender_name":    self.sender_name,
            "trade_type":     inv.trade_type.capitalize(),
        }

        return {
            "subject": template["subject"].format(**ctx),
            "body":    template["body"].format(**ctx),
        }


# ---------------------------------------------------------------------------
# Dispatcher (email + SMS stub)
# ---------------------------------------------------------------------------
class Dispatcher:
    """
    Sends messages via SMTP email.  SMS is stubbed (Twilio integration point).
    Set env vars to enable real email:
        TC_SMTP_HOST, TC_SMTP_PORT, TC_SMTP_USER, TC_SMTP_PASS, TC_FROM_EMAIL
    """

    def __init__(self):
        self.smtp_host = os.getenv("TC_SMTP_HOST", "")
        self.smtp_port = int(os.getenv("TC_SMTP_PORT", "587"))
        self.smtp_user = os.getenv("TC_SMTP_USER", "")
        self.smtp_pass = os.getenv("TC_SMTP_PASS", "")
        self.from_email = os.getenv("TC_FROM_EMAIL", "noreply@tradecollect.ai")
        self.dry_run = not bool(self.smtp_host and self.smtp_user and self.smtp_pass)

        if self.dry_run:
            logger.info("Dispatcher: DRY-RUN mode (no SMTP credentials in env)")

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY-RUN] EMAIL → {to_email} | Subject: {subject[:60]}")
            return True

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = self.from_email
            msg["To"]      = to_email
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.sendmail(self.from_email, [to_email], msg.as_string())

            logger.info(f"EMAIL SENT → {to_email} | {subject[:60]}")
            return True

        except smtplib.SMTPException as exc:
            logger.error(f"SMTP error sending to {to_email}: {exc}")
            return False
        except OSError as exc:
            logger.error(f"Network error sending to {to_email}: {exc}")
            return False

    def send_sms(self, to_phone: str, body: str) -> bool:
        """
        Twilio integration stub.
        Install twilio SDK and set TC_TWILIO_SID / TC_TWILIO_TOKEN / TC_FROM_PHONE
        to enable.
        """
        twilio_sid   = os.getenv("TC_TWILIO_SID", "")
        twilio_token = os.getenv("TC_TWILIO_TOKEN", "")
        from_phone   = os.getenv("TC_FROM_PHONE", "")

        if not (twilio_sid and twilio_token and from_phone):
            logger.info(f"[DRY-RUN] SMS → {to_phone} | {body[:60]}")
            return True

        try:
            from twilio.rest import Client  # type: ignore
            client = Client(twilio_sid, twilio_token)
            message = client.messages.create(
                body=body,
                from_=from_phone,
                to=to_phone,
            )
            logger.info(f"SMS SENT → {to_phone} | SID: {message.sid}")
            return True
        except ImportError:
            logger.warning("Twilio SDK not installed — SMS skipped")
            return False
        except Exception as exc:
            logger.error(f"Twilio error sending to {to_phone}: {exc}")
            return False


# ---------------------------------------------------------------------------
# Collection engine
# ---------------------------------------------------------------------------
class CollectionEngine:
    """
    Orchestrates the full collection workflow for a batch of invoices.
    """

    def __init__(
        self,
        sender_name: str = "TradeCollect Services",
        enable_sms:  bool = False,
    ):
        self.scorer    = RiskScorer()
        self.generator = MessageGenerator(sender_name=sender_name)
        self.dispatcher = Dispatcher()
        self.enable_sms = enable_sms
        self.results: List[Dict] = []

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def load_from_csv(self, filepath: str | Path) -> List[Invoice]:
        """Load invoices from a CSV file.  Required columns documented below."""
        invoices: List[Invoice] = []
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")

        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader, start=2):
                try:
                    inv = Invoice(
                        invoice_id=   row["invoice_id"].strip(),
                        client_name=  row["client_name"].strip(),
                        client_email= row["client_email"].strip(),
                        client_phone= row.get("client_phone", "").strip(),
                        amount_due=   float(row["amount_due"]),
                        issue_date=   row["issue_date"].strip(),
                        due_date=     row["due_date"].strip(),
                        trade_type=   row.get("trade_type", "general").strip(),
                        notes=        row.get("notes", "").strip(),
                    )
                    invoices.append(inv)
                except (KeyError, ValueError) as exc:
                    logger.warning(f"CSV row {i} skipped — {exc}")

        logger.info(f"Loaded {len(invoices)} invoices from {path.name}")
        return invoices

    def load_from_list(self, data: List[Dict]) -> List[Invoice]:
        """Load invoices from a list of dicts (e.g. from a database query)."""
        invoices: List[Invoice] = []
        for i, row in enumerate(data):
            try:
                inv = Invoice(
                    invoice_id=   str(row["invoice_id"]),
                    client_name=  row["client_name"],
                    client_email= row["client_email"],
                    client_phone= row.get("client_phone", ""),
                    amount_due=   float(row["amount_due"]),
                    issue_date=   row["issue_date"],
                    due_date=     row["due_date"],
                    trade_type=   row.get("trade_type", "general"),
                    notes=        row.get("notes", ""),
                )
                invoices.append(inv)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(f"Dict row {i} skipped — {exc}")

        logger.info(f"Loaded {len(invoices)} invoices from dict list")
        return invoices

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------
    def _calculate_days_overdue(self, inv: Invoice) -> int:
        try:
            due = datetime.fromisoformat(inv.due_date)
            delta = (datetime.now() - due).days
            return max(0, delta)
        except ValueError:
            logger.warning(f"Invoice {inv.invoice_id}: bad due_date '{inv.due_date}'")
            return 0

    def _determine_stage(self, inv: Invoice) -> CollectionStage:
        """Map days overdue → collection stage."""
        d = inv.days_overdue
        if d == 0:
            return CollectionStage.FRIENDLY
        if d <= STAGE_DAYS[CollectionStage.FRIENDLY]:
            return CollectionStage.FRIENDLY
        if d <= STAGE_DAYS[CollectionStage.FIRM]:
            return CollectionStage.FIRM
        if d <= STAGE_DAYS[CollectionStage.FINAL]:
            return CollectionStage.FINAL
        return CollectionStage.REFERRAL

    def process_invoice(self, inv: Invoice) -> Dict[str, Any]:
        """Full pipeline for a single invoice."""
        result: Dict[str, Any] = {
            "invoice_id": inv.invoice_id,
            "uid":        inv.uid,
            "client":     inv.client_name,
            "amount":     inv.amount_due,
            "status":     "processed",
            "actions":    [],
            "errors":     [],
        }

        # Skip if already resolved
        if inv.stage in (CollectionStage.PAID, CollectionStage.DISPUTED):
            result["status"] = inv.stage.value
            logger.info(f"Invoice {inv.uid} already {inv.stage.value} — skipped")
            return result

        # 1. Compute days overdue
        inv.days_overdue = self._calculate_days_overdue(inv)

        # 2. Risk scoring
        inv.risk_score, inv.risk_label = self.scorer.score(inv)

        # 3. Stage determination
        inv.stage = self._determine_stage(inv)

        logger.info(
            f"Invoice {inv.uid} | {inv.client_name} | ${inv.amount_due:,.2f} | "
            f"{inv.days_overdue}d overdue | risk={inv.risk_label}({inv.risk_score}) | "
            f"stage={inv.stage.value}"
        )

        # 4. Generate message
        msg = self.generator.generate(inv)
        result["message_subject"] = msg["subject"]

        # 5. Dispatch email
        email_ok = self.dispatcher.send_email(
            to_email=inv.client_email,
            subject=msg["subject"],
            body=msg["body"],
        )
        action: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "channel":   "email",
            "stage":     inv.stage.value,
            "success":   email_ok,
        }
        inv.contact_log.append(action)
        result["actions"].append(action)

        if not email_ok:
            result["errors"].append(f"Email delivery failed to {inv.client_email}")

        # 6. SMS for high-risk final/referral stage
        if (
            self.enable_sms
            and inv.client_phone
            and inv.risk_label == "high"
            and inv.stage in (CollectionStage.FINAL, CollectionStage.REFERRAL)
        ):
            sms_body = (
                f"URGENT — Invoice #{inv.invoice_id} (${inv.amount_due:,.2f}) is "
                f"{inv.days_overdue} days overdue.  Please contact us immediately."
            )
            sms_ok = self.dispatcher.send_sms(inv.client_phone, sms_body)
            sms_action: Dict[str, Any] = {
                "timestamp": datetime.now().isoformat(),
                "channel":   "sms",
                "stage":     inv.stage.value,
                "success":   sms_ok,
            }
            inv.contact_log.append(sms_action)
            result["actions"].append(sms_action)

        result["risk_score"] = inv.risk_score
        result["risk_label"] = inv.risk_label
        result["stage"]      = inv.stage.value
        result["days_overdue"] = inv.days_overdue
        return result

    def run_batch(self, invoices: List[Invoice]) -> "CollectionReport":
        """Process all invoices and produce a CollectionReport."""
        logger.info(f"=== TradeCollect batch starting: {len(invoices)} invoices ===")
        start = time.time()
        results: List[Dict] = []

        for inv in invoices:
            try:
                res = self.process_invoice(inv)
                results.append(res)
            except Exception as exc:
                logger.error(f"Unexpected error on invoice {inv.invoice_id}: {exc}")
                results.append({
                    "invoice_id": inv.invoice_id,
                    "status":     "error",
                    "error":      str(exc),
                })

        elapsed = round(time.time() - start, 2)
        report = CollectionReport(results=results, invoices=invoices, elapsed=elapsed)
        report.save(LOG_DIR)
        logger.info(f"=== Batch complete in {elapsed}s — see {LOG_DIR} ===")
        return report


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
class CollectionReport:
    def __init__(
        self,
        results:  List[Dict],
        invoices: List[Invoice],
        elapsed:  float,
    ):
        self.results  = results
        self.invoices = invoices
        self.elapsed  = elapsed
        self.generated_at = datetime.now().isoformat()

    # ------------------------------------------------------------------
    def _summary_stats(self) -> Dict[str, Any]:
        total_count  = len(self.results)
        total_value  = sum(r.get("amount", 0) for r in self.results)
        by_stage:    Dict[str, int]   = {}
        by_risk:     Dict[str, int]   = {}
        by_risk_val: Dict[str, float] = {}
        errors       = 0

        for r in self.results:
            stage = r.get("stage", "unknown")
            risk  = r.get("risk_label", "unknown")
            amt   = r.get("amount", 0.0)

            by_stage[stage] = by_stage.get(stage, 0) + 1
            by_risk[risk]   = by_risk.get(risk, 0) + 1
            by_risk_val[risk] = by_risk_val.get(risk, 0.0) + amt
            if r.get("errors"):
                errors += 1

        return {
            "total_invoices":       total_count,
            "total_outstanding":    round(total_value, 2),
            "by_collection_stage":  by_stage,
            "by_risk_level":        by_risk,
            "outstanding_by_risk":  {k: round(v, 2) for k, v in by_risk_val.items()},
            "delivery_errors":      errors,
            "processing_seconds":   self.elapsed,
        }

    # ------------------------------------------------------------------
    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # JSON report
        payload = {
            "generated_at": self.generated_at,
            "summary":      self._summary_stats(),
            "results":      self.results,
        }
        json_path = directory / f"report_{timestamp}.json"
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        logger.info(f"JSON report saved → {json_path}")

        # Human-readable summary
        stats = self._summary_stats()
        txt_path = directory / f"report_{timestamp}.txt"
        lines = [
            "=" * 60,
            "  TradeCollect AI — Daily Collection Report",
            f"  Generated: {self.generated_at}",
            "=" * 60,
            f"  Total invoices processed : {stats['total_invoices']}",
            f"  Total outstanding value  : ${stats['total_outstanding']:,.2f}",
            f"  Delivery errors          : {stats['delivery_errors']}",
            f"  Processing time          : {stats['processing_seconds']}s",
            "",
            "  INVOICES BY COLLECTION STAGE",
            "  " + "-" * 36,
        ]
        for stage, count in stats["by_collection_stage"].items():
            lines.append(f"    {stage:<22} {count:>4} invoice(s)")

        lines += [
            "",
            "  OUTSTANDING BY RISK LEVEL",
            "  " + "-" * 36,
        ]
        for risk in ("high", "medium", "low", "unknown"):
            count = stats["by_risk_level"].get(risk, 0)
            value = stats["outstanding_by_risk"].get(risk, 0.0)
            lines.append(f"    {risk:<10} {count:>3} invoice(s)   ${value:>12,.2f}")

        lines += ["", "=" * 60]
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Text report saved → {txt_path}")

    # ------------------------------------------------------------------
    def print_summary(self) -> None:
        stats = self._summary_stats()
        print("\n" + "=" * 60)
        print("  TradeCollect AI — Batch Summary")
        print("=" * 60)
        print(f"  Invoices processed : {stats['total_invoices']}")
        print(f"  Total outstanding  : ${stats['total_outstanding']:,.2f}")
        print(f"  Delivery errors    : {stats['delivery_errors']}")
        print(f"  Time elapsed       : {stats['processing_seconds']}s")
        print("\n  Stage breakdown:")
        for stage, count in stats["by_collection_stage"].items():
            print(f"    {stage:<22} {count}")
        print("\n  Risk breakdown:")
        for risk in ("high", "medium", "low", "unknown"):
            count = stats["by_risk_level"].get(risk, 0)
            value = stats["outstanding_by_risk"].get(risk, 0.0)
            print(f"    {risk:<10} {count:>3} invoice(s)   ${value:>12,.2f}")
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Sample data generator (for demo / self-test)
# ---------------------------------------------------------------------------
def _generate_demo_invoices(n: int = 12) -> List[Dict]:
    """Generate realistic-looking demo invoices for testing."""
    trades = ["plumbing", "electrical", "hvac", "roofing", "painting",
              "carpentry", "landscaping", "general"]
    first  = ["James","Maria","Chen","David","Sarah","Robert","Aisha","Tom"]
    last   = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller"]
    today  = datetime.now()

    records = []
    for i in range(1, n + 1):
        overdue_days = random.choice([0, 5, 9, 15, 22, 35, 55, 70])
        due = today - timedelta(days=overdue_days)
        issue = due - timedelta(days=30)
        name = f"{random.choice(first)} {random.choice(last)}"
        safe_name = name.lower().replace(" ", ".")
        records.append({
            "invoice_id":   f"TC-{1000+i}",
            "client_name":  name,
            "client_email": f"{safe_name}@example.com",
            "client_phone": f"+1555{random.randint(1000000,9999999)}",
            "amount_due":   round(random.uniform(250, 18_000), 2),
            "issue_date":   issue.date().isoformat(),
            "due_date":     due.date().isoformat(),
            "trade_type":   random.choice(trades),
            "notes":        "",
        })
    return records


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("TradeCollect AI — starting standalone demo run")

    # Build engine
    engine = CollectionEngine(
        sender_name="Joshua's Trade Services",
        enable_sms=True,
    )

    # Load demo invoices
    demo_data  = _generate_demo_invoices(n=15)
    invoices   = engine.load_from_list(demo_data)

    # Run collection batch
    report = engine.run_batch(invoices)

    # Print human-readable summary
    report.print_summary()

    # Persist a copy of the processed invoice data
    output_path = LOG_DIR / f"invoices_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump([inv.to_dict() for inv in invoices], fh, indent=2)
    logger.info(f"Invoice state saved → {output_path}")

    # Final health check
    errors = sum(1 for r in report.results if r.get("errors"))
    if errors:
        logger.warning(f"{errors} invoice(s) had delivery errors — check SMTP config")
    else:
        logger.info("All messages dispatched without errors")


if __name__ == "__main__":
    main()