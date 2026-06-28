"""
autonomous_skill_output_validation___format_enforcement.py
TAD's output validation and schema enforcement layer for learned skills.
Ensures all skill outputs conform to expected schemas and flags broken skills for repair.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

MEMORY_DIR = Path("memory")
SKILLS_DIR = Path("skills/learned")
LOG_FILE = MEMORY_DIR / "autonomous_skill_output_validation___format_enforcement_log.jsonl"
REGISTRY_FILE = MEMORY_DIR / "skill_registry.json"

EXPECTED_SCHEMAS = {
    "market_scan": {"status": str, "score": (int, float), "data": dict},
    "decision_score": {"decision": str, "confidence": (int, float), "reasoning": str},
    "finance_analysis": {"verdict": str, "amount": (int, float), "risk": str},
    "research_agent": {"findings": list, "sources": list, "confidence": (int, float)},
}


def ensure_dirs() -> None:
    """Ensure memory and skills directories exist."""
    MEMORY_DIR.mkdir(exist_ok=True, parents=True)
    SKILLS_DIR.mkdir(exist_ok=True, parents=True)


def log_action(action: str, details: Dict[str, Any]) -> None:
    """Log validation action to JSONL file."""
    ensure_dirs()
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "details": details
    }
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[LOG_ERROR] {e}")


def validate_output(
    skill_name: str,
    output: Any,
    expected_schema: Optional[Dict[str, type]] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate skill output against expected schema.
    Returns (is_valid, error_message).
    """
    if output is None:
        return False, "Output is None"

    if expected_schema is None:
        if skill_name in EXPECTED_SCHEMAS:
            expected_schema = EXPECTED_SCHEMAS[skill_name]
        else:
            return True, None

    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return False, f"Output is string but not valid JSON: {output[:100]}"

    if not isinstance(output, dict):
        return False, f"Output must be dict, got {type(output).__name__}"

    for key, expected_type in expected_schema.items():
        if key not in output:
            return False, f"Missing required key: {key}"

        value = output[key]
        if isinstance(expected_type, tuple):
            if not isinstance(value, expected_type):
                return False, f"Key '{key}' type mismatch. Expected {expected_type}, got {type(value).__name__}"
        else:
            if not isinstance(value, expected_type):
                return False, f"Key '{key}' type mismatch. Expected {expected_type.__name__}, got {type(value).__name__}"

    return True, None


def repair_skill(skill_name: str, error: str, output: Any) -> Dict[str, Any]:
    """
    Attempt to repair or restructure broken skill output.
    Returns corrected output dict or error record.
    """
    log_action("repair_attempt", {
        "skill_name": skill_name,
        "error": error,
        "raw_output": str(output)[:200]
    })

    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "skill_name": skill_name,
                "reason": "Could not parse output as JSON",
                "raw": output[:100]
            }

    if isinstance(output, dict):
        if skill_name in EXPECTED_SCHEMAS:
            schema = EXPECTED_SCHEMAS[skill_name]
            repaired = output.copy()
            for key in schema:
                if key not in repaired:
                    repaired[key] = None
            return repaired

    return {
        "status": "failed",
        "skill_name": skill_name,
        "reason": "Could not repair output",
        "type": type(output).__name__
    }


def flag_skill_for_repair(skill_name: str, error: str, severity: str = "medium") -> None:
    """Flag a skill as broken and needing repair."""
    ensure_dirs()
    try:
        with open(REGISTRY_FILE, "r") as f:
            registry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        registry = {"skills": []}

    for skill in registry.get("skills", []):
        if skill.get("name") == skill_name:
            skill["status"] = "broken"
            skill["severity"] = severity
            skill["error"] = error
            skill["flagged_at"] = datetime.utcnow().isoformat()
            break
    else:
        registry.setdefault("skills", []).append({
            "name": skill_name,
            "status": "broken",
            "severity": severity,
            "error": error,
            "flagged_at": datetime.utcnow().isoformat()
        })

    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        log_action("flag_error", {"skill": skill_name, "error": str(e)})

    log_action("skill_flagged", {
        "skill_name": skill_name,
        "severity": severity,
        "error": error
    })


def validate_skill_output(
    skill_name: str,
    output: Any,
    expected_schema: Optional[Dict[str, type]] = None
) -> Dict[str, Any]:
    """
    Main validation function. Validates, repairs, or flags skill output.
    Returns validated output or repair record.
    """
    is_valid, error_msg = validate_output(skill_name, output, expected_schema)

    if is_valid:
        log_action("validation_passed", {
            "skill_name": skill_name,
            "output_type": type(output).__name__
        })
        if isinstance(output, str):
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return output
        return output

    log_action("validation_failed", {
        "skill_name": skill_name,
        "error": error_msg,
        "output_sample": str(output)[:150]
    })

    repaired = repair_skill(skill_name, error_msg, output)

    if repaired.get("status") == "failed":
        flag_skill_for_repair(skill_name, error_msg, severity="high")
        log_action("repair_failed", {
            "skill_name": skill_name,
            "reason": repaired.get("reason")
        })
    else:
        log_action("repair_successful", {
            "skill_name": skill_name,
            "repaired_output": repaired
        })

    return repaired


def register_schema(skill_name: str, schema: Dict[str, type]) -> None:
    """Register a custom schema for a skill."""
    EXPECTED_SCHEMAS[skill_name] = schema
    log_action("schema_registered", {
        "skill_name": skill_name,
        "schema_keys": list(schema.keys())
    })


def main() -> None:
    """Demonstrate validation system."""