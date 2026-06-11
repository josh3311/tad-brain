"""TAD Opportunity Scorer — core data model and score calculation."""

import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Opportunity:
    competition_level: float  # 0 (none) to 10 (saturated)
    pain_level: float         # 0 (no pain) to 10 (extreme pain)
    willingness_to_pay: float # 0 (none) to 10 (very willing)
    growth_potential: float   # 0 (flat) to 10 (10x potential)


def score_opportunity(opp: Opportunity) -> float:
    """Return opportunity score from 0 to 100."""
    # Invert competition: lower competition is better.
    competition_score = 10.0 - opp.competition_level
    total = (
        competition_score
        + opp.pain_level
        + opp.willingness_to_pay
        + opp.growth_potential
    )
    # Four axes, each max 10 -> max raw total 40. Scale to 0-100.
    return total * 2.5


class OpportunityStore:
    """Simple in-memory store for Opportunity records with aggregation."""

    def __init__(self) -> None:
        self._entries: List[Opportunity] = []

    def add(self, opp: Opportunity) -> None:
        """Record an opportunity."""
        self._entries.append(opp)

    def count(self) -> int:
        """Return number of stored opportunities."""
        return len(self._entries)

    def average_score(self) -> float:
        """Return mean score, or 0.0 if empty."""
        if not self._entries:
            return 0.0
        return sum(score_opportunity(o) for o in self._entries) / len(self._entries)

    def best_opportunity(self) -> Optional[Opportunity]:
        """Return the highest-scoring opportunity, or None if empty."""
        if not self._entries:
            return None
        return max(self._entries, key=score_opportunity)


def _run_tests() -> int:
    """Return 0 on pass, non-zero on fail."""
    failures = 0

    # Known input 1: perfect opportunity -> 100
    perfect = Opportunity(0.0, 10.0, 10.0, 10.0)
    if score_opportunity(perfect) != 100.0:
        failures += 1

    # Known input 2: worst opportunity -> 0
    worst = Opportunity(10.0, 0.0, 0.0, 0.0)
    if score_opportunity(worst) != 0.0:
        failures += 1

    # Storage and aggregation tests
    store = OpportunityStore()
    if store.count() != 0:
        failures += 1
    if store.average_score() != 0.0:
        failures += 1
    if store.best_opportunity() is not None:
        failures += 1

    store.add(perfect)
    if store.count() != 1:
        failures += 1
    if store.average_score() != 100.0:
        failures += 1
    if store.best_opportunity() != perfect:
        failures += 1

    store.add(worst)
    if store.count() != 2:
        failures += 1
    if store.average_score() != 50.0:
        failures += 1
    if store.best_opportunity() != perfect:
        failures += 1

    mid = Opportunity(5.0, 5.0, 5.0, 5.0)
    store.add(mid)
    if store.count() != 3:
        failures += 1
    if store.average_score() != 50.0:
        failures += 1
    if store.best_opportunity() != perfect:
        failures += 1

    return failures


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())
    print("Usage: python module.py --test")