"""Core data model and opportunity scoring for TAD client outreach."""

from dataclasses import dataclass
import sys


@dataclass
class Lead:
    company_name: str
    pain_score: int          # 1-10, higher = more painful problem
    competition_score: int   # 1-10, lower = less competition
    willingness_score: int   # 1-10, higher = more willing to pay
    potential_score: int     # 1-10, higher = skyrocket potential

    def opportunity_score(self) -> float:
        # TAD mission: high pain + willingness + potential, divided by competition.
        if self.competition_score <= 0:
            raise ValueError("competition_score must be > 0")
        return (
            self.pain_score *
            self.willingness_score *
            self.potential_score
        ) / self.competition_score


class LeadStore:
    # In-memory aggregation layer for recorded leads.
    def __init__(self):
        self.leads = []

    def add(self, lead):
        # Append a lead to the store.
        self.leads.append(lead)

    def summary(self):
        # Return count, average opportunity score, and best company name.
        if not self.leads:
            return {"count": 0, "average_score": 0.0, "best_company": None}
        scores = []
        for lead in self.leads:
            scores.append(lead.opportunity_score())
        total = sum(scores)
        best_index = 0
        best_score = scores[0]
        for i in range(1, len(scores)):
            if scores[i] > best_score:
                best_score = scores[i]
                best_index = i
        best_company = self.leads[best_index].company_name
        return {
            "count": len(self.leads),
            "average_score": total / len(self.leads),
            "best_company": best_company,
        }


def generate_report(store: LeadStore) -> str:
    # Build a plain-text report from a LeadStore summary.
    summary = store.summary()
    lines = [
        "TAD Client Outreach Report",
        "==========================",
        f"Total leads: {summary['count']}",
        f"Average opportunity score: {summary['average_score']:.2f}",
        f"Best company: {summary['best_company'] or 'N/A'}",
    ]
    if summary["count"] > 0:
        lines.append("")
        lines.append("Lead Details:")
        lines.append("-------------")
        for lead in store.leads:
            score = lead.opportunity_score()
            lines.append(
                f"- {lead.company_name}: pain={lead.pain_score}, "
                f"competition={lead.competition_score}, "
                f"willingness={lead.willingness_score}, "
                f"potential={lead.potential_score}, "
                f"score={score:.2f}"
            )
    return "\n".join(lines)


def _run_tests() -> int:
    # Known input 1: ideal niche (low competition, high fit).
    ideal = Lead("IdealCo", 9, 1, 9, 9)
    if ideal.opportunity_score() != 729.0:
        print("FAIL: ideal score mismatch")
        return 1

    # Known input 2: saturated niche (high competition, moderate fit).
    saturated = Lead("SaturatedCo", 5, 10, 5, 5)
    if saturated.opportunity_score() != 12.5:
        print("FAIL: saturated score mismatch")
        return 1

    # Test 3: empty store summary.
    store = LeadStore()
    empty_summary = store.summary()
    if empty_summary != {"count": 0, "average_score": 0.0, "best_company": None}:
        print("FAIL: empty store summary mismatch")
        return 1

    # Test 4: store aggregation.
    store.add(ideal)
    store.add(saturated)
    full_summary = store.summary()
    expected_summary = {
        "count": 2,
        "average_score": 370.75,
        "best_company": "IdealCo",
    }
    if full_summary != expected_summary:
        print("FAIL: full store summary mismatch")
        return 1

    # Test 5: empty store report.
    empty_store = LeadStore()
    empty_report = generate_report(empty_store)
    if "Total leads: 0" not in empty_report or "N/A" not in empty_report:
        print("FAIL: empty report missing expected content")
        return 1

    # Test 6: populated store report.
    populated_store = LeadStore()
    populated_store.add(ideal)
    populated_store.add(saturated)
    populated_report = generate_report(populated_store)
    if "IdealCo" not in populated_report:
        print("FAIL: populated report missing company name")
        return 1
    if "729.00" not in populated_report:
        print("FAIL: populated report missing expected score")
        return 1
    if "TAD Client Outreach Report" not in populated_report:
        print("FAIL: populated report missing header")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(_run_tests())