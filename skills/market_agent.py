"""
TAD AI — Market Agent Script
Chief Market Intelligence Officer — Loophole Scanner
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
WORKFLOWS  = ROOT / "workflows" / "market-scans"
SKILL_PATH = Path(__file__).parent / "market_agent.md"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8") if SKILL_PATH.exists() else ""


def _read(filename: str) -> dict | list:
    path = MEMORY / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write(filename: str, data):
    MEMORY.mkdir(exist_ok=True)
    (MEMORY / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _log(msg: str):
    log_path = MEMORY / "market_log.jsonl"
    entry = {"ts": datetime.now().isoformat(), "msg": msg}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[MARKET] {msg}")


def _get_killed() -> list:
    killed = _read("killed_opportunities.json")
    if isinstance(killed, dict):
        return killed.get("opportunities", [])
    return []


def _get_previous() -> list:
    log = _read("opportunity_log.json")
    if isinstance(log, dict):
        return [o.get("name", "") for o in log.get("opportunities", [])]
    return []


# ── Core scan engine ──────────────────────────────────────────────────────────

def scan_for_opportunities(focus_area: str = "") -> list:
    """
    Main scan function. Returns top 3 scored opportunities.
    Each opportunity: { name, problem, demand, competition,
                        buildability, revenue_speed, total_score, evidence }
    """
    skill   = _load_skill()
    monkey  = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:2000] \
              if (ROOT / "THE_MONKEY.md").exists() else ""
    killed  = _get_killed()
    previous = _get_previous()

    _log("Starting market scan...")

    prompt = f"""MISSION:
{monkey}

FOCUS AREA (if specified): {focus_area if focus_area else "General AI industry loopholes"}

PREVIOUSLY KILLED OPPORTUNITIES (never resubmit these):
{json.dumps(killed[:20])}

PREVIOUSLY FOUND (avoid duplicates):
{json.dumps(previous[:20])}

TODAY'S DATE: {datetime.now().strftime("%Y-%m-%d")}

Scan the AI industry right now for loopholes.
Think about:
- What are people complaining about in AI tools on Reddit right now?
- What problems do small businesses have with AI that nobody has solved?
- What gaps exist in current AI products (check reviews, complaints)?
- What rising search trends suggest unmet demand?

Find 5 opportunities. Score each one:
- Demand (1-10): people already paying for partial solutions?
- Competition (1-10): how few real competitors?
- Buildability (1-10): can TAD build this in 1-3 nights?
- Revenue speed (1-10): how fast does money come in?

Return ONLY a JSON array of exactly 5 opportunities, sorted by total score descending:
[
  {{
    "name": "short opportunity name",
    "problem": "exact problem people are experiencing",
    "demand": 8,
    "competition": 9,
    "buildability": 8,
    "revenue_speed": 7,
    "total_score": 32,
    "evidence": "where you found this signal",
    "why_no_competition": "why nobody has solved this properly"
  }}
]

Only include opportunities with total_score >= 28.
If you cannot find 5 above 28, include what you find and note the scores.
Return JSON array only. No explanation."""

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": skill},
                {"role": "user",   "content": prompt},
            ],
            temperature=1,
            max_tokens=1500,
        )
        raw   = resp.choices[0].message.content or "[]"
        clean = re.sub(r"```json|```", "", raw).strip()
        opportunities = json.loads(clean)

        # Filter out killed and previous
        filtered = [
            o for o in opportunities
            if o.get("name") not in killed
            and o.get("name") not in previous
            and o.get("total_score", 0) >= 28
        ]

        top3 = sorted(filtered, key=lambda x: x.get("total_score", 0), reverse=True)[:3]
        _log(f"Found {len(filtered)} qualifying opportunities. Top 3 selected.")
        return top3

    except Exception as e:
        _log(f"Scan error: {e}")
        return []


def save_and_report(opportunities: list) -> dict:
    """
    Save scan results and prepare report for CEO Agent.
    """
    today = datetime.now().strftime("%Y-%m-%d-%H%M")

    # Save to opportunity log
    opp_log = _read("opportunity_log.json")
    if not isinstance(opp_log, dict):
        opp_log = {"opportunities": []}
    if "opportunities" not in opp_log:
        opp_log["opportunities"] = []

    for opp in opportunities:
        opp["found_date"] = datetime.now().isoformat()
        opp_log["opportunities"].append(opp)
    _write("opportunity_log.json", opp_log)

    # Save full scan report to workflows
    WORKFLOWS.mkdir(parents=True, exist_ok=True)
    report_path = WORKFLOWS / f"market-scan-{today}.md"
    report_content = f"# Market Scan — {today}\n\n"
    for i, opp in enumerate(opportunities, 1):
        report_content += f"## #{i} — {opp.get('name')} (Score: {opp.get('total_score')}/40)\n\n"
        report_content += f"**Problem:** {opp.get('problem')}\n\n"
        report_content += f"**Scores:** Demand {opp.get('demand')} | "
        report_content += f"Competition {opp.get('competition')} | "
        report_content += f"Buildability {opp.get('buildability')} | "
        report_content += f"Revenue Speed {opp.get('revenue_speed')}\n\n"
        report_content += f"**Evidence:** {opp.get('evidence')}\n\n"
        report_content += f"**Why no competition:** {opp.get('why_no_competition')}\n\n---\n\n"
    report_path.write_text(report_content, encoding="utf-8")

    _log(f"Scan report saved → {report_path}")

    return {
        "report_type":     "opportunity_scan",
        "date":            today,
        "opportunities":   opportunities,
        "top_opportunity": opportunities[0] if opportunities else None,
        "report_path":     str(report_path),
    }


def run_full_scan(focus_area: str = "") -> dict:
    """Full scan cycle — scan, save, return report for CEO Agent."""
    _log("=== Full market scan started ===")
    opportunities = scan_for_opportunities(focus_area)

    if not opportunities:
        _log("No qualifying opportunities found this cycle")
        return {
            "report_type":   "opportunity_scan",
            "opportunities": [],
            "status":        "no_qualifying_opportunities",
        }

    report = save_and_report(opportunities)
    _log(f"=== Scan complete — {len(opportunities)} opportunities ready for CEO ===")
    return report


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Market Agent Test")
    print("=" * 40)
    print("Running full market scan...")
    report = run_full_scan()
    print(json.dumps(report, indent=2))