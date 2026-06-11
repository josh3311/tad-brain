"""
tad_client_outreach.py
Core data model and opportunity scoring for TAD client outreach.
"""

import sys
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any


@dataclass
class OutreachTarget:
    # Minimal data model for a prospective client
    name: str
    pain_score: float          # 0.0 to 10.0
    willingness_to_pay: float  # 0.0 to 10.0
    competition_level: float   # 0.0 to 10.0, lower is better
    skyrocket_potential: float # 0.0 to 10.0


def opportunity_score(target: OutreachTarget) -> float:
    # Priority = pain * willingness * potential / (competition + 1)
    if target.pain_score <= 0 or target.willingness_to_pay <= 0:
        return 0.0
    raw = (
        target.pain_score
        * target.willingness_to_pay
        * target.skyrocket_potential
    ) / (target.competition_level + 1.0)
    return round(raw, 2)


class TargetStore:
    # Storage and aggregation layer for multiple outreach targets

    def __init__(self) -> None:
        self.targets: List[OutreachTarget] = []

    def add(self, target: OutreachTarget) -> None:
        self.targets.append(target)

    def summary(self) -> Dict[str, Any]:
        if not self.targets:
            return {
                "count": 0,
                "avg_score": 0.0,
                "best_name": None,
                "best_score": 0.0,
            }
        scored: List[Tuple[OutreachTarget, float]] = [
            (t, opportunity_score(t)) for t in self.targets
        ]
        total = sum(s for _, s in scored)
        best_target, best_score = max(scored, key=lambda x: x[1])
        return {
            "count": len(self.targets),
            "avg_score": round(total / len(scored), 2),
            "best_name": best_target.name,
            "best_score": best_score,
        }

    def ranked(self) -> List[Tuple[OutreachTarget, float]]:
        scored = [(t, opportunity_score(t)) for t in self.targets]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


def generate_report(store: TargetStore) -> str:
    # Simple text report summarizing the outreach pipeline
    summary = store.summary()
    lines = [
        "=== TAD Client Outreach Report ===",
        f"Total Targets: {summary['count']}",
        f"Average Score: {summary['avg_score']}",
    ]
    if summary["best_name"] is not None:
        lines.append(
            f"Best Prospect: {summary['best_name']} "
            f"(score {summary['best_score']})"
        )
    lines.append("")
    lines.append("Ranked Prospects:")
    for target, score in store.ranked():
        lines.append(f"  {target.name:<15} score={score}")
    lines.append("==================================")
    return "\n".join(lines)


def _run_tests() -> int:
    # Self-checks: exit 0 on pass, non-zero on fail
    ideal = OutreachTarget(
        name="IdealAI",
        pain_score=10.0,
        willingness_to_pay=10.0,
        competition_level=0.0,
        skyrocket_potential=10.0,
    )
    if opportunity_score(ideal) != 1000.0:
        print("FAIL test 1")
        return 1

    mediocre = OutreachTarget(
        name="MehCorp",
        pain_score=4.0,
        willingness_to_pay=5.0,
        competition_level=4.0,
        skyrocket_potential=6.0,
    )
    if opportunity_score(mediocre) != 24.0:
        print("FAIL test 2")
        return 1

    store = TargetStore()
    empty_summary = store.summary()
    if empty_summary["count"] != 0 or empty_summary["avg_score"] != 0.0:
        print("FAIL test 3")
        return 1
    if empty_summary["best_name"] is not None:
        print("FAIL test 4")
        return 1

    store.add(ideal)
    store.add(mediocre)
    summary = store.summary()
    if summary["count"] != 2:
        print("FAIL test 5")
        return 1
    expected_avg = round((1000.0 + 24.0) / 2, 2)
    if summary["avg_score"] != expected_avg:
        print("FAIL test 6")
        return 1
    if summary["best_name"] != "IdealAI" or summary["best_score"] != 1000.0:
        print("FAIL test 7")
        return 1

    ranked = store.ranked()
    if len(ranked) != 2:
        print("FAIL test 8")
        return 1
    if ranked[0][0].name != "IdealAI":
        print("FAIL test 9")
        return 1
    if ranked[1][0].name != "MehCorp":
        print("FAIL test 10")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())