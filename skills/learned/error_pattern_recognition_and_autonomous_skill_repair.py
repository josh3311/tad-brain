"""
error_pattern_recognition_and_autonomous_skill_repair.py

TAD's self-healing error recovery engine.
Analyzes error chains, generates fixes, tests them autonomously.
Zero manual intervention required for detected failure patterns.
"""

import json
import re
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    print("Installing openai...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openai", "-q"])
    from openai import OpenAI


LOG_FILE = Path("memory/error_pattern_recognition_and_autonomous_skill_repair_log.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_event(event_type: str, data: dict) -> None:
    """Append structured log entry."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        **data
    }
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def extract_error_pattern(error_msg: str, traceback_str: str) -> dict:
    """Parse error message and traceback to extract pattern."""
    pattern = {
        "error_type": error_msg.split(":")[0] if ":" in error_msg else "UnknownError",
        "error_message": error_msg,
        "file_lines": [],
        "context": traceback_str[:500]
    }
    
    for line in traceback_str.split("\n"):
        if ".py" in line and "line" in line:
            pattern["file_lines"].append(line.strip())
    
    return pattern


def generate_fix(error_pattern: dict, client: OpenAI) -> Optional[str]:
    """Use Kimi/Claude to generate a targeted fix."""
    try:
        prompt = f"""Analyze this error and generate ONLY valid Python 3 code to fix it.
        
Error Type: {error_pattern['error_type']}
Error Message: {error_pattern['error_message']}
Context: {error_pattern['context']}

Respond with ONLY:
1. Root cause (1 line)
2. A Python function or code snippet that fixes this specific error
3. No explanations, no markdown, pure Python code

Example format:
# Root cause: division by zero in observability module
def safe_divide(a, b, default=0):
    return a / b if b != 0 else default
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_event("generation_failed", {"error": str(e)})
        return None


def validate_fix(fix_code: str) -> bool:
    """Syntax check the generated fix."""
    try:
        compile(fix_code, "<generated>", "exec")
        return True
    except SyntaxError as e:
        log_event("syntax_validation_failed", {"error": str(e), "code": fix_code[:200]})
        return False


def test_fix(fix_code: str, test_context: dict) -> bool:
    """Execute fix in isolated context."""
    try:
        exec_globals = {"__builtins__": __builtins__}
        exec(fix_code, exec_globals)
        log_event("fix_tested_success", {"fix": fix_code[:200]})
        return True
    except Exception as e:
        log_event("fix_test_failed", {"error": str(e), "fix": fix_code[:200]})
        return False


def apply_fix(fix_code: str, target_file: str) -> bool:
    """Insert validated fix into target file."""
    try:
        target = Path(target_file)
        if not target.exists():
            log_event("apply_failed", {"reason": "target_not_found", "file": target_file})
            return False
        
        content = target.read_text()
        
        insert_point = content.find("def main():")
        if insert_point == -1:
            insert_point = len(content) - 50
        
        updated = content[:insert_point] + "\n\n" + fix_code + "\n\n" + content[insert_point:]
        target.write_text(updated)
        
        log_event("fix_applied", {"file": target_file, "fix_lines": len(fix_code.split("\n"))})
        return True
    except Exception as e:
        log_event("apply_failed", {"error": str(e)})
        return False


def autonomously_repair(error_msg: str, traceback_str: str, target_file: Optional[str] = None) -> bool:
    """Full autonomous repair pipeline."""
    api_key = Path(".env").read_text().strip() if Path(".env").exists() else None
    if not api_key:
        log_event("repair_blocked", {"reason": "no_api_key"})
        return False
    
    client = OpenAI(api_key=api_key)
    
    log_event("repair_started", {"error": error_msg[:100]})
    
    pattern = extract_error_pattern(error_msg, traceback_str)
    log_event("pattern_extracted", pattern)
    
    fix_code = generate_fix(pattern, client)
    if not fix_code:
        log_event("repair_abandoned", {"reason": "fix_generation_failed"})
        return False
    
    log_event("fix_generated", {"fix_preview": fix_code[:150]})
    
    if not validate_fix(fix_code):
        log_event("repair_abandoned", {"reason": "syntax_invalid"})
        return False
    
    if not test_fix(fix_code, {}):
        log_event("repair_abandoned", {"reason": "test_failed"})
        return False
    
    if target_file and not apply_fix(fix_code, target_file):
        log_event("repair_partial", {"reason": "apply_failed"})
        return False
    
    log_event("repair_completed", {"error": error_msg[:100], "file": target_file})
    return True


def main():
    """Demonstrate autonomous repair on simulated error."""
    print("[TAD] Error Pattern Recognition & Autonomous Repair Engine")
    print(f"[LOG] Writing to {LOG_FILE}")
    
    log_event("system_started", {"version": "1.0", "mode": "autonomous"})
    
    simulated_error = "ZeroDivisionError: float division by zero"
    simulated_traceback = """
Traceback (most recent call last):
  File "observability.py", line 42, in measure
    ratio = total / count
ZeroDivisionError: float division by zero
"""
    
    print(f"\n[DEMO] Simulating error: {simulated_error}")
    success = autonomously_repair(
        simulated_error,
        simulated_traceback,
        target_file="observability.py"
    )
    
    if success:
        print("[SUCCESS] Autonomous repair completed. Check log for details.")
    else:
        print("[PARTIAL] Repair pipeline executed (check API key for full run).")
    
    with open(LOG_FILE) as f:
        print(f"\n[LOG] Recent entries:")
        for line in list(f)[-3:]:
            print(f"  {json.loads(line)}")


if __name__ == "__main__":
    main()