import sys
from dataclasses import dataclass


@dataclass
class NicheOpportunity:
    # Core data model for a market loophole / niche.
    name: str
    pain_score: float
    willingness_to_pay: float
    growth_potential: float
    competition_level: float


def viability_score(opp: NicheOpportunity) -> float:
    # Calculate a 0-100 viability score.
    # Multiplies pain, willingness, and growth,
    # then penalizes by competition level.
    if not (0 <= opp.pain_score <= 10):
        raise ValueError("pain_score must be between 0 and 10")
    if not (0 <= opp.willingness_to_pay <= 10):
        raise ValueError("willingness_to_pay must be between 0 and 10")
    if not (0 <= opp.growth_potential <= 10):
        raise ValueError("growth_potential must be between 0 and 10")
    if not (0 <= opp.competition_level <= 1):
        raise ValueError("competition_level must be between 0 and 1")
    raw = (
        opp.pain_score
        * opp.willingness_to_pay
        * opp.growth_potential
        * (1.0 - opp.competition_level)
    )
    return round(raw / 10.0, 2)


class OpportunityStore:
    # Storage and aggregation layer for niche opportunities.
    def __init__(self) -> None:
        self._entries: list[NicheOpportunity] = []

    def add(self, opp: NicheOpportunity) -> None:
        self._entries.append(opp)

    def list_all(self) -> list[NicheOpportunity]:
        return list(self._entries)

    def summary(self) -> dict[str, object]:
        if not self._entries:
            return {"count": 0, "average_score": 0.0, "best": None}
        scores = [viability_score(e) for e in self._entries]
        best_index = max(range(len(scores)), key=lambda i: scores[i])
        return {
            "count": len(self._entries),
            "average_score": round(sum(scores) / len(scores), 2),
            "best": self._entries[best_index],
        }


def generate_report(store: OpportunityStore) -> str:
    # Return a plain-text summary of every opportunity.
    summary = store.summary()
    lines: list[str] = []
    lines.append("Market Niche Report")
    lines.append("=" * 20)
    lines.append(f"Total opportunities: {summary['count']}")
    lines.append(f"Average viability: {summary['average_score']}")
    lines.append("")
    for opp in store.list_all():
        score = viability_score(opp)
        lines.append(f"Name: {opp.name}")
        lines.append(f"  Viability Score: {score}")
        lines.append(f"  Pain Score: {opp.pain_score}")
        lines.append(f"  Willingness to Pay: {opp.willingness_to_pay}")
        lines.append(f"  Growth Potential: {opp.growth_potential}")
        lines.append(f"  Competition Level: {opp.competition_level}")
        lines.append("")
    return "\n".join(lines)


def _run_tests() -> int:
    # Self-checks for --test mode.
    errors = 0

    # Basic score calculation.
    opp = NicheOpportunity("Test", 5.0, 6.0, 4.0, 0.5)
    expected = round(5.0 * 6.0 * 4.0 * 0.5 / 10.0, 2)
    if viability_score(opp) != expected:
        print("FAIL: viability_score mismatch")
        errors += 1

    # Store operations.
    store = OpportunityStore()
    store.add(opp)
    summary = store.summary()
    if summary["count"] != 1:
        print("FAIL: store count mismatch")
        errors += 1
    if summary["best"] != opp:
        print("FAIL: store best mismatch")
        errors += 1

    # Empty store.
    empty = OpportunityStore()
    if empty.summary()["count"] != 0:
        print("FAIL: empty store count mismatch")
        errors += 1

    # Report content.
    report = generate_report(store)
    if "Market Niche Report" not in report:
        print("FAIL: report header missing")
        errors += 1
    if "Test" not in report:
        print("FAIL: report opportunity name missing")
        errors += 1

    # Validation errors.
    try:
        viability_score(NicheOpportunity("Bad", -1, 5, 5, 0.5))
        print("FAIL: expected ValueError for pain_score")
        errors += 1
    except ValueError:
        pass

    try:
        viability_score(NicheOpportunity("Bad", 5, 5, 5, 1.5))
        print("FAIL: expected ValueError for competition_level")
        errors += 1
    except ValueError:
        pass

    if errors:
        print(f"{errors} test(s) failed")
        return 1
    print("All tests passed")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.exit(_run_tests())
    demo = OpportunityStore()
    demo.add(NicheOpportunity("Eco Packaging", 8.0, 7.0, 9.0, 0.3))
    demo.add(NicheOpportunity("Remote Pet Care", 6.0, 5.0, 7.0, 0.6))
    print(generate_report(demo))