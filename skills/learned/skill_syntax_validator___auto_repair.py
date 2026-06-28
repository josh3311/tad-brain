"""TAD Syntax Validator & Auto-Repair Engine"""
import ast
import json
import os
from pathlib import Path
from datetime import datetime
from openai import OpenAI

LEARNED_SKILLS_DIR = Path("./memory/skills/learned")
LOG_FILE = Path("./memory/skill_syntax_validator___auto_repair_log.jsonl")
REGISTRY_FILE = Path("./memory/skill_registry.json")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def validate_syntax(code: str) -> tuple[bool, str]:
    """Check if Python code is syntactically valid."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def scan_skills() -> dict:
    """Scan all learned skills and validate syntax."""
    if not LEARNED_SKILLS_DIR.exists():
        return {}
    
    results = {}
    for skill_file in LEARNED_SKILLS_DIR.glob("*.py"):
        if skill_file.name.startswith("_"):
            continue
        try:
            code = skill_file.read_text(encoding="utf-8")
            valid, error = validate_syntax(code)
            results[skill_file.name] = {
                "valid": valid,
                "error": error,
                "path": str(skill_file),
                "size": len(code)
            }
        except Exception as e:
            results[skill_file.name] = {
                "valid": False,
                "error": f"Read error: {str(e)}",
                "path": str(skill_file),
                "size": 0
            }
    return results


def repair_syntax(code: str, error_msg: str) -> str:
    """Use Kimi API to repair syntax errors."""
    prompt = (
        "You are TAD's syntax repair engine. Fix the following Python code "
        "that has syntax errors. Return ONLY valid Python code, no explanation.\n\n"
        f"Error: {error_msg}\n\n"
        f"Code:\n{code}"
    )
    
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return ""


def apply_repair(skill_file: Path, repaired_code: str) -> bool:
    """Write repaired code back to file."""
    try:
        skill_file.write_text(repaired_code, encoding="utf-8")
        return True
    except Exception as e:
        return False


def log_action(action: str, skill: str, status: str, details: str = ""):
    """Log all actions to JSONL log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "skill": skill,
        "status": status,
        "details": details
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Log write error: {e}")


def update_registry(scan_results: dict):
    """Update skill registry with validation results."""
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        if REGISTRY_FILE.exists():
            registry = json.loads(REGISTRY_FILE.read_text())
        else:
            registry = {}
        
        for skill_name, result in scan_results.items():
            if skill_name not in registry:
                registry[skill_name] = {}
            registry[skill_name].update({
                "last_validated": datetime.utcnow().isoformat(),
                "syntax_valid": result["valid"],
                "error": result["error"]
            })
        
        REGISTRY_FILE.write_text(json.dumps(registry, indent=2))
    except Exception as e:
        log_action("update_registry", "all", "FAILED", str(e))


def main():
    """Main validator and auto-repair loop."""
    print("TAD Syntax Validator & Auto-Repair Engine Starting...")
    log_action("startup", "system", "STARTED", "Scanner initialized")
    
    scan_results = scan_skills()
    broken_skills = {k: v for k, v in scan_results.items() if not v["valid"]}
    
    print(f"Scanned {len(scan_results)} skills. Found {len(broken_skills)} with errors.")
    
    for skill_name, info in broken_skills.items():
        skill_path = Path(info["path"])
        original_code = skill_path.read_text(encoding="utf-8")
        
        print(f"\nRepairing {skill_name}...")
        log_action("repair_attempt", skill_name, "STARTED", info["error"])
        
        repaired = repair_syntax(original_code, info["error"])
        
        if repaired:
            valid, err = validate_syntax(repaired)
            if valid:
                if apply_repair(skill_path, repaired):
                    log_action("repair_complete", skill_name, "SUCCESS", "Code repaired and applied")
                    print(f"✓ {skill_name} repaired successfully")
                else:
                    log_action("repair_complete", skill_name, "FAILED", "Could not write file")
            else:
                log_action("repair_complete", skill_name, "FAILED", f"Repaired code still invalid: {err}")
        else:
            log_action("repair_attempt", skill_name, "FAILED", "API returned empty response")
    
    update_registry(scan_results)
    log_action("shutdown", "system", "COMPLETE", f"Processed {len(scan_results)} skills")
    print("\nValidator cycle complete.")


if __name__ == "__main__":
    main()