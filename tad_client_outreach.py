"""Core data model and priority scorer for TAD client outreach.

The priority_score formula identifies which niche opportunities
warrant immediate outreach by balancing pain, budget, growth,
and competition.
"""

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class OutreachTarget:
    """A prospective niche or client opportunity."""
    name: str
    problem_pain: float       # 1.0 (low) to 10.0 (extreme)
    competition_level: float  # 1.0 (none) to 10.0 (saturated)
    willingness_to_pay: float # 1.0 (low) to 10.0 (high)
    growth_potential: float   # 1.0 (flat) to 10.0 (skyrocket)

    def priority_score(self) -> float:
        """Higher score = better outreach target."""
        if self.problem_pain <= 0 or self.willingness_to_pay <= 0:
            return 0.0
        if self.growth_potential <= 0 or self.competition_level <= 0:
            return 0.0
        return (
            self.problem_pain
            * self.willingness_to_pay
            * self.growth_potential
        ) / self.competition_level


def run_tests() -> int:
    """Self-check on known inputs. Returns 0 for pass, 1 for fail."""
    target_a = OutreachTarget(
        name="AI_Logistics_Gap",
        problem_pain=8.0,
        competition_level=2.0,
        willingness_to_pay=9.0,
        growth_potential=10.0,
    )
    if target_a.priority_score() != 360.0:
        return 1

    target_b = OutreachTarget(
        name="AI_Chatbot_Crowd",
        problem_pain=8.0,
        competition_level=8.0,
        willingness_to_pay=9.0,
        growth_potential=10.0,
    )
    if target_b.priority_score() != 90.0:
        return 1

    if target_a.priority_score() <= target_b.priority_score():
        return