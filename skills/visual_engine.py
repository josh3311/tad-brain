"""
TAD AI — Visual Engine Script
Visual Explanation Engine — Show Don't Tell
Version: 1.0
"""

import json
import os
import re
import threading
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

ROOT          = Path(__file__).parent.parent
MEMORY        = ROOT / "memory"
VISUALS_DIR   = MEMORY / "visuals"
TRANSCRIPTS   = MEMORY / "visual_transcripts"
SKILL_PATH    = Path(__file__).parent / "visual_engine.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


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
    log_path = MEMORY / "visual_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[VISUAL] {msg}")


def _ensure_dirs():
    VISUALS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)


# ── Format decision engine ────────────────────────────────────────────────────

def decide_format(content: str, content_type: str = "") -> str:
    """
    Decide whether to use popup, video, or chained popups.
    Returns: 'popup', 'video', or 'chain'
    """
    content_lower = content.lower()

    # Video triggers
    video_triggers = [
        "how it works", "architecture", "flow", "process",
        "step by step", "evolution", "cycle", "pipeline",
        "walkthrough", "breakdown", "overview"
    ]

    # Chain triggers
    chain_triggers = [
        "multiple steps", "phases", "stage 1", "phase 1",
        "first then", "after that"
    ]

    if content_type in ["architecture", "financial_report", "process_explanation"]:
        return "video"

    if any(t in content_lower for t in video_triggers):
        return "video"

    if any(t in content_lower for t in chain_triggers):
        return "chain"

    # Default to popup for simple content
    word_count = len(content.split())
    if word_count > 150:
        return "video"
    elif word_count > 50:
        return "chain"
    else:
        return "popup"


# ── Script generator ──────────────────────────────────────────────────────────

def generate_visual_script(content: str, format_type: str,
                            title: str = "") -> dict:
    """
    Generate a visual script from content.
    Returns structured script for the chosen format.
    """
    skill = _load_skill()

    if format_type == "popup":
        prompt = f"""Convert this content into a clean popup display for TAD AI:

CONTENT: {content}
TITLE: {title if title else "TAD Update"}

Return ONLY a JSON object:
{{
  "title": "short clear title",
  "main_text": "2-3 sentences maximum",
  "highlight": "one key number or fact to emphasize",
  "action_item": "what Joshua should do next if anything",
  "color_theme": "green for positive, orange for neutral, red for alert"
}}"""

    elif format_type == "chain":
        prompt = f"""Convert this content into a chain of 2-4 popup screens for TAD AI:

CONTENT: {content}
TITLE: {title if title else "TAD Explanation"}

Return ONLY a JSON object:
{{
  "title": "overall title",
  "screens": [
    {{
      "screen_number": 1,
      "title": "screen title",
      "content": "2-3 sentences for this screen",
      "visual_hint": "what to show visually on this screen"
    }}
  ]
}}

Maximum 4 screens. Each screen under 3 sentences."""

    else:  # video
        prompt = f"""Convert this content into a 30-60 second video script for TAD AI:

CONTENT: {content}
TITLE: {title if title else "TAD Explanation"}

Return ONLY a JSON object:
{{
  "title": "video title",
  "duration_seconds": 45,
  "narration": "full narration text — what TAD says while video plays",
  "scenes": [
    {{
      "scene_number": 1,
      "duration_seconds": 10,
      "visual": "what appears on screen",
      "narration_segment": "what TAD says during this scene"
    }}
  ],
  "transcript": "full transcript of everything said",
  "key_points": ["main point 1", "main point 2", "main point 3"]
}}

Keep total under 60 seconds. 3-5 scenes maximum."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=1000,
        )
        raw    = resp.choices[0].message.content or "{}"
        clean  = re.sub(r"```json|```", "", raw).strip()
        script = json.loads(clean)
        script["format_type"] = format_type
        _log(f"Visual script generated: {format_type} — {title}")
        return script

    except Exception as e:
        _log(f"Script generation error: {e}")
        return {"format_type": format_type, "title": title, "error": str(e)}


# ── Chart builder ─────────────────────────────────────────────────────────────

def build_chart(data: dict, chart_type: str = "bar",
                title: str = "", save_path: Path = None) -> Path | None:
    """
    Build a matplotlib chart and save it.
    Returns path to saved chart image.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _ensure_dirs()
        if save_path is None:
            timestamp  = datetime.now().strftime("%Y%m%d%H%M%S")
            save_path  = VISUALS_DIR / f"chart_{timestamp}.png"

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor("#0d0d0f")
        ax.set_facecolor("#111115")

        labels = list(data.keys())
        values = list(data.values())

        colors = ["#7f77dd", "#ef9f27", "#1d9e75", "#534AB7", "#e24b4a"]

        if chart_type == "bar":
            bars = ax.bar(labels, values,
                         color=colors[:len(labels)], width=0.6)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width()/2,
                       bar.get_height() + 0.5,
                       f"{val:,.0f}" if isinstance(val, (int, float)) else str(val),
                       ha="center", va="bottom",
                       color="#e0e0f0", fontsize=10)

        elif chart_type == "line":
            ax.plot(labels, values, color="#7f77dd",
                   linewidth=2, marker="o", markersize=6)
            ax.fill_between(range(len(labels)), values,
                           alpha=0.1, color="#7f77dd")

        elif chart_type == "pie":
            ax.pie(values, labels=labels, colors=colors[:len(labels)],
                  autopct="%1.1f%%", textprops={"color": "#e0e0f0"})

        # Styling
        ax.set_title(title, color="#e0e0f0", fontsize=14, pad=15)
        ax.tick_params(colors="#555566")
        ax.spines["bottom"].set_color("#1e1e28")
        ax.spines["left"].set_color("#1e1e28")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlabel("", color="#555566")
        ax.set_ylabel("", color="#555566")
        for label in ax.get_xticklabels() + ax.get_yticklabels():
            label.set_color("#555566")
            label.set_fontsize(9)

        plt.tight_layout()
        plt.savefig(save_path, dpi=150,
                   facecolor="#0d0d0f", bbox_inches="tight")
        plt.close()

        _log(f"Chart saved: {save_path.name}")
        return save_path

    except ImportError:
        _log("matplotlib not installed — run: pip install matplotlib")
        return None
    except Exception as e:
        _log(f"Chart build error: {e}")
        return None


# ── Video generator ───────────────────────────────────────────────────────────

def generate_video(script: dict) -> Path | None:
    """
    Generate a local explanation video from a script.
    Uses matplotlib for visuals + pyttsx3 for narration.
    Returns path to video file or None if generation fails.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation

        _ensure_dirs()
        timestamp  = datetime.now().strftime("%Y%m%d%H%M%S")
        video_id   = f"tad_video_{timestamp}"
        video_path = VISUALS_DIR / f"{video_id}.mp4"

        title    = script.get("title", "TAD Explanation")
        scenes   = script.get("scenes", [])
        if not scenes:
            _log("No scenes in script — cannot generate video")
            return None

        _log(f"Generating video: {title} ({len(scenes)} scenes)")

        fig, ax = plt.subplots(figsize=(12, 7))
        fig.patch.set_facecolor("#0d0d0f")
        ax.set_facecolor("#0d0d0f")
        ax.axis("off")

        def update_frame(frame_num):
            ax.clear()
            ax.set_facecolor("#0d0d0f")
            ax.axis("off")

            # Which scene are we in
            total_frames = 30  # 30fps assumed
            scene_idx    = min(frame_num // total_frames, len(scenes) - 1)
            scene        = scenes[scene_idx]

            # Title
            ax.text(0.5, 0.9, title,
                   transform=ax.transAxes, ha="center",
                   fontsize=16, color="#7f77dd",
                   fontweight="bold")

            # Scene number indicator
            ax.text(0.5, 0.82,
                   f"{'●' * (scene_idx + 1)}{'○' * (len(scenes) - scene_idx - 1)}",
                   transform=ax.transAxes, ha="center",
                   fontsize=12, color="#444455")

            # Scene visual description
            visual_text = scene.get("visual", "")
            wrapped     = _wrap_text(visual_text, 60)
            ax.text(0.5, 0.55, wrapped,
                   transform=ax.transAxes, ha="center", va="center",
                   fontsize=13, color="#e0e0f0",
                   wrap=True, multialignment="center")

            # Narration segment at bottom
            narration = scene.get("narration_segment", "")[:80]
            ax.text(0.5, 0.1, f'"{narration}"',
                   transform=ax.transAxes, ha="center",
                   fontsize=10, color="#555566",
                   style="italic")

            return []

        fps          = 30
        total_frames = fps * script.get("duration_seconds", 30)

        anim = animation.FuncAnimation(
            fig, update_frame,
            frames=total_frames,
            interval=1000/fps,
            blit=False
        )

        writer = animation.FFMpegWriter(fps=fps, bitrate=1800)
        anim.save(str(video_path), writer=writer,
                 savefig_kwargs={"facecolor": "#0d0d0f"})
        plt.close()

        # Save transcript
        transcript = script.get("transcript", script.get("narration", ""))
        if transcript:
            save_transcript(video_id, transcript, title)

        _log(f"Video generated: {video_path.name}")
        return video_path

    except ImportError as e:
        _log(f"Missing dependency for video generation: {e}")
        _log("Run: pip install matplotlib moviepy")
        return None
    except Exception as e:
        _log(f"Video generation error: {e}")
        return None


def _wrap_text(text: str, width: int) -> str:
    """Simple text wrapper."""
    words  = text.split()
    lines  = []
    line   = []
    length = 0
    for word in words:
        if length + len(word) + 1 > width:
            lines.append(" ".join(line))
            line   = [word]
            length = len(word)
        else:
            line.append(word)
            length += len(word) + 1
    if line:
        lines.append(" ".join(line))
    return "\n".join(lines)


# ── Transcript management ─────────────────────────────────────────────────────

def save_transcript(video_id: str, text: str, title: str = ""):
    """Save video transcript for chat display."""
    _ensure_dirs()
    transcript = {
        "video_id":   video_id,
        "title":      title,
        "transcript": text,
        "saved_at":   datetime.now().isoformat(),
    }
    path = TRANSCRIPTS / f"{video_id}.json"
    path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
    _log(f"Transcript saved: {video_id}")
    return transcript


def get_transcript(video_id: str) -> str:
    """Retrieve transcript for a video."""
    path = TRANSCRIPTS / f"{video_id}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("transcript", "")
    return ""


# ── TTS narration ─────────────────────────────────────────────────────────────

def narrate(text: str):
    """Speak text using local pyttsx3 TTS — runs in background thread."""
    def _speak():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            voices = engine.getProperty("voices")
            if len(voices) > 1:
                engine.setProperty("voice", voices[1].id)
            engine.say(text[:500])
            engine.runAndWait()
        except Exception as e:
            _log(f"TTS error: {e}")

    threading.Thread(target=_speak, daemon=True).start()


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup_old_visuals(days: int = 30):
    """Delete video files older than specified days to save disk space."""
    from datetime import timedelta
    import time

    _ensure_dirs()
    cutoff  = time.time() - (days * 86400)
    deleted = []

    for video in VISUALS_DIR.glob("*.mp4"):
        if video.stat().st_mtime < cutoff:
            video.unlink()
            deleted.append(video.name)

    if deleted:
        _log(f"Cleaned up {len(deleted)} old video files")
    return deleted


# ── Main visual pipeline ──────────────────────────────────────────────────────

def explain(content: str, title: str = "",
            content_type: str = "", narrate_it: bool = True) -> dict:
    """
    Main entry point. Takes any content and produces the right visual.
    Returns dict with format used and output path/script.
    """
    _log(f"Visual explanation requested: {title or content[:50]}")

    format_type = decide_format(content, content_type)
    script      = generate_visual_script(content, format_type, title)

    result = {
        "format":    format_type,
        "title":     title,
        "script":    script,
        "timestamp": datetime.now().isoformat(),
    }

    # For videos — attempt generation
    if format_type == "video":
        video_path = generate_video(script)
        if video_path:
            result["video_path"] = str(video_path)
            if narrate_it:
                narration = script.get("narration", script.get("transcript", ""))
                if narration:
                    narrate(narration[:300])
        else:
            # Fallback to chain if video fails
            _log("Video generation failed — falling back to chain popup")
            result["format"] = "chain"
            result["script"] = generate_visual_script(content, "chain", title)

    elif format_type == "popup" and narrate_it:
        main_text = script.get("main_text", "")
        if main_text:
            narrate(main_text)

    _log(f"Visual explanation complete: {format_type}")
    return result


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Visual Engine Test")
    print("=" * 40)

    # Test format decision
    test_cases = [
        ("Market score: 35/40 — HVAC Call Screener approved", ""),
        ("Here is how the CSEO evolution cycle works step by step", "process_explanation"),
        ("Revenue breakdown: Product A $2,400, Product B $1,200, Product C $800", "financial_report"),
    ]

    for content, ctype in test_cases:
        fmt = decide_format(content, ctype)
        print(f"\nContent: {content[:50]}...")
        print(f"Format chosen: {fmt}")

    # Test chart builder
    print("\nBuilding test chart...")
    chart_data = {
        "CEO Agent":    9,
        "Market Agent": 8,
        "Build Agent":  7,
        "CRO Agent":    6,
        "CFO Agent":    8,
    }
    chart_path = build_chart(chart_data, "bar", "TAD Agent Performance")
    if chart_path:
        print(f"Chart saved: {chart_path}")
    else:
        print("Chart build skipped — matplotlib may not be installed")

    # Test script generation
    print("\nGenerating popup script...")
    result = explain(
        "TAD found a new opportunity: AI Call Screener for HVAC. Score 35/40.",
        title="New Opportunity Found",
        narrate_it=False
    )
    print(f"Format: {result.get('format')}")
    print(f"Script: {json.dumps(result.get('script', {}), indent=2)[:300]}")