"""
TAD Daily Scheduler v0.2
- 3:00 AM — Deep scan: market trends + competitor activity + hidden opportunities
- 7:00 AM — Morning briefing: launches visual dashboard + voice narration
"""

import threading
import time
import json
import re
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

DEEP_SCAN_HOUR = 3
BRIEFING_HOUR  = 7

DEEP_SCAN_QUERIES = [
    "AI automation market trends this week high growth low competition 2026",
    "emerging AI business opportunities solo developer overlooked gaps June 2026",
    "AI tools competitors failing customers what problems are unsolved 2026",
    "hidden profitable AI niches very low competition high demand 2026",
    "what AI business is nobody building but everyone needs right now",
]

DEEP_SCAN_SYSTEM = """You are TAD's autonomous intelligence agent scanning for Joshua Abraham.
Joshua is a solo developer building TAD — a personal AI business OS.
He is looking for:
1. Market trends with high growth momentum right now
2. Competitor weaknesses and gaps customers complain about
3. Hidden opportunities — high potential, very low competition, feasible for one developer

For each finding:
- Give a concrete opportunity name
- Explain why it is overlooked
- Give a feasibility score 1-10 for a solo developer
- Estimate time to first dollar

Be direct. No fluff."""

BRIEFING_SYSTEM = """You are TAD's morning briefing agent for Joshua Abraham.

Produce a structured morning briefing in this EXACT JSON format:
{
  "summary": "one sentence overview",
  "opportunities": [
    {
      "name": "opportunity name",
      "score": 8,
      "why": "why it is profitable",
      "time_to_revenue": "2-3 weeks",
      "feasibility": 9
    }
  ],
  "hidden_gem": {
    "name": "gem name",
    "why_overlooked": "why nobody is doing this"
  },
  "competitor_gaps": [
    "gap 1",
    "gap 2"
  ],
  "action_today": "one specific action Joshua should take today",
  "raw": "full briefing text here"
}

Return ONLY valid JSON. No markdown. No extra text."""


def run_deep_scan():
    """3AM — full intelligence scan."""
    from tools.registry import call as tool_call

    print(f"[scheduler] Starting 3AM deep scan — {datetime.now()}")
    today = datetime.now().strftime("%Y-%m-%d")
    all_findings = []

    for query in DEEP_SCAN_QUERIES:
        try:
            result = tool_call("web_search", {"query": query})
            all_findings.append(f"QUERY: {query}\nRESULTS:\n{result}\n---")
            print(f"[scheduler] Scanned: {query[:50]}...")
            time.sleep(2)
        except Exception as e:
            print(f"[scheduler] Search error: {e}")

    if not all_findings:
        return

    combined = "\n\n".join(all_findings)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": DEEP_SCAN_SYSTEM},
                {"role": "user",   "content": f"Analyze and extract best opportunities:\n\n{combined[:6000]}"}
            ],
            max_tokens=3000,
        )
        analysis = response.choices[0].message.content
        tool_call("file_write", {
            "filename": f"deep-scan-{today}.md",
            "content":  f"# TAD Deep Scan — {today}\n\n{analysis}"
        })
        _save_scan_memory("deep_scan", analysis[:500])
        print(f"[scheduler] Deep scan complete — workflows/deep-scan-{today}.md")
    except Exception as e:
        print(f"[scheduler] Analysis error: {e}")


def run_morning_briefing():
    """7AM — parse scan, generate structured briefing, launch visual dashboard."""
    from tools.registry import call as tool_call
    from tad_visual import show_morning_briefing

    print(f"[scheduler] Starting 7AM briefing — {datetime.now()}")
    today = datetime.now().strftime("%Y-%m-%d")

    scan_path = Path(f"workflows/deep-scan-{today}.md")
    scan_content = scan_path.read_text(encoding="utf-8") if scan_path.exists() \
        else "No overnight scan available. Analyze current AI market opportunities."

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BRIEFING_SYSTEM},
                {"role": "user",   "content": f"Create Joshua's morning briefing:\n\n{scan_content[:4000]}"}
            ],
            max_tokens=2000,
        )
        raw = response.choices[0].message.content

        # Parse JSON briefing
        try:
            clean = raw.strip()
            if clean.startswith("```"):
                clean = re.sub(r"```[a-z]*\n?", "", clean).strip("`").strip()
            briefing_data = json.loads(clean)
        except Exception:
            # Fallback if JSON parse fails
            briefing_data = {
                "summary": "Morning briefing ready. Check the full text below.",
                "opportunities": [],
                "hidden_gem": None,
                "competitor_gaps": [],
                "action_today": "Review the full briefing text for today's action.",
                "raw": raw
            }

        # Save to file
        tool_call("file_write", {
            "filename": f"briefing-{today}.md",
            "content":  briefing_data.get("raw", raw)
        })

        # Update THE_MONKEY
        monkey = Path("THE_MONKEY.md")
        if monkey.exists():
            content = monkey.read_text(encoding="utf-8")
            content = re.sub(r"# Last updated:.*", f"# Last updated: {today}", content)
            entry = f"- workflows/briefing-{today}.md"
            if entry not in content:
                content = content.replace(
                    "### Working capabilities",
                    f"{entry}\n### Working capabilities"
                )
            monkey.write_text(content, encoding="utf-8")

        # Launch visual dashboard
        print(f"[scheduler] Launching morning briefing dashboard")
        show_morning_briefing(briefing_data)
        return briefing_data.get("raw", raw)

    except Exception as e:
        print(f"[scheduler] Briefing error: {e}")
        return ""


def _save_scan_memory(scan_type: str, summary: str):
    mem = Path("memory/history.jsonl")
    mem.parent.mkdir(exist_ok=True)
    entry = {"ts": datetime.now().isoformat(), "type": scan_type, "summary": summary}
    with open(mem, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _should_run(target_hour: int, last_run: dict, key: str) -> bool:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if now.hour == target_hour and last_run.get(key) != today:
        last_run[key] = today
        return True
    return False


def start_scheduler(status_callback=None):
    def _loop():
        last_run = {"deep_scan": "", "briefing": ""}
        print("[scheduler] Started — deep scan 3AM, briefing 7AM")
        while True:
            try:
                if _should_run(DEEP_SCAN_HOUR, last_run, "deep_scan"):
                    if status_callback:
                        status_callback("running 3am deep scan...")
                    run_deep_scan()
                if _should_run(BRIEFING_HOUR, last_run, "briefing"):
                    if status_callback:
                        status_callback("generating morning briefing...")
                    run_morning_briefing()
            except Exception as e:
                print(f"[scheduler] Error: {e}")
            time.sleep(60)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    print("Running manual test...")
    run_deep_scan()
    run_morning_briefing()
    print("Done. Check workflows/ folder.")