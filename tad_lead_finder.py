"""
tad_lead_finder.py

Core data model and opportunity scoring for TAD AI lead discovery.
"""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Lead:
    """Core data model for an AI industry loophole opportunity."""
    niche_name: str
    competition_level: float  # 0.0 = none, 1.0 = saturated
    pain_severity: float      # 0.0 = none, 1.0 = extreme
    willingness_to_pay: float # 0.0 = none, 1.0 = very high
    growth_potential: float   # 0.0 = flat, 1.0 = 100%+ skyrocket


def calculate_opportunity_score(lead: Lead) -> float:
    """
    Calculate an opportunity score (0-100) for a lead.
    
    Uses a multiplicative model: an opportunity only scores highly
    when competition is low AND pain, willingness to pay, and growth
    potential are all high.
    """
    for field_name, value in [
        ("competition_level", lead.competition_level),
        ("pain_severity", lead.pain_severity),
        ("willingness_to_pay", lead.willingness_to_pay),
        ("growth_potential", lead.growth_potential),
    ]:
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    
    score = (
        (1.0 - lead.competition_level)
        * lead.pain_severity
        * lead.willingness_to_pay
        * lead.growth_potential
        * 100.0
    )
    return round(score, 2)


class LeadStore:
    """In-memory storage and aggregation for leads."""
    
    def __init__(self):
        self._leads: list[Lead] = []
    
    def add(self, lead: Lead) -> None:
        self._leads.append(lead)
    
    def summarize(self) -> dict:
        if not self._leads:
            return {
                "count": 0,
                "average_score": 0.0,
                "top_lead": None,
            }
        
        scored = [
            (lead, calculate_opportunity_score(lead))
            for lead in self._leads
        ]
        total = sum(s for _, s in scored)
        top_lead, top_score = max(scored, key=lambda x: x[1])
        
        return {
            "count": len(self._leads),
            "average_score": round(total / len(self._leads), 2),
            "top_lead": top_lead.niche_name,
            "top_score": top_score,
        }


def generate_report(store: LeadStore) -> str:
    """Return a simple text report summarizing the lead store."""
    summary = store.summarize()
    lines = [
        "TAD Lead Finder Report",
        "=" * 22,
        f"Total leads: {summary['count']}",
    ]
    if summary["count"] > 0:
        lines.append(f"Average score: {summary['average_score']}")
        lines.append(
            f"Top lead: {summary['top_lead']} "
            f"(score: {summary['top_score']})"
        )
    return "\n".join(lines)


def _run_tests() -> int:
    # Valid lead scoring
    lead = Lead(
        niche_name="AI Transcription",
        competition_level=0.2,
        pain_severity=0.8,
        willingness_to_pay=0.9,
        growth_potential=0.7,
    )
    score = calculate_opportunity_score(lead)
    expected = round((0.8 * 0.8 * 0.9 * 0.7 * 100.0), 2)
    assert score == expected, f"Expected {expected}, got {score}"
    
    # Perfect and zero boundaries
    perfect = Lead("Perfect", 0.0, 1.0, 1.0, 1.0)
    assert calculate_opportunity_score(perfect) == 100.0
    
    zero = Lead("Zero", 1.0, 1.0, 1.0, 1.0)
    assert calculate_opportunity