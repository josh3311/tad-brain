"""
TAD Code Executor
Runs Python files safely using subprocess.
Auto-installs missing packages.
Returns test results back to the build loop.
"""

import subprocess
import sys
import re
import time
from pathlib import Path
from datetime import datetime


# ── Python executable inside venv ─────────────
PYTHON = str(Path(".venv/Scripts/python.exe"))
PIP    = str(Path(".venv/Scripts/pip.exe"))

# Fallback to system python if venv not found
if not Path(PYTHON).exists():
    PYTHON = sys.executable
    PIP    = str(Path(sys.executable).parent / "pip.exe")
    if not Path(PIP).exists():
        PIP = "pip"


def syntax_check(filepath: str) -> dict:
    """
    Check Python file for syntax errors.
    Fast — no execution, just compile check.
    """
    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, "-m", "py_compile", filepath],
            capture_output=True, text=True,
            timeout=15, cwd="."
        )
        duration = round(time.time() - start, 2)
        success  = result.returncode == 0
        return {
            "type":       "syntax_check",
            "file":       filepath,
            "success":    success,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
            "duration":   duration,
            "return_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"type": "syntax_check", "file": filepath, "success": False,
                "error": "timeout", "stderr": "Syntax check timed out"}
    except Exception as e:
        return {"type": "syntax_check", "file": filepath, "success": False,
                "error": str(e), "stderr": str(e)}


def run_file(filepath: str, args: list = None, timeout: int = 30) -> dict:
    """
    Execute a Python file and capture all output.
    Returns full result including stdout, stderr, return code.
    """
    start = time.time()
    cmd   = [PYTHON, filepath] + (args or [])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=".",
            encoding="utf-8", errors="replace"
        )
        duration = round(time.time() - start, 2)
        success  = result.returncode == 0

        return {
            "type":        "run",
            "file":        filepath,
            "success":     success,
            "stdout":      result.stdout[:3000],
            "stderr":      result.stderr[:2000],
            "return_code": result.returncode,
            "duration":    duration,
            "timed_out":   False
        }

    except subprocess.TimeoutExpired:
        return {
            "type":      "run",
            "file":      filepath,
            "success":   False,
            "stdout":    "",
            "stderr":    f"Execution timed out after {timeout}s",
            "return_code": -1,
            "duration":  timeout,
            "timed_out": True
        }
    except Exception as e:
        return {
            "type":      "run",
            "file":      filepath,
            "success":   False,
            "stdout":    "",
            "stderr":    str(e),
            "return_code": -1,
            "duration":  0,
            "timed_out": False
        }


def import_check(module_path: str) -> dict:
    """
    Check if a Python file can be imported without errors.
    Converts file path to module import.
    """
    # Convert path to module: tools/registry.py → tools.registry
    module = module_path.replace("/", ".").replace("\\", ".").replace(".py", "")
    module = module.lstrip(".")

    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, "-c", f"import {module}; print('import OK: {module}')"],
            capture_output=True, text=True,
            timeout=20, cwd=".",
            encoding="utf-8", errors="replace"
        )
        duration = round(time.time() - start, 2)
        success  = result.returncode == 0

        return {
            "type":     "import_check",
            "module":   module,
            "success":  success,
            "stdout":   result.stdout,
            "stderr":   result.stderr,
            "duration": duration
        }
    except Exception as e:
        return {
            "type":    "import_check",
            "module":  module,
            "success": False,
            "stderr":  str(e)
        }


def detect_missing_package(stderr: str) -> str | None:
    """
    Parse stderr for ModuleNotFoundError.
    Returns package name or None.
    """
    patterns = [
        r"ModuleNotFoundError: No module named '([^']+)'",
        r"ImportError: No module named '([^']+)'",
        r"ImportError: cannot import name .* from '([^']+)'",
    ]
    for pattern in patterns:
        match = re.search(pattern, stderr)
        if match:
            # Get root package name (e.g. "sklearn" from "sklearn.model_selection")
            pkg = match.group(1).split(".")[0]
            # Common package name mappings
            mappings = {
                "sklearn":    "scikit-learn",
                "cv2":        "opencv-python",
                "PIL":        "Pillow",
                "bs4":        "beautifulsoup4",
                "dotenv":     "python-dotenv",
                "ddgs":       "ddgs",
                "customtkinter": "customtkinter",
            }
            return mappings.get(pkg, pkg)
    return None


def install_package(package: str) -> dict:
    """
    Auto-install a Python package using pip.
    No approval needed — TAD installs what it needs.
    """
    print(f"[executor] Auto-installing: {package}")
    start = time.time()
    try:
        result = subprocess.run(
            [PIP, "install", package, "--quiet"],
            capture_output=True, text=True,
            timeout=120, cwd="."
        )
        duration = round(time.time() - start, 2)
        success  = result.returncode == 0

        if success:
            print(f"[executor] ✓ Installed {package} in {duration}s")
        else:
            print(f"[executor] ✗ Failed to install {package}: {result.stderr[:100]}")

        return {
            "package":    package,
            "success":    success,
            "stdout":     result.stdout,
            "stderr":     result.stderr,
            "duration":   duration
        }
    except Exception as e:
        return {"package": package, "success": False, "error": str(e)}


def test_file(filepath: str, timeout: int = 30) -> dict:
    """
    Full test pipeline for a single file:
    1. Syntax check
    2. Import check (auto-install if missing package)
    3. Run check
    Returns comprehensive result.
    """
    filepath = str(filepath)

    if not filepath.endswith(".py"):
        return {
            "file":    filepath,
            "success": True,
            "message": "Non-Python file — no test needed",
            "tests":   []
        }

    if not Path(filepath).exists():
        return {
            "file":    filepath,
            "success": False,
            "message": "File not found",
            "tests":   []
        }

    tests    = []
    auto_installed = []

    # ── Step 1: Syntax check ──
    syn = syntax_check(filepath)
    tests.append(syn)
    if not syn["success"]:
        return {
            "file":    filepath,
            "success": False,
            "message": f"Syntax error: {syn['stderr'][:200]}",
            "tests":   tests,
            "auto_installed": auto_installed
        }

    # ── Step 2: Import check with auto-install ──
    imp = import_check(filepath)
    tests.append(imp)

    if not imp["success"]:
        pkg = detect_missing_package(imp["stderr"])
        if pkg:
            install_result = install_package(pkg)
            auto_installed.append(pkg)
            tests.append({"type": "auto_install", **install_result})

            if install_result["success"]:
                # Retry import check
                imp2 = import_check(filepath)
                tests.append(imp2)
                if not imp2["success"]:
                    return {
                        "file":    filepath,
                        "success": False,
                        "message": f"Import still failing after installing {pkg}: {imp2['stderr'][:200]}",
                        "tests":   tests,
                        "auto_installed": auto_installed
                    }
            else:
                return {
                    "file":    filepath,
                    "success": False,
                    "message": f"Could not install {pkg}",
                    "tests":   tests,
                    "auto_installed": auto_installed
                }

    # ── Step 3: Quick run check ──
    # Only run files that have a safe main guard
    content = Path(filepath).read_text(encoding="utf-8", errors="replace")
    if 'if __name__' in content and '--test' in content:
        run = run_file(filepath, args=["--test"], timeout=timeout)
    else:
        # Just do syntax + import for files without explicit test mode
        run = {"type": "run", "success": True, "message": "Skipped (no --test flag)"}
    tests.append(run)

    all_passed = all(t.get("success", True) for t in tests)

    return {
        "file":          filepath,
        "success":       all_passed,
        "message":       "All tests passed" if all_passed else "Tests failed",
        "tests":         tests,
        "auto_installed": auto_installed
    }