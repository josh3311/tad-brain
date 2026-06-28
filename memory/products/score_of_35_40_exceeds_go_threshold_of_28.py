"""
Dental Office AI Receptionist System
=====================================
Product: DentalMind AI Receptionist
Target: Small-to-mid dental offices (1-5 dentists)
Problem: Dental offices lose 30-40% of after-hours calls → lost revenue.
         Front desk staff spend 60% of time on scheduling/intake/reminders.
Solution: AI receptionist handles scheduling, intake forms, appointment reminders,
          insurance verification prompts, and FAQ — 24/7, no extra headcount.

Revenue model: $299/mo per office (starter), $599/mo (pro with SMS + integrations)
TAD Mission fit: Clear pain, willingness to pay, low AI competition in dental vertical.

Author: TAD Build Agent
Date: 2026-06-28
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging setup — all output to memory/ folder per TAD standards
# ---------------------------------------------------------------------------
MEMORY_DIR = Path("memory/products/dental_receptionist")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = MEMORY_DIR / "dental_receptionist.log"
DATA_FILE = MEMORY_DIR / "appointments.json"
PATIENTS_FILE = MEMORY_DIR / "patients.json"
METRICS_FILE = MEMORY_DIR / "metrics.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("DentalMindAI")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Patient:
    patient_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    email: str = ""
    date_of_birth: str = ""          # YYYY-MM-DD
    insurance_provider: str = ""
    insurance_member_id: str = ""
    medical_history_flags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_visit: Optional[str] = None

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


@dataclass
class Appointment:
    appointment_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    patient_id: str = ""
    patient_name: str = ""
    appointment_type: str = ""       # cleaning, exam, filling, emergency, consult
    requested_date: str = ""         # YYYY-MM-DD
    requested_time: str = ""         # HH:MM
    confirmed_slot: Optional[str] = None
    status: str = "pending"          # pending | confirmed | cancelled | completed
    notes: str = ""
    reminder_sent: bool = False
    intake_complete: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Appointment type catalogue with duration + prep notes
# ---------------------------------------------------------------------------

APPOINTMENT_CATALOGUE = {
    "cleaning": {
        "duration_min": 60,
        "prep": "Please arrive 10 minutes early. Avoid eating 2 hours before.",
        "base_cost": 150,
    },
    "exam": {
        "duration_min": 45,
        "prep": "Bring your insurance card and photo ID.",
        "base_cost": 100,
    },
    "filling": {
        "duration_min": 90,
        "prep": "You may experience numbness after. Arrange a ride if needed.",
        "base_cost": 250,
    },
    "emergency": {
        "duration_min": 30,
        "prep": "Call ahead. We will triage you on arrival.",
        "base_cost": 175,
    },
    "consult": {
        "duration_min": 30,
        "prep": "Bring any recent X-rays or dental records.",
        "base_cost": 75,
    },
    "whitening": {
        "duration_min": 60,
        "prep": "Avoid coffee and red wine 48 hours before.",
        "base_cost": 350,
    },
    "root_canal": {
        "duration_min": 120,
        "prep": "Arrange a ride. You will be under local anaesthetic.",
        "base_cost": 900,
    },
    "crown": {
        "duration_min": 90,
        "prep": "Two visits required. First visit is a prep appointment.",
        "base_cost": 1200,
    },
}

# Office hours (Mon–Fri 08:00–17:00, Sat 09:00–13:00)
OFFICE_HOURS = {
    "Monday":    ("08:00", "17:00"),
    "Tuesday":   ("08:00", "17:00"),
    "Wednesday": ("08:00", "17:00"),
    "Thursday":  ("08:00", "17:00"),
    "Friday":    ("08:00", "16:00"),
    "Saturday":  ("09:00", "13:00"),
    "Sunday":    None,  # closed
}

# Common FAQ answers
FAQ_DATABASE = {
    "insurance": (
        "We accept most major dental insurance plans including Delta Dental, "
        "Cigna, Aetna, MetLife, and United Concordia. Please bring your "
        "insurance card to your first visit. We will verify benefits before "
        "your appointment."
    ),
    "payment": (
        "We accept cash, all major credit cards, CareCredit, and Sunbit "
        "financing. Payment plans are available — ask our front desk."
    ),
    "cancel": (
        "We require 24-hour notice for cancellations. Late cancellations or "
        "no-shows may incur a $50 fee. To cancel, reply CANCEL to this "
        "message or call our office."
    ),
    "parking": (
        "Free parking is available in the lot directly behind our building. "
        "Street parking is also available on Main St."
    ),
    "emergency": (
        "For dental emergencies during office hours, call us immediately. "
        "After hours, call our emergency line at (555) 999-0000. "
        "For life-threatening situations, call 911."
    ),
    "new_patient": (
        "Welcome! New patients should arrive 15 minutes early to complete "
        "intake paperwork. You can also complete forms online — we will "
        "send a link after scheduling."
    ),
    "children": (
        "We see patients of all ages! For children under 3, we recommend "
        "a complimentary 'happy visit' first to get comfortable with our office."
    ),
    "xray": (
        "We use digital X-rays which emit up to 80% less radiation than "
        "traditional film X-rays. New patients typically receive a full "
        "series; returning patients receive bite-wings annually."
    ),
}


# ---------------------------------------------------------------------------
# Core persistence helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    """Load JSON file or return empty structure."""
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            log.warning(f"JSON decode error on {path}: {e} — starting fresh")
    return {}


def _save_json(path: Path, data: dict) -> None:
    """Atomic-ish JSON save."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Patient registry
# ---------------------------------------------------------------------------

class PatientRegistry:
    """Simple file-backed patient store."""

    def __init__(self):
        raw = _load_json(PATIENTS_FILE)
        self._store: dict[str, dict] = raw
        log.info(f"PatientRegistry loaded {len(self._store)} patients")

    def find_by_phone(self, phone: str) -> Optional[Patient]:
        clean = re.sub(r"\D", "", phone)
        for pid, data in self._store.items():
            stored = re.sub(r"\D", "", data.get("phone", ""))
            if stored == clean:
                return Patient(**data)
        return None

    def find_by_name(self, first: str, last: str) -> Optional[Patient]:
        key = f"{first.lower()} {last.lower()}"
        for pid, data in self._store.items():
            stored = f"{data.get('first_name','').lower()} {data.get('last_name','').lower()}"
            if stored == key:
                return Patient(**data)
        return None

    def upsert(self, patient: Patient) -> None:
        self._store[patient.patient_id] = asdict(patient)
        _save_json(PATIENTS_FILE, self._store)
        log.info(f"Patient upserted: {patient.full_name} ({patient.patient_id})")

    def all_patients(self) -> list[Patient]:
        return [Patient(**d) for d in self._store.values()]


# ---------------------------------------------------------------------------
# Appointment scheduler
# ---------------------------------------------------------------------------

class AppointmentScheduler:
    """Manages appointment booking, availability, and status."""

    SLOT_INTERVAL_MIN = 30  # slots every 30 minutes

    def __init__(self):
        raw = _load_json(DATA_FILE)
        self._store: dict[str, dict] = raw
        log.info(f"AppointmentScheduler loaded {len(self._store)} appointments")

    # ------------------------------------------------------------------
    # Availability logic
    # ------------------------------------------------------------------

    def _slots_for_date(self, date_str: str) -> list[str]:
        """Return list of HH:MM slot strings for a given YYYY-MM-DD date."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return []
        day_name = dt.strftime("%A")
        hours = OFFICE_HOURS.get(day_name)
        if hours is None:
            return []  # closed
        start_h, start_m = map(int, hours[0].split(":"))
        end_h, end_m = map(int, hours[1].split(":"))
        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m
        slots = []
        t = start_mins
        while t + self.SLOT_INTERVAL_MIN <= end_mins:
            slots.append(f"{t // 60:02d}:{t % 60:02d}")
            t += self.SLOT_INTERVAL_MIN
        return slots

    def _booked_slots(self, date_str: str) -> set[str]:
        """Return set of already-booked start times on given date."""
        booked = set()
        for appt in self._store.values():
            if appt.get("confirmed_slot", "").startswith(date_str):
                time_part = appt["confirmed_slot"].split("T")[-1] if "T" in appt["confirmed_slot"] else ""
                if time_part:
                    booked.add(time_part[:5])
        return booked

    def available_slots(self, date_str: str, appointment_type: str = "cleaning") -> list[str]:
        """Return available HH:MM slots for a date, excluding booked ones."""
        duration = APPOINTMENT_CATALOGUE.get(appointment_type, {}).get("duration_min", 60)
        slots_needed = max(1, duration // self.SLOT_INTERVAL_MIN)
        all_slots = self._slots_for_date(date_str)
        booked = self._booked_slots(date_str)

        available = []
        for i, slot in enumerate(all_slots):
            # Check consecutive slots are all free for multi-slot appointments
            required = all_slots[i: i + slots_needed]
            if len(required) == slots_needed and not any(s in booked for s in required):
                available.append(slot)
        return available

    def next_available_slots(self, appointment_type: str = "cleaning", days_ahead: int = 14) -> list[dict]:
        """Find next available slots across upcoming days."""
        results = []
        today = datetime.now().date()
        for delta in range(1, days_ahead + 1):
            check_date = (today + timedelta(days=delta)).strftime("%Y-%m-%d")
            slots = self.available_slots(check_date, appointment_type)
            if slots:
                results.append({"date": check_date, "slots": slots[:4]})  # cap at 4 per day
            if len(results) >= 5:
                break
        return results

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------

    def book(self, patient: Patient, appointment_type: str,
             date_str: str, time_str: str, notes: str = "") -> tuple[bool, str, Optional[Appointment]]:
        """
        Attempt to book a slot.
        Returns (success, message, appointment_or_None).
        """
        appt_type_lower = appointment_type.lower().replace(" ", "_")
        if appt_type_lower not in APPOINTMENT_CATALOGUE:
            available_types = ", ".join(APPOINTMENT_CATALOGUE.keys())
            return False, f"Unknown appointment type '{appointment_type}'. Available: {available_types}", None

        available = self.available_slots(date_str, appt_type_lower)
        if time_str not in available:
            if available:
                suggestion = ", ".join(available[:3])
                return False, (
                    f"Sorry, {time_str} on {date_str} is not available for a {appointment_type}. "
                    f"Available times: {suggestion}"
                ), None
            else:
                return False, f"No availability on {date_str}. Please choose another date.", None

        appt = Appointment(
            patient_id=patient.patient_id,
            patient_name=patient.full_name,
            appointment_type=appt_type_lower,
            requested_date=date_str,
            requested_time=time_str,
            confirmed_slot=f"{date_str}T{time_str}",
            status="confirmed",
            notes=notes,
        )
        self._store[appt.appointment_id] = asdict(appt)
        _save_json(DATA_FILE, self._store)

        prep = APPOINTMENT_CATALOGUE[appt_type_lower]["prep"]
        msg = (
            f"✅ Appointment confirmed!\n"
            f"   Patient: {patient.full_name}\n"
            f"   Type: {appointment_type.title()}\n"
            f"   Date/Time: {date_str} at {time_str}\n"
            f"   Appointment ID: {appt.appointment_id}\n"
            f"   Prep instructions: {prep}"
        )
        log.info(f"Appointment booked: {appt.appointment_id} for {patient.full_name} on {date_str} {time_str}")
        return True, msg, appt

    def cancel(self, appointment_id: str) -> tuple[bool, str]:
        """Cancel an appointment by ID."""
        if appointment_id not in self._store:
            return False, f"Appointment ID '{appointment_id}' not found."
        appt = self._store[appointment_id]
        if appt["status"] == "cancelled":
            return False, "This appointment is already cancelled."
        appt["status"] = "cancelled"
        _save_json(DATA_FILE, self._store)
        log.info(f"Appointment cancelled: {appointment_id}")
        return True, f"Appointment {appointment_id} has been cancelled. We hope to see you soon!"

    def get_upcoming(self, patient_id: str) -> list[Appointment]:
        """Return upcoming (confirmed) appointments for a patient."""
        now = datetime.now().isoformat()
        results = []
        for data in self._store.values():
            if (data.get("patient_id") == patient_id
                    and data.get("status") == "confirmed"
                    and data.get("confirmed_slot", "") >= now):
                results.append(Appointment(**data))
        results.sort(key=lambda a: a.confirmed_slot or "")
        return results

    def appointments_needing_reminder(self, hours_ahead: int = 24) -> list[Appointment]:
        """Return confirmed appointments within N hours that haven't had a reminder sent."""
        target = datetime.now() + timedelta(hours=hours_ahead)
        due = []
        for data in self._store.values():
            if data.get("status") == "confirmed" and not data.get("reminder_sent"):
                slot_str = data.get("confirmed_slot", "")
                if slot_str:
                    try:
                        slot_dt = datetime.fromisoformat(slot_str)
                        if datetime.now() <= slot_dt <= target:
                            due.append(Appointment(**data))
                    except ValueError:
                        pass
        return due

    def mark_reminder_sent(self, appointment_id: str) -> None:
        if appointment_id in self._store:
            self._store[appointment_id]["reminder_sent"] = True
            _save_json(DATA_FILE, self._store)


# ---------------------------------------------------------------------------
# Intake form handler
# ---------------------------------------------------------------------------

class IntakeFormHandler:
    """
    Collects new patient intake information step-by-step.
    In production this would integrate with a web form or SMS flow.
    Here it validates and stores intake data.
    """

    REQUIRED_FIELDS = ["first_name", "last_name", "date_of_birth", "phone", "email"]

    MEDICAL_FLAGS_KEYWORDS = [
        "diabetes", "heart", "blood pressure", "hypertension", "blood thinner",
        "warfarin", "aspirin", "pacemaker", "pregnant", "allergy", "penicillin",
        "latex", "bisphosphonate", "cancer", "chemotherapy", "radiation", "hiv",
        "hepatitis", "osteoporosis",
    ]

    def validate(self, intake_data: dict) -> tuple[bool, list[str]]:
        """Validate intake form data. Returns (valid, list_of_errors)."""
        errors = []

        for field_name in self.REQUIRED_FIELDS:
            if not intake_data.get(field_name, "").strip():
                errors.append(f"Missing required field: {field_name}")

        phone = intake_data.get("phone", "")
        clean_phone = re.sub(r"\D", "", phone)
        if phone and len(clean_phone) < 10:
            errors.append("Phone number must be at least 10 digits")

        email = intake_data.get("email", "")
        if email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
            errors.append("Invalid email address format")

        dob = intake_data.get("date_of_birth", "")
        if dob:
            try:
                dob_dt = datetime.strptime(dob, "%Y-%m-%d")
                if dob_dt > datetime.now():
                    errors.append("Date of birth cannot be in the future")
                if (datetime.now() - dob_dt).days > 365 * 120:
                    errors.append("Date of birth appears invalid (>120 years ago)")
            except ValueError:
                errors.append("Date of birth must be in YYYY-MM-DD format")

        return len(errors) == 0, errors

    def extract_medical_flags(self, free_text: str) -> list[str]:
        """Scan free-text medical history for known flag keywords."""
        flags = []
        lower = free_text.lower()
        for kw in self.MEDICAL_FLAGS_KEYWORDS:
            if kw in lower:
                flags.append(kw)
        return flags

    def process_intake(self, intake_data: dict, registry: PatientRegistry) -> tuple[bool, str, Optional[Patient]]:
        """
        Validate intake data, flag medical alerts, create/update patient record.
        Returns (success, message, patient_or_None).
        """
        valid, errors = self.validate(intake_data)
        if not valid:
            return False, "Intake form has errors:\n" + "\n".join(f"  • {e}" for e in errors), None

        # Check for medical flags in history field
        history_text = intake_data.get("medical_history", "")
        flags = self.extract_medical_flags(history_text)

        # Check for existing patient (by phone)
        existing = registry.find_by_phone(intake_data.get("phone", ""))

        if existing:
            # Update existing patient
            existing.email = intake_data.get("email", existing.email)
            existing.insurance_provider = intake_data.get("insurance_provider", existing.insurance_provider)
            existing.insurance_member_id = intake_data.get("insurance_member_id", existing.insurance_member_id)
            if flags:
                existing.medical_history_flags = list(set(existing.medical_history_flags + flags))
            registry.upsert(existing)
            patient = existing
            action = "updated"
        else:
            patient = Patient(
                first_name=intake_data["first_name"].strip().title(),
                last_name=intake_data["last_name"].strip().title(),
                phone=intake_data["phone"].strip(),
                email=intake_data.get("email", "").strip().lower(),
                date_of_birth=intake_data.get("date_of_birth", ""),
                insurance_provider=intake_data.get("insurance_provider", ""),
                insurance_member_id=intake_data.get("insurance_member_id", ""),
                medical_history_flags=flags,
            )
            registry.upsert(patient)
            action = "created"

        flag_msg = ""
        if flags:
            flag_msg = f"\n⚠️  Medical flags noted (review before treatment): {', '.join(flags)}"

        msg = (
            f"✅ Intake {action} for {patient.full_name} (ID: {patient.patient_id}){flag_msg}\n"
            f"   Insurance: {patient.insurance_provider or 'Not provided'}"
        )
        log.info(f"Intake processed for {patient.full_name}: {action}, flags={flags}")
        return True, msg, patient


# ---------------------------------------------------------------------------
# FAQ / Natural language router
# ---------------------------------------------------------------------------

class DentalFAQRouter:
    """
    Simple keyword-based router for common patient questions.
    In production, this would call an LLM with RAG over the office's
    knowledge base. Here we use deterministic keyword matching.
    """

    INTENT_MAP = {
        "insurance": ["insurance", "coverage", "plan", "delta", "cigna", "aetna", "metlife", "covered"],
        "payment": ["pay", "payment", "cost", "price", "how much", "credit card", "financing", "carecredit"],
        "cancel": ["cancel", "reschedule", "change", "postpone", "move my appointment"],
        "parking": ["park", "parking", "where to park", "lot"],
        "emergency": ["emergency", "urgent", "pain", "broken tooth", "knocked out", "abscess", "swelling"],
        "new_patient": ["new patient", "first time", "first visit", "never been"],
        "children": ["child", "kid", "baby", "toddler", "pediatric"],
        "xray": ["x-ray", "xray", "x ray", "radiation", "film"],
    }

    def classify_intent(self, message: str) -> Optional[str]:
        """Classify message into a FAQ intent category."""
        lower = message.lower()
        for intent, keywords in self.INTENT_MAP.items():
            for kw in keywords:
                if kw in lower:
                    return intent
        return None

    def answer(self, message: str) -> str:
        """Return a FAQ answer or a helpful fallback."""
        intent = self.classify_intent(message)
        if intent:
            log.info(f"FAQ intent matched: {intent}")
            return FAQ_DATABASE[intent]
        return (
            "I want to make sure I give you the right answer! "
            "Our team is available Mon–Fri 8am–5pm at (555) 123-4567, "
            "or reply with your question and we will get back to you shortly."
        )


# ---------------------------------------------------------------------------
# Reminder engine
# ---------------------------------------------------------------------------

class ReminderEngine:
    """
    Generates reminder messages and (in production) dispatches via SMS/email.
    Here it logs and returns message strings for the dispatcher to send.
    """

    def generate_reminder(self, appt: Appointment) -> str:
        """Build a human-friendly reminder message."""
        appt_info = APPOINTMENT_CATALOGUE.get(appt.appointment_type, {})
        prep = appt_info.get("prep", "")
        slot = appt.confirmed_slot or f"{appt.requested_date}T{appt.requested_time}"
        try:
            dt = datetime.fromisoformat(slot)
            display = dt.strftime("%A, %B %d at %I:%M %p")
        except ValueError:
            display = slot

        msg = (
            f"Hi {appt.patient_name}! This is a reminder from Bright Smile Dental. "
            f"You have a {appt.appointment_type.replace('_', ' ').title()} appointment "
            f"scheduled for {display}. "
            f"{prep} "
            f"To cancel or reschedule, reply CANCEL or call (555) 123-4567. "
            f"See you soon!"
        )
        return msg

    def process_reminders(self, scheduler: AppointmentScheduler) -> list[dict]:
        """
        Find appointments needing reminders and generate messages.
        Returns list of {appointment_id, patient_name, message} dicts.
        In production: call SMS API here (Twilio, etc.)
        """
        due = scheduler.appointments_needing_reminder(hours_ahead=24)
        dispatched = []
        for appt in due:
            msg = self.generate_reminder(appt)
            # Production: send_sms(patient_phone, msg) or send_email(patient_email, msg)
            log.info(f"REMINDER → {appt.patient_name} (appt {appt.appointment_id}): {msg[:80]}...")
            scheduler.mark_reminder_sent(appt.appointment_id)
            dispatched.append({
                "appointment_id": appt.appointment_id,
                "patient_name": appt.patient_name,
                "message": msg,
                "dispatched_at": datetime.now().isoformat(),
            })
        if dispatched:
            log.info(f"Reminder engine dispatched {len(dispatched)} reminders")
        return dispatched


# ---------------------------------------------------------------------------
# Metrics tracker
# ---------------------------------------------------------------------------

class MetricsTracker:
    """Track business metrics: bookings, cancellations, intake completions."""

    def __init__(self):
        raw = _load_json(METRICS_FILE)
        self._data = raw if raw else {
            "total_bookings": 0,
            "total_cancellations": 0,
            "total_intakes": 0,
            "total_faq_answered": 0,
            "total_reminders_sent": 0,
            "revenue_booked_usd": 0.0,
            "sessions": [],
        }

    def record(self, event: str, value: float = 1.0, meta: dict = None) -> None:
        if event == "booking":
            self._data["total_bookings"] += 1
            self._data["revenue_booked_usd"] += value
        elif event == "cancellation":
            self._data["total_cancellations"] += 1
        elif event == "intake":
            self._data["total_intakes"] += 1
        elif event == "faq":
            self._data["total_faq_answered"] += 1
        elif event == "reminder":
            self._data["total_reminders_sent"] += int(value)

        self._data["sessions"].append({
            "event": event,
            "value": value,
            "meta": meta or {},
            "ts": datetime.now().isoformat(),
        })
        _save_json(METRICS_FILE, self._data)

    def summary(self) -> str:
        d = self._data
        return (
            f"\n{'='*50}\n"
            f"  DentalMind AI — Business Metrics\n"
            f"{'='*50}\n"
            f"  Total bookings:      {d['total_bookings']}\n"
            f"  Total cancellations: {d['total_cancellations']}\n"
            f"  Intake forms done:   {d['total_intakes']}\n"
            f"  FAQ queries handled: {d['total_faq_answered']}\n"
            f"  Reminders sent:      {d['total_reminders_sent']}\n"
            f"  Revenue booked:      ${d['revenue_booked_usd']:,.2f}\n"
            f"{'='*50}"
        )


# ---------------------------------------------------------------------------
# Main AI Receptionist orchestrator
# ---------------------------------------------------------------------------

class DentalAIReceptionist:
    """
    Top-level orchestrator. In production this would be the webhook handler
    for incoming calls/SMS/web chat. Here it exposes a process_request()
    method that routes intent and returns a response string.
    """

    def __init__(self, office_name: str = "Bright Smile Dental"):
        self.office_name = office_name
        self.registry = PatientRegistry()
        self.scheduler = AppointmentScheduler()
        self.intake_handler = IntakeFormHandler()
        self.faq_router = DentalFAQRouter()
        self.reminder_engine = ReminderEngine()
        self.metrics = MetricsTracker()
        log.info(f"DentalAIReceptionist initialised for '{office_name}'")

    def process_request(self, request_type: str, payload: dict) -> str:
        """
        Route a request to the appropriate handler.

        request_type options:
          - "book"           : payload = {patient_phone, appointment_type, date, time, [notes]}
          - "intake"         : payload = {first_name, last_name, dob, phone, email, ...}
          - "cancel"         : payload = {appointment_id}
          - "availability"   : payload = {appointment_type, [days_ahead]}
          - "faq"            : payload = {message}
          - "reminders"      : payload = {} — run reminder dispatch cycle
          - "lookup_patient" : payload = {phone} or {first_name, last_name}
          - "metrics"        : payload = {} — return summary
        """
        log.info(f"Request received: {request_type} | payload keys: {list(payload.keys())}")

        try:
            if request_type == "book":
                return self._handle_booking(payload)
            elif request_type == "intake":
                return self._handle_intake(payload)
            elif request_type == "cancel":
                return self._handle_cancel(payload)
            elif request_type == "availability":
                return self._handle_availability(payload)
            elif request_type == "faq":
                return self._handle_faq(payload)
            elif request_type == "reminders":
                return self._handle_reminders()
            elif request_type == "lookup_patient":
                return self._handle_lookup(payload)
            elif request_type == "metrics":
                return self.metrics.summary()
            else:
                return f"Unknown request type: '{request_type}'. I can help with booking, intake, cancellations, availability, and FAQ."

        except Exception as e:
            log.error(f"Unhandled error in process_request({request_type}): {e}", exc_info=True)
            return (
                f"I'm sorry, something went wrong on our end. "
                f"Please call us directly at (555) 123-4567 and we'll be happy to help!"
            )

    # ------------------------------------------------------------------
    # Sub-handlers
    # ------------------------------------------------------------------

    def _handle_booking(self, payload: dict) -> str:
        phone = payload.get("patient_phone", "")
        patient = self.registry.find_by_phone(phone) if phone else None

        if not patient:
            # Auto-create minimal patient record for walk-ins / first contact
            first = payload.get("first_name", "")
            last = payload.get("last_name", "")
            if first and last:
                patient = self.registry.find_by_name(first, last)
            if not patient:
                if not first or not last:
                    return (
                        "To book an appointment, I'll need your name and phone number. "
                        "Could you provide those?"
                    )
                patient = Patient(
                    first_name=first.strip().title(),
                    last_name=last.strip().title(),
                    phone=phone,
                    email=payload.get("email", ""),
                )
                self.registry.upsert(patient)
                log.info(f"Auto-created patient record for {patient.full_name}")

        appt_type = payload.get("appointment_type", "cleaning")
        date_str = payload.get("date", "")
        time_str = payload.get("time", "")

        if not date_str or not time_str:
            # Offer next available
            options = self.scheduler.next_available_slots(appt_type, days_ahead=14)
            if not options:
                return "I'm sorry, there are no available slots in the next two weeks. Please call us directly."
            lines = [f"Here are the next available slots for a {appt_type.replace('_', ' ').title()}:"]
            for opt in options[:3]:
                lines.append(f"  📅 {opt['date']}: {', '.join(opt['slots'][:3])}")
            lines.append("Reply with your preferred date and time to confirm.")
            return "\n".join(lines)

        success, msg, appt = self.scheduler.book(patient, appt_type, date_str, time_str, payload.get("notes", ""))
        if success and appt:
            cost = APPOINTMENT_CATALOGUE.get(appt.appointment_type, {}).get("base_cost", 0)
            self.metrics.record("booking", value=float(cost), meta={"appt_id": appt.appointment_id})
        return msg

    def _handle_intake(self, payload: dict) -> str:
        success, msg, patient = self.intake_handler.process_intake(payload, self.registry)
        if success:
            self.metrics.record("intake")
        return msg

    def _handle_cancel(self, payload: dict) -> str:
        appt_id = payload.get("appointment_id", "").strip()
        if not appt_id:
            return "Please provide your appointment ID to cancel. You can find it in your confirmation message."
        success, msg = self.scheduler.cancel(appt_id)
        if success:
            self.metrics.record("cancellation")
        return msg

    def _handle_availability(self, payload: dict) -> str:
        appt_type = payload.get("appointment_type", "cleaning")
        days = int(payload.get("days_ahead", 14))
        options = self.scheduler.next_available_slots(appt_type, days_ahead=days)
        if not options:
            return f"No availability found for '{appt_type}' in the next {days} days. Please call us."
        lines = [f"Available slots for {appt_type.replace('_', ' ').title()}:"]
        for opt in options:
            lines.append(f"  📅 {opt['date']}: {', '.join(opt['slots'])}")
        return "\n".join(lines)

    def _handle_faq(self, payload: dict) -> str:
        message = payload.get("message", "")
        if not message:
            return "How can I help you today?"
        answer = self.faq_router.answer(message)
        self.metrics.record("faq")
        return answer

    def _handle_reminders(self) -> str:
        dispatched = self.reminder_engine.process_reminders(self.scheduler)
        self.metrics.record("reminder", value=float(len(dispatched)))
        if dispatched:
            return f"✅ Sent {len(dispatched)} appointment reminder(s)."
        return "No reminders due at this time."

    def _handle_lookup(self, payload: dict) -> str:
        phone = payload.get("phone", "")
        first = payload.get("first_name", "")
        last = payload.get("last_name", "")

        patient = None
        if phone:
            patient = self.registry.find_by_phone(phone)
        elif first and last:
            patient = self.registry.find_by_name(first, last)

        if not patient:
            return "Patient not found. They may not be in our system yet — please complete an intake form."

        upcoming = self.scheduler.get_upcoming(patient.patient_id)
        appt_lines = []
        for a in upcoming[:3]:
            appt_lines.append(f"  • {a.confirmed_slot} — {a.appointment_type.replace('_',' ').title()}")

        return (
            f"Patient: {patient.full_name} (ID: {patient.patient_id})\n"
            f"Phone: {patient.phone} | Email: {patient.email}\n"
            f"Insurance: {patient.insurance_provider or 'None on file'}\n"
            f"Medical flags: {', '.join(patient.medical_history_flags) if patient.medical_history_flags else 'None'}\n"
            f"Upcoming appointments ({len(upcoming)}):\n"
            + ("\n".join(appt_lines) if appt_lines else "  None")
        )


# ---------------------------------------------------------------------------
# Demo / standalone runner
# ---------------------------------------------------------------------------

def _run_demo():
    """
    End-to-end demo: intake → booking → FAQ → reminder → metrics.
    Uses no external services — all data written to memory/products/dental_receptionist/
    """
    print("\n" + "=" * 60)
    print("  DentalMind AI Receptionist — Demo Run")
    print("=" * 60)

    receptionist = DentalAIReceptionist(office_name="Bright Smile Dental")

    # 1. New patient intake
    print("\n[1] New Patient Intake")
    print("-" * 40)
    result = receptionist.process_request("intake", {
        "first_name": "Sarah",
        "last_name": "Mitchell",
        "date_of_birth": "1988-03-15",
        "phone": "5551234567",
        "email": "sarah.mitchell@email.com",
        "insurance_provider": "Delta Dental",
        "insurance_member_id": "DD-789012",
        "medical_history": "I take aspirin daily and have mild hypertension. No known latex allergy.",
    })
    print(result)

    # 2. Check availability
    print("\n[2] Check Availability — Cleaning")
    print("-" * 40)
    result = receptionist.process_request("availability", {
        "appointment_type": "cleaning",
        "days_ahead": 7,
    })
    print(result)

    # 3. Book appointment (find first available slot automatically)
    print("\n[3] Book Appointment")
    print("-" * 40)
    # Find first slot dynamically
    scheduler_temp = receptionist.scheduler
    options = scheduler_temp.next_available_slots("cleaning", days_ahead=7)
    if options:
        book_date = options[0]["date"]
        book_time = options[0]["slots"][0]
    else:
        # Fallback: next weekday at 09:00
        dt = datetime.now() + timedelta(days=1)
        while dt.strftime("%A") in ("Saturday", "Sunday"):
            dt += timedelta(days=1)
        book_date = dt.strftime("%Y-%m-%d")
        book_time = "09:00"

    result = receptionist.process_request("book", {
        "patient_phone": "5551234567",
        "appointment_type": "cleaning",
        "date": book_date,
        "time": book_time,
    })
    print(result)

    # 4. FAQ — insurance question
    print("\n[4] Patient FAQ — Insurance")
    print("-" * 40)
    result = receptionist.process_request("faq", {
        "message": "Do you accept Delta Dental insurance?"
    })
    print(result)

    # 5. FAQ — emergency
    print("\n[5] Patient FAQ — Dental Emergency")
    print("-" * 40)
    result = receptionist.process_request("faq", {
        "message": "I have severe tooth pain and swelling, what should I do?"
    })
    print(result)

    # 6. Patient lookup
    print("\n[6] Patient Lookup")
    print("-" * 40)
    result = receptionist.process_request("lookup_patient", {"phone": "5551234567"})
    print(result)

    # 7. Reminders cycle
    print("\n[7] Reminder Engine Cycle")
    print("-" * 40)
    result = receptionist.process_request("reminders", {})
    print(result)

    # 8. Second patient — minimal walk-in booking
    print("\n[8] Walk-in Booking (new patient, no prior intake)")
    print("-" * 40)
    options2 = scheduler_temp.next_available_slots("exam", days_ahead=7)
    if options2:
        d2 = options2[0]["date"]
        t2 = options2[0]["slots"][0]
    else:
        d2 = book_date
        t2 = "10:30"

    result = receptionist.process_request("book", {
        "first_name": "James",
        "last_name": "Okafor",
        "patient_phone": "5559876543",
        "appointment_type": "exam",
        "date": d2,
        "time": t2,
    })
    print(result)

    # 9. FAQ — unknown question (fallback)
    print("\n[9] FAQ — Unknown Question (fallback)")
    print("-" * 40)
    result = receptionist.process_request("faq", {
        "message": "Do you offer nitrous oxide sedation?"
    })
    print(result)

    # 10. Business metrics
    print("\n[10] Business Metrics Summary")
    print("-" * 40)
    result = receptionist.process_request("metrics", {})
    print(result)

    print("\n✅ Demo complete. All data saved to:", MEMORY_DIR)
    log.info("Demo run completed successfully")


if __name__ == "__main__":
    _run_demo()