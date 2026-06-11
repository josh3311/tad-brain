"""TAD Skill Gap Analyzer — core model and readiness calculation."""

import sys
from dataclasses import dataclass
from typing import List, Dict


@dataclass(frozen=True)
class Skill:
    name: str
    current: int
    required: int
    weight: float = 1.0


@dataclass(frozen=True)
class Gap:
    name: str
    deficit: int
    risk_score: float


def compute_gaps(skills: List[Skill]) -> List[Gap]:
    """Return gaps sorted by descending risk."""
    gaps: List[Gap] = []
    for s in skills:
        deficit = max(0, s.required - s.current)
        gaps.append(Gap(s.name, deficit, deficit * s.weight))
    gaps.sort(key=lambda g: g.risk_score, reverse=True)
    return gaps


def readiness_ratio(skills: List[Skill]) -> float:
    """Weighted readiness percentage (0.0–100.0)."""
    weighted_current = 0.0
    weighted_required = 0.0
    for s in skills:
        weighted_current += min(s.current, s.required) * s.weight
        weighted_required += s.required * s.weight
    if weighted_required == 0.0:
        return 100.0
    return (weighted_current / weighted_required) * 100.0


@dataclass(frozen=True)
class Summary:
    avg_readiness: float
    total_gaps: List[Gap]


class Ledger:
    """Store multiple skill assessments and summarize them."""

    def __init__(self):
        self._entries: List[List[Skill]] = []

    def add(self, skills: List[Skill]) -> None:
        self._entries.append(list(skills))

    def summarize(self) -> Summary:
        if not self._entries:
            return Summary(0.0, [])
        total_readiness = 0.0
        gap_acc: Dict[str, tuple[int, float]] = {}
        for skills in self._entries:
            total_readiness += readiness_ratio(skills)
            for g in compute_gaps(skills):
                prev_deficit, prev_risk = gap_acc.get(g.name, (0, 0.0))
                gap_acc[g.name] = (prev_deficit + g.deficit,
                                   prev_risk + g.risk_score)
        avg_readiness = total_readiness / len(self._entries)
        total_gaps = [
            Gap(name, deficit, risk)
            for name, (deficit, risk) in gap_acc.items()
        ]
        total_gaps.sort(key=lambda g: g.risk_score, reverse=True)
        return Summary(avg_readiness, total_gaps)


def _run_tests() -> None:
    """Self-checks; raise AssertionError on failure."""
    skills = [
        Skill("Python", 60, 90, 1.0),
        Skill("Rust", 20, 80, 2.0),
    ]
    gaps = compute_gaps(skills)
    ratio = readiness_ratio(skills)

    assert len(gaps) == 2
    assert gaps[0].name == "Rust"
    assert gaps[0].deficit == 60
    assert abs(gaps[0].risk_score - 120.0) < 1e-9
    assert gaps[1].name == "Python"
    assert gaps[1].deficit == 30
    assert abs(gaps[1].risk_score - 30.0) < 1e-9

    assert abs(ratio - 40.0) < 1e-9

    full = [Skill("X", 100, 100, 1.0)]
    assert compute_gaps(full)[0].deficit == 0
    assert abs(readiness_ratio(full) - 100.0) < 1e-9

    ledger = Ledger()
    assert abs(ledger.summarize().avg_readiness - 0.0) < 1e-9
    assert ledger.summarize().total_gaps == []

    ledger.add(skills)
    ledger.add([
        Skill("Python", 80, 90, 1.0),
        Skill("Rust", 60, 80, 2.0),
    ])
    summary = ledger.summarize()
    assert abs(summary.avg_readiness - 60.0) < 1e-9
    assert len(summary.total_gaps) == 2
    assert summary.total_gaps[0].name == "Rust"


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()