"""
TAD — Memory file reader tool (2026-06-12)

Gives the Conversation Agent read-only, sandboxed access to memory/
so "what happened last night?" gets a real answer instead of
"no access". Registered as an Anthropic tool in tad_gui._call_claude.
"""

from pathlib import Path

ROOT = Path(__file__).parent

# Files the agent should reach for first on "what happened" questions
SUGGESTED_FILES = [
    "session_report.md",
    "decision_log.jsonl",
    "ceo_log.jsonl",
    "metrics.json",
    "pii_audit.jsonl",
]


def read_memory_file(filename: str) -> str:
    """Read a file from memory/ directory. Read-only, sandboxed."""
    SAFE_DIR = (ROOT / "memory").resolve()
    target = (SAFE_DIR / filename).resolve()
    if not str(target).startswith(str(SAFE_DIR)):
        return "Access denied: path outside memory/"
    if not target.exists():
        return f"File not found: {filename}"
    if not target.is_file():
        return f"Not a file: {filename}"
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Read error: {e}"
    if filename.endswith(".jsonl"):
        lines = content.strip().split("\n")
        content = "\n".join(lines[-20:])
    return content[:5000]


def list_memory_files() -> str:
    """List filenames available in memory/ (helps the agent pick a file)."""
    mem = ROOT / "memory"
    if not mem.exists():
        return "memory/ directory not found"
    names = sorted(p.name for p in mem.iterdir() if p.is_file())
    return "\n".join(names)


# Anthropic tool schema for the Conversation Agent
MEMORY_TOOL_SCHEMA = [
    {
        "name": "read_memory_file",
        "description": (
            "Read a file from TAD's memory/ directory (read-only, sandboxed). "
            "Use this to answer questions about what TAD did, built, decided "
            "or spent — e.g. session_report.md, decision_log.jsonl, "
            "ceo_log.jsonl, metrics.json, pii_audit.jsonl. "
            "jsonl files return only the last 20 lines."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename inside memory/, e.g. 'session_report.md'",
                }
            },
            "required": ["filename"],
        },
    },
    {
        "name": "list_memory_files",
        "description": "List the filenames available in TAD's memory/ directory.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def call_memory_tool(name: str, args: dict) -> str:
    """Dispatch a tool call by name. Returns a string result for the model."""
    if name == "read_memory_file":
        return read_memory_file(args.get("filename", ""))
    if name == "list_memory_files":
        return list_memory_files()
    return f"Unknown tool: {name}"
