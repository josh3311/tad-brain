"""
tad_lead_finder core module.

Data model for an AI niche opportunity and its viability scoring
based on TAD's four criteria:
- low competition
- high pain
- willingness to pay
- 100x skyrocket potential
"""

import dataclasses
import sys
from typing import List, Optional


@dataclasses.dataclass(frozen=True)
class Lead:
    """Represents a single niche opportunity."""
    name: str
    competition: float  # 0=no competition benefit, 10=zero competition
    pain: float         # 0=no pain, 10=extreme pain
    willingness: float  # 0=won't pay, 10=eager to pay
    skyrocket: float    # 0=no potential, 10=100x potential

    def score(self) -> float:
        return (
            self.competition
            + self.pain
            + self.willingness
            + self.skyrocket
        ) / 4.0


def _run_tests() -> None:
    lead = Lead("Test", 8.0, 9.0, 7.0, 6.0)
    assert lead.name == "Test"
    assert lead.score() == 7.5
    try:
        lead.name = "X"
        raise AssertionError("frozen instance should be immutable")
    except dataclasses.FrozenInstanceError:
        pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
        sys.exit(0)