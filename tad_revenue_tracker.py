"""
tad_revenue_tracker.py

Core data model and annualized revenue calculation for TAD.
"""

from dataclasses import dataclass
import sys
from typing import List


@dataclass(frozen=True)
class RevenueDeal:
    """Immutable record for a single revenue deal."""
    name: str
    monthly_value: float


def annualized_revenue(deals: List[RevenueDeal]) -> float:
    """Return total annualized revenue from a list of deals."""
    return sum(deal.monthly_value for deal in deals) * 12


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        assert annualized_revenue([]) == 0.0

        d1 = RevenueDeal(name="Alpha", monthly_value=100.0)
        assert annualized_revenue([d1]) == 1200.0

        d2 = RevenueDeal(name="Beta", monthly_value=50.0)
        assert annualized_revenue([d1, d2]) == 1800.0

        try:
            d1.monthly_value = 200.0
            raise AssertionError("frozen dataclass should reject mutation")
        except AttributeError:
            pass

        print("All tests passed.")
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()