"""
tad_lead_finder.py
Core data model and opportunity score calculation for TAD AI.
"""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Lead:
    name: str
    problem_summary: str
    competition: int  # 0 (saturated) to 10 (no competition)
    pain: int         # 0 to 10
    pay_willingness: int  # 0 to 10
    potential: int    # 0 to 10 (100% skyrocket potential)


def score_lead(lead: Lead) -> float:
    """
    Return an opportunity score between 0.0 and 10.0.
    """
    return (
        lead.competition
        + lead.pain
        + lead.pay_willingness
        + lead.potential
    ) / 4.0


def _run_tests() -> None:
    perfect = Lead(
        name="Perfect",
        problem_summary="All tens",
        competition=10,
        pain=10,
        pay_willingness=10,
        potential=10,
    )
    assert score_lead(perfect) == 10.0

    zero = Lead(
        name="Zero",
        problem_summary="All zeros",
        competition=0,
        pain=0,
        pay_willingness=0,
        potential=0,
    )
    assert score_lead(zero) == 0.0

    mixed = Lead(
        name="Mixed",
        problem_summary="Varied",
        competition=10,
        pain=0,
        pay_willingness=10,
        potential=0,
    )
    assert score_lead(mixed) == 5.0

    print("All tests passed.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
    else:
        sys.exit(1)