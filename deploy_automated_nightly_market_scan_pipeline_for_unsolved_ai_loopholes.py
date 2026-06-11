"""Core data model and opportunity scoring for TAD nightly market scans."""

from dataclasses import dataclass
import sys
from typing import List, Optional


@dataclass(frozen=True)
class Loophole:
    """Represents an unsolved AI market loophole."""
    title: str
    problem_pain: float
    willingness_to_pay: float
    skyrocket_potential: float
    competition_level: float


def score_loophole(opportunity: Loophole) -> float:
    """Calculate opportunity score.

    High pain, willingness to pay, and skyrocket potential raise the
    score. Competition suppresses it quadratically because TAD only
    pursues niches with little to no competition.
    """
    numerator = (
        opportunity.problem_pain
        * opportunity.willingness_to_pay
        * opportunity.skyrocket_potential
    )
    denominator = 1.0 + (opportunity.competition_level ** 2)
    return numerator / denominator


@dataclass
class RegistrySummary:
    count: int
    total_score: float
    average_score: float
    best_loophole: Optional[Loophole]


class LoopholeRegistry:
    """Storage and aggregation layer for recorded loopholes."""

    def __init__(self) -> None:
        self._entries: List[Loophole] = []

    def add(self, opportunity: Loophole) -> None:
        self._entries.append(opportunity)

    def summarize(self) -> RegistrySummary:
        count = len(self._entries)
        if count == 0:
            return RegistrySummary(
                count=0,
                total_score=0.0,
                average_score=0.0,
                best_loophole=None,
            )
        scores = [score_loophole(e) for e in self._entries]
        total_score = sum(scores)
        average_score = total_score / count
        best_idx = max(range(count), key=lambda i: scores[i])
        return RegistrySummary(
            count=count,
            total_score=total_score,
            average_score=average_score,
            best_loophole=self._entries[best_idx],
        )


def render_report(summary: RegistrySummary, fmt: str = "text") -> str:
    """Render a summary as plain text or HTML."""
    if fmt == "html":
        if summary.best_loophole:
            best = (
                f"  <li>Best: {summary.best_loophole.title} "
                f"(score {score_loophole(summary.best_loophole):.2f})</li>"
            )
        else:
            best = "  <li>Best: None</li>"
        return (
            "<h1>TAD Nightly Market Scan</h1>\n"
            "<ul>\n"
            f"  <li>Count: {summary.count}</li>\n"
            f"  <li>Total Score: {summary.total_score:.2f}</li>\n"
            f"  <li>Average Score: {summary.average_score:.2f}</li>\n"
            f"{best}\n"
            "</ul>"
        )
    lines = [
        "TAD Nightly Market Scan",
        "=" * 23,
        f"Loopholes:     {summary.count}",
        f"Total Score:   {summary.total_score:.2f}",
        f"Average Score: {summary.average_score:.2f}",
    ]
    if summary.best_loophole:
        lines.append(
            f"Best Pick:     {summary.best_loophole.title} "
            f"(score {score_loophole(summary.best_loophole):.2f})"
        )
    else:
        lines.append("Best Pick:     None")
    return "\n".join(lines)


def _demo() -> None:
    """Run a small CLI demo."""
    registry = LoopholeRegistry()
    registry.add(
        Loophole("Auto-CAD for HVAC", 8.0, 9.0, 7.5, 0.5)
    )
    registry.add(
        Loophole("Legal doc parser", 7.0, 8.0, 6.0, 2.0)
    )
    print(render_report(registry.summarize()))
    print()
    print(render_report(registry.summarize(), fmt="html"))


def _run_tests() -> int:
    """Quick self-checks without network or API keys."""
    perfect = Loophole(
        title="Perfect",
        problem_pain=10.0,
        willingness_to_pay=10.0,
        skyrocket_potential=10.0,
        competition_level=0.0,
    )
    assert score_loophole(perfect) == 1000.0

    high_comp = Loophole(
        title="High Competition",
        problem_pain=10.0,
        willingness_to_pay=10.0,
        skyrocket_potential=10.0,
        competition_level=3.0,
    )
    assert score_loophole(high_comp) == 100.0

    registry = LoopholeRegistry()
    empty = registry.summarize()
    assert empty.count == 0
    assert empty.total_score == 0.0
    assert empty.average_score == 0.0
    assert empty.best_loophole is None
    assert "None" in render_report(empty)
    assert "None" in render_report(empty, fmt="html")

    registry.add(high_comp)
    registry.add(perfect)
    summary = registry.summarize()
    assert summary.count == 2
    assert summary.best_loophole == perfect
    assert summary.total_score == 1100.0
    assert summary.average_score == 550.0

    text = render_report(summary)
    assert "Perfect" in text
    assert "1000.00" in text

    html = render_report(summary, fmt="html")
    assert "<h1>" in html
    assert "Perfect" in html
    assert "1000.00" in html

    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())
    _demo()