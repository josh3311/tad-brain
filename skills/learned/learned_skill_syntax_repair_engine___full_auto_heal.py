"""
learned_skill_syntax_repair_engine___full_auto_heal.py
TAD's autonomous syntax fixer for broken learned skills.
Parses broken .py files, identifies error types, applies surgical repairs.
"""

import json
import os
import re
import ast
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

SKILLS_DIR = Path("skills/learned")
MEMORY_DIR = Path("memory")
LOG_FILE = MEMORY_DIR / "learned_skill_syntax_repair_engine___full_auto_heal_log.jsonl"
REGISTRY_FILE = MEMORY_DIR / "skill_registry.json"


def log_action(action: str, status: str, details: Dict = None) -> None:
    """Log repair actions to JSONL."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "status": status,
        "details": details or {}
    }
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"[LOG ERROR] {e}")


def identify_syntax_error(filepath: Path) -> Optional[Dict]:
    """Parse broken file, return error type and location."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"type": "read_error", "message": str(e)}

    try:
        ast.parse(content)
        return None  # No syntax error
    except SyntaxError as e:
        return {
            "type": "syntax_error",
            "line": e.lineno,
            "offset": e.offset,
            "msg": e.msg,
            "text": e.text.strip() if e.text else "",
        }
    except Exception as e:
        return {"type": "parse_error", "message": str(e)}


def repair_unterminated_string(lines: List[str], error_line: int) -> Tuple[List[str], bool]:
    """Fix unterminated string literal by closing quote."""
    if error_line < 1 or error_line > len(lines):
        return lines, False

    idx = error_line - 1
    line = lines[idx]

    # Count quotes (simple heuristic)
    double_quotes = line.count('"') - line.count('\\"')
    single_quotes = line.count("'") - line.count("\\'")

    if double_quotes % 2 == 1:
        lines[idx] = line.rstrip() + '"'
        return lines, True
    elif single_quotes % 2 == 1:
        lines[idx] = line.rstrip() + "'"
        return lines, True

    return lines, False


def repair_missing_colon(lines: List[str], error_line: int) -> Tuple[List[str], bool]:
    """Fix missing colon in if/for/def/class statements."""
    if error_line < 1 or error_line > len(lines):
        return lines, False

    idx = error_line - 1
    line = lines[idx].rstrip()

    # Check for statement keywords missing colon
    if re.match(r"^\s*(if|elif|else|for|while|def|class|try|except|finally|with)\b", line):
        if not line.endswith(":"):
            lines[idx] = line + ":"
            return lines, True

    return lines, False


def repair_mismatched_parens(lines: List[str]) -> Tuple[List[str], bool]:
    """Fix mismatched parentheses/brackets across file."""
    content = "\n".join(lines)
    open_parens = content.count("(") - content.count("\\(")
    open_brackets = content.count("[") - content.count("\\[")
    open_braces = content.count("{") - content.count("\\{")

    close_parens = content.count(")") - content.count("\\)")
    close_brackets = content.count("]") - content.count("\\]")
    close_braces = content.count("}") - content.count("\\}")

    repaired = False

    # Add missing closing parens
    while open_parens > close_parens:
        lines[-1] += ")"
        close_parens += 1
        repaired = True

    # Add missing closing brackets
    while open_brackets > close_brackets:
        lines[-1] += "]"
        close_brackets += 1
        repaired = True

    # Add missing closing braces
    while open_braces > close_braces:
        lines[-1] += "}"
        close_braces += 1
        repaired = True

    return lines, repaired


def repair_broken_skill(filepath: Path) -> Dict:
    """Attempt autonomous repair of broken skill file."""
    error_info = identify_syntax_error(filepath)

    if error_info is None:
        return {"file": str(filepath), "status": "ok", "message": "No syntax errors"}

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return {"file": str(filepath), "status": "failed", "error": str(e)}

    # Strip newlines for processing
    lines = [line.rstrip("\n") for line in lines]
    repaired = False

    # Apply targeted repairs
    if "unterminated string" in error_info.get("msg", "").lower():
        lines, repaired = repair_unterminated_string(lines, error_info.get("line"))

    elif "expected ':'" in error_info.get("msg", ""):
        lines, repaired = repair_missing_colon(lines, error_info.get("line"))

    # Always try paren matching
    lines, paren_repaired = repair_mismatched_parens(lines)
    repaired = repaired or paren_repaired

    if not repaired:
        return {
            "file": str(filepath),
            "status": "unrepaired",
            "error_type": error_info.get("type"),
            "error_msg": error_info.get("msg"),
            "line": error_info.get("line"),
        }

    # Validate repair
    try:
        ast.parse("\n".join(lines))
        # Write back
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return {
            "file": str(filepath),
            "status": "repaired",
            "error_type": error_info.get("type"),
            "line": error_info.get("line"),
        }
    except SyntaxError as e:
        return {
            "file": str(filepath),
            "status": "repair_failed",
            "original_error": error_info.get("msg"),
            "validation_error": e.msg,
        }


def scan_and_repair_all() -> Dict:
    """Scan all learned skills, identify and repair broken ones."""
    if not SKILLS_DIR.exists():
        return {"status": "error", "message": f"{SKILLS_DIR} not found"}

    broken_files = []
    repaired_files = []
    unrepaired_files = []

    for skill_file in sorted(SKILLS_DIR.glob("*.py")):
        if skill_file.name.startswith("_"):
            continue

        error_info = identify_syntax_error(skill_file)
        if error_info:
            broken_files.append(skill_file)
            result = repair_broken_skill(skill_file)
            log_action("repair_attempt", result["status"], result)

            if result["status"] == "repaired":
                repaired_files.append(skill_file.name)