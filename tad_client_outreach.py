"""Core data model and outreach priority scoring for TAD client outreach."""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class OutreachLead:
    name: str
    niche: str
    pain_score: float
    competition_level: float
    willingness_to_pay: float
    skyrocket_potential: float


def calculate_priority(lead: OutreachLead) -> float:
    # Validate inputs are within 0-10 range
    for label, value in (
        ("pain_score", lead.pain_score),
        ("competition_level", lead.competition_level),
        ("willingness_to_pay", lead.willingness_to_pay),
        ("skyrocket_potential", lead.skyrocket_potential),
    ):
        if not (0.0 <= value <= 10.0):
            raise ValueError(f"{label} must be between 0.0 and 10.0")

    inverted_competition = 10.0 - lead.competition_level
    score = (
        lead.pain_score * 0.30
        + inverted_competition * 0.30
        + lead.willingness_to_pay * 0.20
        + lead.skyrocket_potential * 0.20
    )
    return round(score, 2)


class LeadStore:
    # Simple in-memory storage and aggregation for outreach leads.
    def __init__(self):
        self._leads = []

    def add(self, lead: OutreachLead) -> None:
        self._leads.append(lead)

    def summary(self):
        # Return count, average priority, and highest-priority lead.
        if not self._leads:
            return {"count": 0, "avg_priority": 0.0, "top_lead": None}

        priorities = [calculate_priority(lead) for lead in self._leads]
        avg = round(sum(priorities) / len(priorities), 2)
        top_index = priorities.index(max(priorities))
        return {
            "count": len(self._leads),
            "avg_priority": avg,
            "top_lead": self._leads[top_index],
        }


def generate_report(store: LeadStore) -> str:
    # Build a simple text summary of the lead store.
    data = store.summary()
    count = data["count"]
    avg = data["avg_priority"]
    top = data["top_lead"]
    lines = [
        "=== TAD Client Outreach Report ===",
        f"Total Leads: {count}",
        f"Average Priority: {avg}",
    ]
    if top is not None:
        lines.append(
            f"Top Lead: {top.name} ({top.niche}) "
            f"- Priority {calculate_priority(top)}"
        )
    else:
        lines.append("Top Lead: None")
    lines.append("===================================")
    return "\n".join(lines)


def _run_tests() -> int:
    try:
        ideal = OutreachLead(
            name="Ideal",
            niche="Agentic Compliance",
            pain_score=10.0,
            competition_level=0.0,
            willingness_to_pay=10.0,
            skyrocket_potential=10.0,
        )
        assert calculate_priority(ideal) == 10.0

        crowded = OutreachLead(
            name="Crowded",
            niche="Copywriting",
            pain_score=8.0,
            competition_level=10.0,
            willingness_to_pay=8.0,
            skyrocket_potential=8.0,
        )
        assert calculate_priority(crowded) == 5.6

        store = LeadStore()
        empty = store.summary()
        assert empty["count"] == 0
        assert empty["avg_priority"] == 0.0
        assert empty["top_lead"] is None

        store.add(ideal)
        single = store.summary()
        assert single["count"] == 1
        assert single["avg_priority"] == 10.0
        assert single["top_lead"] == ideal

        store.add(crowded)
        multi = store.summary()
        assert multi["count"] == 2
        assert multi["avg_priority"] == 7.8
        assert multi["top_lead"] == ideal

        # Test report generation
        empty_store = LeadStore()
        empty_report = generate_report(empty_store)
        assert "Total Leads: 0" in empty_report
        assert "Average Priority: 0.0" in empty_report
        assert "Top Lead: None" in empty_report

        full_store = LeadStore()
        full_store.add(ideal)
        full_store.add(crowded)
        full_report = generate_report(full_store)
        assert "Total Leads: 2" in full_report
        assert "Average Priority: 7.8" in full_report
        assert "Ideal" in full_report
        assert "Agentic Compliance" in full_report
        assert "Priority 10.0" in full_report
    except Exception:
        print("FAIL")
        return 1

    print("PASS")
    return 0


def _demo() -> None:
    # Small CLI demo showing report output.
    store = LeadStore()
    store.add(
        OutreachLead(
            name="Acme AI",
            niche="Agentic Compliance",
            pain_score=9.0,
            competition_level=2.0,
            willingness_to_pay=8.0,
            skyrocket_potential=9.0,
        )
    )
    store.add(
        OutreachLead(
            name="Beta Bots",
            niche="Customer Support",
            pain_score=7.0,
            competition_level=5.0,
            willingness_to_pay=6.0,
            skyrocket_potential=7.0,
        )
    )
    print(generate_report(store))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())
    _demo()