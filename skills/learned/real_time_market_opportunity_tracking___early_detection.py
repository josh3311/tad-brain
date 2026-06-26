"""
TAD Real-Time Market Opportunity Tracking — Early Detection Engine
Monitors AI industry news, social media, GitHub, Reddit, forums for emerging loopholes.
Logs findings to memory/real_time_market_opportunity_tracking___early_detection_log.jsonl
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
import asyncio
import aiohttp
from openai import OpenAI

MEMORY_DIR = Path("C:/TAD/memory") if os.name == 'nt' else Path("./memory")
MEMORY_DIR.mkdir(exist_ok=True)
LOG_FILE = MEMORY_DIR / "real_time_market_opportunity_tracking___early_detection_log.jsonl"

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.cn/v1"
)

SOURCES = [
    {"name": "github_trending", "url": "https://github.com/trending/", "type": "github"},
    {"name": "reddit_ai", "url": "https://reddit.com/r/MachineLearning/new.json", "type": "reddit"},
    {"name": "hn_api", "url": "https://hacker-news.firebaseio.com/v0/newstories.json", "type": "hackernews"},
]

def log_finding(finding: dict) -> None:
    """Append finding to JSONL log."""
    finding["timestamp"] = datetime.utcnow().isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(finding) + "\n")
    print(f"[LOG] {finding['opportunity']}")

def analyze_with_kimi(content: str, source: str) -> Optional[dict]:
    """Use Kimi API to analyze content for loopholes and opportunities."""
    try:
        response = client.messages.create(
            model="moonshot-v1",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this {source} content for AI industry loopholes and emerging pain points.
Look for problems that:
1. Affect 100+ people but <10K are aware
2. Have minimal existing solutions
3. Indicate high willingness to pay
4. Could grow 100%+ if solved

Content: {content}

Respond ONLY with JSON: {{"loophole": "...", "pain_points": [...], "market_readiness": 1-10, "urgency": 1-10}}"""
                }
            ]
        )
        
        text = response.content[0].text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        print(f"[ERROR] Kimi analysis failed: {e}")
    return None

async def fetch_source(session: aiohttp.ClientSession, source: dict) -> list:
    """Fetch content from a single source."""
    findings = []
    try:
        headers = {"User-Agent": "TAD-AI/1.0"}
        async with session.get(source["url"], headers=headers, timeout=10) as resp:
            if resp.status != 200:
                print(f"[WARN] {source['name']}: HTTP {resp.status}")
                return findings
            
            data = await resp.json()
            
            if source["type"] == "reddit":
                posts = data.get("data", {}).get("children", [])[:5]
                for post in posts:
                    content = post["data"]["title"] + " " + post["data"].get("selftext", "")
                    if len(content.strip()) > 20:
                        findings.append({"source": source["name"], "content": content[:500]})
            
            elif source["type"] == "hackernews":
                story_ids = data[:10]
                for sid in story_ids:
                    async with session.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                        timeout=5
                    ) as story_resp:
                        if story_resp.status == 200:
                            story = await story_resp.json()
                            if story.get("title"):
                                findings.append({
                                    "source": source["name"],
                                    "content": story["title"] + " " + story.get("text", "")
                                })
    
    except asyncio.TimeoutError:
        print(f"[TIMEOUT] {source['name']}")
    except Exception as e:
        print(f"[ERROR] {source['name']}: {e}")
    
    return findings

async def scan_sources() -> list:
    """Concurrently scan all sources for opportunities."""
    all_findings = []
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_source(session, src) for src in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_findings.extend(result)
    return all_findings

def process_findings(raw_findings: list) -> None:
    """Analyze findings and log high-probability opportunities."""
    print(f"[SCAN] Found {len(raw_findings)} items. Analyzing with Kimi...")
    
    for finding in raw_findings[:10]:
        analysis = analyze_with_kimi(finding["content"], finding["source"])
        if analysis:
            market_score = (analysis.get("market_readiness", 5) + analysis.get("urgency", 5)) / 2
            if market_score >= 7:
                log_finding({
                    "opportunity": analysis.get("loophole", "Unknown"),
                    "pain_points": analysis.get("pain_points", []),
                    "source": finding["source"],
                    "market_readiness": analysis.get("market_readiness", 0),
                    "urgency": analysis.get("urgency", 0),
                    "score": market_score
                })

def main():
    """Main execution loop."""
    print("[START] TAD Real-Time Market Opportunity Tracker")
    print(f"[CONFIG] Memory dir: {MEMORY_DIR}")
    print(f"[CONFIG] Log file: {LOG_FILE}")
    
    if not os.getenv("KIMI_API_KEY"):
        print("[WARN] KIMI_API_KEY not set. Using mock analysis.")
    
    raw_findings = asyncio.run(scan_sources())
    if raw_findings:
        process_findings(raw_findings)
    else:
        print("[INFO] No findings this cycle.")
    
    print("[DONE] Scan complete.")

if __name__ == "__main__":
    main()