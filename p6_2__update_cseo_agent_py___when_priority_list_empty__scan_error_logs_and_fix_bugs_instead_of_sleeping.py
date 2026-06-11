"""cseo_agent.py — Core data model and urgency scoring for the CSEO agent.
When the priority list is empty, the agent scans error logs and
computes an urgency score to pick the next bug to fix instead of sleeping.
"""

import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Bug:
    msg: str
    urgency: float = 0.0


class BugStore:
    # Storage and aggregation layer for processed bugs.
    def __init__(self) -> None:
        self.history: List[Bug] = []
        self.counts: Dict[str, int] = defaultdict(int)

    def record(self, bug: Bug) -> None:
        self.history.append(bug)
        self.counts[bug.msg] += 1

    def summary(self) -> Dict[str, object]:
        if not self.history:
            return {"total": 0, "average_urgency": 0.0, "top_recurring": None}
        total = len(self.history)
        avg = sum(b.urgency for b in self.history) / total
        top = max(self.counts, key=self.counts.get)
        return {
            "total": total,
            "average_urgency": avg,
            "top_recurring": top,
            "top_count": self.counts[top],
        }


def score_urgency(line: str) -> float:
    u = 0.0
    if "ERROR" in line:
        u += 10.0
    if "CRITICAL" in line:
        u += 20.0
    return u


def scan_logs(lines: List[str]) -> List[Bug]:
    return [
        Bug(msg=l.strip(), urgency=score_urgency(l))
        for l in lines
        if score_urgency(l) > 0
    ]


def pick_next(bugs: List[Bug]) -> Bug:
    return max(bugs, key=lambda b: b.urgency)


def run_cycle(priority: List[Bug], logs: List[str], store: BugStore) -> None:
    if priority:
        store.record(priority.pop(0))
        return
    found = scan_logs(logs)
    if found:
        store.record(pick_next(found))


def generate_report(store: BugStore) -> str:
    # Simple text summary of processed bugs.
    s = store.summary()
    lines: List[str] = []
    lines.append("CSEO Agent Report")
    lines.append("=" * 30)
    lines.append(f"Total bugs processed: {s['total']}")
    lines.append(f"Average urgency: {s['average_urgency']:.2f}")
    top = s.get("top_recurring")
    if top is not None:
        count = s.get("top_count", 0)
        lines.append(f"Top recurring issue: {top} ({count} occurrences)")
    return "\n".join(lines)


def _test() -> None:
    # Urgency scoring
    assert score_urgency("INFO ok") == 0.0
    assert score_urgency("ERROR fail") == 10.0
    assert score_urgency("CRITICAL ERROR") == 30.0

    # Log scanning
    logs = ["INFO x", "ERROR disk full", "CRITICAL meltdown"]
    bugs = scan_logs(logs)
    assert len(bugs) == 2
    assert bugs[0].urgency == 10.0
    assert bugs[1].urgency == 20.0

    # Pick next
    assert pick_next(bugs).msg == "CRITICAL meltdown"

    # Storage and aggregation
    store = BugStore()
    assert store.summary()["total"] == 0
    store.record(Bug("a", 5.0))
    store.record(Bug("b", 15.0))
    store.record(Bug("a", 5.0))
    s = store.summary()
    assert s["total"] == 3
    assert abs(s["average_urgency"] - 8.333333) < 0.001
    assert s["top_recurring"] == "a"
    assert s["top_count"] == 2

    # Cycle drains priority first
    store2 = BugStore()
    run_cycle([Bug("prio", 99.0)], logs, store2)
    assert store2.history[0].msg == "prio"

    # Cycle falls back to logs when priority empty
    store3 = BugStore()
    run_cycle([], logs, store3)
    assert store3.history[0].msg == "CRITICAL meltdown"

    # Report generation
    rpt = generate_report(BugStore())
    assert "Total bugs processed: 0" in rpt
    assert "Average urgency: 0.00" in rpt
    assert "Top recurring" not in rpt

    store4 = BugStore()
    store4.record(Bug("timeout", 10.0))
    store4.record(Bug("timeout", 10.0))
    store4.record(Bug("crash", 25.0))
    rpt2 = generate_report(store4)
    assert "Top recurring issue: timeout (2 occurrences)" in rpt2


if __name__ == "__main__":
    if "--test" in sys.argv:
        _test()