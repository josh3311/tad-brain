"""Feedback loop back to CSEO — core data model and loopback score."""

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class FeedbackPulse:
    score: float
    signal: str


def loopback_score(pulse: FeedbackPulse) -> float:
    """Compute loopback score from pulse."""
    if pulse.signal == "strong":
        return min(pulse.score * 1.2, 1.0)
    if pulse.signal == "weak":
        return pulse.score * 0.8
    return pulse.score


class FeedbackLedger:
    """Store multiple pulses and compute aggregate statistics."""

    def __init__(self):
        self._entries = []

    def record(self, pulse: FeedbackPulse) -> None:
        self._entries.append(pulse)

    def summary(self) -> dict:
        if not self._entries:
            return {"count": 0, "avg_raw": 0.0, "avg_loopback": 0.0}
        count = len(self._entries)
        total_raw = sum(p.score for p in self._entries)
        total_loopback = sum(loopback_score(p) for p in self._entries)
        return {
            "count": count,
            "avg_raw": total_raw / count,
            "avg_loopback": total_loopback / count,
        }


def format_report(ledger: FeedbackLedger, fmt: str = "text") -> str:
    """Return a summary report in text or HTML."""
    summary = ledger.summary()
    if fmt == "html":
        return (
            "<h1>Feedback Report</h1>\n"
            "<ul>\n"
            f"  <li>Count: {summary['count']}</li>\n"
            f"  <li>Avg Raw: {summary['avg_raw']:.2f}</li>\n"
            f"  <li>Avg Loopback: {summary['avg_loopback']:.2f}</li>\n"
            "</ul>"
        )
    return (
        "Feedback Report\n"
        f"  Count: {summary['count']}\n"
        f"  Avg Raw: {summary['avg_raw']:.2f}\n"
        f"  Avg Loopback: {summary['avg_loopback']:.2f}"
    )


def _run_tests() -> None:
    strong = FeedbackPulse(score=0.5, signal="strong")
    weak = FeedbackPulse(score=0.5, signal="weak")
    neutral = FeedbackPulse(score=0.5, signal="neutral")

    assert loopback_score(strong) == 0.6
    assert loopback_score(weak) == 0.4
    assert loopback_score(neutral) == 0.5

    try:
        strong.score = 0.9
        raise AssertionError("expected frozen instance")
    except AttributeError:
        pass

    ledger = FeedbackLedger()
    assert ledger.summary() == {"count": 0, "avg_raw": 0.0, "avg_loopback": 0.0}

    ledger.record(strong)
    ledger.record(weak)
    ledger.record(neutral)
    result = ledger.summary()
    assert result["count"] == 3
    assert result["avg_raw"] == 0.5
    assert result["avg_loopback"] == 0.5

    # Tests for the new report feature
    empty = FeedbackLedger()
    assert "Count: 0" in format_report(empty, "text")
    assert "Avg Raw: 0.00" in format_report(empty, "text")
    assert "<h1>Feedback Report</h1>" in format_report(empty, "html")
    assert "<li>Count: 0</li>" in format_report(empty, "html")

    assert "Count: 3" in format_report(ledger, "text")
    assert "Avg Loopback: 0.50" in format_report(ledger, "text")
    assert "<li>Avg Loopback: 0.50</li>" in format_report(ledger, "html")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
        print("ok")
    else:
        # CLI demo of the report feature
        demo = FeedbackLedger()
        demo.record(FeedbackPulse(0.8, "strong"))
        demo.record(FeedbackPulse(0.4, "weak"))
        demo.record(FeedbackPulse(0.6, "neutral"))
        print(format_report(demo, "text"))
        print()
        print(format_report(demo, "html"))