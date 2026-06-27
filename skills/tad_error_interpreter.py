"""
TAD Error Interpreter — plain-English error explanations for the Command Center.
Calls Claude Haiku with a strict 2-sentence format.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def interpret_error(raw_error: str) -> str:
    """
    Return a 2-sentence explanation of raw_error.
    Sentence 1: what broke. Sentence 2: what to do.
    Falls back to a canned message if the API call fails.
    """
    try:
        from config_providers import claude_chat
        prompt = (
            f"Explain in exactly 2 sentences. "
            f"Sentence 1: what broke. Sentence 2: what to do. "
            f"No jargon. No markdown. Keep it under 40 words total. "
            f"Error: {raw_error[:400]}"
        )
        result = claude_chat(
            system="You are a plain-English error explainer for a non-technical user.",
            user=prompt,
            max_tokens=80,
        )
        return result.strip() if result else _fallback(raw_error)
    except Exception:
        return _fallback(raw_error)


def _fallback(raw_error: str) -> str:
    short = raw_error[:100].replace("\n", " ")
    return f"An error occurred in TAD: {short}. Check the terminal for the full traceback."
