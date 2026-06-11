"""
TAD Lead Finder - Core data model and opportunity scoring.
"""

import sys
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Lead:
    name: str
    competition: float
    pain: float
    willingness: float
    skyrocket: float


def score_lead(lead: Lead) -> float:
    # TAD opportunity score: equally weighted average of the four pillars.
    # Returns 0.0 (worst) to 1.0 (perfect loophole).
    return (lead.competition + lead.pain + lead.willingness + lead.skyrocket) / 4.0


@dataclass
class LeadStore:
    # Aggregation layer for recording and summarizing leads.
    _leads: List[Lead] = field(default_factory=list)

    def add(self, lead: Lead) -> None:
        self._leads.append(lead)

    def count(self) -> int:
        return len(self._leads)

    def average_score(self) -> float:
        if not self._leads:
            return 0.0
        return sum(score_lead(lead) for lead in self._leads) / len(self._leads)

    def best_lead(self) -> Optional[Lead]:
        if not self._leads:
            return None
        return max(self._leads, key=score_lead)


def generate_report(store: LeadStore) -> str:
    # Build a simple text summary of the lead store.
    lines = [
        "Lead Report",
        "-----------",
        f"Total leads: {store.count()}",
        f"Average score: {store.average_score():.2f}",
    ]
    best = store.best_lead()
    if best is not None:
        lines.append(f"Best lead: {best.name} ({score_lead(best):.2f})")
    else:
        lines.append("Best lead: None")
    return "\n".join(lines)


def run_tests() -> None:
    perfect = Lead("Perfect", 1.0, 1.0, 1.0, 1.0)
    assert score_lead(perfect) == 1.0, "Perfect lead must score 1.0"

    mediocre = Lead("Mediocre", 0.5, 0.5, 0.5, 0.5)
    assert score_lead(mediocre) == 0.5, "Mediocre lead must score 0.5"

    mixed = Lead("Mixed", 1.0, 0.0, 1.0, 0.0)
    assert score_lead(mixed) == 0.5, "Mixed lead must score 0.5"

    store = LeadStore()
    assert store.count() == 0, "Empty store count must be 0"
    assert store.average_score() == 0.0, "Empty store average must be 0.0"
    assert store.best_lead() is None, "Empty store best lead must be None"

    store.add(mediocre)
    assert store.count() == 1, "Store count must be 1 after one add"
    assert store.average_score() == 0.5, "Store average must be 0.5"
    assert store.best_lead() == mediocre, "Only lead must be best"

    store.add(perfect)
    assert store.count() == 2, "Store count must be 2"
    assert store.average_score() == 0.75, "Average of 0.5 and 1.0 must be 0.75"
    assert store.best_lead() == perfect, "Best lead must be perfect"

    report = generate_report(store)
    assert "Total leads: 2" in report
    assert "Average score: 0.75" in report
    assert "Best lead: Perfect (1.00)" in report


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        run_tests()
    else:
        sys.exit("Usage: python tad_lead_finder.py --test")