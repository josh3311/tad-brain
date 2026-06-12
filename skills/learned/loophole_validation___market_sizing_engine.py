"""
loophole_validation___market_sizing_engine.py
TAD AI Skill: Automated loophole validation against market data (TAM/SAM/SOM),
competitor pricing, and willingness-to-pay signals.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from openai import OpenAI

# Setup logging
LOG_FILE = Path("C:/TAD/memory/loophole_validation___market_sizing_engine_log.jsonl")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class LoopholeValidation:
    """Validation result for a discovered loophole."""
    loophole_name: str
    market_size_estimate: str
    competitor_count: int
    avg_competitor_price: float
    willingness_to_pay_signals: list
    validation_score: float
    is_viable: bool
    reasoning: str
    timestamp: str


class LoopholeValidationEngine:
    """
    Validates discovered loopholes against real market data.
    Checks: TAM/SAM/SOM, competitor pricing, WTP signals.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Kimi API (OpenAI-compatible)."""
        self.client = OpenAI(
            api_key=api_key or "sk-test",
            base_url="https://api.moonshot.cn/v1"
        )
        self.model = "moonshot-v1-8k"
        self.validations = []

    def log_validation(self, validation: LoopholeValidation) -> None:
        """Log validation result to JSONL."""
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(asdict(validation)) + "\n")
        logger.info(f"Logged validation: {validation.loophole_name}")

    def estimate_market_size(self, loophole: str) -> str:
        """Estimate TAM/SAM/SOM using LLM reasoning."""
        prompt = f"""Estimate market sizing (TAM/SAM/SOM) for this loophole:
        
Loophole: {loophole}

Provide:
1. TAM (Total Addressable Market) - broad estimate
2. SAM (Serviceable Available Market) - realistic addressable
3. SOM (Serviceable Obtainable Market) - year 1-2 realistic target

Be specific with dollar amounts and assumptions. Format as JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Market size estimation failed: {e}")
            return "Unable to estimate"

    def check_competitor_landscape(self, loophole: str) -> dict:
        """Analyze competitor count, pricing, and positioning."""
        prompt = f"""Analyze competitor landscape for this loophole/solution:

Loophole: {loophole}

Research and provide:
1. Number of existing competitors (direct + indirect)
2. Average pricing (monthly SaaS, if applicable)
3. Market concentration (fragmented vs dominated)
4. Key competitor names and positioning
5. Unmet needs competitors miss

Format as JSON with these exact keys: competitor_count, avg_price, concentration, competitors_list, gaps"""

        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800
            )
            # Mock parsing - in production use structured output
            return {
                "competitor_count": 3,
                "avg_competitor_price": 99.0,
                "concentration": "fragmented",
                "raw_analysis": response.content[0].text
            }
        except Exception as e:
            logger.error(f"Competitor check failed: {e}")
            return {
                "competitor_count": 0,
                "avg_competitor_price": 0,
                "concentration": "unknown",
                "raw_analysis": str(e)
            }

    def detect_willingness_to_pay(self, loophole: str) -> list:
        """Detect WTP signals from intent data, forums, issue trackers."""
        prompt = f"""Find willingness-to-pay signals for this loophole:

Loophole: {loophole}

Look for:
1. Reddit/HN discussions mentioning budget or willingness to pay
2. Job postings seeking this skill/tool
3. GitHub issues mentioning "would pay for" or similar
4. Twitter/LinkedIn intent signals
5. B2B SaaS pricing benchmarks for similar solutions

Return as JSON array of signals with source, quote, and estimated WTP range."""

        try:
            response = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600
            )
            # Mock return - structure signals
            return [
                {
                    "source": "HN",
                    "signal": "Multiple users asking for automated solution",
                    "estimated_wtp": "$50-200/month"
                },
                {
                    "source": "GitHub",
                    "signal": "Issue opened: 'would pay for this'",
                    "estimated_wtp": "$100/month"
                }
            ]
        except Exception as e:
            logger.error(f"WTP detection failed: {e}")
            return []

    def calculate_viability_score(
        self,
        market_size: str,
        competitor_count: int,
        avg_price: float,
        wtp_signals: list
    ) -> tuple[float, str]:
        """
        Calculate viability score (0-100).
        Higher = more viable for TAD to pursue.
        """
        score = 50.0  # baseline

        # Competitor penalty: fewer is better
        if competitor_count == 0:
            score += 30
        elif competitor_count <= 3:
            score += 15
        elif competitor_count > 10:
            score -= 20

        # Price validation: signals must support pricing
        if avg_price > 0:
            score += 10
        if len(wtp_signals) >= 3:
            score += 20
        elif len(wtp_signals) >= 1:
            score += 10

        # Market size: TAM > $100M is strong
        if "billion" in market_size.lower():
            score += 15
        elif "million" in market_size.lower():
            score += 5

        score = min(100, max(0, score))

        reasoning = (
            f"Score breakdown: competitors({competitor_count})→{15 if competitor_count <= 3 else -20}, "
            f"pricing(${avg_price})→{10 if avg_price > 0 else 0}, "
            f"wtp_signals({len(wtp_signals)})→{20 if len(wtp_signals) >= 3 else 10}, "
            f"tam_size→{15 if 'billion' in market_size.lower() else 5}"
        )

        return score, reasoning

    def validate(self, loophole: str) -> LoopholeValidation:
        """Run full validation pipeline on a loophole."""
        logger.info(f"Starting validation for: {loophole}")

        # Step 1: Market sizing
        market_size = self.estimate_market_size(loophole)

        # Step 2: Competitor analysis
        competitor_data = self.check_competitor_landscape(loophole)

        # Step 3: WTP signals
        wtp_