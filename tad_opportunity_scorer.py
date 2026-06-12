"""TAD Opportunity Scorer — core data model and scoring calculation."""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Opportunity:
    # TAD niche criteria
    name: str
    competition: float  # 0-10, lower is better (0 = no competition)
    pain: float         # 0-10, higher is better
    willingness: float  # 0-10, higher is better
    skyrocket: float    # 0-10, higher is better


def score_opportunity(opp: Opportunity) -> float:
    # Score = (pain * willingness * skyrocket) / competition, capped at 100.
    # Floor competition at 0.1 to avoid division by zero.
    comp = max(opp.competition, 0.1)
    raw = (opp.pain * opp.willingness * opp.skyrocket) / comp
    return min(raw, 100.0)


def run_tests() -> int:
    errors = 0

    # Test 1: perfect niche (low competition, high everything) -> 100.0
    perfect = Opportunity("AI Loophole X", 1.0, 10.0, 10.0, 10.0)
    if score_opportunity(perfect) != 100.0:
        errors += 1

    # Test 2: saturated dud (high competition, low everything) -> 0.1
    dud = Opportunity("Saturated Dud", 10.0, 1.0, 1.0, 1.0)
    if score_opportunity(dud) != 0.1:
        errors += 1

    return errors


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_tests())