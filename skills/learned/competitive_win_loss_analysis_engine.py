"""
Competitive Win/Loss Analysis Engine for TAD.
Analyzes deal outcomes, competitor messaging, and winning strategies.
Logs all analysis to memory/competitive_win_loss_analysis_engine_log.jsonl
"""

import json
import os
from datetime import datetime
from pathlib import Path
import anthropic

MEMORY_DIR = Path("C:\\TAD\\memory")
LOG_FILE = MEMORY_DIR / "competitive_win_loss_analysis_engine_log.jsonl"
DEALS_DB = MEMORY_DIR / "deals_analysis.json"


def ensure_memory_dir():
    """Ensure memory directory exists."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def log_action(action: str, data: dict):
    """Log actions to JSONL file."""
    ensure_memory_dir()
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "data": data
    }
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"Error logging action: {e}")


def load_deals():
    """Load existing deals database."""
    if DEALS_DB.exists():
        try:
            with open(DEALS_DB, "r") as f:
                return json.load(f)
        except Exception:
            return {"won": [], "lost": []}
    return {"won": [], "lost": []}


def save_deals(deals_data: dict):
    """Save deals database."""
    ensure_memory_dir()
    try:
        with open(DEALS_DB, "w") as f:
            json.dump(deals_data, f, indent=2)
    except Exception as e:
        print(f"Error saving deals: {e}")


def record_deal_outcome(
    deal_id: str,
    company: str,
    deal_value: float,
    outcome: str,
    competitor: str = None,
    messaging_used: list = None,
    competitor_messaging: list = None,
    loss_reason: str = None
):
    """Record a deal outcome (won or lost)."""
    ensure_memory_dir()
    
    deal_record = {
        "deal_id": deal_id,
        "company": company,
        "deal_value": deal_value,
        "outcome": outcome,
        "competitor": competitor,
        "messaging_used": messaging_used or [],
        "competitor_messaging": competitor_messaging or [],
        "loss_reason": loss_reason,
        "timestamp": datetime.now().isoformat()
    }
    
    deals = load_deals()
    if outcome.lower() == "won":
        deals["won"].append(deal_record)
    else:
        deals["lost"].append(deal_record)
    
    save_deals(deals)
    log_action("deal_recorded", deal_record)
    return deal_record


def analyze_win_patterns():
    """Analyze patterns from won deals."""
    deals = load_deals()
    
    if not deals["won"]:
        return {"status": "no_data", "message": "No won deals yet"}
    
    messaging_frequency = {}
    for deal in deals["won"]:
        for msg in deal.get("messaging_used", []):
            messaging_frequency[msg] = messaging_frequency.get(msg, 0) + 1
    
    analysis = {
        "total_won": len(deals["won"]),
        "total_won_value": sum(d["deal_value"] for d in deals["won"]),
        "top_messaging": sorted(
            messaging_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5],
        "timestamp": datetime.now().isoformat()
    }
    
    log_action("win_pattern_analysis", analysis)
    return analysis


def analyze_loss_patterns():
    """Analyze patterns from lost deals."""
    deals = load_deals()
    
    if not deals["lost"]:
        return {"status": "no_data", "message": "No lost deals yet"}
    
    loss_reasons = {}
    competitor_wins = {}
    
    for deal in deals["lost"]:
        reason = deal.get("loss_reason", "unknown")
        loss_reasons[reason] = loss_reasons.get(reason, 0) + 1
        
        competitor = deal.get("competitor", "unknown")
        competitor_wins[competitor] = competitor_wins.get(competitor, 0) + 1
    
    analysis = {
        "total_lost": len(deals["lost"]),
        "total_lost_value": sum(d["deal_value"] for d in deals["lost"]),
        "top_loss_reasons": sorted(
            loss_reasons.items(),
            key=lambda x: x[1],
            reverse=True
        ),
        "competitor_wins": sorted(
            competitor_wins.items(),
            key=lambda x: x[1],
            reverse=True
        ),
        "timestamp": datetime.now().isoformat()
    }
    
    log_action("loss_pattern_analysis", analysis)
    return analysis


def generate_messaging_recommendations():
    """Generate messaging recommendations using Kimi API."""
    ensure_memory_dir()
    
    win_analysis = analyze_win_patterns()
    loss_analysis = analyze_loss_patterns()
    
    try:
        client = anthropic.Anthropic()
        
        prompt = f"""
Based on this competitive win/loss data, generate messaging recommendations:

WINS:
- Total won deals: {win_analysis.get('total_won', 0)}
- Total value: ${win_analysis.get('total_won_value', 0)}
- Top performing messaging: {win_analysis.get('top_messaging', [])}

LOSSES:
- Total lost deals: {loss_analysis.get('total_lost', 0)}
- Total value: ${loss_analysis.get('total_lost_value', 0)}
- Top loss reasons: {loss_analysis.get('top_loss_reasons', [])}
- Competitors winning: {loss_analysis.get('competitor_wins', [])}

Generate 3 specific messaging improvements that should be tested immediately.
Focus on what worked in wins and addressing top loss reasons.
"""
        
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        recommendations = message.content[0].text
        
        result = {
            "recommendations": recommendations,
            "generated_at": datetime.now().isoformat()
        }
        
        log_action("messaging_recommendations_generated", result)
        return result
        
    except Exception as e:
        error_result = {"error": str(e), "timestamp": datetime.now().isoformat()}
        log_action("messaging_recommendations_error", error_result)
        return error_result


def get_competitive_intelligence():
    """Get overall competitive intelligence summary."""
    win_analysis = analyze_win_patterns()
    loss_analysis = analyze_loss_patterns()
    
    deals = load_deals()
    win_rate = 0
    if deals["won"] or deals["lost"]:
        total = len(deals["won"]) + len(deals["lost"])
        win_rate = (len(deals["won"]) / total) * 100 if total > 0 else 0
    
    intelligence = {
        "win_rate_percent": round(win_rate, 2),
        "win_analysis": win_analysis,
        "loss_analysis": loss_analysis,
        "generated_at": datetime.now().isoformat()
    }
    
    log_action("competitive_intelligence_summary", intelligence)
    return intelligence


def main():
    """Main entry point for competitive win/loss analysis engine."""
    print("TAD Competitive Win/Loss Analysis Engine")
    print("=" * 50)
    
    ensure_memory_dir()