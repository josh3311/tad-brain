"""TAD Opportunity Scorer — core data model and scoring logic."""

import sys
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Opportunity:
    name: str
    competition: float       # 0 (none) to 10 (saturated)
    pain_score: float        # 0 to 10
    willingness_to_pay: float  # 0 to 10
    growth_potential: float  # 0 to 10


def calculate_score(opp: Opportunity) -> float:
    # invert competition so lower is better
    low_competition = 10.0 - opp.competition
    total = (
        opp.pain_score * 0.25
        + opp.willingness_to_pay * 0.25
        + opp.growth_potential * 0.25
        + low_competition * 0.25
    )
    return round(total, 2)


class OpportunityStore:
    # simple in-memory storage with aggregation helpers
    def __init__(self) -> None:
        self._items: List[Opportunity] = []

    def add(self, opp: Opportunity) -> None:
        self._items.append(opp)

    def best(self) -> Optional[Opportunity]:
        if not self._items:
            return None
        return max(self._items, key=calculate_score)

    def average_score(self) -> float:
        if not self._items:
            return 0.0
        total = sum(calculate_score(o) for o in self._items)
        return round(total / len(self._items), 2)


def _tests() -> bool:
    passed = True

    perfect = Opportunity(
        "Perfect", 0.0, 10.0, 10.0, 10.0
    )
    if calculate_score(perfect) != 10.0:
        passed = False

    worst = Opportunity(
        "Worst", 10.0, 0.0, 0.0, 0.0
    )
    if calculate_score(worst) != 0.0:
        passed = False

    # -- storage and aggregation checks --
    store = OpportunityStore()
    if store.best() is not None:
        passed = False
    if store.average_score() != 0.0:
        passed = False

    store.add(perfect)
    store.add(worst)
    if store.best() is not perfect:
        passed = False
    if store.average_score() != 5.0:
        passed = False

    return passed


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if _tests() else 1)