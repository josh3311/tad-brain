import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from ddgs import DDGS

load_dotenv()


# ─────────────────────────────────────────────
#  TOOL: web_search
#  Uses DuckDuckGo — free, no API key needed
# ─────────────────────────────────────────────

def web_search(query: str) -> str:
    """Search the web using DuckDuckGo. Free, no key needed."""
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=8):
                results.append(
                    f"TITLE: {r.get('title', '')}\n"
                    f"URL: {r.get('href', '')}\n"
                    f"SUMMARY: {r.get('body', '')}\n"
                )
        if not results:
            return "[web_search] No results found."
        return "\n---\n".join(results)
    except Exception as e:
        return f"[web_search error] {str(e)}"


# ─────────────────────────────────────────────
#  TOOL: file_write
#  Saves content to /workflows folder
# ─────────────────────────────────────────────

def file_write(filename: str, content: str) -> str:
    """Write content to a file inside the workflows folder."""
    try:
        folder = Path("workflows")
        folder.mkdir(exist_ok=True)
        filepath = folder / filename
        filepath.write_text(content, encoding="utf-8")
        return f"[file_write] Saved to {filepath}"
    except Exception as e:
        return f"[file_write error] {str(e)}"


# ─────────────────────────────────────────────
#  TOOL: file_read
#  Reads a file from /workflows folder
# ─────────────────────────────────────────────

def file_read(filename: str) -> str:
    """Read content from a file inside the workflows folder."""
    try:
        filepath = Path("workflows") / filename
        if not filepath.exists():
            return f"[file_read] File not found: {filename}"
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        return f"[file_read error] {str(e)}"


# ─────────────────────────────────────────────
#  REGISTRY — maps tool names to functions
#  To add a new tool: add entry here + write fn
# ─────────────────────────────────────────────

TOOLS = {
    "web_search": web_search,
    "file_write": file_write,
    "file_read":  file_read,
}

# OpenAI-format schemas sent to Kimi
SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for real-time current information, market trends, news, opportunities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to look up"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Save a report, analysis, or document to a file in the workflows folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename to save as, e.g. market-analysis-june-2026.md"
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file"
                    }
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a previously saved report or file from the workflows folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "The filename to read"
                    }
                },
                "required": ["filename"]
            }
        }
    },
]


def call(name: str, args: dict) -> str:
    """Call a tool by name with args. Returns string result."""
    if name not in TOOLS:
        return f"[registry] Unknown tool: {name}"
    return TOOLS[name](**args)


def has(name: str) -> bool:
    return name in TOOLS