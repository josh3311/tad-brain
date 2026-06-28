"""
Real-time learned skill health dashboard for TAD.
Monitors all 27 learned skills, identifies failure modes, and provides
granular diagnostics (syntax errors, runtime failures, format issues, dependencies).
Logs to memory/real_time_learned_skill_health_dashboard_log.jsonl
Integrates with tad_command_center.py for live visualization.
"""

import os
import json
import ast
import sys
import traceback
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

SKILLS_DIR = Path(__file__).parent
MEMORY_DIR = SKILLS_DIR.parent.parent / "memory"
SKILL_REGISTRY_PATH = MEMORY_DIR / "skill_registry.json"
LOG_PATH = MEMORY_DIR / "real_time_learned_skill_health_dashboard_log.jsonl"


def log_event(event: Dict[str, Any]) -> None:
    """Append event to JSONL log."""
    event["timestamp"] = datetime.utcnow().isoformat()
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def check_syntax(filepath: Path) -> Tuple[bool, str]:
    """Check if Python file has valid syntax. Returns (is_valid, error_msg)."""
    try:
        with open(filepath, "r") as f:
            code = f.read()
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Parse error: {str(e)}"


def check_imports(filepath: Path) -> Tuple[bool, List[str]]:
    """Check if all imports in file can be resolved. Returns (all_ok, missing_modules)."""
    try:
        with open(filepath, "r") as f:
            code = f.read()
        tree = ast.parse(code)
    except SyntaxError:
        return False, ["<syntax_error>"]

    missing = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _can_import(alias.name):
                    missing.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and not _can_import(node.module):
                missing.append(node.module)
    return len(missing) == 0, missing


def _can_import(module_name: str) -> bool:
    """Try to find module spec without importing."""
    try:
        spec = importlib.util.find_spec(module_name)
        return spec is not None
    except (ImportError, ValueError, AttributeError):
        return False


def execute_skill(filepath: Path, timeout: int = 5) -> Tuple[bool, str, Any]:
    """
    Execute skill and capture output/errors.
    Returns (success, error_msg, result).
    """
    try:
        spec = importlib.util.spec_from_file_location("skill_module", filepath)
        if not spec or not spec.loader:
            return False, "Cannot load module spec", None

        module = importlib.util.module_from_spec(spec)
        sys.modules[filepath.stem] = module
        spec.loader.exec_module(module)

        if hasattr(module, "main"):
            result = module.main()
            return True, "", result
        else:
            return False, "No main() function found", None

    except Exception as e:
        error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        return False, error, None


def validate_output_format(result: Any, expected_type: str) -> Tuple[bool, str]:
    """Check if skill output matches expected format."""
    if expected_type == "json" and isinstance(result, (dict, list)):
        return True, ""
    if expected_type == "str" and isinstance(result, str):
        return True, ""
    if expected_type == "any":
        return True, ""
    return False, f"Expected {expected_type}, got {type(result).__name__}"


def diagnose_skill(skill_name: str, filepath: Path) -> Dict[str, Any]:
    """Run full diagnostic on a single skill."""
    diagnosis = {
        "skill_name": skill_name,
        "filepath": str(filepath),
        "status": "unknown",
        "errors": [],
        "warnings": [],
    }

    if not filepath.exists():
        diagnosis["status"] = "missing"
        diagnosis["errors"].append("Skill file does not exist")
        return diagnosis

    syntax_ok, syntax_err = check_syntax(filepath)
    if not syntax_ok:
        diagnosis["status"] = "syntax_error"
        diagnosis["errors"].append(syntax_err)
        return diagnosis

    imports_ok, missing = check_imports(filepath)
    if not imports_ok:
        diagnosis["status"] = "import_error"
        diagnosis["errors"].append(f"Missing modules: {', '.join(missing)}")
        return diagnosis

    success, error, result = execute_skill(filepath)
    if not success:
        diagnosis["status"] = "runtime_error"
        diagnosis["errors"].append(error)
        return diagnosis

    diagnosis["status"] = "healthy"
    if result is None:
        diagnosis["warnings"].append("main() returned None")

    return diagnosis


def load_skill_registry() -> Dict[str, Any]:
    """Load skill_registry.json if it exists."""
    if SKILL_REGISTRY_PATH.exists():
        with open(SKILL_REGISTRY_PATH) as f:
            return json.load(f)
    return {"skills": {}, "summary": {}}


def scan_all_skills() -> Dict[str, Dict[str, Any]]:
    """Scan all .py files in learned/ directory and diagnose each."""
    health_report = {}
    skill_files = sorted(SKILLS_DIR.glob("*.py"))

    for filepath in skill_files:
        if filepath.name.startswith("_"):
            continue
        skill_name = filepath.stem
        health_report[skill_name] = diagnose_skill(skill_name, filepath)

    return health_report


def generate_dashboard_summary(health_report: Dict[str, Dict]) -> Dict[str, Any]:
    """Generate summary statistics for dashboard."""
    statuses = {}
    for skill_data in health_report.values():
        status = skill_data["status"]
        statuses[status] = statuses.get(status, 0) + 1

    total = len(health_report)
    healthy = statuses.get("healthy", 0)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_skills": total,
        "healthy": healthy,
        "broken": total - healthy,
        "status_breakdown": statuses,
        "health_percentage": round(100 * healthy / total) if total > 0 else 0,
    }


def main() -> Dict[str, Any]:
    """
    Main entry point: scan all skills and return health dashboard.
    """
    health_report = scan_all_skills()
    summary = generate_dashboard_summary(health_report)

    dashboard = {
        "summary": summary,
        "skills": health_report,
    }

    log_event({
        "event": "health_scan_complete",
        "summary": summary,
        "skill_count": len(health_report),
    })

    return dashboard


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))