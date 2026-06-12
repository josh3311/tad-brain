"""Shared test setup — put repo root and skills/ on sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
for p in (str(ROOT), str(ROOT / "skills")):
    if p not in sys.path:
        sys.path.insert(0, p)
