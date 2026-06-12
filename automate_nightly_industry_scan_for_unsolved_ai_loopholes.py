"""Core data model and opportunity scoring for nightly AI loophole scans."""

from dataclasses import dataclass
import sys
from typing import List


@dataclass(frozen=True)
class Loophole:
    # Raw signals gathered by the industry scanner
    name: str
    competition_level: float   # 0.0 = none, 1.0 = saturated
    pain_score: float          # 0.0 = no pain, 1.0 = extreme
    willingness_to_pay: float  # 0.0 = none, 1.0 = high
    skyrocket_potential: float # 0.0 = flat, 1.0 = 100x potential


def opportunity_score(loophole: Loophole) -> float:
    # Multiplicative model: all four criteria are mandatory.
    # Weakness in any one factor suppresses the overall score.
    return (
        (1.0 - loophole.competition_level)
        * loophole.pain_score
        * loophole.willingness_to_pay
        * loophole.skyrocket_potential
    )


def decision(loophole: Loophole, threshold: float = 0.5) -> str:
    return "GO" if opportunity_score(loophole) >= threshold else "NO-GO"


@dataclass
class ScanSummary:
    count: int
    go_count: int
    avg_score: float
    best_name: str
    best_score: float


class ScanLedger:
    # Records multiple loopholes and produces aggregate stats.
    def __init__(self) -> None:
        self.entries: List[Loophole] = []

    def add(self, loophole: Loophole) -> None:
        self.entries.append(loophole)

    def summary(self) -> ScanSummary:
        if not self.entries:
            return ScanSummary(
                count=0,
                go_count=0,
                avg_score=0.0,
                best_name="",
                best_score=0.0,
            )
        scores = [opportunity_score(e) for e in self.entries]
        go_count = sum(1 for s in scores if s >= 0.5)
        avg_score = sum(scores) / len(scores)
        best_index = max(range(len(scores)), key=lambda i: scores[i])
        return ScanSummary(
            count=len(self.entries),
            go_count=go_count,
            avg_score=avg_score,
            best_name=self.entries[best_index].name,
            best_score=scores[best_index],
        )


def format_report(summary: ScanSummary) -> str:
    # Simple plain-text report suitable for CLI or email
    lines = [
        "=== Nightly AI Loophole Scan Report ===",
        f"Total scanned:  {summary.count}",
        f"GO decisions:   {summary.go_count}",
        f"Average score:  {summary.avg_score:.4f}",
    ]
    if summary.best_name:
        lines.append(f"Best candidate: {summary.best_name}")
        lines.append(f"Best score:     {summary.best_score:.4f}")
    else:
        lines.append("Best candidate: N/A")
    return "\n".join(lines)


def _test() -> int:
    # Perfect opportunity -> maximum score, GO
    perfect = Loophole(
        name="Perfect",
        competition_level=0.0,
        pain_score=1.0,
        willingness_to_pay=1.0,
        skyrocket_potential=1.0,
    )
    assert opportunity_score(perfect) == 1.0
    assert decision(perfect) == "GO"

    # Saturated market -> zero score, NO-GO
    saturated = Loophole(
        name="Saturated",
        competition_level=1.0,
        pain_score=1.0,
        willingness_to_pay=1.0,
        skyrocket_potential=1.0,
    )
    assert opportunity_score(saturated) == 0.0
    assert decision(saturated) == "NO-GO"

    # Borderline acceptable -> 0.8^3 == 0.512, just above threshold
    borderline = Loophole(
        name="Borderline",
        competition_level=0.0,
        pain_score=0.8,
        willingness_to_pay=0.8,
        skyrocket_potential=0.8,
    )
    assert abs(opportunity_score(borderline) - 0.512) < 1e-9
    assert decision(borderline) == "GO"

    # Ledger: empty state
    ledger = ScanLedger()
    empty = ledger.summary()
    assert empty.count == 0
    assert empty.go_count == 0
    assert empty.avg_score == 0.0
    assert empty.best_name == ""

    # Ledger: mixed entries
    ledger.add(perfect)
    ledger.add(saturated)
    ledger.add(borderline)
    full = ledger.summary()
    assert full.count == 3
    assert full.go_count == 2
    assert abs(full.avg_score - (1.0 + 0.0 + 0.512) / 3) < 1e-9
    assert full.best_name == "Perfect"
    assert abs(full.best_score - 1.0) < 1e-9

    # Report: empty summary rendering
    empty_report = format_report(empty)
    assert "Total scanned:  0" in empty_report
    assert "GO decisions:   0" in empty_report
    assert "Best candidate: N/A" in empty_report

    # Report: populated summary rendering
    full_report = format_report(full)
    assert "Total scanned:  3" in full_report
    assert "GO decisions:   2" in full_report
    assert "Best candidate: Perfect" in full_report
    assert "Best score:     1.0000" in full_report

    print("All tests passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_test())

    #