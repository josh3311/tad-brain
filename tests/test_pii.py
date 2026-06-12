"""PII scanner — flags real PII, no false positives on clean system data."""
from tad_pii import scan_for_pii, redact_pii


def test_flags_email():
    r = scan_for_pii("contact jane.doe@example.com please")
    assert r["has_pii"] and r["counts"]["email"] == 1


def test_flags_phone():
    r = scan_for_pii("call me at 416-555-0199 or (905) 555-1234")
    assert r["counts"]["phone"] == 2


def test_flags_ssn_and_sin():
    assert scan_for_pii("SSN 123-45-6789")["counts"]["ssn_sin"] == 1
    assert scan_for_pii("SIN 123-456-789")["counts"]["ssn_sin"] == 1


def test_flags_address():
    r = scan_for_pii("ship to 42 Maple Street, Toronto")
    assert r["counts"]["address"] == 1


def test_clean_system_text_no_false_positives():
    clean = (
        "Health check 2026-06-12T01:00:00.544307 — 0 issues, score 29/40, "
        "revenue $1250.00, 33 tests passed, PID 18432, v0.4.1"
    )
    r = scan_for_pii(clean)
    assert r["has_pii"] is False
    assert r["flags"] == []


def test_masked_flags_never_contain_full_match():
    r = scan_for_pii("jane.doe@example.com")
    assert "jane.doe@example.com" not in str(r)


def test_redact_pii():
    out = redact_pii("email jane.doe@example.com phone 416-555-0199")
    assert "jane.doe" not in out and "416-555" not in out
    assert "[REDACTED-EMAIL]" in out and "[REDACTED-PHONE]" in out
