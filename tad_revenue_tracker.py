"""
tad_revenue_tracker.py
Core data model and total revenue calculation for TAD AI.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Dict
import sys


@dataclass
class RevenueEntry:
    amount: float
    source: str
    date: date


class RevenueTracker:
    def __init__(self):
        self.entries: List[RevenueEntry] = []

    def add_entry(self, entry: RevenueEntry) -> None:
        self.entries.append(entry)

    def total_revenue(self) -> float:
        return sum(entry.amount for entry in self.entries)

    def revenue_by_source(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for entry in self.entries:
            result[entry.source] = result.get(entry.source, 0.0) + entry.amount
        return result


def run_tests() -> int:
    tracker = RevenueTracker()

    # Empty tracker must total zero
    if tracker.total_revenue() != 0.0:
        print("FAIL: empty tracker")
        return 1

    # Sum of two known entries
    tracker.add_entry(RevenueEntry(100.0, "Alpha", date(2026, 1, 1)))
    tracker.add_entry(RevenueEntry(250.5, "Beta", date(2026, 2, 1)))

    if tracker.total_revenue() != 350.5:
        print("FAIL: known total mismatch")
        return 1

    # Aggregation by source
    tracker.add_entry(RevenueEntry(50.0, "Alpha", date(2026, 3, 1)))
    by_source = tracker.revenue_by_source()
    if by_source.get("Alpha") != 150.0:
        print("FAIL: Alpha source aggregation mismatch")
        return 1
    if by_source.get("Beta") != 250.5:
        print("FAIL: Beta source aggregation mismatch")
        return 1
    if len(by_source) != 2:
        print("FAIL: unexpected source count")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_tests())