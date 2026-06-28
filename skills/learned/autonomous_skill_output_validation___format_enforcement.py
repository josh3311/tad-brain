"""
Autonomous Skill Output Validation — Format Enforcement Layer
Learned skills produce inconsistent output formats (JSON, plain text, dict, raw strings).
This module validates and standardizes all skill outputs before pipeline consumption.
"""

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, Union
from pathlib import Path


class SkillOutputValidator:
    """Validates and enforces consistent output format across all learned skills."""

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = Path(memory_dir)
        self.log_file = self.memory_dir / "autonomous_skill_output_validation___format_enforcement_log.jsonl"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def log_action(self, action: str, details: Dict[str, Any], status: str = "info") -> None:
        """Log validation actions to JSONL."""
        try:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "action": action,
                "status": status,
                "details": details,
            }
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[ERROR] Log write failed: {e}")

    def raw_decode(self, raw_output: str) -> Dict[str, Any]:
        """Extract JSON from raw text, handling trailing content (Claude quirk)."""
        try:
            # Try direct parse first
            return json.loads(raw_output.strip())
        except json.JSONDecodeError:
            pass

        # Find JSON block (starts { or [, ends } or ])
        brace_start = raw_output.find("{")
        bracket_start = raw_output.find("[")
        
        start = -1
        if brace_start >= 0 and bracket_start >= 0:
            start = min(brace_start, bracket_start)
        elif brace_start >= 0:
            start = brace_start
        elif bracket_start >= 0:
            start = bracket_start

        if start == -1:
            raise ValueError("No JSON object or array found in output")

        # Find matching closing brace/bracket
        depth = 0
        in_string = False
        escape = False
        end = -1

        for i in range(start, len(raw_output)):
            char = raw_output[i]

            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue

            if char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break

        if end == -1:
            raise ValueError("Unmatched JSON braces/brackets")

        json_str = raw_output[start:end]
        return json.loads(json_str)

    def validate_output(self, skill_name: str, raw_output: Any) -> Dict[str, Any]:
        """
        Validate and standardize skill output.
        Returns {"success": bool, "data": object, "error": str|null, "original_type": str}
        """
        original_type = type(raw_output).__name__

        # Already dict
        if isinstance(raw_output, dict):
            self.log_action(
                "validate_output",
                {
                    "skill": skill_name,
                    "input_type": original_type,
                    "output_type": "dict",
                    "size": len(raw_output),
                },
                status="success",
            )
            return {
                "success": True,
                "data": raw_output,
                "error": None,
                "original_type": original_type,
            }

        # String: try JSON parse with raw_decode fallback
        if isinstance(raw_output, str):
            try:
                parsed = self.raw_decode(raw_output)
                self.log_action(
                    "validate_output",
                    {
                        "skill": skill_name,
                        "input_type": original_type,
                        "output_type": "dict",
                        "parse_method": "raw_decode",
                    },
                    status="success",
                )
                return {
                    "success": True,
                    "data": parsed,
                    "error": None,
                    "original_type": original_type,
                }
            except Exception as e:
                # Return as plain text wrapped in dict
                self.log_action(
                    "validate_output",
                    {
                        "skill": skill_name,
                        "input_type": original_type,
                        "fallback": "text_wrap",
                        "error": str(e),
                    },
                    status="warn",
                )
                return {
                    "success": True,
                    "data": {"output": raw_output, "type": "text"},
                    "error": f"Could not parse JSON: {str(e)}",
                    "original_type": original_type,
                }

        # List
        if isinstance(raw_output, list):
            self.log_action(
                "validate_output",
                {
                    "skill": skill_name,
                    "input_type": original_type,
                    "output_type": "list",
                    "length": len(raw_output),
                },
                status="success",
            )
            return {
                "success": True,
                "data": {"items": raw_output},
                "error": None,
                "original_type": original_type,
            }

        # Other types: wrap
        self.log_action(
            "validate_output",
            {"skill": skill_name, "input_type": original_type, "fallback": "generic_wrap"},
            status="warn",
        )
        return {
            "success": True,
            "data": {"value": raw_output},
            "error": None,
            "original_type": original_type,
        }

    def enforce_schema(
        self, data: Dict[str, Any], required_keys: list = None, allowed_types: Dict[str, type] = None
    ) -> Dict[str, Any]:
        """
        Enforce schema on validated data.
        required_keys: list of key names that must exist
        allowed_types: dict mapping key names to required types
        """
        errors = []

        if required_keys:
            for key in required_keys:
                if key not in data:
                    errors.append(f"Missing required key: {key}")

        if allowed_types:
            for key, expected_type in allowed_types.items():
                if key in data and not isinstance(data[key], expected_type):
                    errors.append(f"Key '{key}' has type {type(data[key]).__name__}, expected {expected_type.__name__}")

        return {"valid": len(errors) == 0, "errors": errors, "data": data}


def main():
    """Test and demonstrate the validation layer."""
    validator = SkillOutputValidator()

    # Test cases
    test_cases = [
        ("skill_json", '{"result": true, "message": "success"}'),
        ("skill_json_with_trailing", '{"result": true}\nsome trailing text'),
        ("skill_dict", {"result": True, "message": "success"}),
        ("skill_list", [1, 2, 3, 4]),
        ("skill_plain_text", "This is plain output"),
        ("skill_number", 42),
    ]

    print("[SKILL OUTPUT VALIDATION]")
    print("=" * 60)

    for skill_name, raw_output in test_cases:
        result = validator.validate_output(skill_name, raw_output)
        print(f"\nSkill: {skill_name}")
        print