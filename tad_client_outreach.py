"""
Core data model and lead scoring logic for TAD client outreach.
"""

import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Lead:
    name: str
    pain_score: float  # 1-10, higher = more painful problem
    willingness_to_pay: float  # 1-10, higher = more willing
    competition_level: float  # 1-10, lower = better
    market_potential: float  # 1-10, higher = more upside


def outreach_score(lead: Lead) -> float:
    # Invert competition so that lower input yields higher contribution
    competition_factor = 11.0 - lead.competition_level
    score = (
        lead.pain_score * 0.30
        + lead.willingness_to_pay * 0.30
        + lead.market_potential * 0.30
        + competition_factor * 0.10
    )
    return round(score, 2)


class LeadStore:
    # In-memory collection with sorting and simple aggregation
    def __init__(self) -> None:
        self.leads: List[Lead] = []

    def add(self, lead: Lead) -> None:
        self.leads.append(lead)

    def ranked(self) -> List[Tuple[Lead, float]]:
        scored = [(lead, outreach_score(lead)) for lead in self.leads]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def summary(self) -> Dict[str, Any]:
        if not self.leads:
            return {"count": 0, "average_score": 0.0}
        scores = [outreach_score(lead) for lead in self.leads]
        avg = round(sum(scores) / len(scores), 2)
        return {"count": len(self.leads), "average_score": avg}


def generate_report(store: LeadStore) -> str:
    # Build a simple text summary of the lead store
    lines: List[str] = []
    summary = store.summary()
    lines.append("=== TAD Client Outreach Report ===")
    lines.append(f"Total leads: {summary['count']}")
    lines.append(f"Average outreach score: {summary['average_score']}")
    lines.append("")
    ranked = store.ranked()
    if ranked:
        lines.append("Ranked leads:")
        for lead, score in ranked:
            lines.append(f"  {lead.name}: {score}")
    else:
        lines.append("No leads in store.")
    return "\n".join(lines)


def run_tests() -> int:
    # Known input 1: excellent opportunity -> should score highest
    lead_a = Lead(
        name="NicheAI_A",
        pain_score=9.0,
        willingness_to_pay=9.0,
        competition_level=1.0,
        market_potential=9.0,
    )
    expected_a = 9.1
    actual_a = outreach_score(lead_a)
    if actual_a != expected_a:
        print(f"FAIL lead_a: expected {expected_a}, got {actual_a}")
        return 1

    # Known input 2: poor opportunity -> should score lowest
    lead_b = Lead(
        name="NicheAI_B",
        pain_score=3.0,
        willingness_to_pay=3.0,
        competition_level=9.0,
        market_potential=3.0,
    )
    expected_b = 2.9
    actual_b = outreach_score(lead_b)
    if actual_b != expected_b:
        print(f"FAIL lead_b: expected {expected_b}, got {actual_b}")
        return 1

    # Test storage and aggregation layer
    store = LeadStore()
    store.add(lead_a)
    store.add(lead_b)

    ranked = store.ranked()
    if len(ranked) != 2:
        print(f"FAIL ranked length: expected 2, got {len(ranked)}")