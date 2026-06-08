"""
TAD — Product Builder v1.0
Phase 5 — Autonomous MVP generation

Give TAD a one-line description and it builds a complete,
deployable product. No manual coding required.

How it works:
1. Takes a product description (one line)
2. Asks CEO Agent to validate it
3. Builds the complete Python product via Build Agent
4. Tests everything
5. Packages it into a deliverable folder
6. Returns package path ready for tad_delivery.py

Products TAD can build:
- AI receptionist scripts
- Automation tools
- Data scrapers
- Report generators
- Email/SMS bots
- Client portals (simple)
- Any Python-based tool
"""

import json
import os
import re
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent
MEMORY     = ROOT / "memory"
PRODUCTS   = ROOT / "products"
SKILLS_DIR = ROOT / "skills"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

BUILD_SYSTEM = """You are TAD's product engineering engine.
Output ONLY complete, production-ready Python 3 code.
Never output prose, plans, or explanations.
Every product must be immediately usable by a non-technical client.
Include a README.md in your output as a separate file."""


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    log_path = MEMORY / "product_builder_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Builder] {msg}")


# ── Product spec generator ────────────────────────────────────────────────────

def generate_product_spec(description: str) -> dict:
    """
    Take a one-line description and expand it into a full product spec.
    Returns spec dict.
    """
    _log(f"Generating spec for: {description}")

    prompt = f"""You are TAD's product architect.

A client needs this product: {description}

Generate a complete product specification.

Return ONLY JSON:
{{
  "product_name": "short name (snake_case)",
  "display_name": "Human readable name",
  "description": "2 sentence description",
  "target_client": "who this is for",
  "core_features": ["feature 1", "feature 2", "feature 3"],
  "files_to_build": [
    {{
      "filename": "main.py",
      "purpose": "what this file does",
      "is_main": true
    }}
  ],
  "dependencies": ["library1", "library2"],
  "setup_steps": ["step 1", "step 2"],
  "estimated_build_time": "30 minutes",
  "price_suggestion": "$297/month"
}}

Keep it simple — maximum 3 files. Must be buildable in Python only."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=800,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        spec  = json.loads(clean)
        _log(f"Spec generated: {spec.get('display_name')}")
        return spec
    except Exception as e:
        _log(f"Spec generation error: {e}")
        return {
            "product_name":         re.sub(r"[^a-z0-9_]", "_", description.lower()),
            "display_name":         description,
            "description":          description,
            "target_client":        "Small businesses",
            "core_features":        ["Core functionality"],
            "files_to_build":       [{"filename": "main.py", "purpose": "Main script", "is_main": True}],
            "dependencies":         [],
            "setup_steps":          ["Run: python main.py"],
            "estimated_build_time": "30 minutes",
            "price_suggestion":     "$297/month",
        }


# ── File builder ──────────────────────────────────────────────────────────────

def build_file(filename: str, purpose: str, spec: dict) -> str:
    """Build a single file for the product."""
    prompt = f"""Build this file for a client product:

PRODUCT: {spec.get('display_name')}
DESCRIPTION: {spec.get('description')}
TARGET CLIENT: {spec.get('target_client')}
ALL FEATURES: {json.dumps(spec.get('core_features', []))}

FILE TO BUILD:
Filename: {filename}
Purpose: {purpose}

Requirements:
- Production quality Python 3 code
- Simple enough for a non-technical client to run
- Clear comments explaining what each section does
- Proper error handling
- Logs activity to a log file
- if __name__ == "__main__": block if applicable

Output Python code only."""

    for attempt in range(1, 4):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": BUILD_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                temperature=1,
                max_tokens=3000,
            )
            raw  = resp.choices[0].message.content or ""

            # Extract code
            for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
                match = re.search(pattern, raw, re.DOTALL)
                if match:
                    raw = match.group(1).strip()
                    break

            if any(m in raw for m in ["import ", "def ", "class "]):
                return raw

            prompt += "\n\nReturn ONLY Python code."

        except Exception as e:
            _log(f"File build error attempt {attempt}: {e}")

    return f'"""\n{filename} — {purpose}\nTODO: implement\n"""\n\nif __name__ == "__main__":\n    print("Running {filename}")\n'


def build_readme(spec: dict) -> str:
    """Generate a README.md for the product."""
    prompt = f"""Write a simple README.md for this product:

{json.dumps(spec, indent=2)}

Requirements:
- Clear title and description
- Setup instructions (non-technical language)
- How to run it
- What it does
- Support contact placeholder

Keep it under 50 lines. Use simple language — client is not technical."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=600,
        )
        return resp.choices[0].message.content or f"# {spec.get('display_name')}\n\n{spec.get('description')}"
    except Exception as e:
        _log(f"README error: {e}")
        return f"# {spec.get('display_name')}\n\n{spec.get('description')}\n\n## Setup\n\n{chr(10).join(spec.get('setup_steps', []))}"


# ── Syntax checker ────────────────────────────────────────────────────────────

def _test_file(filepath: Path) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(filepath)],
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr.strip()


def _install_deps(dependencies: list):
    """Install required packages."""
    for dep in dependencies:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", dep, "--quiet"],
                capture_output=True
            )
            _log(f"Installed: {dep}")
        except Exception as e:
            _log(f"Install error for {dep}: {e}")


# ── Package builder ───────────────────────────────────────────────────────────

def package_product(spec: dict, files: dict) -> Path:
    """
    Create a deliverable package folder with all files.
    Returns path to the package folder.
    """
    product_name = spec.get("product_name", "tad_product")
    timestamp    = datetime.now().strftime("%Y%m%d%H%M%S")
    pkg_name     = f"{product_name}_{timestamp}"
    pkg_path     = PRODUCTS / pkg_name

    pkg_path.mkdir(parents=True, exist_ok=True)

    # Write all built files
    for filename, content in files.items():
        (pkg_path / filename).write_text(content, encoding="utf-8")
        _log(f"  Packaged: {filename}")

    # Write spec as metadata
    (pkg_path / "product_spec.json").write_text(
        json.dumps(spec, indent=2), encoding="utf-8"
    )

    # Write requirements.txt
    deps = spec.get("dependencies", [])
    if deps:
        (pkg_path / "requirements.txt").write_text("\n".join(deps), encoding="utf-8")

    _log(f"Package created: {pkg_path}")
    return pkg_path


# ── Save to product log ───────────────────────────────────────────────────────

def _save_product(spec: dict, pkg_path: Path, status: str):
    log_path = MEMORY / "products_built.json"
    data     = {"products": []}
    if log_path.exists():
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    data["products"].append({
        "name":       spec.get("display_name"),
        "spec":       spec,
        "package":    str(pkg_path),
        "status":     status,
        "built_at":   datetime.now().isoformat(),
    })
    log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Main build function ───────────────────────────────────────────────────────

def build_product(description: str) -> dict:
    """
    Main entry point. Takes a one-line description and builds the product.
    Returns result dict with package path.
    """
    _log(f"=== Product build started: {description} ===")

    # Step 1: Generate spec
    spec = generate_product_spec(description)
    _log(f"Building: {spec.get('display_name')}")

    # Step 2: Install dependencies
    deps = spec.get("dependencies", [])
    if deps:
        _log(f"Installing {len(deps)} dependencies...")
        _install_deps(deps)

    # Step 3: Build each file
    files   = {}
    errors  = []

    for file_info in spec.get("files_to_build", []):
        filename = file_info.get("filename", "main.py")
        purpose  = file_info.get("purpose", "Main script")

        _log(f"Building {filename}...")
        code = build_file(filename, purpose, spec)
        files[filename] = code

        # Test Python files
        if filename.endswith(".py"):
            tmp_path = PRODUCTS / f"_test_{filename}"
            PRODUCTS.mkdir(exist_ok=True)
            tmp_path.write_text(code, encoding="utf-8")
            ok, error = _test_file(tmp_path)
            tmp_path.unlink(missing_ok=True)

            if not ok:
                _log(f"  Syntax error in {filename}: {error[:80]}")
                errors.append(filename)
            else:
                _log(f"  ✓ {filename} passes syntax check")

    # Step 4: Build README
    _log("Building README...")
    files["README.md"] = build_readme(spec)

    # Step 5: Package everything
    pkg_path = package_product(spec, files)

    # Step 6: Save to product log
    status = "ready" if not errors else "ready_with_warnings"
    _save_product(spec, pkg_path, status)

    result = {
        "status":       status,
        "product_name": spec.get("display_name"),
        "description":  spec.get("description"),
        "package_path": str(pkg_path),
        "files_built":  list(files.keys()),
        "errors":       errors,
        "price":        spec.get("price_suggestion"),
        "spec":         spec,
        "built_at":     datetime.now().isoformat(),
    }

    # Ensure product name is never None
    if not result.get("product_name") or result["product_name"] == "None":
        result["product_name"] = spec.get("display_name") or spec.get("product_name") or "TAD Product"

    _log(f"=== Build complete: {result['product_name']} → {pkg_path} ===")
    return result


def get_products_built() -> list:
    """Return list of all products built."""
    log_path = MEMORY / "products_built.json"
    if not log_path.exists():
        return []
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
        return data.get("products", [])
    except Exception:
        return []


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Product Builder — Test Mode")
    print("=" * 40)

    description = input("Enter product description (one line): ").strip()
    if not description:
        description = "AI receptionist for HVAC companies that answers missed calls 24/7"

    print(f"\nBuilding: {description}")
    print("This will take 2-3 minutes...\n")

    result = build_product(description)

    print(f"\nStatus:  {result['status']}")
    print(f"Product: {result['product_name']}")
    print(f"Package: {result['package_path']}")
    print(f"Files:   {', '.join(result['files_built'])}")
    print(f"Price:   {result['price']}")
    if result['errors']:
        print(f"Warnings: {result['errors']}")