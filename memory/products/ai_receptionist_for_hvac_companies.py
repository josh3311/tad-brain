"""
AI Receptionist for HVAC Companies
====================================
Production module: handles inbound calls, classifies intent, routes to
technician / schedules appointment / escalates emergencies.

Integrations (via env vars):
  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
  ANTHROPIC_API_KEY  (Claude for intent / dialogue)
  CALENDLY_API_KEY   (optional — appointment booking)
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS  (email alerts)

Run standalone:
  python ai_receptionist_for_hvac_companies.py

Author : TAD Build Agent
Created: 2026-06-28
"""

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import os
import re
import sys
import json
import time
import logging
import smtplib
import hashlib
import datetime
import threading
import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from enum import Enum

# ---------------------------------------------------------------------------
# Paths & Logging
# ---------------------------------------------------------------------------
MEMORY_DIR = Path("memory/products/hvac_receptionist")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = MEMORY_DIR / "hvac_receptionist.log"
CALL_LOG_FILE = MEMORY_DIR / "call_log.jsonl"
APPOINTMENT_FILE = MEMORY_DIR / "appointments.jsonl"
LEAD_FILE = MEMORY_DIR / "leads.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("hvac_receptionist")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CALENDLY_API_KEY = os.getenv("CALENDLY_API_KEY", "")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8765"))


# ---------------------------------------------------------------------------
# Domain enums & data classes
# ---------------------------------------------------------------------------
class CallIntent(Enum):
    EMERGENCY = "emergency"
    APPOINTMENT_NEW = "appointment_new"
    APPOINTMENT_RESCHEDULE = "appointment_reschedule"
    QUOTE_REQUEST = "quote_request"
    BILLING = "billing"
    EXISTING_JOB_STATUS = "existing_job_status"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


class CallOutcome(Enum):
    EMERGENCY_ESCALATED = "emergency_escalated"
    APPOINTMENT_BOOKED = "appointment_booked"
    LEAD_CAPTURED = "lead_captured"
    TRANSFERRED = "transferred"
    VOICEMAIL = "voicemail"
    RESOLVED = "resolved"
    FAILED = "failed"


@dataclass
class CallerInfo:
    phone: str
    name: str = "Unknown"
    address: str = ""
    system_type: str = ""          # e.g. "central AC", "heat pump", "furnace"
    issue_description: str = ""
    is_existing_customer: bool = False
    customer_id: str = ""


@dataclass
class CallRecord:
    call_sid: str
    caller: CallerInfo
    intent: CallIntent = CallIntent.UNKNOWN
    outcome: CallOutcome = CallOutcome.FAILED
    transcript: List[Dict[str, str]] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    duration_seconds: int = 0
    appointment_id: str = ""
    technician_alerted: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["intent"] = self.intent.value
        d["outcome"] = self.outcome.value
        return d


@dataclass
class Appointment:
    appointment_id: str
    caller: CallerInfo
    proposed_date: str          # ISO 8601
    service_type: str
    priority: str               # "emergency" | "urgent" | "standard"
    technician_id: str = ""
    confirmed: bool = False
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# HVAC domain knowledge
# ---------------------------------------------------------------------------
EMERGENCY_KEYWORDS = [
    "gas leak", "carbon monoxide", "no heat", "freezing", "smoke",
    "burning smell", "sparks", "flooding", "water everywhere",
    "electrical", "not working at all", "completely out", "emergency",
    "urgent", "can't breathe", "dangerous",
]

HVAC_SYSTEM_TYPES = [
    "central air", "central ac", "heat pump", "furnace", "boiler",
    "mini split", "ductless", "package unit", "rooftop unit",
    "geothermal", "radiant heat", "baseboard",
]

BUSINESS_HOURS = {
    "monday": (8, 18),
    "tuesday": (8, 18),
    "wednesday": (8, 18),
    "thursday": (8, 18),
    "friday": (8, 17),
    "saturday": (9, 14),
    "sunday": None,             # closed
}

AFTER_HOURS_SURCHARGE = 150.0   # dollars
EMERGENCY_DISPATCH_FEE = 250.0


def is_business_hours() -> bool:
    """Return True if current time falls within HVAC business hours."""
    now = datetime.datetime.now()
    day_name = now.strftime("%A").lower()
    hours = BUSINESS_HOURS.get(day_name)
    if hours is None:
        return False
    open_h, close_h = hours
    return open_h <= now.hour < close_h


def detect_emergency(text: str) -> bool:
    """Heuristic check — returns True if caller text contains emergency signal."""
    lower = text.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


def extract_system_type(text: str) -> str:
    """Identify HVAC system type from free text."""
    lower = text.lower()
    for sys_type in HVAC_SYSTEM_TYPES:
        if sys_type in lower:
            return sys_type
    return "unknown"


def extract_phone(text: str) -> str:
    """Pull first phone-like number from text."""
    pattern = r"\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
    match = re.search(pattern, text)
    return match.group(0) if match else ""


# ---------------------------------------------------------------------------
# Claude (Anthropic) integration
# ---------------------------------------------------------------------------
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-opus-4-5"
MAX_TOKENS = 800

SYSTEM_PROMPT_RECEPTIONIST = """You are an AI receptionist for an HVAC (heating, ventilation, and air conditioning) company.
Your job is to:
1. Greet callers warmly and professionally
2. Understand why they are calling
3. Collect relevant information (name, address, system type, problem description)
4. Classify their need (emergency, appointment, quote, billing, status check)
5. Guide them to the next step (book appointment, escalate emergency, capture lead)

HVAC context you must know:
- Common systems: central AC, heat pump, furnace, boiler, mini-split
- Emergencies: gas leaks, carbon monoxide, complete heat loss in freezing weather, electrical hazards
- Typical services: annual maintenance, repair, installation, inspection, duct cleaning
- Seasonal peaks: AC season (May-Sept), heating season (Oct-Mar)

Always:
- Be empathetic, especially for emergencies
- Ask one question at a time
- Repeat back key details to confirm accuracy
- Never promise a price — only say a technician will provide a quote
- If caller seems upset, stay calm and offer concrete next steps

Return ONLY valid JSON with these keys:
{
  "reply": "your spoken response to the caller",
  "intent": "emergency|appointment_new|appointment_reschedule|quote_request|billing|existing_job_status|general_inquiry|unknown",
  "collected": {
    "name": "",
    "address": "",
    "system_type": "",
    "issue": "",
    "preferred_date": "",
    "preferred_time": ""
  },
  "ready_to_close": true/false,
  "escalate_now": true/false
}"""


def call_claude(
    conversation: List[Dict[str, str]],
    system_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send conversation to Claude API. Returns parsed JSON from model.
    Falls back gracefully on any error.
    """
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY not set — using mock response")
        return _mock_claude_response(conversation)

    system = system_override or SYSTEM_PROMPT_RECEPTIONIST
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": conversation,
    }).encode("utf-8")

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                outer = json.loads(raw)
                content_text = outer["content"][0]["text"]
                # Strip markdown fences if present
                content_text = re.sub(r"