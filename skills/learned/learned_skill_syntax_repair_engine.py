"""TAD Learned Skill Syntax Repair Engine

Detects, parses, and surgically repairs syntax errors in generated Python code.
Scans skills/learned/ for broken skills, fixes them in-place, and logs all repairs.
"""

import ast
import json
import os
from pathlib import Path
from datetime import datetime
from openai import OpenAI

client = OpenAI()

SKILLS_DIR = "skills/learned"
LOG_FILE = "memory/learned_skill_syntax_repair_engine_log.jsonl"
REGISTRY_FILE = "memory/skill_registry.json"


def detect_syntax_errors(code: str) -> dict:
    """Parse code with AST; return error details if syntax error found."""
    try:
        ast.parse(code)
        return {"has_error": False, "error": None, "line": None}
    except SyntaxError as e:
        return {
            "has_error": True,
            "error": str(e.msg),
            "line": e.lineno,
            "offset": e.offset,
            "text": e.text,
        }


def repair_syntax_error(filename: str, code: str) -> str:
    """Use Kimi to repair a single syntax error."""
    error_info = detect_syntax_errors(code)
    if not error_info["has_error"]:
        return code

    prompt = (
        "You are TAD's syntax repair expert. Fix ONLY the syntax error in this Python code. "
        "Return ONLY the corrected code, no explanation.\n\n"
        f"Error: {error_info['error']}\n"
        f"Line {error_info['line']}: {error_info['text']}\n\n"
        f"Code:\n{code}"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_action("repair_failed", {"filename": filename, "error": str(e)})
        return code


def validate_and_repair_all_skills() -> dict:
    """Scan skills/learned/ and repair all broken skills."""
    Path(SKILLS_DIR).mkdir(parents=True, exist_ok=True)
    Path("memory").mkdir(parents=True, exist_ok=True)

    results = {"scanned": 0, "broken": 0, "repaired": 0, "failed": 0, "details": []}

    for skill_file in Path(SKILLS_DIR).glob("*.py"):
        results["scanned"] += 1
        code = skill_file.read_text()
        error_info = detect_syntax_errors(code)

        if error_info["has_error"]:
            results["broken"] += 1
            repaired_code = repair_syntax_error(skill_file.name, code)
            error_check = detect_syntax_errors(repaired_code)

            if not error_check["has_error"]:
                skill_file.write_text(repaired_code)
                results["repaired"] += 1
                results["details"].append(
                    {
                        "file": skill_file.name,
                        "original_error": error_info["error"],
                        "status": "repaired",
                    }
                )
                log_action("skill_repaired", {"file": skill_file.name, "line": error_info["line"]})
            else:
                results["failed"] += 1
                results["details"].append(
                    {
                        "file": skill_file.name,
                        "original_error": error_info["error"],
                        "status": "failed_to_repair",
                    }
                )
                log_action("repair_failed", {"file": skill_file.name})

    return results


def log_action(action: str, details: dict) -> None:
    """Log action to JSONL file."""
    Path("memory").mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        **details,
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    """Run full syntax repair cycle."""
    print("\n[TAD] Syntax Repair Engine Starting...\n")

    results = validate_and_repair_all_skills()

    print(f"Scanned: {results['scanned']}")
    print(f"Broken: {results['broken']}")
    print(f"Repaired: {results['repaired']}")
    print(f"Failed: {results['failed']}")

    for detail in results["details"]:
        status_icon = "✓" if detail["status"] == "repaired" else "✗"
        print(f"{status_icon} {detail['file']}: {detail['status']}")

    log_action("repair_cycle_complete", results)
    print(f"\nLog: {LOG_FILE}")


if __name__ == "__main__":
    main()