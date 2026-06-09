"""
TAD — Provider Configuration
Defines which AI model handles which type of task.

ARCHITECTURE DECISION (permanent):
- Claude Haiku  → reasoning, JSON, decisions, market scans, analysis
- Kimi K2       → code generation only (build agent, night mode)

This keeps costs low and reliability high.
"""

import os
import anthropic
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Claude client (reasoning + JSON) ─────────────────────────────────────────
claude = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY", "")
)
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# ── Kimi client (code generation only) ───────────────────────────────────────
kimi = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
KIMI_MODEL = "kimi-k2.6"


# ── Router ────────────────────────────────────────────────────────────────────

def get_reasoning_client():
    """Claude — for market scans, decisions, analysis, JSON tasks."""
    return claude, CLAUDE_MODEL


def get_code_client():
    """Kimi — for code generation only."""
    return kimi, KIMI_MODEL


def claude_chat(system: str, user: str, max_tokens: int = 1000) -> str:
    """
    Simple Claude call. Returns text response.
    Use for all reasoning, JSON, analysis tasks.
    """
    try:
        msg = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text or ""
    except Exception as e:
        print(f"[Claude] Error: {e}")
        return ""


def claude_json(system: str, user: str, max_tokens: int = 2000) -> str:
    """
    Claude call that enforces JSON output.
    Strips markdown fences automatically.
    """
    import re
    system_with_json = system + "\n\nALWAYS respond with valid JSON only. No markdown, no explanation."
    raw = claude_chat(system_with_json, user, max_tokens)
    clean = re.sub(r"```json|```", "", raw).strip()
    return clean


def kimi_code(system: str, user: str, max_tokens: int = 3000) -> str:
    """
    Kimi call for code generation.
    Returns raw code string.
    """
    import re
    try:
        resp = kimi.chat.completions.create(
            model=KIMI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=1,
            max_tokens=max_tokens,
        )
        raw = resp.choices[0].message.content or ""
        # Extract code from markdown fences
        for pattern in [r"```python\s*(.*?)```", r"```\s*(.*?)```"]:
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                return match.group(1).strip()
        return raw.strip()
    except Exception as e:
        print(f"[Kimi] Error: {e}")
        return ""


if __name__ == "__main__":
    print("TAD Provider Config — Test")
    print("=" * 40)

    print("\nTesting Claude (reasoning)...")
    result = claude_chat(
        "You are a helpful assistant.",
        "Say hello in one sentence."
    )
    print(f"Claude: {result}")

    print("\nTesting Claude JSON...")
    result = claude_json(
        "You are a market analyst.",
        'Return a JSON object with key "status" set to "working"'
    )
    print(f"Claude JSON: {result}")

    print("\nTesting Kimi (code)...")
    result = kimi_code(
        "You are a Python developer.",
        "Write a one-line Python function that adds two numbers."
    )
    print(f"Kimi code: {result}")
