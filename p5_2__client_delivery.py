"""P5-2 Client Delivery — core data model and pricing logic."""

import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Deliverable:
    """A single deliverable item for a client."""
    client: str
    item: str
    weight_kg: float
    distance_km: float


RATE_PER_KG_KM = 0.01


def price(deliverable: Deliverable) -> float:
    """Calculate price for a single deliverable."""
    return deliverable.weight_kg * deliverable.distance_km * RATE_PER_KG_KM


def revenue_by_client(deliverables: List[Deliverable]) -> dict[str, float]:
    """Aggregate revenue per client."""
    totals = defaultdict(float)
    for d in deliverables:
        totals[d.client] += price(d)
    return dict(totals)


def run_tests() -> int:
    """Quick self-checks."""
    d1 = Deliverable("Alice", "box", 10.0, 5.0)
    d2 = Deliverable("Bob", "letter", 0.5, 10.0)
    d3 = Deliverable("Alice", "parcel", 2.0, 3.0)

    rev = revenue_by_client([d1, d2, d3])

    expected_alice = (10.0 * 5.0 + 2.0 * 3.0) * RATE_PER_KG_KM
    expected_bob = (0.5 * 10.0) * RATE_PER_KG_KM

    if abs(rev["Alice"] - expected_alice) > 1e-9:
        print("FAIL Alice")
        return 1
    if abs(rev["Bob"] - expected_bob) > 1e-9:
        print("FAIL Bob")