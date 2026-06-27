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
import anthropic
from dotenv import load_dotenv

load_dotenv()

ROOT       = Path(__file__).parent.parent
MEMORY     = ROOT / "memory"
WORKFLOWS  = ROOT / "workflows" / "market-scans"
SKILL_PATH = Path(__file__).parent / "market_agent.md"

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
MODEL  = "claude-haiku-4-5-20251001"

import sys as _sys
if str(ROOT) not in _sys.path:
    _sys.path.insert(0, str(ROOT))
try:
    from skills.agent_soul import _get_agent_context, _log_history, _check_learned_skills
except ImportError:
    def _get_agent_context(n): return ""
    def _log_history(n, e): pass
    def _check_learned_skills(kws): return []


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


# ── Web search ───────────────────────────────────────────────────────────────

def _web_search(query: str) -> str:
    """
    Search the web using DuckDuckGo (free, no API key needed).
    Returns top results as text.
    """
    try:
        import urllib.request
        import urllib.parse

        # DuckDuckGo instant answer API
        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "TAD-AI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        results = []

        # Abstract (main answer)
        if data.get("Abstract"):
            results.append(f"Summary: {data['Abstract'][:300]}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text'][:150]}")

        return "\n".join(results) if results else "No results found."

    except Exception as e:
        _log(f"Web search error: {e}")
        return "Search unavailable."


def _research_opportunity(niche: str) -> dict:
    """
    Do real-time research on a niche before scoring.
    Searches Reddit signals, competitors, and market size.
    """
    _log(f"Researching: {niche}")
    research = {}

    # Search 1 — Reddit pain points
    reddit_results = _web_search(f"{niche} problems complaints site:reddit.com")
    research["reddit_signals"] = reddit_results[:400]

    # Search 2 — Existing competitors
    competitor_results = _web_search(f"AI software tool for {niche} small business")
    research["competitors"] = competitor_results[:400]

    # Search 3 — Market demand signals
    demand_results = _web_search(f"{niche} business owners struggling AI automation 2024 2025")
    research["demand_signals"] = demand_results[:400]

    return research


def _get_current_niches() -> str:
    """
    Search for currently trending AI pain points in real time.
    """
    _log("Searching for current AI pain points...")
    results = []

    searches = [
        "small business owners AI automation problems 2025",
        "what AI tools do small businesses need but don't exist",
        "AI software gaps underserved markets 2025",
    ]

    for query in searches:
        result = _web_search(query)
        if result and result != "Search unavailable." and result != "No results found.":
            results.append(result[:300])

    return "\n\n".join(results) if results else ""


# ── Core scan engine ──────────────────────────────────────────────────────────

def scan_for_opportunities(focus_area: str = "") -> list:
    """
    Main scan function. Returns top 3 scored opportunities.
    """
    killed   = _get_killed()
    previous = _get_previous()
    focus    = focus_area if focus_area else "AI automation for small local businesses"
    monkey   = (ROOT / "THE_MONKEY.md").read_text(encoding="utf-8")[:500]                if (ROOT / "THE_MONKEY.md").exists() else ""

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

Include ALL opportunities you find regardless of score.
Score them honestly but always return at least 3 opportunities.
Return JSON array only. No explanation."""

    try:
        _ctx = _get_agent_context("market")
        _sys_prompt = ((_ctx + "\n\n") if _ctx else "") + "You are a market research assistant. Always respond with valid JSON only. No markdown."

        # Run relevant learned skills to enhance the scan before calling Claude
        try:
            from skills.agent_soul import execute_learned_skill
            relevant = _check_learned_skills([
                "market", "opportunity", "tracking", "loophole", "detection",
                "competitive", "analysis", "early",
            ])
            skill_insights = []
            for skill_name in relevant[:2]:  # max 2 skills — avoid token bloat
                _log(f"Running learned skill: {skill_name}")
                result = execute_learned_skill(
                    skill_name, {"task": "market_scan", "focus": focus_area}
                )
                if result and result.strip() not in ("None", "") \
                        and "failed" not in result.lower() and "not found" not in result.lower() \
                        and "no known entry" not in result.lower():
                    skill_insights.append(f"Learned skill '{skill_name}': {result[:200]}")
            if skill_insights:
                prompt += "\n\nInsights from TAD's learned skills:\n" + "\n".join(skill_insights)
                _log(f"{len(skill_insights)} learned skill(s) contributed to this scan")
        except Exception as _e:
            _log(f"Skill execution skipped: {_e}")

        msg = claude.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=_sys_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text or "[]"
        print(f"[MARKET DEBUG] Raw response ({len(raw)} chars): {raw[:300]}")
        clean = re.sub(r"```json|```", "", raw).strip()
        start = clean.find("[")
        end   = clean.rfind("]")
        if start != -1 and end != -1 and end > start:
            clean = clean[start:end+1]
        else:
            clean = "[]"
        opportunities = json.loads(clean)

        # Filter out killed and previous
        filtered = [
            o for o in opportunities
            if o.get("name") not in killed
            and o.get("name") not in previous
            and o.get("total_score", 0) >= 20
        ]

        top3 = sorted(filtered, key=lambda x: x.get("total_score", 0), reverse=True)[:3]
        _log(f"Found {len(filtered)} qualifying opportunities. Top 3 selected.")
        relevant_skills = _check_learned_skills(["market", "opportunity", "scan"])
        if relevant_skills:
            _log(f"Learned skills available: {relevant_skills}")
        _log_history("market", {
            "action": "scan",
            "found": len(filtered),
            "top_3": [o.get("name") for o in top3],
            "top_score": top3[0].get("total_score") if top3 else 0,
        })
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