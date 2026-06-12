"""AI Output Bias Detection for Sensitive Domains.

Production module for auditing AI system outputs across hiring,
lending, and healthcare to detect demographic bias before deployment.
Calculates disparate impact, demographic parity, and flags adverse
outcomes in structured decisions and unstructured text.
"""

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MEMORY_DIR = Path("memory")
LOG_FILE = MEMORY_DIR / "tad_bias_detector.log"
AUDIT_TRAIL = MEMORY_DIR / "audit_trail.jsonl"
DEFAULT_THRESHOLD = 0.8

DOMAIN_REGISTRY = {
    "hiring": {
        "protected_attributes": ["gender", "race", "age", "ethnicity"],
        "decision_key": "hired",
        "score_key": "interview_score",
    },
    "lending": {
        "protected_attributes": ["race", "gender", "age", "marital_status"],
        "decision_key": "approved",
        "score_key": "credit_score",
    },
    "healthcare": {
        "protected_attributes": ["race", "gender", "age", "disability"],
        "decision_key": "treatment_approved",
        "score_key": "risk_score",
    },
}

TEXT_PATTERNS = {
    "gender": r"\b(male|female|man|woman|men|women|non-binary|transgender)\b",
    "race": r"\b(black|white|asian|hispanic|latino|latina|african american|caucasian)\b",
    "age": r"\b(\d{1,3}\s*(year old|years old|yo))\b|\b(aged?\s*\d{1,3})\b",
    "ethnicity": r"\b(hispanic|latino|latina|asian|african|european|middle eastern)\b",
    "marital_status": r"\b(single|married|divorced|widowed)\b",
    "disability": r"\b(disabled|disability|handicapped|wheelchair|blind|deaf)\b",
}

NEGATIVE_OUTCOME_WORDS = [
    "denied", "rejected", "excluded", "high risk", "ineligible",
    "not approved", "declined", "unqualified", "withdrawn",
]

STEREOTYPE_ADJECTIVES = [
    "unreliable", "unstable", "risky", "problematic", "difficult",
    "noncompliant", "aggressive", "unmotivated", "fragile",
]

POSITIVE_OUTCOME_WORDS = [
    "approved", "accepted", "hired", "recommended", "low risk",
    "qualified", "preferred", "selected",
]


def _ensure_memory_dir() -> None:
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Failed to create memory directory: {e}") from e


def _setup_logging() -> None:
    _ensure_memory_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


class BiasAuditTrail:
    def __init__(self) -> None:
        _ensure_memory_dir()
        self.logger = logging.getLogger("BiasAuditTrail")

    def append(self, entry: Dict[str, Any]) -> None:
        try:
            with open(AUDIT_TRAIL, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
            self.logger.info("Audit trail appended for run %s", entry.get("run_id"))
        except (OSError, IOError) as e:
            self.logger.error("Failed to write audit trail: %s", e)


class StructuredBiasAnalyzer:
    def __init__(self, domain: str, threshold: float = DEFAULT_THRESHOLD):
        if domain not in DOMAIN_REGISTRY:
            raise ValueError(f"Unknown domain: {domain}")
        self.domain = domain
        self.config = DOMAIN_REGISTRY[domain]
        self.threshold = threshold
        self.logger = logging.getLogger("StructuredBiasAnalyzer")

    def analyze(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not records:
            self.logger.warning("Empty record set provided for structured analysis")
            return {"status": "no_data", "bias_detected": False}

        results = {
            "domain": self.domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_records": len(records),
            "protected_attributes": {},
        }

        for attr in self.config["protected_attributes"]:
            self.logger.info("Analyzing protected attribute: %s", attr)
            attr_result = self._analyze_attribute(records, attr)
            results["protected_attributes"][attr] = attr_result

        return results

    def _analyze_attribute(self, records: List[Dict[str, Any]], attr: str) -> Dict[str, Any]:
        groups = defaultdict(list)
        for rec in records:
            val = rec.get(attr)
            if val is not None:
                groups[str(val).lower()].append(rec)

        if not groups:
            return {"status": "missing_attribute", "groups": {}, "bias_detected": False}

        decision_key = self.config.get("decision_key", "decision")
        group_stats = {}
        for group_name, group_records in groups.items():
            decisions = [
                1 if r.get(decision_key) in (1, True, "yes", "approved", "hired") else 0
                for r in group_records
            ]
            selection_rate = sum(decisions) / len(decisions) if decisions else 0.0
            group_stats[group_name] = {
                "count": len(group_records),
                "positive_count": sum(decisions),
                "selection_rate": round(selection_rate, 4),
            }

        ref_group = max(group_stats.items(), key=lambda x: x[1]["selection_rate"])
        ref_name, ref_data = ref_group
        ref_rate = ref_data["selection_rate"] if ref_data["selection_rate"] > 0 else 1e-9

        flagged_groups = []
        for group_name, stats in group_stats.items():
            ratio = stats["selection_rate"] / ref_rate
            parity_diff = stats["selection_rate"] - ref_rate
            stats["disparate_impact_ratio"] = round(ratio, 4)
            stats["demographic_parity_diff"] = round(parity_diff, 4)
            stats["reference_group"] = ref_name
            if ratio < self.threshold:
                stats["bias_flag"] = True
                stats["severity"] = "high" if ratio < 0.5 else "medium"
                flagged_groups.append(group_name)
            else:
                stats["bias_flag"] = False
                stats["severity"] = "none"

        return {
            "group_count": len(group_stats),
            "reference_group": ref_name,
            "group_stats": group_stats,
            "flagged_groups": flagged_groups,
            "bias_detected": len(flagged_groups) > 0,
        }


class TextBiasAnalyzer:
    def __init__(self, domain: str):
        self.domain = domain
        self.logger