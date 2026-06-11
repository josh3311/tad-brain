"""Core approval gate model and escalation logic for TAD.

Fixes underlying data/decision layer for tad_gui.py popup launch.
"""

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class ApprovalRequest:
    proposal_id: str
    estimated_cost: float
    risk_score: float
    description: str


def requires_ceo_approval(request: ApprovalRequest) -> bool:
    """Return True if the proposal must trigger an ApprovalGate popup."""
    # cost threshold for capital expenditure
    if request.estimated_cost > 1000.0:
        return True
    # risk threshold for operational danger
    if request.risk_score >= 7.0:
        return True
    return False


class ApprovalLedger:
    """Record multiple approval requests and compute aggregates."""

    def __init__(self):
        self._entries = []

    def add(self, request: ApprovalRequest) -> None:
        self._entries.append(request)

    def count(self) -> int:
        return len(self._entries)

    def count_ceo_required(self) -> int:
        return sum(
            1 for r in self._entries if requires_ceo_approval(r)
        )

    def total_cost(self) -> float:
        return sum(r.estimated_cost for r in self._entries)

    def average_risk(self) -> float:
        if not self._entries:
            return 0.0
        return sum(r.risk_score for r in self._entries) / len(
            self._entries
        )


def format_report(ledger: ApprovalLedger) -> str:
    """Return a plain-text summary of the ledger."""
    lines = [
        "TAD Approval Report",
        "===================",
        f"Total Requests: {ledger.count()}",
        f"CEO Required:   {ledger.count_ceo_required()}",
        f"Total Cost:     ${ledger.total_cost():,.2f}",
        f"Average Risk:   {ledger.average_risk():.2f}",
    ]
    return "\n".join(lines)


def _run_tests() -> None:
    """Self-checks for the escalation logic. No network needed."""
    # low cost and low risk -> no approval needed
    trivial = ApprovalRequest(
        proposal_id="TAD-001",
        estimated_cost=100.0,
        risk_score=2.0,
        description="Routine API call",
    )
    assert requires_ceo_approval(trivial) is False

    # high cost triggers approval
    expensive = ApprovalRequest(
        proposal_id="TAD-002",
        estimated_cost=5000.0,
        risk_score=3.0,
        description="GPU cluster rental",
    )
    assert requires_ceo_approval(expensive) is True

    # high risk triggers approval
    risky = ApprovalRequest(
        proposal_id="TAD-003",
        estimated_cost=50.0,
        risk_score=8.5,
        description="Unvetted code execution",
    )
    assert requires_ceo_approval(risky) is True

    # boundary values: exactly 1000 cost is False, exactly 7 risk is True
    boundary_cost = ApprovalRequest(
        proposal_id="TAD-004",
        estimated_cost=1000.0,
        risk_score=2.0,
        description="Boundary cost test",
    )
    assert requires_ceo_approval(boundary_cost) is False

    boundary_risk = ApprovalRequest(
        proposal_id="TAD-005",
        estimated_cost=50.0,
        risk_score=7.0,
        description="Boundary risk test",
    )
    assert requires_ceo_approval(boundary_risk) is True

    # storage and aggregation layer tests
    ledger = ApprovalLedger()
    assert ledger.count() == 0
    assert ledger.total_cost() == 0.0
    assert ledger.average_risk() == 0.0

    ledger.add(trivial)
    ledger.add(expensive)
    ledger.add(risky)
    assert ledger.count() == 3
    assert ledger.count_ceo_required() == 2
    assert ledger.total_cost() == 5150.0
    assert ledger.average_risk() == 4.5

    # report generation tests
    report = format_report(ledger)
    assert "Total Requests: 3" in report
    assert "CEO Required:   2" in report
    assert "$5,150.00" in report
    assert "Average Risk:   4.50" in report

    empty_ledger = ApprovalLedger()
    empty_report = format_report(empty_ledger)
    assert "Total Requests: 0" in empty_report
    assert "$0.00" in empty_report
    assert "Average Risk:   0.00" in empty_report


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        try:
            _run_tests()
            sys.exit(0)
        except AssertionError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            sys.exit(1)