"""
TAD AI — Conversation Engine Script
Human Conversation Engine — TAD's Personality and Voice
Version: 1.0
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
SKILL_PATH = Path(__file__).parent / "conversation_engine.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# Mood categories TAD recognises
MOODS = {
    "frustrated":  "acknowledge frustration first, be direct and solution-focused",
    "excited":     "match the energy, build on it, be enthusiastic",
    "tired":       "be brief, direct, no fluff, get to the point fast",
    "thinking":    "listen more, ask one clarifying question, give space",
    "confused":    "use a simple analogy first, then explain step by step",
    "neutral":     "be natural, direct, conversational",
    "happy":       "be warm, match positive energy, keep momentum",
    "stressed":    "be calm, break it down, one thing at a time",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""


def _read(filename: str) -> dict:
    path = MEMORY / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write(filename: str, data: dict):
    MEMORY.mkdir(exist_ok=True)
    (MEMORY / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _log(msg: str):
    log_path = MEMORY / "conversation_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _get_recent_history(limit: int = 5) -> list:
    """Get recent conversation history."""
    history_path = MEMORY / "history.jsonl"
    if not history_path.exists():
        return []
    lines = history_path.read_text(encoding="utf-8").strip().splitlines()
    recent = []
    for line in lines[-limit:]:
        try:
            recent.append(json.loads(line))
        except Exception:
            pass
    return recent


# ── Mood detection ────────────────────────────────────────────────────────────

def detect_mood(message: str) -> str:
    """
    Detect Joshua's emotional tone from his message.
    Returns mood string.
    """
    message_lower = message.lower()

    # Pattern-based detection first (fast)
    if any(w in message_lower for w in ["ugh", "frustrated", "annoyed", "not working", "broken", "why"]):
        return "frustrated"
    if any(w in message_lower for w in ["amazing", "love it", "perfect", "great", "yes!", "let's go"]):
        return "excited"
    if any(w in message_lower for w in ["tired", "exhausted", "quick", "briefly", "short"]):
        return "tired"
    if any(w in message_lower for w in ["hmm", "thinking", "what if", "maybe", "wondering"]):
        return "thinking"
    if any(w in message_lower for w in ["confused", "don't understand", "what does", "explain"]):
        return "confused"
    if any(w in message_lower for w in ["stressed", "overwhelmed", "too much", "panic"]):
        return "stressed"

    return "neutral"


# ── Style learning ────────────────────────────────────────────────────────────

def load_style() -> dict:
    """Load Joshua's communication style preferences."""
    style = _read("conversation_style.json")
    if not style:
        # Default style profile
        style = {
            "preferred_length":    "concise",
            "prefers_analogies":   True,
            "direct_feedback":     True,
            "energy_level":        "medium",
            "topics_care_about":   ["business", "AI", "money", "TAD"],
            "phrases_he_uses":     [],
            "response_patterns":   {},
            "last_updated":        datetime.now().isoformat(),
        }
        _write("conversation_style.json", style)
    return style


def update_style(observation: str, category: str = "general"):
    """Update Joshua's communication style based on observations."""
    style = load_style()
    if "observations" not in style:
        style["observations"] = []
    style["observations"].append({
        "observation": observation,
        "category":    category,
        "date":        datetime.now().isoformat(),
    })
    style["last_updated"] = datetime.now().isoformat()
    _write("conversation_style.json", style)


# ── Response shaping ──────────────────────────────────────────────────────────

def shape_response(raw_response: str, mood: str,
                   message: str, context: str = "") -> str:
    """
    Shape a raw AI response to match TAD's personality and Joshua's mood.
    Returns the shaped response ready to speak or display.
    """
    skill  = _load_skill()
    style  = load_style()
    history = _get_recent_history(3)

    mood_instruction = MOODS.get(mood, MOODS["neutral"])

    prompt = f"""JOSHUA'S CURRENT MOOD: {mood}
MOOD INSTRUCTION: {mood_instruction}

JOSHUA'S MESSAGE: {message}

RAW RESPONSE TO SHAPE:
{raw_response}

COMMUNICATION STYLE PREFERENCES:
{json.dumps(style, indent=2)[:500]}

RECENT CONVERSATION CONTEXT:
{json.dumps([{"user": h.get("user", ""), "tad": h.get("tad", "")[:80]} for h in history], indent=2)}

ADDITIONAL CONTEXT: {context}

Shape this response to sound like TAD — a real, direct, intelligent
business partner who genuinely knows Joshua.

RULES:
- Never start with "I"
- No hollow affirmations ("Great question!", "Absolutely!", "Certainly!")
- Match Joshua's energy level based on his mood
- Keep it concise unless detail is truly needed
- End with forward momentum — what happens next
- Sound human — natural rhythm, not robotic
- No bullet points in casual responses
- One question maximum if you need to ask anything

Return ONLY the shaped response text. Nothing else."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=400,
        )
        shaped = resp.choices[0].message.content.strip() or raw_response
        _log(f"Response shaped for mood: {mood}")
        return shaped

    except Exception as e:
        _log(f"Response shaping error: {e}")
        return raw_response


# ── Full conversation processing ──────────────────────────────────────────────

def process_message(message: str, raw_response: str,
                    context: str = "") -> dict:
    """
    Full conversation processing pipeline.
    Detects mood → shapes response → updates style.
    Returns shaped response with metadata.
    """
    mood   = detect_mood(message)
    shaped = shape_response(raw_response, mood, message, context)

    # Learn from this interaction
    if len(message) > 20:
        words = message.lower().split()
        style = load_style()
        if "phrases_he_uses" not in style:
            style["phrases_he_uses"] = []
        # Track unique phrases Joshua uses
        for word in words:
            if len(word) > 4 and word not in style["phrases_he_uses"]:
                style["phrases_he_uses"].append(word)
        style["phrases_he_uses"] = style["phrases_he_uses"][-50:]
        _write("conversation_style.json", style)

    return {
        "original_message": message,
        "detected_mood":    mood,
        "shaped_response":  shaped,
        "timestamp":        datetime.now().isoformat(),
    }


def get_conversation_summary() -> str:
    """Generate a one-line summary of TAD's conversation style with Joshua."""
    style   = load_style()
    history = _get_recent_history(10)

    total_convos = len(history)
    mood_counts  = {}
    for entry in history:
        msg  = entry.get("user", "")
        mood = detect_mood(msg)
        mood_counts[mood] = mood_counts.get(mood, 0) + 1

    dominant_mood = max(mood_counts, key=mood_counts.get) if mood_counts else "neutral"
    return f"Joshua most often communicates in a {dominant_mood} tone. {total_convos} conversations logged."


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Conversation Engine Test")
    print("=" * 40)

    test_cases = [
        {
            "message":  "ugh this is not working again",
            "response": "The scheduler needs a threading fix. Here is the corrected code.",
        },
        {
            "message":  "yes! let's go that market scan looks amazing",
            "response": "The market scan found 3 opportunities above 28/40. Top one scores 35.",
        },
        {
            "message":  "I don't understand how the decision agent works",
            "response": "The decision agent scores each opportunity on 4 criteria out of 40.",
        },
    ]

    for test in test_cases:
        print(f"\nMessage: {test['message']}")
        result = process_message(test["message"], test["response"])
        print(f"Mood detected: {result['detected_mood']}")
        print(f"Shaped response: {result['shaped_response']}")
        print("-" * 40)

    print("\nConversation summary:")
    print(get_conversation_summary())