"""Core data model and viability calculation for TAD Product Builder."""

import sys
from dataclasses import dataclass
from typing import List, Optional

# Weights reflect TAD mission criteria.
WEIGHT_PAIN = 0.30
WEIGHT_GAP = 0.25
WEIGHT_WILLINGNESS = 0.25
WEIGHT_GROWTH = 0.20


@dataclass(frozen=True)
class Opportunity:
    """Niche opportunity rated 0-10 across four dimensions."""
    pain_score: float
    market_gap_score: float
    willingness_to_pay_score: float
    growth_potential_score: float


def calculate_viability(opp: Opportunity) -> float:
    """Return weighted viability score (0.0 - 10.0)."""
    def clamp(v: float) -> float:
        return max(0.0, min(10.0, v))

    pain = clamp(opp.pain_score)
    gap = clamp(opp.market_gap_score)
    willingness = clamp(opp.willingness_to_pay_score)
    growth = clamp(opp.growth_potential_score)

    score = (
        pain * WEIGHT_PAIN
        + gap * WEIGHT_GAP
        + willingness * WEIGHT_WILLINGNESS
        + growth * WEIGHT_GROWTH
    )
    return round(score, 4)


class OpportunityStore:
    """Simple in-memory storage and aggregation for opportunities."""

    def __init__(self) -> None:
        self._entries: List[Opportunity] = []

    def add(self, opp: Opportunity) -> None:
        """Record an opportunity."""
        self._entries.append(opp)

    def count(self) -> int:
        """Return number of stored entries."""
        return len(self._entries)

    def average_viability(self) -> float:
        """Return mean viability across all entries (0.0 if empty)."""
        if not self._entries:
            return 0.0
        total = sum(calculate_viability(e) for e in self._entries)
        return round(total / self.count(), 4)

    def best(self) -> Optional[Opportunity]:
        """Return the highest-viability entry, or None if empty."""
        if not self._entries:
            return None
        return max(self._entries, key=calculate_viability)


def generate_report(store: OpportunityStore) -> str:
    """Return a plain-text summary of the store."""