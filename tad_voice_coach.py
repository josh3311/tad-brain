"""
TAD — Voice Coach v1.0
Phase 4 — Live call coaching

TAD listens to Joshua's sales calls and coaches him in real time.
- Listens to the call via mic
- Transcribes what both parties say
- Analyzes the conversation in real time
- Tells Joshua exactly what to say next via popup + TTS
- Tracks objections and provides counter-arguments
- Scores the call after it ends
- Saves full transcript + coaching notes to memory
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent
MEMORY     = ROOT / "memory"
SKILLS_DIR = ROOT / "skills"
LOG_PATH   = MEMORY / "voice_coach_log.jsonl"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# ── Coaching config ───────────────────────────────────────────────────────────
COACH_INTERVAL   = 3    # analyze conversation every N utterances
MAX_SUGGESTION_LEN = 80 # keep suggestions short and speakable


# ── Logging ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    MEMORY.mkdir(exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[Coach] {msg}")


# ── Call session ──────────────────────────────────────────────────────────────

class CallSession:
    """Tracks a single coaching session."""

    def __init__(self, prospect_name: str = "Prospect",
                 product: str = "", context: str = ""):
        self.prospect_name  = prospect_name
        self.product        = product
        self.context        = context
        self.transcript     = []          # list of {speaker, text, ts}
        self.suggestions    = []          # coaching suggestions given
        self.objections     = []          # objections detected
        self.started_at     = datetime.now().isoformat()
        self.ended_at       = None
        self.call_score     = None
        self.utterance_count = 0
        self.active         = False
        self.stop_event     = threading.Event()

    def add_utterance(self, speaker: str, text: str):
        self.transcript.append({
            "speaker": speaker,
            "text":    text,
            "ts":      datetime.now().isoformat(),
        })
        self.utterance_count += 1

    def get_transcript_text(self, last_n: int = 10) -> str:
        recent = self.transcript[-last_n:]
        return "\n".join(
            f"{u['speaker']}: {u['text']}" for u in recent
        )

    def save(self):
        """Save session to memory."""
        MEMORY.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        path      = MEMORY / f"call_session_{timestamp}.json"
        data      = {
            "prospect":    self.prospect_name,
            "product":     self.product,
            "started_at":  self.started_at,
            "ended_at":    self.ended_at,
            "call_score":  self.call_score,
            "transcript":  self.transcript,
            "suggestions": self.suggestions,
            "objections":  self.objections,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _log(f"Session saved → {path.name}")
        return path


# ── Coaching engine ───────────────────────────────────────────────────────────

def get_coaching_suggestion(session: CallSession) -> str:
    """
    Analyze the conversation so far and return the next thing Joshua should say.
    Returns a short, direct coaching suggestion.
    """
    transcript = session.get_transcript_text(last_n=8)
    if not transcript:
        return ""

    # Load marketing agent skill for sales context
    skill_text = ""
    skill_path = SKILLS_DIR / "marketing_agent.md"
    if skill_path.exists():
        skill_text = skill_path.read_text(encoding="utf-8")[:1000]

    prompt = f"""You are TAD — Joshua's real-time sales coach.

CALL CONTEXT:
- Prospect: {session.prospect_name}
- Product: {session.product}
- Context: {session.context}

RECENT CONVERSATION:
{transcript}

SALES PRINCIPLES:
{skill_text[:500]}

Based on this conversation, what should Joshua say NEXT?

Rules:
- Give ONE specific sentence or question Joshua should say right now
- Under 20 words — Joshua needs to read it quickly
- Be direct — no "you could say" — just give the actual words
- If prospect raised an objection, give the counter-argument
- If conversation is going well, push toward next step
- If silence or stalling, give an engaging question

Return ONLY the suggestion text. Nothing else."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a real-time sales coach. Be ultra-brief and direct."},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=60,
        )
        suggestion = resp.choices[0].message.content.strip() or ""
        # Clean up any quotes
        suggestion = suggestion.strip('"\'')
        return suggestion[:MAX_SUGGESTION_LEN]

    except Exception as e:
        _log(f"Coaching suggestion error: {e}")
        return ""


def detect_objection(text: str) -> str | None:
    """
    Detect if the prospect raised an objection.
    Returns the objection type or None.
    """
    text_lower = text.lower()
    objections = {
        "price":     ["too expensive", "costs too much", "can't afford", "out of budget", "price"],
        "time":      ["not now", "bad time", "too busy", "later", "next month", "next year"],
        "trust":     ["never heard of", "who are you", "not sure", "seems risky", "prove it"],
        "need":      ["don't need", "already have", "works fine", "no problem with"],
        "authority": ["need to ask", "check with", "my partner", "my boss", "not my decision"],
    }
    for obj_type, phrases in objections.items():
        if any(p in text_lower for p in phrases):
            return obj_type
    return None


def score_call(session: CallSession) -> dict:
    """Score the call after it ends."""
    transcript = session.get_transcript_text(last_n=50)

    prompt = f"""Score this sales call for Joshua.

TRANSCRIPT:
{transcript}

PRODUCT: {session.product}
PROSPECT: {session.prospect_name}
OBJECTIONS DETECTED: {session.objections}
SUGGESTIONS GIVEN: {len(session.suggestions)}

Score on:
1. Rapport building (1-10)
2. Problem identification (1-10)
3. Objection handling (1-10)
4. Closing attempt (1-10)
5. Overall call quality (1-10)

Return ONLY JSON:
{{
  "rapport": 0,
  "problem_id": 0,
  "objection_handling": 0,
  "closing": 0,
  "overall": 0,
  "outcome": "closed/follow_up/lost/unknown",
  "top_strength": "one sentence",
  "top_improvement": "one sentence",
  "next_action": "what Joshua should do next"
}}"""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=300,
        )
        raw   = resp.choices[0].message.content or "{}"
        clean = re.sub(r"```json|```", "", raw).strip()
        return json.loads(clean)
    except Exception as e:
        _log(f"Call scoring error: {e}")
        return {"overall": 0, "outcome": "unknown", "next_action": "Review call transcript"}


# ── TTS for coaching suggestions ──────────────────────────────────────────────

def _speak_suggestion(text: str):
    """Speak coaching suggestion via pyttsx3 in background."""
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 200)  # faster for coaching
            voices = engine.getProperty("voices")
            if len(voices) > 1:
                engine.setProperty("voice", voices[1].id)
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            _log(f"TTS error: {e}")
    threading.Thread(target=_speak, daemon=True).start()


# ── Coaching popup ────────────────────────────────────────────────────────────

def _show_coaching_popup(suggestion: str, objection_type: str = None):
    """Show coaching suggestion as a popup overlay."""
    try:
        import customtkinter as ctk
        import tkinter as tk

        popup = ctk.CTkToplevel()
        popup.title("TAD Coach")
        popup.geometry("500x120+100+100")
        popup.configure(fg_color="#0a1020")
        popup.attributes("-topmost", True)  # always on top during call
        popup.attributes("-alpha", 0.92)    # slightly transparent

        # Color based on objection
        border_color = "#e24b4a" if objection_type else "#1d9e75"
        label_color  = "#e24b4a" if objection_type else "#1d9e75"
        prefix       = f"⚡ {objection_type.upper()} objection — " if objection_type else "💬 Say: "

        frame = ctk.CTkFrame(popup, fg_color="#0a1020",
                            border_color=border_color, border_width=2,
                            corner_radius=10)
        frame.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            frame,
            text=f"{prefix}{suggestion}",
            font=("Courier", 13, "bold"),
            text_color=label_color,
            wraplength=460,
            justify="left"
        ).pack(padx=16, pady=(14, 8))

        # Auto-close after 8 seconds
        popup.after(8000, popup.destroy)

    except Exception as e:
        _log(f"Popup error: {e}")
        # Fallback — just print
        print(f"\n💬 TAD COACH: {suggestion}\n")


# ── Main coaching loop ────────────────────────────────────────────────────────

def run_coaching_session(session: CallSession,
                          on_suggestion=None,
                          on_transcript_update=None):
    """
    Main coaching loop. Listens to call, coaches in real time.
    Runs in a background thread.

    on_suggestion(text, objection_type) — called when suggestion is ready
    on_transcript_update(speaker, text) — called when new utterance captured
    """
    try:
        from voice_input import listen_once
    except ImportError:
        _log("voice_input not found — cannot start coaching")
        return

    session.active = True
    _log(f"Coaching session started — {session.prospect_name}")

    while not session.stop_event.is_set():
        try:
            # Listen for next utterance
            text = listen_once()

            if session.stop_event.is_set():
                break

            if not text or len(text.split()) < 2:
                continue

            # Determine speaker (Joshua speaks shorter phrases in sales)
            # Simple heuristic — can be improved with speaker diarization
            speaker = "Joshua" if len(text.split()) < 8 else session.prospect_name
            session.add_utterance(speaker, text)

            if on_transcript_update:
                on_transcript_update(speaker, text)

            # Detect objection
            if speaker == session.prospect_name:
                obj_type = detect_objection(text)
                if obj_type and obj_type not in session.objections:
                    session.objections.append(obj_type)
                    _log(f"Objection detected: {obj_type}")

                    # Immediate coaching on objection
                    suggestion = get_coaching_suggestion(session)
                    if suggestion:
                        session.suggestions.append({
                            "suggestion": suggestion,
                            "trigger":    "objection",
                            "objection":  obj_type,
                            "ts":         datetime.now().isoformat(),
                        })
                        _log(f"Coaching: {suggestion}")
                        _speak_suggestion(suggestion)
                        if on_suggestion:
                            on_suggestion(suggestion, obj_type)
                        else:
                            _show_coaching_popup(suggestion, obj_type)
                        continue

            # Regular coaching every N utterances
            if session.utterance_count % COACH_INTERVAL == 0:
                suggestion = get_coaching_suggestion(session)
                if suggestion:
                    session.suggestions.append({
                        "suggestion": suggestion,
                        "trigger":    "regular",
                        "ts":         datetime.now().isoformat(),
                    })
                    _log(f"Coaching: {suggestion}")
                    _speak_suggestion(suggestion)
                    if on_suggestion:
                        on_suggestion(suggestion, None)
                    else:
                        _show_coaching_popup(suggestion)

        except Exception as e:
            if not session.stop_event.is_set():
                _log(f"Coaching loop error: {e}")
                time.sleep(1)

    # End of call
    session.active    = False
    session.ended_at  = datetime.now().isoformat()

    # Score the call
    _log("Scoring call...")
    session.call_score = score_call(session)
    _log(f"Call score: {session.call_score.get('overall')}/10 — {session.call_score.get('outcome')}")

    # Save session
    session.save()
    _log("Coaching session complete")


# ── Public API ────────────────────────────────────────────────────────────────

_active_session: CallSession | None = None


def start_coaching(prospect_name: str = "Prospect",
                   product: str = "",
                   context: str = "",
                   on_suggestion=None,
                   on_transcript_update=None) -> CallSession:
    """
    Start a live coaching session.
    Returns the CallSession object.

    Usage in tad_gui.py:
        from tad_voice_coach import start_coaching, stop_coaching
        session = start_coaching(
            prospect_name="Mike Johnson",
            product="HVAC Call Screener",
            on_suggestion=lambda text, obj: self._show_coaching_popup(text, obj)
        )
    """
    global _active_session

    session = CallSession(
        prospect_name=prospect_name,
        product=product,
        context=context,
    )
    _active_session = session

    t = threading.Thread(
        target=run_coaching_session,
        args=(session, on_suggestion, on_transcript_update),
        daemon=True,
        name="TADVoiceCoach"
    )
    t.start()
    _log(f"Coaching started for call with {prospect_name}")
    return session


def stop_coaching() -> dict | None:
    """Stop the active coaching session and return the call score."""
    global _active_session
    if _active_session and _active_session.active:
        _active_session.stop_event.set()
        score = _active_session.call_score
        _log("Coaching stopped")
        return score
    return None


def get_active_session() -> CallSession | None:
    return _active_session


def is_coaching() -> bool:
    return _active_session is not None and _active_session.active


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Voice Coach — Test Mode")
    print("=" * 40)
    print("Simulating a sales call coaching session...")
    print("TAD will listen and coach every 3 utterances")
    print("Press Ctrl+C to end the call\n")

    def on_suggestion(text: str, objection_type: str = None):
        if objection_type:
            print(f"\n⚡ [{objection_type.upper()} OBJECTION] TAD says: {text}\n")
        else:
            print(f"\n💬 TAD COACH: {text}\n")

    def on_transcript(speaker: str, text: str):
        print(f"  [{speaker}]: {text}")

    session = start_coaching(
        prospect_name="Test Prospect",
        product="AI Receptionist",
        context="Cold call — prospect hasn't heard of us",
        on_suggestion=on_suggestion,
        on_transcript_update=on_transcript,
    )

    print("Coaching session active. Speak naturally...")
    print("TAD will coach you in real time.\n")

    try:
        while is_coaching():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nEnding call...")
        score = stop_coaching()
        if score:
            print(f"\nCall Score: {score.get('overall')}/10")
            print(f"Outcome: {score.get('outcome')}")
            print(f"Strength: {score.get('top_strength')}")
            print(f"Improve: {score.get('top_improvement')}")
            print(f"Next: {score.get('next_action')}")
