"""TAD Revenue Tracker - core data model and net profit calculation."""

from dataclasses import dataclass
from typing import Dict, List
import sys


@dataclass
class Transaction:
    source: str
    revenue: float
    api_cost: float


class RevenueTracker:
    def __init__(self) -> None:
        self.transactions: List[Transaction] = []

    def add(self, txn: Transaction) -> None:
        self.transactions.append(txn)

    def total_revenue(self) -> float:
        return sum(t.revenue for t in self.transactions)

    def total_api_cost(self) -> float:
        return sum(t.api_cost for t in self.transactions)

    def net_profit(self) -> float:
        return self.total_revenue() - self.total_api_cost()

    def profit_by_source(self) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for t in self.transactions:
            net = t.revenue - t.api_cost
            result[t.source] = result.get(t.source, 0.0) + net
        return result


class Ledger:
    # Storage layer that accumulates multiple RevenueTracker batches.
    def __init__(self) -> None:
        self.batches: Dict[str, RevenueTracker] = {}

    def record(self, name: str, tracker: RevenueTracker) -> None:
        if name not in self.batches:
            self.batches[name] = tracker
        else:
            self.batches[name].transactions.extend(tracker.transactions)


def _test() -> None:
    rt = RevenueTracker()
    rt.add(Transaction("ads", 100.0, 10.0))
    rt.add(Transaction("subs", 50.0, 5.0))

    assert rt.total_revenue() == 150.0
    assert rt.total_api_cost() == 15.0
    assert rt.net_profit() == 135.0

    by_src = rt.profit_by_source()
    assert by_src == {"ads": 90.0, "subs": 45.0}

    ledger = Ledger()
    ledger.record("batch1", rt)
    assert ledger.batches["batch1"].net_profit() == 135.0

    rt2 = RevenueTracker()
    rt2.add(Transaction("ads", 20.0, 2.0))
    ledger.record("batch1", rt2)
    assert ledger.batches["batch1"].total_revenue() == 170.0

    print("PASS")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        try:
            _test()
        except Exception:
            sys.exit(1)
    else:
        print("Usage: python tad_revenue_tracker.py --test")