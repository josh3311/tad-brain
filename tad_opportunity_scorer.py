"""
TAD Opportunity Scorer - core data model and scoring formula.
"""

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class Opportunity:
    # Core data model for a niche loophole opportunity.
    name: str
    competition_level: float  # 0 = no competition, 10 = saturated
    pain_level: float         # 0 = no pain, 10 = extreme pain
    willingness_to_pay: float # 0 = won't pay, 10 = will pay immediately
    skyrocket_potential: float# 0 = flat growth, 10 = guaranteed 100%+ growth


def score_opportunity(opp: Opportunity) -> float:
    # Multiplicative scoring: opportunity is only as strong as its weakest
    # critical factor.  Competition is inverted because low competition is
    # required for a high score.
    competition_factor = 10.0 - opp.competition_level
    raw = opp.pain_level * opp.willingness_to_pay * opp.skyrocket_potential * competition_factor
    # Normalize to a 0-100 scale.
    return raw / 100.0


class OpportunityStore:
    # Simple in-memory storage and aggregation layer for opportunities.
    def __init__(self) -> None:
        self._entries = []

    def add(self, opp: Opportunity) -> None:
        self._entries.append(opp)

    def count(self) -> int:
        return