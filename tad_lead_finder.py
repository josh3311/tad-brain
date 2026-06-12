"""
tad_lead_finder.py
Core data model and viability evaluator for TAD AI lead discovery.
"""

import sys
from dataclasses import dataclass


@dataclass
class Lead:
    """Represents a niche opportunity discovered by TAD."""
    name: str
    competition_index: float   # 0.0 (none) to 1.0 (saturated)
    pain_score: float          # 0.0 to 10.0
    willingness_to_pay: float  # 0.0 to 10.0
    skyrocket_potential: float # 0.0 to 10.0, where 10.0 = 100%+ upside


def evaluate_lead(lead: Lead) -> dict:
    """
    Compute TAD viability score (0.0-100.0) and GO/NO-GO verdict.
    Weights mirror the TAD mission prompt priorities.
    """
    if not (0.0 <= lead.competition_index <= 1.0):
        raise ValueError("competition_index must be between 0.0 and 1.0")
    for field in (lead.pain_score, lead.willingness_to_pay, lead.skyrocket_potential):
        if not (0.0 <= field <= 10.0):
            raise ValueError("Scores must be between 0.0 and 10.0")

    # Normalize factors to 0.0-1.0
    competition_factor