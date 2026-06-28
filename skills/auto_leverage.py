"""
auto_leverage.py — TAD Intent Resolution Engine
================================================
Author:  Joshua Nkeng Abraham Fowah
Project: TAD (Total Autonomous Director) — josh3311/tad-brain
Phase:   6 | June 27, 2026

WHAT THIS FILE DOES:
Resolves the precise meaning and intent behind a task prompt
before any agent executes. Prevents silent guesswork, wrong builds,
and hallucinations from ambiguous input.

TWO MODES:
  Threshold Mode    → task_type='autonomous'
                      Picks most probable meaning, logs it, proceeds.
                      Used by: night_mode, scheduler, CSEO, all background tasks.

  Deep Clarity Mode → task_type='interactive'
                      Asks user one clarifying question before proceeding.
                      Used by: GUI chat, voice input, user-initiated tasks.

ENTRY POINT:
  from skills.auto_leverage import resolve_intent
  result = resolve_intent(prompt, task_type)

FULL CONCEPT DOC:
  C:\\TAD\\docs\\auto_leverage_framework.md
  C:\\TAD\\docs\\Auto_Leverage_Framework_TAD.docx
"""

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_providers import claude_json

log = logging.getLogger("auto_leverage")

# Words/phrases that commonly carry multiple meanings in TAD task context
AMBIGUOUS_TRIGGERS = [
    "fix", "update", "improve", "change", "build", "create",
    "check", "review", "analyse", "handle", "manage", "optimize",
    "it", "this", "that", "the thing", "the issue", "the problem"
]

def detect_ambiguous_terms(prompt: str) -> list:
    """Return list of flagged words found in the prompt."""
    prompt_lower = prompt.lower()
    return [word for word in AMBIGUOUS_TRIGGERS if word in prompt_lower]

def score_interpretations(prompt: str, flagged: list) -> tuple:
    """
    THRESHOLD MODE — ask Haiku to pick the most probable meaning.
    Returns (resolved_meaning: str, confidence: int)
    """
    raw = claude_json(
        system=(
            "You are TAD's intent resolver. Given a task prompt and a list of "
            "ambiguous words, return JSON with: "
            "{ \"resolved\": \"one-sentence interpretation of what the task means\", "
            "\"confidence\": <int 0-100> }. "
            "Be decisive. Pick the most probable meaning given the full prompt context. "
            "Return ONLY valid JSON, no preamble."
        ),
        user=(
            f"Prompt: {prompt}\n"
            f"Ambiguous words flagged: {flagged}\n"
            f"What does this prompt most likely mean? Return JSON only."
        )
    )
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result = {}
    return result.get("resolved", prompt), result.get("confidence", 70)

def build_clarifying_question(prompt: str, flagged: list) -> str:
    """
    DEEP CLARITY MODE — generate one precise clarifying question.
    Returns question string.
    """
    raw = claude_json(
        system=(
            "You are TAD's intent resolver. Given a task prompt and ambiguous words, "
            "return JSON with one clarifying question that will resolve the ambiguity. "
            "Format: { \"question\": \"your single question here\" }. "
            "Target the most ambiguous word directly. One question only. "
            "Return ONLY valid JSON, no preamble."
        ),
        user=(
            f"Prompt: {prompt}\n"
            f"Ambiguous words flagged: {flagged}\n"
            f"What is the single most important clarifying question?"
        )
    )
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result = {}
    return result.get("question", f"Can you clarify what you mean by: {flagged[0]}?")

def resolve_intent(prompt: str, task_type: str = "interactive") -> dict:
    """
    Main entry point for Auto-Leverage.

    Returns dict:
    {
        "resolved_prompt": str,       # prompt with intent locked in
        "mode": str,                  # "threshold" or "deep_clarity"
        "flagged": list,              # words that were ambiguous
        "confidence": int or None,    # threshold mode only
        "question": str or None,      # deep clarity mode only
        "needs_user_input": bool      # True = caller must ask user before proceeding
    }
    """
    flagged = detect_ambiguous_terms(prompt)

    # No ambiguity detected — pass through clean
    if not flagged:
        log.info(f"[AUTO-LEVERAGE] Clean prompt — no ambiguity detected.")
        return {
            "resolved_prompt": prompt,
            "mode": "passthrough",
            "flagged": [],
            "confidence": 100,
            "question": None,
            "needs_user_input": False
        }

    log.info(f"[AUTO-LEVERAGE] Flagged terms: {flagged} | mode: {task_type}")

    # THRESHOLD MODE — autonomous tasks decide themselves
    if task_type == "autonomous":
        resolved, confidence = score_interpretations(prompt, flagged)
        log.info(f"[AUTO-LEVERAGE] THRESHOLD — resolved as: '{resolved}' ({confidence}%)")
        return {
            "resolved_prompt": resolved,
            "mode": "threshold",
            "flagged": flagged,
            "confidence": confidence,
            "question": None,
            "needs_user_input": False
        }

    # DEEP CLARITY MODE — interactive tasks ask user
    else:
        question = build_clarifying_question(prompt, flagged)
        log.info(f"[AUTO-LEVERAGE] DEEP CLARITY — asking user: '{question}'")
        return {
            "resolved_prompt": None,
            "mode": "deep_clarity",
            "flagged": flagged,
            "confidence": None,
            "question": question,
            "needs_user_input": True
        }
