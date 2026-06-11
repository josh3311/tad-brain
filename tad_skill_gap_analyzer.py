"""TAD Skill Gap Analyzer - core data model and gap calculation."""

import sys
import argparse
from dataclasses import dataclass
from typing import Set, List


@dataclass(frozen=True)
class Position:
    name: str
    required_skills: Set[str]


@dataclass(frozen=True)
class GapReport:
    position_name: str
    missing_skills: Set[str]
    coverage_percent: float


def analyze_skill_gap(position: Position, available_skills: Set[str]) -> GapReport:
    # Calculate missing skills and coverage percentage for a position.
    required = position.required_skills
    if not required:
        return GapReport(
            position_name=position.name,
            missing_skills=set(),
            coverage_percent=100.0,
        )
    present = required & available_skills
    missing = required - available_skills
    coverage = (len(present) / len(required)) * 100.0
    return GapReport(
        position_name=position.name,
        missing_skills=missing,
        coverage_percent=coverage,
    )


@dataclass(frozen=True)
class SummaryReport:
    total_positions: int
    average_coverage: float
    fully_covered: int
    positions_with_gaps: List[str]
    all_missing_skills: Set[str]


class GapLedger:
    # Storage and aggregation layer for multiple gap reports.
    def __init__(self) -> None:
        self._reports: List[GapReport] = []

    def record(self, report: GapReport) -> None:
        self._reports.append(report)

    def summarize(self) -> SummaryReport:
        total = len(self._reports)
        if total == 0:
            return SummaryReport(
                total_positions=0,
                average_coverage=0.0,
                fully_covered=0,
                positions_with_gaps=[],
                all_missing_skills=set(),
            )
        average = sum(r.coverage_percent for r in self._reports) / total
        fully = sum(1 for r in self._reports if r.coverage_percent == 100.0)
        gap_names = [r.position_name for r in self._reports if r.missing_skills]
        all_missing: Set[str] = set()
        for r in self._reports:
            all_missing |= r.missing_skills
        return SummaryReport(
            total_positions=total,
            average_coverage=average,
            fully_covered=fully,
            positions_with_gaps=gap_names,
            all_missing_skills=all_missing,
        )


def run_tests() -> int:
    # Known input 1: partial coverage (1 missing skill).
    ceo = Position(
        name="CEO Agent",
        required_skills={
            "strategic_planning",
            "decision_making",
            "report_analysis",
        },
    )
    report = analyze_skill_gap(ceo, {"strategic_planning", "decision_making"})
    if report.position_name != "CEO Agent":
        print("FAIL: position name mismatch")
        return 1
    if report.missing_skills != {"report_analysis"}:
        print("FAIL: missing skills mismatch")
        return 1
    if abs(report.coverage_percent - 66.66666666666666) > 1e-9:
        print("FAIL: coverage percent mismatch")
        return 1

    # Known input 2: full coverage.
    cto = Position(
        name="CTO Agent",
        required_skills={"code_generation", "system_design"},
    )
    report2 = analyze_skill_gap(
        cto, {"code_generation", "system_design", "debugging"}
    )
    if report2.missing_skills:
        print("FAIL: expected no missing skills for full coverage")
        return 1
    if report2.coverage_percent != 100.0:
        print("FAIL: expected 100 percent coverage")
        return 1

    # Ledger tests.
    ledger = GapLedger()

    # Empty ledger.
    empty_summary = ledger.summarize()
    if empty_summary.total_positions != 0:
        print("FAIL: empty ledger total mismatch")
        return 1
    if empty_summary.average_coverage != 0.0:
        print("FAIL: empty ledger average mismatch")
        return 1

    # Record partial and full coverage.
    ledger.record(report)
    ledger.record(report2)
    summary = ledger.summarize()

    if summary.total_positions != 2:
        print("FAIL: ledger total positions mismatch")