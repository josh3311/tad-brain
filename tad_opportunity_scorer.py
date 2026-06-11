"""
TAD Opportunity Scorer — core data model and geometric-mean score,
plus storage/aggregation layer.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import sys
import math


@dataclass(frozen=True)
class Opportunity:
    # 0.0 = worst, 1.0 = best for each axis
    competition: float  # 1.0 means no competition
    pain: float         # 1.0 means extremely painful problem
    willingness: float  # 1.0 means high willingness to pay
    potential: float    # 1.0 means 100% skyrocket potential


def score_opportunity(opp: Opportunity) -> float:
    """Return the opportunity score as the geometric mean of the four factors."""
    vals = (opp.competition, opp.pain, opp.willingness, opp.potential)
    for v in vals:
        if not (0.0 <= v <= 1.0):
            raise ValueError("All opportunity fields must be in [0.0, 1.0]")
    product = vals[0] * vals[1] * vals[2] * vals[3]
    if product == 0.0:
        return 0.0
    return product ** 0.25


class OpportunityStore:
    """Simple aggregation layer for multiple Opportunity records."""

    def __init__(self) -> None:
        self._entries: List[Opportunity] = []

    def add(self, opp: Opportunity) -> None:
        """Record a new opportunity."""
        self._entries.append(opp)

    def count(self) -> int:
        """Return number of recorded opportunities."""
        return len(self._entries)

    def best(self) -> Optional[Opportunity]:
        """Return the opportunity with the highest score, or None if empty."""
        if not self._entries:
            return None
        return max(self._entries, key=score_opportunity)

    def average_score(self) -> float:
        """Return arithmetic mean of scores; 0.0 if empty."""
        if not self._entries:
            return 0.0
        total = sum(score_opportunity(o) for o in self._entries)
        return total / len(self._entries)

    def summary(self) -> Dict[str, float]:
        """Return a summary dict with count, average_score, and best_score."""
        best_opp = self.best()
        return {
            "count": float(self.count()),
            "average_score": self.average_score(),
            "best_score": score_opportunity(best_opp) if best_opp else 0.0,
        }


def generate_report(store: OpportunityStore) -> str:
    """Return a plain text summary of the opportunities in the store."""
    summary = store.summary()
    lines = [
        "Opportunity Report",
        "==================",
        f"Count: {int(summary['count'])}",
        f"Average Score: {summary['average_score']:.4f}",
        f"Best Score: {summary['best_score']:.4f}",
    ]
    best = store.best()
    if best:
        lines.append("Best Opportunity:")
        lines.append(f"  Competition: {best.competition:.2f}")
        lines.append(f"  Pain: {best.pain:.2f}")
        lines.append(f"  Willingness: {best.willingness:.2f}")
        lines.append(f"  Potential: {best.potential:.2f}")
    return "\n".join(lines)


def run_tests() -> int:
    """Self-checks. Return 0 on pass, 1 on fail."""
    try:
        # core model tests
        perfect = Opportunity(1.0, 1.0, 1.0, 1.0)
        assert math.isclose(score_opportunity(perfect), 1.0), "perfect score failed"

        zero_comp = Opportunity(0.0, 1.0, 1.0, 1.0)
        assert math.isclose(score_opportunity(zero_comp), 0.0), (
            "zero competition score failed"
        )

        known = Opportunity(1.0, 1.0, 1.0, 0.0625)
        assert math.isclose(score_opportunity(known), 0.5), "known score failed"

        # validation tests
        try:
            score_opportunity(Opportunity(1.5, 0.5, 0.5, 0.5))
            raise AssertionError("invalid value did not raise")
        except ValueError:
            pass

        # store tests
        store = OpportunityStore()
        assert store.count() == 0
        assert store.best() is None
        assert store.average_score() == 0.0

        store.add(perfect)
        assert store.count() == 1
        assert store.best() == perfect

        store.add(zero_comp)
        assert store.count() == 2
        assert store.best() == perfect

        store.add(known)
        avg = store.average_score()
        assert math.isclose(avg, (1.0 + 0.0 + 0.5) / 3.0), "average score failed"

        summary = store.summary()
        assert summary["count"] == 3.0
        assert math.isclose(summary["best_score"], 1.0)
        assert math.isclose(summary["average_score"], avg)

        # report output tests
        rstore = OpportunityStore()
        rstore.add(Opportunity(1.0, 1.0, 1.0, 1.0))
        rstore.add(Opportunity(0.0, 1.0, 1.0, 1.0))
        report = generate_report(rstore)
        assert "Opportunity Report" in report
        assert "Count: 2" in report
        assert "Average Score:" in report
        assert "Best Score:" in report
        assert "Best Opportunity:" in report
        assert "Competition: 1.00" in report

        empty_report = generate_report(OpportunityStore())
        assert "Count: 0" in empty_report
        assert "Best Opportunity:" not in empty_report

    except AssertionError as e:
        print(f"FAIL: {e}")
        return 1
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_tests())

    # small CLI demo
    demo = OpportunityStore()
    demo.add(Opportunity(0.8, 0.9, 0.7, 0.6))
    demo.add(Opportunity(0.2, 0.5, 0.4, 0.3))
    print(generate_report(demo))