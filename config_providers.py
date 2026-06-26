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


def claude_build(prompt: str, max_tokens: int = 8000) -> str:
    """
    Claude Sonnet (BUILD_MODEL env var) — primary Build Agent model.
    Better code quality than Kimi, no reasoning-token workarounds needed.
    Same ANTHROPIC_API_KEY as Haiku — no new key required.
    Falls back to kimi_code() automatically if this fails (via _generate_code).
    """
    build_model = os.getenv("BUILD_MODEL", "claude-sonnet-4-6")
    try:
        msg = claude.messages.create(
            model=build_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text or ""
    except Exception as e:
        print(f"[claude_build] Error: {e}")
        return ""


def minimax_code(prompt: str, max_tokens: int = 8000) -> str:
    """
    MiniMax M3 — Build Agent fallback #1.
    Fires automatically if claude_build() fails or returns empty.
    SWE-Bench score: 59.0% (competitive with Kimi K2.6's 58.6%).
    OpenAI-compatible API — same request structure as other providers.
    """
    import requests
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise ValueError("MINIMAX_API_KEY not set in .env")
    response = requests.post(
        "https://api.minimax.io/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": "MiniMax-M3",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens,
              "temperature": 0.6},
        timeout=120
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]


def deepseek_code(prompt: str, max_tokens: int = 8000) -> str:
    """
    DeepSeek V4 Pro — Build Agent fallback #2 (cheapest per token).
    Fires automatically if both claude_build() and minimax_code() fail.
    MIT licensed model. $1.74/$3.48 per 1M tokens input/output.
    OpenAI-compatible API.
    """
    import requests
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY not set in .env")
    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={"model": "deepseek-coder",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens,
              "temperature": 0.6},
        timeout=120
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]


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
