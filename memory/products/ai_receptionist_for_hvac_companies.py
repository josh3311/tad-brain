"""
AI Receptionist for HVAC Companies
====================================
Production module: handles inbound call intake, triage, scheduling,
emergency escalation, and CRM logging for HVAC businesses.

Architecture:
  - HVACReceptionist      : core orchestrator
  - CallSession           : represents one inbound call
  - AppointmentScheduler  : slot management + confirmation
  - EmergencyEscalator    : 24/7 urgent-issue routing
  - TwilioAdapter         : thin wrapper around Twilio REST
  - ClaudeAdapter         : LLM intent + entity extraction
  - LogStore              : append-only JSONL log to memory/

Standalone demo: python ai_receptionist_for_hvac_companies.py
"""

import os
import re
import sys
import json
import uuid
import logging
import datetime
import textwrap
import traceback
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field, asdict

# ──────────────────────────────────────────────
# Logging bootstrap  (memory/ folder)
# ──────────────────────────────────────────────
MEMORY_DIR = Path(__file__).parent / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = MEMORY_DIR / "hvac_receptionist.log"
CALLS_LOG = MEMORY_DIR / "hvac_calls.jsonl"
APPTS_LOG = MEMORY_DIR / "hvac_appointments.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("hvac_receptionist")


# ──────────────────────────────────────────────
# Enums & constants
# ──────────────────────────────────────────────
class CallIntent(str, Enum):
    NEW_APPOINTMENT   = "new_appointment"
    RESCHEDULE        = "reschedule"
    CANCEL            = "cancel"
    EMERGENCY         = "emergency"
    BILLING           = "billing"
    STATUS_CHECK      = "status_check"
    GENERAL_INQUIRY   = "general_inquiry"
    UNKNOWN           = "unknown"


class Priority(str, Enum):
    EMERGENCY = "emergency"   # no heat/AC in extreme weather, gas leak, flooding
    HIGH      = "high"        # system completely down, elderly/infant in home
    MEDIUM    = "medium"      # system degraded, noise, efficiency concerns
    LOW       = "low"         # maintenance, filter change, annual tune-up


EMERGENCY_KEYWORDS = [
    "gas leak", "carbon monoxide", "co detector", "flooding", "water damage",
    "no heat", "no ac", "not working", "completely out", "dangerous",
    "fire", "smoke", "freezing", "burning smell", "sparks",
]

SYSTEM_TYPES = [
    "central air", "heat pump", "furnace", "boiler", "mini split",
    "geothermal", "ductless", "packaged unit", "rooftop unit", "vrf",
    "radiant heat", "baseboard heat", "window unit",
]

BUSINESS_HOURS = {
    0: (8, 18),   # Monday    08:00 – 18:00
    1: (8, 18),   # Tuesday
    2: (8, 18),   # Wednesday
    3: (8, 18),   # Thursday
    4: (8, 17),   # Friday    08:00 – 17:00
    5: (9, 14),   # Saturday  09:00 – 14:00
    6: None,      # Sunday    closed (emergency only)
}

AFTER_HOURS_MESSAGE = (
    "Our office is currently closed. For HVAC emergencies — no heat, no air, "
    "gas smell, or carbon monoxide — please press 1 to reach our on-call technician. "
    "For non-emergency service, please leave your name and number and we'll call "
    "you first thing when we open."
)


# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────
@dataclass
class CustomerInfo:
    name:         str = ""
    phone:        str = ""
    address:      str = ""
    email:        str = ""
    system_type:  str = ""
    system_age:   Optional[int] = None   # years
    last_service: Optional[str] = None   # ISO date


@dataclass
class CallSession:
    session_id:    str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at:    str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    ended_at:      Optional[str] = None
    caller_number: str = ""
    intent:        CallIntent = CallIntent.UNKNOWN
    priority:      Priority   = Priority.LOW
    customer:      CustomerInfo = field(default_factory=CustomerInfo)
    transcript:    List[Dict[str, str]] = field(default_factory=list)
    resolution:    str = ""
    appointment_id: Optional[str] = None
    escalated:     bool = False
    sentiment:     str = "neutral"   # positive | neutral | frustrated | distressed


@dataclass
class Appointment:
    appointment_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id:     str = ""
    created_at:     str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    customer:       CustomerInfo = field(default_factory=CustomerInfo)
    slot_date:      str = ""   # YYYY-MM-DD
    slot_time:      str = ""   # HH:MM
    job_type:       str = ""
    priority:       Priority = Priority.LOW
    technician:     str = ""
    confirmed:      bool = False
    notes:          str = ""


# ──────────────────────────────────────────────
# LogStore — thread-safe JSONL append
# ──────────────────────────────────────────────
class LogStore:
    """Append-only JSONL log; each record is one JSON line."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: Dict[str, Any]) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:
            logger.error("LogStore write error %s: %s", self.path, exc)

    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records


call_store = LogStore(CALLS_LOG)
appt_store = LogStore(APPTS_LOG)


# ──────────────────────────────────────────────
# TwilioAdapter — real Twilio or stub
# ──────────────────────────────────────────────
class TwilioAdapter:
    """
    Wraps Twilio REST API.
    Falls back to stub mode when credentials are absent so the module
    can be demoed without real accounts.
    """

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token  = os.getenv("TWILIO_AUTH_TOKEN",  "")
        self.from_number = os.getenv("TWILIO_FROM_NUMBER", "+15550000000")
        self._client     = None
        self._stub_mode  = not (self.account_sid and self.auth_token)

        if not self._stub_mode:
            try:
                from twilio.rest import Client  # type: ignore
                self._client = Client(self.account_sid, self.auth_token)
                logger.info("TwilioAdapter: live mode")
            except ImportError:
                logger.warning("twilio package not installed — falling back to stub")
                self._stub_mode = True
        else:
            logger.info("TwilioAdapter: stub mode (no credentials)")

    def send_sms(self, to: str, body: str) -> str:
        """Returns SID or stub ID."""
        if self._stub_mode:
            sid = f"STUB_{uuid.uuid4().hex[:12].upper()}"
            logger.info("[STUB SMS] to=%s | %s", to, body[:80])
            return sid
        try:
            msg = self._client.messages.create(
                body=body,
                from_=self.from_number,
                to=to,
            )
            logger.info("SMS sent to %s | SID=%s", to, msg.sid)
            return msg.sid
        except Exception as exc:
            logger.error("SMS failed to %s: %s", to, exc)
            return ""

    def make_call(self, to: str, twiml_url: str) -> str:
        """Initiates an outbound call; returns call SID."""
        if self._stub_mode:
            sid = f"STUB_CALL_{uuid.uuid4().hex[:8].upper()}"
            logger.info("[STUB CALL] to=%s url=%s", to, twiml_url)
            return sid
        try:
            call = self._client.calls.create(
                url=twiml_url,
                to=to,
                from_=self.from_number,
            )
            logger.info("Call initiated to %s | SID=%s", to, call.sid)
            return call.sid
        except Exception as exc:
            logger.error("Call failed to %s: %s", to, exc)
            return ""

    def generate_twiml_response(self, message: str, gather: bool = True) -> str:
        """Returns a TwiML XML string for a voice response."""
        safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        gather_block = ""
        if gather:
            gather_block = (
                '<Gather input="speech dtmf" timeout="5" action="/handle-input">'
                f"<Say>{safe}</Say>"
                "</Gather>"
            )
        else:
            gather_block = f"<Say>{safe}</Say>"

        return f'<?xml version="1.0" encoding="UTF-8"?><Response>{gather_block}</Response>'


# ──────────────────────────────────────────────
# ClaudeAdapter — LLM intent & entity extraction
# ──────────────────────────────────────────────
class ClaudeAdapter:
    """
    Uses Anthropic Claude to extract intent, entities, and sentiment from
    caller speech.  Falls back to rule-based extraction when the API key
    is absent or a network error occurs.
    """

    SYSTEM_PROMPT = textwrap.dedent("""
        You are an AI intake specialist for an HVAC company. Your job is to:
        1. Identify the caller's intent (new_appointment, reschedule, cancel,
           emergency, billing, status_check, general_inquiry, unknown).
        2. Extract structured entities: name, address, phone, email,
           system_type, system_age, issue_description.
        3. Assess urgency: emergency | high | medium | low.
        4. Assess sentiment: positive | neutral | frustrated | distressed.
        5. Draft a short, empathetic response to say back to the caller.

        Always respond with valid JSON only. Schema:
        {
          "intent": "<intent>",
          "priority": "<priority>",
          "sentiment": "<sentiment>",
          "entities": {
            "name": "", "address": "", "phone": "", "email": "",
            "system_type": "", "system_age": null, "issue_description": ""
          },
          "response_text": "<what the AI receptionist should say next>"
        }
    """).strip()

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client = None
        self._stub_mode = not self.api_key

        if not self._stub_mode:
            try:
                import anthropic  # type: ignore
                self._client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("ClaudeAdapter: live mode")
            except ImportError:
                logger.warning("anthropic package not installed — stub mode")
                self._stub_mode = True
        else:
            logger.info("ClaudeAdapter: stub mode (no API key)")

    def analyze(self, caller_text: str, history: List[Dict] = None) -> Dict[str, Any]:
        """Returns structured analysis dict."""
        if self._stub_mode:
            return self._rule_based_fallback(caller_text)
        try:
            messages = []
            if history:
                for turn in history[-6:]:   # last 3 exchanges
                    messages.append({"role": turn["role"], "content": turn["content"]})
            messages.append({"role": "user", "content": caller_text})

            resp = self._client.messages.create(
                model="claude-opus-4-5",
                max_tokens=512,
                system=self.SYSTEM_PROMPT,
                messages=messages,
            )
            raw = resp.content[0].text.strip()
            return self._parse_json(raw)
        except Exception as exc:
            logger.error("ClaudeAdapter.analyze error: %s", exc)
            return self._rule_based_fallback(caller_text)

    # ------------------------------------------------------------------
    def _parse_json(self, raw: str) -> Dict[str, Any]:
        """Extract JSON from model output even if wrapped in markdown."""
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.warning("ClaudeAdapter: could not parse JSON, using fallback")
        return self._rule_based_fallback(raw)

    def _rule_based_fallback(self, text: str) -> Dict[str, Any]:
        """Deterministic keyword-based extraction used in stub mode."""
        text_lower = text.lower()

        # Intent
        intent = CallIntent.UNKNOWN
        if any(w in text_lower for w in ["schedule", "appointment", "come out", "book"]):
            intent = CallIntent.NEW_APPOINTMENT
        elif any(w in text_lower for w in ["reschedule", "change my appointment", "move my"]):
            intent = CallIntent.RESCHEDULE
        elif any(w in text_lower for w in ["cancel", "cancellation"]):
            intent = CallIntent.CANCEL
        elif any(w in text_lower for w in EMERGENCY_KEYWORDS):
            intent = CallIntent.EMERGENCY
        elif any(w in text_lower for w in ["bill", "invoice", "charge", "payment"]):
            intent = CallIntent.BILLING
        elif any(w in text_lower for w in ["status", "where is", "eta", "on their way"]):
            intent = CallIntent.STATUS_CHECK
        elif any(w in text_lower for w in ["question", "how much", "price", "cost", "info"]):
            intent = CallIntent.GENERAL_INQUIRY

        # Priority
        if intent == CallIntent.EMERGENCY or any(w in text_lower for w in EMERGENCY_KEYWORDS):
            priority = Priority.EMERGENCY
        elif any(w in text_lower for w in ["completely", "not working", "broken", "down"]):
            priority = Priority.HIGH
        elif any(w in text_lower for w in ["strange noise", "not cooling", "not heating", "slow"]):
            priority = Priority.MEDIUM
        else:
            priority = Priority.LOW

        # Sentiment
        if any(w in text_lower for w in ["furious", "angry", "ridiculous", "unacceptable", "terrible"]):
            sentiment = "frustrated"
        elif any(w in text_lower for w in ["scared", "afraid", "dangerous", "help", "please"]):
            sentiment = "distressed"
        elif any(w in text_lower for w in ["thank", "great", "appreciate", "wonderful"]):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        # System type detection
        system_type = ""
        for st in SYSTEM_TYPES:
            if st in text_lower:
                system_type = st
                break

        # Response text
        if priority == Priority.EMERGENCY:
            response_text = (
                "I can hear this is urgent and I'm going to get you help right away. "
                "I'm connecting you to our on-call technician immediately."
            )
        elif intent == CallIntent.NEW_APPOINTMENT:
            response_text = (
                "I'd be happy to schedule a service visit for you. "
                "Could I get your name and address so I can find the best available slot?"
            )
        elif intent == CallIntent.BILLING:
            response_text = (
                "I can help with your billing question. "
                "Could you give me your name and the invoice number if you have it?"
            )
        else:
            response_text = (
                "Thank you for calling. I'm here to help — "
                "could you tell me a bit more about what you need today?"
            )

        # Extract name (simple heuristic: "my name is X" or "this is X")
        name_match = re.search(
            r"(?:my name is|this is|i am|i'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            text,
            re.IGNORECASE,
        )
        name = name_match.group(1).strip() if name_match else ""

        # Extract phone (US formats)
        phone_match = re.search(
            r"\b(\+?1?\s?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})\b", text
        )
        phone = re.sub(r"[^\d+]", "", phone_match.group(1)) if phone_match else ""

        return {
            "intent":    intent.value,
            "priority":  priority.value,
            "sentiment": sentiment,
            "entities": {
                "name":              name,
                "address":           "",
                "phone":             phone,
                "email":             "",
                "system_type":       system_type,
                "system_age":        None,
                "issue_description": text[:200],
            },
            "response_text": response_text,
        }


# ──────────────────────────────────────────────
# AppointmentScheduler
# ──────────────────────────────────────────────
class AppointmentScheduler:
    """
    Manages appointment slots.
    In production: integrate with ServiceTitan, Jobber, or Housecall Pro.
    Here: lightweight in-memory + JSONL persistence.
    """

    SLOT_DURATION_MINUTES = 120  # 2-hour windows standard in HVAC

    def __init__(self, twilio: TwilioAdapter):
        self.twilio   = twilio
        self._booked  = self._load_booked()

    def _load_booked(self) -> Dict[str, List[str]]:
        """Returns { 'YYYY-MM-DD': ['HH:MM', ...] }"""
        booked: Dict[str, List[str]] = {}
        for rec in appt_store.read_all():
            if rec.get("confirmed"):
                d = rec.get("slot_date", "")
                t = rec.get("slot_time", "")
                if d and t:
                    booked.setdefault(d, []).append(t)
        return booked

    def available_slots(
        self,
        from_date: Optional[datetime.date] = None,
        days_ahead: int = 5,
        priority: Priority = Priority.LOW,
    ) -> List[Tuple[str, str]]:
        """
        Returns list of (date_str, time_str) tuples.
        Emergency priority: next 24 h only, including after-hours.
        """
        slots = []
        start = from_date or datetime.date.today()

        if priority == Priority.EMERGENCY:
            # Return first available technician slot — could be now
            now = datetime.datetime.now()
            slot_dt = now + datetime.timedelta(minutes=30)
            return [(slot_dt.strftime("%Y-%m-%d"), slot_dt.strftime("%H:%M"))]

        for offset in range(days_ahead):
            day = start + datetime.timedelta(days=offset)
            weekday = day.weekday()
            hours = BUSINESS_HOURS.get(weekday)
            if hours is None:
                continue
            open_h, close_h = hours
            current = datetime.datetime(day.year, day.month, day.day, open_h, 0)
            end     = datetime.datetime(day.year, day.month, day.day, close_h, 0)

            while current + datetime.timedelta(minutes=self.SLOT_DURATION_MINUTES) <= end:
                time_str = current.strftime("%H:%M")
                date_str = day.strftime("%Y-%m-%d")
                taken = time_str in self._booked.get(date_str, [])
                if not taken:
                    slots.append((date_str, time_str))
                current += datetime.timedelta(minutes=self.SLOT_DURATION_MINUTES)

        return slots[:10]  # cap at 10 options

    def book(
        self,
        session: "CallSession",
        slot_date: str,
        slot_time: str,
        job_type: str,
        notes: str = "",
    ) -> Appointment:
        """Creates, persists, and confirms an appointment."""
        appt = Appointment(
            session_id  = session.session_id,
            customer    = session.customer,
            slot_date   = slot_date,
            slot_time   = slot_time,
            job_type    = job_type,
            priority    = session.priority,
            confirmed   = True,
            notes       = notes,
        )

        # Mark slot as taken
        self._booked.setdefault(slot_date, []).append(slot_time)

        # Persist
        record = asdict(appt)
        appt_store.append(record)
        logger.info(
            "Appointment booked | id=%s | %s %s | %s",
            appt.appointment_id, slot_date, slot_time, session.customer.name,
        )

        # Send confirmation SMS
        if session.customer.phone:
            body = (
                f"Hi {session.customer.name or 'there'}, your HVAC service is confirmed for "
                f"{slot_date} at {slot_time}. Our tech will call 30 min before arrival. "
                f"Reply STOP to opt out."
            )
            self.twilio.send_sms(session.customer.phone, body)

        return appt

    def cancel(self, appointment_id: str) -> bool:
        """Marks an appointment cancelled (soft delete via new log record)."""
        appt_store.append({
            "action":         "cancel",
            "appointment_id": appointment_id,
            "cancelled_at":   datetime.datetime.utcnow().isoformat(),
        })
        logger.info("Appointment cancelled | id=%s", appointment_id)
        return True


# ──────────────────────────────────────────────
# EmergencyEscalator
# ──────────────────────────────────────────────
class EmergencyEscalator:
    """
    Routes emergency calls to on-call technician.
    Sends SMS alert, logs escalation, and generates TwiML to connect the call.
    """

    def __init__(self, twilio: TwilioAdapter):
        self.twilio         = twilio
        self.oncall_number  = os.getenv("HVAC_ONCALL_NUMBER", "+15559990000")
        self.dispatch_email = os.getenv("HVAC_DISPATCH_EMAIL", "dispatch@hvacbiz.com")

    def escalate(self, session: "CallSession", issue: str) -> str:
        """
        Fires SMS to on-call tech, logs escalation.
        Returns the TwiML to bridge the caller to the technician.
        """
        session.escalated = True
        alert_body = (
            f"🚨 HVAC EMERGENCY 🚨\n"
            f"Caller: {session.customer.name or session.caller_number}\n"
            f"Number: {session.customer.phone or session.caller_number}\n"
            f"Address: {session.customer.address or 'not provided'}\n"
            f"Issue: {issue[:200]}\n"
            f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        self.twilio.send_sms(self.oncall_number, alert_body)

        logger.warning(
            "EMERGENCY ESCALATED | session=%s | issue=%s",
            session.session_id, issue[:80],
        )

        # TwiML to warm-transfer caller to on-call tech
        safe_number = self.oncall_number.replace("&", "&amp;")
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response>"
            "<Say>I'm connecting you to our on-call technician right now. "
            "Please hold for just a moment.</Say>"
            f'<Dial timeout="30" record="record-from-ringing">{safe_number}</Dial>'
            "<Say>Our technician did not answer. Please call back or stay on the line "
            "and we will try again shortly.</Say>"
            "</Response>"
        )
        return twiml


# ──────────────────────────────────────────────
# HVACReceptionist — core orchestrator
# ──────────────────────────────────────────────
class HVACReceptionist:
    """
    Handles the full lifecycle of an inbound HVAC call:
      1. Greeting (with business-hours awareness)
      2. Intent & entity extraction via Claude
      3. Emergency escalation if needed
      4. Appointment scheduling flow
      5. Call wrap-up + CRM logging
    """

    GREETING_HOURS = (
        "Thank you for calling {company}. I'm your AI receptionist. "
        "How can I help you today?"
    )
    GREETING_AFTER = AFTER_HOURS_MESSAGE

    def __init__(
        self,
        company_name: str = "ABC HVAC Services",
        twilio: Optional[TwilioAdapter] = None,
        claude: Optional[ClaudeAdapter] = None,
        scheduler: Optional[AppointmentScheduler] = None,
        escalator: Optional[EmergencyEscalator] = None,
    ):
        self.company_name = company_name
        self.twilio       = twilio    or TwilioAdapter()
        self.claude       = claude    or ClaudeAdapter()
        self.scheduler    = scheduler or AppointmentScheduler(self.twilio)
        self.escalator    = escalator or EmergencyEscalator(self.twilio)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def start_session(self, caller_number: str) -> CallSession:
        session = CallSession(caller_number=caller_number)
        session.customer.phone = caller_number
        logger.info("Session started | id=%s | caller=%s", session.session_id, caller_number)
        return session

    def greeting(self, session: CallSession) -> str:
        """Returns TwiML greeting appropriate for current time."""
        if self._is_business_hours():
            msg = self.GREETING_HOURS.format(company=self.company_name)
        else:
            msg = self.GREETING_AFTER
        session.transcript.append({"role": "assistant", "content": msg})
        return self.twilio.generate_twiml_response(msg, gather=True)

    def handle_input(self, session: CallSession, caller_speech: str) -> str:
        """
        Main turn handler — called each time the caller speaks.
        Returns TwiML with the next response.
        """
        logger.info("Input | session=%s | text=%s", session.session_id, caller_speech[:80])
        session.transcript.append({"role": "user", "content": caller_speech})

        # Analyze with Claude (or rule fallback)
        analysis = self.claude.analyze(caller_speech, session.transcript)

        # Update session state
        session.intent    = CallIntent(analysis.get("intent",    CallIntent.UNKNOWN.value))
        session.priority  = Priority  (analysis.get("priority",  Priority.LOW.value))
        session.sentiment = analysis.get("sentiment", "neutral")

        entities = analysis.get("entities", {})
        self._merge_entities(session.customer, entities)

        response_text = analysis.get("response_text", "Could you repeat that?")

        # ── Emergency path ─────────────────────────────────────────────
        if session.priority == Priority.EMERGENCY or session.intent == CallIntent.EMERGENCY:
            twiml = self.escalator.escalate(
                session,
                entities.get("issue_description", caller_speech),
            )
            session.resolution = "emergency_escalated"
            session.transcript.append({"role": "assistant", "content": response_text})
            return twiml

        # ── Appointment booking ────────────────────────────────────────
        if session.intent == CallIntent.NEW_APPOINTMENT:
            twiml, done = self._appointment_flow(session, response_text)
            if done:
                session.resolution = "appointment_booked"
            return twiml

        # ── Cancellation ───────────────────────────────────────────────
        if session.intent == CallIntent.CANCEL and session.appointment_id:
            self.scheduler.cancel(session.appointment_id)
            response_text = (
                f"I've cancelled your appointment, {session.customer.name or 'there'}. "
                "Is there anything else I can help you with?"
            )
            session.resolution = "appointment_cancelled"

        # ── Billing / status / general ─────────────────────────────────
        if session.intent in (CallIntent.BILLING, CallIntent.STATUS_CHECK):
            response_text += (
                " I'll make sure a team member calls you back within 2 business hours "
                "to handle this personally."
            )
            self._flag_for_callback(session, session.intent.value)
            session.resolution = "callback_flagged"

        session.transcript.append({"role": "assistant", "content": response_text})
        gather = session.resolution == ""
        return self.twilio.generate_twiml_response(response_text, gather=gather)

    def end_session(self, session: CallSession) -> None:
        """Finalises and persists the call record."""
        session.ended_at = datetime.datetime.utcnow().isoformat()
        if not session.resolution:
            session.resolution = "completed"
        record = asdict(session)
        call_store.append(record)
        logger.info(
            "Session ended | id=%s | intent=%s | priority=%s | resolution=%s",
            session.session_id, session.intent.value,
            session.priority.value, session.resolution,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _is_business_hours(self) -> bool:
        now     = datetime.datetime.now()
        weekday = now.weekday()
        hours   = BUSINESS_HOURS.get(weekday)
        if hours is None:
            return False
        open_h, close_h = hours
        return open_h <= now.hour < close_h

    def _merge_entities(self, customer: CustomerInfo, entities: Dict) -> None:
        """Non-destructively merge extracted entities into customer record."""
        for field_name in ("name", "address", "email", "system_type"):
            val = entities.get(field_name, "")
            if val and not getattr(customer, field_name):
                setattr(customer, field_name, val)
        if entities.get("phone") and not customer.phone:
            customer.phone = entities["phone"]
        if entities.get("system_age") is not None and customer.system_age is None:
            customer.system_age = entities["system_age"]

    def _appointment_flow(
        self, session: CallSession, initial_response: str
    ) -> Tuple[str, bool]:
        """
        Returns (TwiML, is_complete).
        If we have enough info (name + address), books a slot immediately.
        Otherwise, asks for missing details.
        """
        c = session.customer

        if not c.name:
            msg = "What name should I put the appointment under?"
            session.transcript.append({"role": "assistant", "content": msg})
            return self.twilio.generate_twiml_response(msg, gather=True), False

        if not c.address:
            msg = f"Thanks, {c.name}. What's the service address?"
            session.transcript.append({"role": "assistant", "content": msg})
            return self.twilio.generate_twiml_response(msg, gather=True), False

        # We have enough to book — pick first available slot
        slots = self.scheduler.available_slots(priority=session.priority)
        if not slots:
            msg = (
                "I'm sorry, I don't see any open slots in the next 5 days. "
                "Let me flag this for our scheduler to call you back within the hour."
            )
            self._flag_for_callback(session, "no_slots")
            session.transcript.append({"role": "assistant", "content": msg})
            return self.twilio.generate_twiml_response(msg, gather=False), True

        slot_date, slot_time = slots[0]
        issue_desc = ""
        for turn in reversed(session.transcript):
            if turn["role"] == "user":
                issue_desc = turn["content"][:200]
                break

        appt = self.scheduler.book(
            session,
            slot_date=slot_date,
            slot_time=slot_time,
            job_type=issue_desc or "HVAC Service",
            notes=f"Priority: {session.priority.value} | System: {c.system_type or 'unknown'}",
        )
        session.appointment_id = appt.appointment_id

        friendly_date = datetime.datetime.strptime(slot_date, "%Y-%m-%d").strftime("%A, %B %d")
        msg = (
            f"Perfect! I've booked your appointment for {friendly_date} at {slot_time}. "
            f"You'll receive a confirmation text at {c.phone or 'the number you called from'}. "
            "Our technician will call 30 minutes before arrival. Is there anything else?"
        )
        session.transcript.append({"role": "assistant", "content": msg})
        return self.twilio.generate_twiml_response(msg, gather=False), True

    def _flag_for_callback(self, session: CallSession, reason: str) -> None:
        """Write a callback-needed record to the call log."""
        call_store.append({
            "type":        "callback_needed",
            "session_id":  session.session_id,
            "caller":      session.customer.phone or session.caller_number,
            "name":        session.customer.name,
            "reason":      reason,
            "flagged_at":  datetime.datetime.utcnow().isoformat(),
        })
        logger.info("Callback flagged | session=%s | reason=%s", session.session_id, reason)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def daily_summary(self) -> Dict[str, Any]:
        """Aggregate today's calls from the log."""
        today = datetime.date.today().isoformat()
        all_calls = call_store.read_all()
        today_calls = [
            c for c in all_calls
            if c.get("started_at", "").startswith(today)
            and c.get("type") != "callback_needed"
        ]

        intents: Dict[str, int] = {}
        priorities: Dict[str, int] = {}
        resolutions: Dict[str, int] = {}
        escalations = 0

        for c in today_calls:
            i = c.get("intent", "unknown")
            intents[i] = intents.get(i, 0) + 1
            p = c.get("priority", "low")
            priorities[p] = priorities.get(p, 0) + 1
            r = c.get("resolution", "unknown")
            resolutions[r] = resolutions.get(r, 0) + 1
            if c.get("escalated"):
                escalations += 1

        return {
            "date":         today,
            "total_calls":  len(today_calls),
            "escalations":  escalations,
            "intents":      intents,
            "priorities":   priorities,
            "resolutions":  resolutions,
        }


# ──────────────────────────────────────────────
# Webhook handlers (Flask-style, usable with any WSGI)
# ──────────────────────────────────────────────
def build_flask_app(receptionist: HVACReceptionist):
    """
    Returns a Flask app with Twilio webhook endpoints.
    Only imported / built when Flask is available.
    """
    try:
        from flask import Flask, request, Response  # type: ignore
    except ImportError:
        logger.error("Flask not installed — webhook server unavailable")
        return None

    app = Flask("hvac_receptionist")
    _sessions: Dict[str, CallSession] = {}

    @app.route("/incoming-call", methods=["POST"])
    def incoming_call():
        caller = request.form.get("From", "unknown")
        session = receptionist.start_session(caller)
        _sessions[session.session_id] = session
        twiml = receptionist.greeting(session)
        # Store session_id in a Gather action URL
        twiml = twiml.replace(
            'action="/handle-input"',
            f'action="/handle-input?sid={session.session_id}"',
        )
        return Response(twiml, mimetype="application/xml")

    @app.route("/handle-input", methods=["POST"])
    def handle_input():
        sid        = request.args.get("sid", "")
        session    = _sessions.get(sid)
        speech     = request.form.get("SpeechResult", "")
        dtmf       = request.form.get("Digits", "")
        user_input = speech or dtmf

        if not session:
            # Session expired or unknown — create a new one
            caller  = request.form.get("From", "unknown")
            session = receptionist.start_session(caller)
            _sessions[session.session_id] = session
            sid = session.session_id

        if not user_input:
            msg = "I'm sorry, I didn't catch that. Could you say that again?"
            twiml = receptionist.twilio.generate_twiml_response(msg)
            twiml = twiml.replace('action="/handle-input"', f'action="/handle-input?sid={sid}"')
            return Response(twiml, mimetype="application/xml")

        twiml = receptionist.handle_input(session, user_input)

        if session.resolution:
            receptionist.end_session(session)
            _sessions.pop(sid, None)
        else:
            twiml = twiml.replace(
                'action="/handle-input"',
                f'action="/handle-input?sid={sid}"',
            )

        return Response(twiml, mimetype="application/xml")

    @app.route("/summary", methods=["GET"])
    def summary():
        data = receptionist.daily_summary()
        return data

    return app


# ──────────────────────────────────────────────
# Standalone demo
# ──────────────────────────────────────────────
def run_demo() -> None:
    """
    Simulates three inbound calls through the full pipeline
    without any real Twilio or Anthropic credentials.
    """
    print("\n" + "═" * 65)
    print("  HVAC AI Receptionist — Standalone Demo")
    print("═" * 65 + "\n")

    receptionist = HVACReceptionist(company_name="Frost & Flame HVAC")

    scenarios = [
        {
            "label":  "EMERGENCY — no heat, elderly resident",
            "caller": "+15551112222",
            "turns": [
                "There's no heat in my house and it's 18 degrees outside. "
                "My name is Margaret Collins. I live at 4821 Elm Street. "
                "My furnace completely stopped working an hour ago.",
            ],
        },
        {
            "label":  "NEW APPOINTMENT — AC tune-up",
            "caller": "+15553334444",
            "turns": [
                "Hi, I'd like to schedule a maintenance check for my central air unit.",
                "My name is David Park. I'm at 112 Maple Avenue.",
            ],
        },
        {
            "label":  "BILLING INQUIRY",
            "caller": "+15557778888",
            "turns": [
                "Hi I got an invoice last week and I think the charge is wrong. "
                "This is Sandra Torres, my number is 555-777-8888.",
            ],
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"  Scenario: {scenario['label']}")
        print(f"  Caller:   {scenario['caller']}")
        print(f"{'─' * 60}")

        session = receptionist.start_session(scenario["caller"])

        # Greeting
        twiml = receptionist.greeting(session)
        greeting_text = re.search(r"<Say>(.*?)</Say>", twiml, re.DOTALL)
        if greeting_text:
            print(f"\n[AI] {greeting_text.group(1).strip()}")

        # Process each turn
        for turn_text in scenario["turns"]:
            print(f"[Caller] {turn_text[:100]}")
            twiml = receptionist.handle_input(session, turn_text)
            response_text = re.findall(r"<Say>(.*?)</Say>", twiml, re.DOTALL)
            for rt in response_text:
                print(f"[AI] {rt.strip()}")
            if "<Dial>" in twiml:
                print("[SYSTEM] ☎ Warm transfer to on-call technician initiated")

        receptionist.end_session(session)
        print(f"\n  ✓ Resolution: {session.resolution}")
        print(f"  ✓ Priority:   {session.priority.value}")
        print(f"  ✓ Escalated:  {session.escalated}")
        if session.appointment_id:
            print(f"  ✓ Appointment: {session.appointment_id}")

    # Daily summary
    print(f"\n{'═' * 65}")
    print("  Daily Summary")
    print(f"{'═' * 65}")
    summary = receptionist.daily_summary()
    print(json.dumps(summary, indent=2))

    print(f"\n✓ Logs written to {CALLS_LOG}")
    print(f"✓ Appointments logged to {APPTS_LOG}")
    print(f"✓ Full log at {LOG_PATH}\n")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="HVAC AI Receptionist")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start Flask webhook server (requires TWILIO_* env vars)",
    )
    parser.add_argument("--port",    type=int, default=5050)
    parser.add_argument("--host",    type=str, default="0.0.0.0")
    parser.add_argument("--company", type=str, default="Frost & Flame HVAC")
    args = parser.parse_args()

    if args.serve:
        receptionist = HVACReceptionist(company_name=args.company)
        app = build_flask_app(receptionist)
        if app:
            logger.info("Starting webhook server on %s:%d", args.host, args.port)
            app.run(host=args.host, port=args.port, debug=False)
        else:
            logger.error("Cannot start server — Flask not available")
            sys.exit(1)
    else:
        run_demo()