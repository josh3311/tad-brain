#!/usr/bin/env python3
"""
memory/products/hvac_ai_receptionist/call_intake.py

HVAC AI Receptionist — Call Intake Form
Captures: caller name, phone, address, system type, problem description
Includes --test self-check mode.

TAD AI | CEO: Joshua Abraham
"""

import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
INTAKE_DIR = Path(__file__).parent / "intakes"


def _ensure_dirs():
    INTAKE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
SYSTEM_TYPES = [
    "central_ac",
    "heat_pump",
    "furnace",
    "mini_split",
    "boiler",
    "geothermal",
    "window_unit",
    "other",
]


def _validate_phone(raw: str) -> str:
    """Strip formatting, require 10 digits (US)."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"Invalid phone number: '{raw}'. Need 10 digits.")
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _validate_name(raw: str) -> str:
    raw = raw.strip()
    if len(raw) < 2:
        raise ValueError("Name must be at least 2 characters.")
    if not re.match(r"^[A-Za-z\s'\-\.]+$", raw):
        raise ValueError("Name contains invalid characters.")
    return raw.title()


def _validate_address(raw: str) -> str:
    raw = raw.strip()
    if len(raw) < 5:
        raise ValueError("Address seems too short. Please enter full address.")
    return raw


def _validate_system_type(raw: str) -> str:
    raw = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if raw not in SYSTEM_TYPES:
        raise ValueError(
            f"Unknown system type '{raw}'.\nValid options: {', '.join(SYSTEM_TYPES)}"
        )
    return raw


def _validate_problem(raw: str) -> str:
    raw = raw.strip()
    if len(raw) < 10:
        raise ValueError("Problem description must be at least 10 characters.")
    return raw


# ---------------------------------------------------------------------------
# Prompt helper — retries on bad input
# ---------------------------------------------------------------------------
def _prompt(label: str, validator, hint: str = "") -> str:
    while True:
        try:
            display = f"{label}"
            if hint:
                display += f" [{hint}]"
            display += ": "
            raw = input(display)
            return validator(raw)
        except ValueError as exc:
            print(f"  ⚠  {exc}")
        except (KeyboardInterrupt, EOFError):
            print("\nIntake cancelled.")
            sys.exit(0)


# ---------------------------------------------------------------------------
# Core intake form
# ---------------------------------------------------------------------------
def run_intake(stream=None) -> dict:
    """
    Interactive call intake form.
    Returns a dict with all captured fields + metadata.
    Optionally accepts a stream of pre-answered strings (for testing).
    """
    _ensure_dirs()

    answers = iter(stream) if stream else None

    def _input(prompt_text: str) -> str:
        if answers:
            val = next(answers)
            print(f"{prompt_text}{val}")
            return val
        return input(prompt_text)

    def _prompted(label: str, validator, hint: str = "") -> str:
        while True:
            try:
                display = label
                if hint:
                    display += f" [{hint}]"
                display += ": "
                raw = _input(display)
                return validator(raw)
            except ValueError as exc:
                print(f"  ⚠  {exc}")
                if answers:
                    raise  # don't loop forever in test mode

    print("\n" + "=" * 58)
    print("  🌡  HVAC AI RECEPTIONIST — NEW CALL INTAKE")
    print("=" * 58)
    print("  Please provide the caller's information below.\n")

    name = _prompted("Caller Name", _validate_name)
    phone = _prompted("Phone Number", _validate_phone, "10-digit US")
    address = _prompted("Service Address", _validate_address, "full street address")

    print(f"\n  System types: {', '.join(SYSTEM_TYPES)}")
    system_type = _prompted("System Type", _validate_system_type)

    print("\n  Briefly describe the problem (be specific):")
    problem = _prompted("Problem", _validate_problem)

    ticket_id = str(uuid.uuid4())[:8].upper()
    timestamp = datetime.utcnow().isoformat() + "Z"

    record = {
        "ticket_id": ticket_id,
        "timestamp": timestamp,
        "caller_name": name,
        "phone": phone,
        "service_address": address,
        "system_type": system_type,
        "problem_description": problem,
        "status": "new",
    }

    # Persist
    out_path = INTAKE_DIR / f"{timestamp[:10]}_{ticket_id}.json"
    out_path.write_text(json.dumps(record, indent=2))

    print("\n" + "-" * 58)
    print(f"  ✅  Intake saved — Ticket #{ticket_id}")
    print(f"  Name    : {name}")
    print(f"  Phone   : {phone}")
    print(f"  Address : {address}")
    print(f"  System  : {system_type}")
    print(f"  Problem : {problem[:80]}{'...' if len(problem) > 80 else ''}")
    print(f"  File    : {out_path}")
    print("-" * 58 + "\n")

    return record


# ---------------------------------------------------------------------------
# Self-check / --test mode
# ---------------------------------------------------------------------------
def _run_tests():
    import traceback

    PASS = "✅ PASS"
    FAIL = "❌ FAIL"
    results = []

    def check(name: str, fn):
        try:
            fn()
            results.append((PASS, name))
        except Exception as exc:
            results.append((FAIL, f"{name} — {exc}"))
            traceback.print_exc()

    # --- Phone validation ---
    def t_phone_valid():
        assert _validate_phone("8005551234") == "(800) 555-1234"
        assert _validate_phone("(800) 555-1234") == "(800) 555-1234"
        assert _validate_phone("18005551234") == "(800) 555-1234"
        assert _validate_phone("800.555.1234") == "(800) 555-1234"

    def t_phone_invalid():
        try:
            _validate_phone("12345")
            assert False, "Should have raised"
        except ValueError:
            pass

    # --- Name validation ---
    def t_name_valid():
        assert _validate_name("john doe") == "John Doe"
        assert _validate_name("O'Brien") == "O'Brien"

    def t_name_invalid():
        try:
            _validate_name("X")
            assert False, "Should have raised"
        except ValueError:
            pass

    # --- System type validation ---
    def t_system_valid():
        assert _validate_system_type("heat pump") == "heat_pump"
        assert _validate_system_type("Mini-Split") == "mini_split"
        assert _validate_system_type("furnace") == "furnace"

    def t_system_invalid():
        try:
            _validate_system_type("rocket engine")
            assert False, "Should have raised"
        except ValueError:
            pass

    # --- Problem validation ---
    def t_problem_valid():
        result = _validate_problem("Unit is blowing hot air all day.")
        assert len(result) >= 10

    def t_problem_invalid():
        try:
            _validate_problem("broken")
            assert False, "Should have raised"
        except ValueError:
            pass

    # --- Full intake (simulated) ---
    def t_full_intake():
        _ensure_dirs()
        answers = [
            "Jane Smith",
            "8005550199",
            "742 Evergreen Terrace, Springfield, IL 62701",
            "central_ac",
            "Unit stopped cooling yesterday afternoon. Strange clicking noise before shutdown.",
        ]
        record = run_intake(stream=answers)
        assert record["caller_name"] == "Jane Smith"
        assert record["phone"] == "(800) 555-0199"
        assert record["system_type"] == "central_ac"
        assert len(record["ticket_id"]) == 8
        assert record["status"] == "new"
        # Verify file was written
        files = list(INTAKE_DIR.glob(f"*_{record['ticket_id']}.json"))
        assert len(files) == 1
        loaded = json.loads(files[0].read_text())
        assert loaded["caller_name"] == "Jane Smith"
        # Cleanup
        files[0].unlink()

    check("Phone: valid formats", t_phone_valid)
    check("Phone: invalid rejected", t_phone_invalid)
    check("Name: valid formats", t_name_valid)
    check("Name: too short rejected", t_name_invalid)
    check("System type: valid aliases", t_system_valid)
    check("System type: unknown rejected", t_system_invalid)
    check("Problem: valid length", t_problem_valid)
    check("Problem: too short rejected", t_problem_invalid)
    check("Full intake simulation", t_full_intake)

    print("\n" + "=" * 58)
    print("  TAD SELF-CHECK RESULTS")
    print("=" * 58)
    passed = sum(1 for r in results if r[0] == PASS)
    for status, name in results:
        print(f"  {status}  {name}")
    print("-" * 58)
    print(f"  {passed}/{len(results)} tests passed")
    print("=" * 58 + "\n")

    if passed < len(results):
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        run_intake()