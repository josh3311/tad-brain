"""TAD Revenue Tracker — core data model and total revenue calculation."""

import sys
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RevenueEntry:
    # single source of truth for one revenue event
    source: str   # e.g. "API Sales"
    amount: float # dollars, negative for refunds
    date: str     # YYYY-MM-DD


class RevenueTracker:
    # holds all entries and performs the one vital calculation
    def __init__(self):
        self.entries: List[RevenueEntry] = []

    def add_entry(self, source: str, amount: float, date: str) -> None:
        self.entries.append(RevenueEntry(source, amount, date))

    def total_revenue(self) -> float:
        return sum(entry.amount for entry in self.entries)

    def revenue_by_source(self) -> Dict[str, float]:
        # aggregation layer: summarize totals per source
        result: Dict[str, float] = {}
        for entry in self.entries:
            result[entry.source] = result.get(entry.source, 0.0) + entry.amount
        return result

    def text_report(self) -> str:
        # simple text summary of revenue totals
        lines: List[str] = []
        lines.append("Revenue Report")
        lines.append("=" * 14)
        lines.append(f"Total Revenue: ${self.total_revenue():.2f}")
        lines.append("")
        lines.append("By Source:")
        for source, amount in sorted(self.revenue_by_source().items()):
            lines.append(f"  {source}: ${amount:.2f}")
        return "\n".join(lines)


def run_tests() -> int:
    # self-checks with known inputs; no network or keys needed
    try:
        tracker = RevenueTracker()
        assert tracker.total_revenue() == 0.0
        assert tracker.revenue_by_source() == {}

        tracker.add_entry("API Sales", 100.0, "2024-01-01")
        tracker.add_entry("API Sales", 50.0, "2024-01-02")
        tracker.add_entry("Subscriptions", -10.0, "2024-01-03")

        assert tracker.total_revenue() == 140.0
        by_source = tracker.revenue_by_source()
        assert by_source["API Sales"] == 150.0
        assert by_source["Subscriptions"] == -10.0

        report = tracker.text_report()
        assert "Total Revenue: $140.00" in report
        assert "API Sales: $150.00" in report
        assert "Subscriptions: $-10.00" in report

        print("tests passed")
        return 0
    except AssertionError:
        print("tests failed")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(run_tests())