"""Core data model and TAD opportunity scoring logic."""

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Opportunity:
    """A niche opportunity evaluated by TAD."""
    name: str
    competition: float      # 0.0 = no competition, 1.0 = saturated
    pain: float             # 0.0 = no pain, 1.0 = extreme
    willingness_to_pay: float  # 0.0 = none, 1.0 = high
    growth_potential: float    # 0.0 = flat, 1.0 = skyrocket


def tad_score(opp: Opportunity) -> float:
    """Calculate TAD score: high value multiplied by low competition wins."""
    value = opp.pain + opp.willingness_to_pay + opp.growth_potential
    return round(value * (1.0 - opp.competition), 4)


class LeadStore:
    """Simple in-memory store for Opportunity entries with summarization."""

    def __init__(self) -> None:
        self._leads = []

    def add(self, opp: Opportunity) -> None:
        self._leads.append(opp)

    def best(self) -> Optional[Opportunity]:
        if not self._leads:
            return None
        return max(self._leads, key=tad_score)

    def average_score(self) -> float:
        if not self._leads:
            return 0.0
        return round(sum(tad_score(o) for o in self._leads) / len(self._leads), 4)

    def summarize(self) -> dict:
        best_opp = self.best()
        return {
            "count": len(self._leads),
            "average_score": self.average_score(),
            "best": best_opp.name if best_opp else None,
            "best_score": tad_score(best_opp) if best_opp else 0.0,
        }


def generate_report(store: LeadStore, html: bool = False) -> str:
    """Return a simple text or HTML report summarizing the lead store."""
    summary = store.summarize()
    if html:
        lines = [
            "<html><body>",
            "  <h1>TAD Lead Report</h1>",
            "  <ul>",
            f"    <li>Count: {summary['count']}</li>",
            f"    <li>Average Score: {summary['average_score']}</li>",
            f"    <li>Best Lead: {summary['best']}</li>",
            f"    <li>Best Score: {summary['best_score']}</li>",
            "  </ul>",
            "</body></html>",
        ]
        return "\n".join(lines)
    lines = [
        "TAD Lead Report",
        "===============",
        f"Count:         {summary['count']}",
        f"Average Score: {summary['average_score']}",
        f"Best Lead:     {summary['best']}",
        f"Best Score:    {summary['best_score']}",
    ]
    return "\n".join(lines)


def _run_tests() -> int:
    """Self-checks. Returns 0 on pass, raises AssertionError on fail."""
    # Perfect niche: no competition, maximum value signals
    ideal = Opportunity("Ideal", 0.0, 1.0, 1.0, 1.0)
    assert tad_score(ideal) == 3.0, f"ideal score failed: {tad_score(ideal)}"

    # Saturated niche: high value but destroyed by competition
    saturated = Opportunity("Saturated", 1.0, 1.0, 1.0, 1.0)
    assert tad_score(saturated) == 0.0, f"saturated score failed: {tad_score(saturated)}"

    # Moderate niche: mid values
    moderate = Opportunity("Moderate", 0.5, 0.5, 0.5, 0.5)
    assert tad_score(moderate) == 0.75, f"moderate score failed: {tad_score(moderate)}"

    # --- LeadStore tests ---
    store = LeadStore()

    # Empty store behavior
    assert store.best() is None
    assert store.average_score() == 0.0
    empty_summary = store.summarize()
    assert empty_summary == {
        "count": 0,
        "average_score": 0.0,
        "best": None,
        "best_score": 0.0,
    }

    # Non-empty store behavior
    store.add(moderate)
    store.add(ideal)
    store.add(saturated)

    assert store.best() == ideal
    assert store.average_score() == 1.25

    full_summary = store.summarize()
    assert full_summary == {
        "count": 3,
        "average_score": 1.25,
        "best": "Ideal",
        "best_score": 3.0,
    }

    # --- Report generation tests ---
    text_report = generate_report(store, html=False)
    assert "TAD Lead Report" in text_report
    assert "Count:         3" in text_report
    assert "Average Score: 1.25" in text_report
    assert "Best Lead:     Ideal" in text_report
    assert "Best Score:    3.0" in text_report

    html_report = generate_report(store, html=True)
    assert "<html><body>" in html_report
    assert "<h1>TAD Lead Report</h1>" in html_report
    assert "<li>Count: 3</li>" in html_report
    assert "<li>Average Score: 1.25</li>" in html_report
    assert "<li>Best Lead: Ideal</li>" in html_report
    assert "<li>Best Score: 3.0</li>" in html_report
    assert "</body></html>" in html_report

    empty_store = LeadStore()
    empty_text = generate_report(empty_store, html=False)
    assert "Best Lead:     None" in empty_text
    assert "Best Score:    0.0" in empty_text

    return 0


def _demo() -> None:
    """Small CLI demo creating sample leads and printing reports."""
    store = LeadStore()
    store.add(Opportunity("AI Tutors", 0.2, 0.9, 0.8, 0.9))
    store.add(Opportunity("SaaS for Dentists", 0.6, 0.5, 0.6, 0.4))
    store.add(Opportunity("Niche Newsletters", 0.1, 0.7, 0.5, 0.8))

    print(generate_report(store, html=False))
    print()
    print(generate_report(store, html=True))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        try:
            exit(_run_tests())
        except AssertionError as e:
            print(f"TEST FAILED: {e}", file=sys.stderr)
            exit(1)
    else:
        _demo()