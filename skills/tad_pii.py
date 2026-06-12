"""
TAD — PII Handling Skill
Regex-only PII detection (no external API). Flags emails, phone numbers,
SIN/SSN-like patterns, and street addresses before client data is stored
in memory/.

Wired into the Ops Agent as a pre-storage check: ops_agent._write() scans
outgoing data and records any hits to memory/pii_audit.jsonl (matches are
masked in the audit log so the log itself never stores raw PII).
"""

import json
import re
from datetime import datetime
from pathlib import Path

ROOT       = Path(__file__).parent.parent
AUDIT_PATH = ROOT / "memory" / "pii_audit.jsonl"

# Order matters: more specific patterns (SSN/SIN) are checked before the
# generic phone pattern so "123-45-6789" is flagged once, as ssn_sin.
PATTERNS = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    # US SSN (123-45-6789) or Canadian SIN (123-456-789)
    "ssn_sin": re.compile(
        r"\b\d{3}[- ](?:\d{2}[- ]\d{4}|\d{3}[- ]\d{3})\b"
    ),
    # Phone: requires separators or +country code, which keeps timestamps,
    # scores and plain numbers from false-positiving.
    "phone": re.compile(
        r"(?<!\d)(?:\+?1[\s.\-])?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)"
    ),
    # Street address: number + name + street-type suffix
    "address": re.compile(
        r"\b\d{1,5}\s+[A-Za-z][A-Za-z']*(?:\s[A-Za-z][A-Za-z']*){0,2}\s+"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|"
        r"Court|Ct|Way|Crescent|Cres|Place|Pl|Terrace|Ter)\.?\b",
        re.IGNORECASE,
    ),
}


def _mask(value: str) -> str:
    """Mask a matched value so audit logs never store raw PII."""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def scan_for_pii(text: str) -> dict:
    """
    Scan text for PII. Returns:
      {
        "has_pii": bool,
        "flags": [{"type": "email", "masked": "jo***@***om", "position": 12}, ...],
        "counts": {"email": 1, "phone": 0, ...}
      }
    Use before writing any client-supplied data to memory/.
    """
    if not isinstance(text, str):
        text = json.dumps(text, default=str)

    flags  = []
    counts = {}
    claimed = []  # spans already flagged, so phone doesn't re-flag an SSN

    for pii_type, pattern in PATTERNS.items():
        counts[pii_type] = 0
        for m in pattern.finditer(text):
            span = (m.start(), m.end())
            if any(s < span[1] and span[0] < e for s, e in claimed):
                continue
            claimed.append(span)
            counts[pii_type] += 1
            flags.append({
                "type":     pii_type,
                "masked":   _mask(m.group(0)),
                "position": m.start(),
            })

    return {"has_pii": bool(flags), "flags": flags, "counts": counts}


def redact_pii(text: str, replacement: str = "[REDACTED-{type}]") -> str:
    """Return text with all detected PII replaced."""
    for pii_type, pattern in PATTERNS.items():
        text = pattern.sub(replacement.format(type=pii_type.upper()), text)
    return text


def check_before_storage(data, source: str = "unknown") -> dict:
    """
    Pre-storage gate for memory/ writes. Scans data (str or JSON-serializable),
    appends any hits to memory/pii_audit.jsonl, and returns the scan result.
    Non-blocking: the caller decides whether to redact or proceed.
    """
    result = scan_for_pii(data)
    if result["has_pii"]:
        AUDIT_PATH.parent.mkdir(exist_ok=True)
        entry = {
            "ts":     datetime.now().isoformat(),
            "source": source,
            "counts": result["counts"],
            "flags":  result["flags"],
        }
        with open(AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    return result


if __name__ == "__main__":
    dirty = ("Client Jane Doe, jane.doe@example.com, call 416-555-0199, "
             "SIN 123-456-789, lives at 42 Maple Street, Toronto")
    clean = ("Health check complete at 2026-06-12T01:00:00 — 0 issues, "
             "score 29/40, revenue $1250.00, 33 tests passed")

    print("DIRTY:", json.dumps(scan_for_pii(dirty), indent=2))
    print("CLEAN:", json.dumps(scan_for_pii(clean), indent=2))
    print("REDACTED:", redact_pii(dirty))
