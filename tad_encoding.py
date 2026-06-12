"""
TAD — UTF-8 console fix (2026-06-12)

Windows consoles default to cp1252, so any print()/log containing
→ ✓ ✗ ✅ ❌ crashes with "'charmap' codec can't encode character".
Call force_utf8() once at the top of every entry-point script.

PYTHONIOENCODING is also exported so child processes spawned via
subprocess (code_executor, git hooks, etc.) inherit UTF-8 too —
no per-file symbol replacement needed.
"""

import os
import sys


def force_utf8():
    """Make stdout/stderr UTF-8 safe on Windows cp1252 consoles."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None and hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # never let the encoding fix itself crash a script
