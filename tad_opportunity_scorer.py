"""TAD Opportunity Scorer — core data model and scoring logic."""

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class Opportunity:
    # Core data model for a niche opportunity.
    name: str
    competition_level: float   # 0.0 = none, 1.0 = saturated
    pain_level: float          # 0.0 = no pain, 1.0 = extreme
    willingness_to_pay: float  # 0.0 = none, 1.0 = very high
    skyrocket_potential: float # 0.0 = flat, 1.0 = 100%+ growth


class OpportunityError(ValueError):
    # Raised when opportunity fields are out of bounds.
    pass


def score_opportunity(opp: Opportunity) -> float:
    # Calculate TAD score (0–100).
    # Weights reflect TAD mission priorities.
    for attr in (
        opp.competition_level,
        opp.pain_level,
        opp.willingness_to_pay,
        opp.skyrocket_potential,
    ):
        if not (0.0 <= attr <= 1.0):
            raise OpportunityError(
                "Opportunity metrics must be between 0.0 and 1.0"
            )

    low_competition = 1.0 - opp.competition_level
    weighted = (
        low_competition * 0.30
        + opp.pain_level * 0.30
        + opp.willingness_to_pay * 0.25
        + opp.skyrocket_potential * 0.15
    )
    return weighted * 100.0


def _run_tests():
    # Self-checks: no network or API keys needed.
    perfect = Opportunity(
        name="Perfect",
        competition_level=0.0,
        pain_level=1.0,
        willingness_to_pay=1.0,
        skyrocket_potential=1.0,
    )
    assert score_opportunity(perfect) == 100.0

    worst = Opportunity(
        name="Worst",
        competition_level=1.0,
        pain_level=0.0,
        willingness_to_pay=0.0,
        skyrocket_potential=0.0,
    )
    assert score_opportunity(worst) == 0.0

    mid = Opportunity(
        name="Mid",
        competition_level=0.5,
        pain_level=0.5,
        willingness_to_pay=0.5,
        skyrocket_potential=0.5,
    )
    assert score_opportunity(mid) == 50.0

    try:
        bad = Opportunity(
            name="Bad",
            competition_level=1.5,
            pain_level=0.0,
            willingness_to_pay=0.0,
            skyrocket_potential=0.0,
        )
        score_opportunity(bad)
        raise AssertionError("Expected OpportunityError")
    except OpportunityError:
        pass

    print("OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        print("Usage: python tad_opportunity_scorer.py --test")
        sys.exit(1)