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

PRODUCT_TRIGGERS = [
    "build", "create", "develop", "ship", "market", "pitch",
    "score", "assess", "decide", "approve", "opportunity"
]

COMPLAINT_SKIP_TRIGGERS = [
    "health check", "ops check", "briefing", "p&l",
    "git push", "run test", "pytest"
]


def extract_complaint_intelligence(prompt: str, context: str = "") -> dict:
    """
    Before any agent builds or assesses, extract the real human pain
    behind the prompt. Answers 4 questions every agent needs to know:
    1. WHO has this problem (specific persona, not generic "developers")
    2. WHAT have they already tried and why it failed
    3. WHAT does a solution that actually resonates look like to them
    4. WHAT language do they use when describing this pain

    Called automatically when task involves: build, assess, pitch, market,
    score, decide. Skipped for: ops check, health check, briefing, scan.

    Returns dict:
    {
        "who": str,               # specific persona suffering this pain
        "tried_and_failed": str,  # what they've already tried
        "resonant_solution": str, # what would actually feel like relief
        "their_language": str,    # exact words they use about this pain
        "confidence": int,        # 0-100, how well we understood the pain
        "needs_research": bool    # True = market agent should search first
    }
    """
    if any(t in prompt.lower() for t in COMPLAINT_SKIP_TRIGGERS):
        return {
            "who": "", "tried_and_failed": "", "resonant_solution": "",
            "their_language": "", "confidence": 100, "needs_research": False
        }

    raw = claude_json(
        system=(
            "You are TAD's complaint intelligence engine. Given a product "
            "idea or task prompt, extract the real human pain behind it. "
            "Think like a user researcher who has read 1000 Reddit complaints "
            "about this problem. Return JSON only: "
            "{ \"who\": \"specific persona\", "
            "\"tried_and_failed\": \"what they tried\", "
            "\"resonant_solution\": \"what would feel like relief\", "
            "\"their_language\": \"exact words they use\", "
            "\"confidence\": <int 0-100>, "
            "\"needs_research\": <bool> }"
        ),
        user=(
            f"Task/prompt: {prompt}\n"
            f"Additional context: {context[:500] if context else 'none'}\n"
            f"Extract the real human pain behind this. Be specific about WHO "
            f"suffers, not generic. Return JSON only."
        )
    )
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        result = {}
    return {
        "who":                result.get("who", ""),
        "tried_and_failed":   result.get("tried_and_failed", ""),
        "resonant_solution":  result.get("resonant_solution", ""),
        "their_language":     result.get("their_language", ""),
        "confidence":         result.get("confidence", 70),
        "needs_research":     result.get("needs_research", False),
    }


def resolve_intent(prompt: str, task_type: str = "interactive") -> dict:
    """
    Main entry point for Auto-Leverage.

    Returns dict:
    {
        "resolved_prompt": str,           # prompt with intent locked in
        "mode": str,                      # "threshold", "deep_clarity", or "passthrough"
        "flagged": list,                  # words that were ambiguous
        "confidence": int or None,        # threshold mode only
        "question": str or None,          # deep clarity mode only
        "needs_user_input": bool,         # True = caller must ask user before proceeding
        "complaint_intelligence": dict    # real human pain behind product tasks
    }
    """
    flagged = detect_ambiguous_terms(prompt)

    # Extract complaint intelligence for product/build tasks
    needs_complaint_intel = any(t in prompt.lower() for t in PRODUCT_TRIGGERS)
    complaint_intel = {}
    if needs_complaint_intel:
        complaint_intel = extract_complaint_intelligence(prompt, context="")
        if complaint_intel.get("who"):
            log.info(f"[AUTO-LEVERAGE] Complaint intel — WHO: {complaint_intel['who'][:60]}")

    # No ambiguity detected — pass through clean
    if not flagged:
        log.info(f"[AUTO-LEVERAGE] Clean prompt — no ambiguity detected.")
        return {
            "resolved_prompt":       prompt,
            "mode":                  "passthrough",
            "flagged":               [],
            "confidence":            100,
            "question":              None,
            "needs_user_input":      False,
            "complaint_intelligence": complaint_intel,
        }

    log.info(f"[AUTO-LEVERAGE] Flagged terms: {flagged} | mode: {task_type}")

    # THRESHOLD MODE — autonomous tasks decide themselves
    if task_type == "autonomous":
        resolved, confidence = score_interpretations(prompt, flagged)
        log.info(f"[AUTO-LEVERAGE] THRESHOLD — resolved as: '{resolved}' ({confidence}%)")
        return {
            "resolved_prompt":       resolved,
            "mode":                  "threshold",
            "flagged":               flagged,
            "confidence":            confidence,
            "question":              None,
            "needs_user_input":      False,
            "complaint_intelligence": complaint_intel,
        }

    # DEEP CLARITY MODE — interactive tasks ask user
    else:
        question = build_clarifying_question(prompt, flagged)
        log.info(f"[AUTO-LEVERAGE] DEEP CLARITY — asking user: '{question}'")
        return {
            "resolved_prompt":       None,
            "mode":                  "deep_clarity",
            "flagged":               flagged,
            "confidence":            None,
            "question":              question,
            "needs_user_input":      True,
            "complaint_intelligence": complaint_intel,
        }
