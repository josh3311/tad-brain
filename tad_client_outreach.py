"""TAD client outreach — core niche opportunity scorer."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class NicheOpportunity:
    name: str
    competition_level: float   # 0 = none, 10 = saturated
    pain_score: float          # 0 = no pain, 10 = extreme
    willingness_to_pay: float  # 0 = unwilling, 10 = very willing
    skyrocket_potential: float # 0 = flat, 10 = 100x+ potential


def opportunity_score(niche: NicheOpportunity) -> float:
    """Score a niche; higher is better, rewards low competition."""
    return (
        niche.pain_score
        * niche.willingness_to_pay
        * niche.skyrocket_potential
    ) / (niche.competition_level + 1.0)


class NicheStore:
    """Storage and aggregation layer for niche opportunities."""

    def __init__(self) -> None:
        self._entries: List[NicheOpportunity] = []

    def add(self, niche: NicheOpportunity) -> None:
        self._