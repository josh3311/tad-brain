"""
Healthcare AI Bias Detection & Regulatory Compliance Platform
============================================================
TAD Build | CEO: Joshua Abraham | 2026-06-28

Opportunity: $2.1B TAM in AI bias detection for healthcare vertical.
Core insight: Competitors focus on OUTPUT bias; we detect TRAINING DATA bias
before models are deployed — earlier, cheaper, more defensible regulatory position.

MVP Scope: Healthcare vertical first (HIPAA, FDA AI/ML guidance, EU AI Act).
Revenue model: SaaS per-model audit + ongoing monitoring subscription.

Business Logic:
  1. Ingest training dataset metadata or sample records
  2. Run statistical bias detection across protected attributes
  3. Score regulatory risk (FDA, HIPAA, EU AI Act alignment)
  4. Generate compliance report with remediation recommendations
  5. Log everything to memory/ for TAD pipeline continuity
"""

import os
import sys
import json
import math
import uuid
import logging
import hashlib
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import defaultdict, Counter

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
MEMORY = ROOT / "memory" / "products"
MEMORY.mkdir(parents=True, exist_ok=True)

LOG_FILE = MEMORY / "bias_platform.log"
REPORT_DIR = MEMORY / "bias_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bias_platform")

# ── Constants ──────────────────────────────────────────────────────────────────
PROTECTED_ATTRIBUTES = [
    "age", "sex", "gender", "race", "ethnicity", "religion",
    "national_origin", "disability", "pregnancy_status",
    "socioeconomic_status", "insurance_type", "zip_code",
]

REGULATORY_FRAMEWORKS = {
    "FDA_AI_ML": {
        "full_name": "FDA Artificial Intelligence/Machine Learning Action Plan",
        "key_requirements": [
            "Pre-determined change control plan",
            "Algorithm transparency",
            "Performance monitoring across subgroups",
            "Real-world performance reporting",
        ],
        "bias_threshold_disparate_impact": 0.80,  # 4/5ths rule
        "severity_mapping": {"critical": 0.70, "high": 0.80, "medium": 0.90},
    },
    "HIPAA": {
        "full_name": "Health Insurance Portability and Accountability Act",
        "key_requirements": [
            "PHI de-identification before training",
            "Minimum necessary standard",
            "Access controls on training data",
            "Audit trails for data use",
        ],
        "bias_threshold_disparate_impact": 0.80,
        "severity_mapping": {"critical": 0.60, "high": 0.75, "medium": 0.85},
    },
    "EU_AI_ACT": {
        "full_name": "EU Artificial Intelligence Act",
        "key_requirements": [
            "High-risk AI system documentation",
            "Fundamental rights impact assessment",
            "Human oversight mechanisms",
            "Accuracy, robustness and cybersecurity",
            "Bias monitoring and corrective action",
        ],
        "bias_threshold_disparate_impact": 0.85,  # stricter than US
        "severity_mapping": {"critical": 0.70, "high": 0.85, "medium": 0.92},
    },
    "ACA_SECTION_1557": {
        "full_name": "ACA Section 1557 — Non-discrimination in Health Programs",
        "key_requirements": [
            "Non-discrimination on protected bases",
            "Language access services",
            "Accessibility requirements",
        ],
        "bias_threshold_disparate_impact": 0.80,
        "severity_mapping": {"critical": 0.65, "high": 0.78, "medium": 0.88},
    },
}

HEALTHCARE_VERTICALS = {
    "clinical_decision_support": {
        "risk_multiplier": 1.5,
        "description": "AI that directly influences clinical decisions",
        "examples": ["sepsis prediction", "cancer screening", "drug dosing"],
    },
    "revenue_cycle": {
        "risk_multiplier": 1.0,
        "description": "Billing, coding, prior authorization",
        "examples": ["claim denial prediction", "prior auth scoring"],
    },
    "population_health": {
        "risk_multiplier": 1.2,
        "description": "Risk stratification, care gap identification",
        "examples": ["readmission risk", "chronic disease management"],
    },
    "diagnostic_imaging": {
        "risk_multiplier": 1.8,
        "description": "AI reading radiology, pathology images",
        "examples": ["chest X-ray interpretation", "diabetic retinopathy"],
    },
    "mental_health": {
        "risk_multiplier": 1.6,
        "description": "Mental health screening and monitoring",
        "examples": ["depression screening", "suicide risk assessment"],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

class DatasetProfile:
    """Represents a training dataset submitted for bias audit."""

    def __init__(
        self,
        name: str,
        records: list[dict[str, Any]],
        target_column: str,
        healthcare_vertical: str = "clinical_decision_support",
        model_purpose: str = "unspecified",
    ):
        self.dataset_id = str(uuid.uuid4())[:8]
        self.name = name
        self.records = records
        self.target_column = target_column
        self.healthcare_vertical = healthcare_vertical
        self.model_purpose = model_purpose
        self.row_count = len(records)
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.checksum = self._checksum()

    def _checksum(self) -> str:
        payload = json.dumps(self.records[:10], sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def column_names(self) -> list[str]:
        if not self.records:
            return []
        return list(self.records[0].keys())

    def detected_protected_attributes(self) -> list[str]:
        cols = [c.lower() for c in self.column_names()]
        found = []
        for attr in PROTECTED_ATTRIBUTES:
            for col in cols:
                if attr in col or col in attr:
                    found.append(col)
                    break
        return list(set(found))

    def to_dict(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "row_count": self.row_count,
            "target_column": self.target_column,
            "healthcare_vertical": self.healthcare_vertical,
            "model_purpose": self.model_purpose,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "columns": self.column_names(),
            "detected_protected_attributes": self.detected_protected_attributes(),
        }


class BiasMetric:
    """A single measured bias finding for one protected attribute."""

    def __init__(
        self,
        attribute: str,
        metric_name: str,
        value: float,
        reference_value: float,
        direction: str,  # "over_represented" | "under_represented" | "balanced"
        affected_group: str,
        sample_sizes: dict[str, int],
    ):
        self.attribute = attribute
        self.metric_name = metric_name
        self.value = value
        self.reference_value = reference_value
        self.direction = direction
        self.affected_group = affected_group
        self.sample_sizes = sample_sizes
        self.disparate_impact_ratio = self._compute_dir()

    def _compute_dir(self) -> float:
        """Disparate Impact Ratio — values below 0.80 trigger regulatory flags."""
        if self.reference_value == 0:
            return 0.0
        return min(self.value / self.reference_value, self.reference_value / self.value)

    def severity(self, framework: str = "FDA_AI_ML") -> str:
        thresholds = REGULATORY_FRAMEWORKS[framework]["severity_mapping"]
        di = self.disparate_impact_ratio
        if di < thresholds["critical"]:
            return "CRITICAL"
        if di < thresholds["high"]:
            return "HIGH"
        if di < thresholds["medium"]:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict:
        return {
            "attribute": self.attribute,
            "metric_name": self.metric_name,
            "value": round(self.value, 4),
            "reference_value": round(self.reference_value, 4),
            "direction": self.direction,
            "affected_group": self.affected_group,
            "sample_sizes": self.sample_sizes,
            "disparate_impact_ratio": round(self.disparate_impact_ratio, 4),
            "severity_FDA": self.severity("FDA_AI_ML"),
            "severity_EU": self.severity("EU_AI_ACT"),
            "severity_HIPAA": self.severity("HIPAA"),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  BIAS DETECTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class TrainingBiasDetector:
    """
    Detects bias in training data BEFORE model training.
    Competitive moat: competitors measure output bias post-deployment;
    we find the root cause in the training data itself.
    """

    def __init__(self, dataset: DatasetProfile):
        self.dataset = dataset
        self.metrics: list[BiasMetric] = []
        self.warnings: list[str] = []

    # ── Representation Bias ────────────────────────────────────────────────────

    def detect_representation_bias(self) -> list[BiasMetric]:
        """
        Checks whether protected groups are proportionally represented.
        A group comprising 30% of the real population but only 5% of training
        data will produce a model that performs poorly for them.
        """
        metrics = []
        records = self.dataset.records
        if not records:
            return metrics

        for attr in self.dataset.detected_protected_attributes():
            values = [str(r.get(attr, "MISSING")).strip().lower() for r in records]
            total = len(values)
            counter = Counter(values)

            if len(counter) < 2:
                self.warnings.append(
                    f"Attribute '{attr}' has only one unique value — possible data issue."
                )
                continue

            # Most common group = reference (majority)
            sorted_groups = counter.most_common()
            majority_group, majority_count = sorted_groups[0]
            majority_rate = majority_count / total

            for group, count in sorted_groups[1:]:
                group_rate = count / total
                direction = (
                    "under_represented" if group_rate < 0.10 else
                    "over_represented" if group_rate > 0.60 else
                    "balanced"
                )
                m = BiasMetric(
                    attribute=attr,
                    metric_name="representation_rate",
                    value=group_rate,
                    reference_value=majority_rate,
                    direction=direction,
                    affected_group=group,
                    sample_sizes={majority_group: majority_count, group: count},
                )
                metrics.append(m)

        return metrics

    # ── Label Bias ─────────────────────────────────────────────────────────────

    def detect_label_bias(self) -> list[BiasMetric]:
        """
        Checks whether positive outcomes (label=1) are distributed equally
        across protected groups. Unequal positive label rates = proxy discrimination.
        """
        metrics = []
        records = self.dataset.records
        target = self.dataset.target_column

        if target not in self.dataset.column_names():
            self.warnings.append(
                f"Target column '{target}' not found — skipping label bias analysis."
            )
            return metrics

        for attr in self.dataset.detected_protected_attributes():
            group_labels: dict[str, list[int]] = defaultdict(list)

            for r in records:
                group = str(r.get(attr, "MISSING")).strip().lower()
                label_raw = r.get(target, 0)
                try:
                    label = int(float(label_raw))
                except (ValueError, TypeError):
                    label = 1 if str(label_raw).lower() in ("yes", "true", "positive", "1") else 0
                group_labels[group].append(label)

            if len(group_labels) < 2:
                continue

            group_rates = {
                g: (sum(labels) / len(labels), len(labels))
                for g, labels in group_labels.items()
                if len(labels) >= 5  # minimum sample for statistical meaning
            }

            if len(group_rates) < 2:
                continue

            # Reference = group with highest positive rate
            ref_group = max(group_rates, key=lambda g: group_rates[g][0])
            ref_rate, ref_count = group_rates[ref_group]

            for group, (rate, count) in group_rates.items():
                if group == ref_group:
                    continue
                direction = (
                    "under_represented" if rate < ref_rate * 0.80 else
                    "over_represented" if rate > ref_rate * 1.20 else
                    "balanced"
                )
                m = BiasMetric(
                    attribute=attr,
                    metric_name="positive_label_rate",
                    value=rate,
                    reference_value=ref_rate,
                    direction=direction,
                    affected_group=group,
                    sample_sizes={ref_group: ref_count, group: count},
                )
                metrics.append(m)

        return metrics

    # ── Missing Data Bias ──────────────────────────────────────────────────────

    def detect_missing_data_bias(self) -> list[BiasMetric]:
        """
        Missing data is rarely random. If records for minority groups
        are 40% missing a critical feature but majority is only 2% missing,
        the model learns to ignore that group's signals — silent exclusion.
        """
        metrics = []
        records = self.dataset.records
        if not records:
            return metrics

        all_cols = set(self.dataset.column_names())
        non_attr_cols = all_cols - set(PROTECTED_ATTRIBUTES)

        for attr in self.dataset.detected_protected_attributes():
            group_missing: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

            for r in records:
                group = str(r.get(attr, "MISSING")).strip().lower()
                for col in non_attr_cols:
                    val = r.get(col, None)
                    is_missing = val is None or str(val).strip() in ("", "null", "none", "nan", "n/a")
                    group_missing[group][col] += 1 if is_missing else 0

            group_sizes = Counter(
                str(r.get(attr, "MISSING")).strip().lower() for r in records
            )

            if len(group_sizes) < 2:
                continue

            ref_group = group_sizes.most_common(1)[0][0]
            ref_size = group_sizes[ref_group]

            for group, size in group_sizes.items():
                if group == ref_group or size < 5:
                    continue

                ref_missing_rate = (
                    sum(group_missing[ref_group].values()) /
                    max(ref_size * len(non_attr_cols), 1)
                )
                grp_missing_rate = (
                    sum(group_missing[group].values()) /
                    max(size * len(non_attr_cols), 1)
                )

                if grp_missing_rate == 0 and ref_missing_rate == 0:
                    continue

                direction = (
                    "over_represented" if grp_missing_rate > ref_missing_rate * 1.5
                    else "balanced"
                )
                m = BiasMetric(
                    attribute=attr,
                    metric_name="missing_data_rate",
                    value=grp_missing_rate,
                    reference_value=max(ref_missing_rate, 0.001),
                    direction=direction,
                    affected_group=group,
                    sample_sizes={ref_group: ref_size, group: size},
                )
                metrics.append(m)

        return metrics

    # ── Temporal Bias ──────────────────────────────────────────────────────────

    def detect_temporal_bias(self, date_column: str | None = None) -> list[BiasMetric]:
        """
        If training data was collected before a certain period,
        demographic shifts mean it no longer represents current populations.
        Detects recency bias in data collection.
        """
        metrics = []
        records = self.dataset.records

        # Auto-detect a date column if not specified
        if date_column is None:
            for col in self.dataset.column_names():
                if any(kw in col.lower() for kw in ["date", "time", "year", "created", "admitted"]):
                    date_column = col
                    break

        if not date_column:
            return metrics

        years = []
        for r in records:
            val = r.get(date_column, "")
            try:
                # Try to parse year from various formats
                if isinstance(val, int) and 1900 < val < 2030:
                    years.append(val)
                elif isinstance(val, str):
                    for part in val.split("-"):
                        if part.strip().isdigit() and 1900 < int(part.strip()) < 2030:
                            years.append(int(part.strip()))
                            break
            except (ValueError, AttributeError):
                continue

        if len(years) < 10:
            return metrics

        current_year = datetime.now().year
        old_records = sum(1 for y in years if y < current_year - 5)
        total = len(years)
        staleness_rate = old_records / total

        if staleness_rate > 0.30:
            m = BiasMetric(
                attribute=date_column,
                metric_name="temporal_staleness_rate",
                value=staleness_rate,
                reference_value=0.20,  # acceptable threshold
                direction="over_represented",
                affected_group="pre_2020_records",
                sample_sizes={"recent": total - old_records, "stale": old_records},
            )
            metrics.append(m)

        return metrics

    # ── Run All Detectors ──────────────────────────────────────────────────────

    def run_all(self) -> list[BiasMetric]:
        log.info(f"[BiasDetector] Scanning dataset '{self.dataset.name}' "
                 f"({self.dataset.row_count} rows) ...")

        all_metrics = []
        all_metrics.extend(self.detect_representation_bias())
        all_metrics.extend(self.detect_label_bias())
        all_metrics.extend(self.detect_missing_data_bias())
        all_metrics.extend(self.detect_temporal_bias())

        self.metrics = all_metrics
        log.info(f"[BiasDetector] Found {len(all_metrics)} bias metrics, "
                 f"{len(self.warnings)} warnings.")
        return all_metrics


# ═══════════════════════════════════════════════════════════════════════════════
#  REGULATORY RISK SCORER
# ═══════════════════════════════════════════════════════════════════════════════

class RegulatoryRiskScorer:
    """
    Maps bias findings to regulatory framework risk scores.
    Produces a numeric risk score (0–100) and actionable compliance gaps.
    """

    def __init__(
        self,
        metrics: list[BiasMetric],
        dataset: DatasetProfile,
        frameworks: list[str] | None = None,
    ):
        self.metrics = metrics
        self.dataset = dataset
        self.frameworks = frameworks or list(REGULATORY_FRAMEWORKS.keys())
        self.scores: dict[str, float] = {}
        self.compliance_gaps: list[dict] = []

    def score_framework(self, framework: str) -> float:
        """
        Score 0–100: 0 = clean, 100 = maximum regulatory risk.
        Formula: weighted sum of severity penalties, adjusted by vertical risk.
        """
        if framework not in REGULATORY_FRAMEWORKS:
            raise ValueError(f"Unknown framework: {framework}")

        penalty_map = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 2}
        vertical = HEALTHCARE_VERTICALS.get(
            self.dataset.healthcare_vertical, HEALTHCARE_VERTICALS["clinical_decision_support"]
        )
        multiplier = vertical["risk_multiplier"]

        raw_penalty = 0.0
        for m in self.metrics:
            sev = m.severity(framework)
            raw_penalty += penalty_map.get(sev, 0)

        # Normalize to 0–100, apply vertical multiplier, cap at 100
        base_score = min(raw_penalty, 100.0)
        adjusted = min(base_score * multiplier, 100.0)
        return round(adjusted, 1)

    def identify_compliance_gaps(self, framework: str) -> list[dict]:
        gaps = []
        fw_config = REGULATORY_FRAMEWORKS[framework]
        threshold = fw_config["bias_threshold_disparate_impact"]

        failing_metrics = [
            m for m in self.metrics
            if m.disparate_impact_ratio < threshold
        ]

        for m in failing_metrics:
            gaps.append({
                "framework": framework,
                "attribute": m.attribute,
                "affected_group": m.affected_group,
                "metric": m.metric_name,
                "disparate_impact_ratio": round(m.disparate_impact_ratio, 4),
                "required_minimum": threshold,
                "severity": m.severity(framework),
                "gap_description": (
                    f"Group '{m.affected_group}' has a disparate impact ratio of "
                    f"{m.disparate_impact_ratio:.2%}, below the {framework} threshold "
                    f"of {threshold:.0%}. This constitutes a potential regulatory violation."
                ),
            })

        return gaps

    def run(self) -> dict[str, Any]:
        log.info("[RegulatoryScorer] Computing regulatory risk scores ...")
        for fw in self.frameworks:
            self.scores[fw] = self.score_framework(fw)
            self.compliance_gaps.extend(self.identify_compliance_gaps(fw))

        overall_risk = max(self.scores.values()) if self.scores else 0.0
        risk_level = (
            "CRITICAL" if overall_risk >= 75 else
            "HIGH" if overall_risk >= 50 else
            "MEDIUM" if overall_risk >= 25 else
            "LOW"
        )

        log.info(f"[RegulatoryScorer] Overall risk: {overall_risk} ({risk_level})")
        return {
            "framework_scores": self.scores,
            "overall_risk_score": overall_risk,
            "risk_level": risk_level,
            "compliance_gaps": self.compliance_gaps,
            "total_gaps": len(self.compliance_gaps),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  REMEDIATION RECOMMENDER
# ═══════════════════════════════════════════════════════════════════════════════

class RemediationRecommender:
    """
    Translates bias findings into actionable, prioritized remediation steps.
    Each recommendation is tied to a specific metric and regulatory requirement.
    """

    REMEDIATION_PLAYBOOK = {
        "representation_rate": [
            "Collect additional training samples from under-represented groups "
            "through targeted data partnerships with FQHCs and community health centers.",
            "Apply stratified sampling during dataset construction to ensure "
            "proportional representation across all protected attribute groups.",
            "Use data augmentation techniques (SMOTE, synthetic data) as a "
            "temporary bridge while real-world data collection scales.",
            "Document the known representation gap in the model card and "
            "restrict deployment to populations where training data is representative.",
        ],
        "positive_label_rate": [
            "Audit the labeling process: who labeled this data and what "
            "criteria were used? Label bias often reflects clinician bias.",
            "Use algorithmic fairness constraints (equalized odds, "
            "demographic parity) during model training.",
            "Apply re-weighting or re-sampling to balance positive label "
            "rates across protected groups before training.",
            "Commission an independent clinical review of labels for a "
            "stratified sample across protected groups.",
        ],
        "missing_data_rate": [
            "Investigate WHY data is missing disproportionately — "
            "is it a collection process issue, EHR field coverage, or "
            "patient access patterns?",
            "Use multiple imputation methods that account for "
            "group membership rather than single-value imputation.",
            "Exclude features with >40% missingness in any protected "
            "group unless missingness itself is clinically meaningful.",
            "Flag records with high missingness during inference and "
            "route to human review rather than automated decision.",
        ],
        "temporal_staleness_rate": [
            "Establish a data refresh cadence — healthcare populations "
            "shift over 3–5 year cycles; models should retrain accordingly.",
            "Weight recent records more heavily in training using "
            "temporal weighting schemes.",
            "Monitor model performance drift monthly using a held-out "
            "current-year validation set.",
            "Document training data date range in regulatory submissions "
            "and model documentation.",
        ],
    }

    def generate(self, metrics: list[BiasMetric], risk_result: dict) -> list[dict]:
        recommendations = []
        seen = set()

        # Sort by severity (CRITICAL first)
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        sorted_metrics = sorted(
            metrics,
            key=lambda m: severity_order.get(m.severity("FDA_AI_ML"), 9)
        )

        for m in sorted_metrics:
            key = f"{m.metric_name}::{m.attribute}::{m.affected_group}"
            if key in seen:
                continue
            seen.add(key)

            steps = self.REMEDIATION_PLAYBOOK.get(m.metric_name, [
                "Investigate this bias metric with your data science team.",
                "Consult with a regulatory affairs specialist for this finding.",
            ])

            recommendations.append({
                "priority": m.severity("FDA_AI_ML"),
                "attribute": m.attribute,
                "affected_group": m.affected_group,
                "metric": m.metric_name,
                "disparate_impact_ratio": round(m.disparate_impact_ratio, 4),
                "remediation_steps": steps,
                "estimated_effort": self._estimate_effort(m),
                "regulatory_urgency": self._regulatory_urgency(m, risk_result),
            })

        return recommendations

    def _estimate_effort(self, m: BiasMetric) -> str:
        di = m.disparate_impact_ratio
        if di < 0.60:
            return "HIGH — significant data collection or architectural changes required"
        if di < 0.80:
            return "MEDIUM — resampling and re-weighting likely sufficient"
        return "LOW — minor adjustments to sampling strategy"

    def _regulatory_urgency(self, m: BiasMetric, risk_result: dict) -> str:
        sev = m.severity("FDA_AI_ML")
        overall = risk_result.get("overall_risk_score", 0)
        if sev == "CRITICAL" or overall >= 75:
            return "IMMEDIATE — do not deploy until resolved"
        if sev == "HIGH" or overall >= 50:
            return "PRE-DEPLOYMENT — resolve before submission"
        if sev == "MEDIUM":
            return "POST-DEPLOYMENT — monitor and remediate within 90 days"
        return "ROUTINE — address in next model iteration"


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPLIANCE REPORT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class ComplianceReportGenerator:
    """
    Produces a structured JSON report + human-readable summary.
    Report persisted to memory/products/bias_reports/ for TAD pipeline.
    """

    def __init__(
        self,
        dataset: DatasetProfile,
        metrics: list[BiasMetric],
        risk_result: dict,
        recommendations: list[dict],
        warnings: list[str],
    ):
        self.dataset = dataset
        self.metrics = metrics
        self.risk_result = risk_result
        self.recommendations = recommendations
        self.warnings = warnings
        self.report_id = str(uuid.uuid4())[:12]
        self.generated_at = datetime.now(timezone.utc).isoformat()

    def build_report(self) -> dict:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "platform": "TAD Healthcare AI Bias Detection Platform",
            "version": "1.0.0",
            "dataset": self.dataset.to_dict(),
            "executive_summary": self._executive_summary(),
            "bias_metrics": [m.to_dict() for m in self.metrics],
            "regulatory_risk": self.risk_result,
            "recommendations": self.recommendations,
            "warnings": self.warnings,
            "audit_trail": {
                "auditor": "TAD Automated Bias Engine",
                "methodology": "Statistical representation, label distribution, "
                               "missing data pattern, and temporal currency analysis",
                "frameworks_applied": list(REGULATORY_FRAMEWORKS.keys()),
                "report_hash": self._report_hash(),
            },
        }

    def _executive_summary(self) -> dict:
        critical = sum(1 for m in self.metrics if m.severity("FDA_AI_ML") == "CRITICAL")
        high = sum(1 for m in self.metrics if m.severity("FDA_AI_ML") == "HIGH")
        medium = sum(1 for m in self.metrics if m.severity("FDA_AI_ML") == "MEDIUM")
        low = sum(1 for m in self.metrics if m.severity("FDA_AI_ML") == "LOW")

        verdict = (
            "FAIL — DO NOT DEPLOY" if critical > 0 or self.risk_result["overall_risk_score"] >= 75
            else "CONDITIONAL PASS — Remediate HIGH findings before deployment"
            if high > 0 or self.risk_result["overall_risk_score"] >= 50
            else "PASS WITH MONITORING — Address MEDIUM findings within 90 days"
            if medium > 0
            else "PASS — No significant bias detected"
        )

        return {
            "verdict": verdict,
            "overall_risk_score": self.risk_result["overall_risk_score"],
            "risk_level": self.risk_result["risk_level"],
            "total_bias_metrics": len(self.metrics),
            "severity_breakdown": {
                "CRITICAL": critical, "HIGH": high, "MEDIUM": medium, "LOW": low
            },
            "protected_attributes_flagged": list(set(m.attribute for m in self.metrics)),
            "highest_risk_framework": (
                max(self.risk_result["framework_scores"],
                    key=self.risk_result["framework_scores"].get)
                if self.risk_result["framework_scores"] else "N/A"
            ),
            "total_compliance_gaps": self.risk_result["total_gaps"],
            "immediate_action_required": critical > 0 or self.risk_result["overall_risk_score"] >= 75,
        }

    def _report_hash(self) -> str:
        payload = json.dumps(
            [m.to_dict() for m in self.metrics],
            sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:24]

    def save(self, report: dict) -> Path:
        filename = REPORT_DIR / f"bias_report_{self.report_id}_{self.dataset.name[:20]}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            log.info(f"[ReportGenerator] Saved report to {filename}")
        except OSError as e:
            log.error(f"[ReportGenerator] Failed to save report: {e}")
            raise
        return filename

    def print_summary(self, report: dict) -> None:
        summary = report["executive_summary"]
        print("\n" + "═" * 70)
        print("  TAD HEALTHCARE AI BIAS DETECTION PLATFORM — AUDIT REPORT")
        print("═" * 70)
        print(f"  Report ID  : {report['report_id']}")
        print(f"  Dataset    : {report['dataset']['name']} ({report['dataset']['row_count']} rows)")
        print(f"  Vertical   : {report['dataset']['healthcare_vertical']}")
        print(f"  Generated  : {report['generated_at']}")
        print("─" * 70)
        print(f"  VERDICT    : {summary['verdict']}")
        print(f"  Risk Score : {summary['overall_risk_score']}/100 ({summary['risk_level']})")
        print(f"  Bias Found : {summary['total_bias_metrics']} metrics across "
              f"{len(summary['protected_attributes_flagged'])} attributes")
        print(f"  Breakdown  : CRITICAL={summary['severity_breakdown']['CRITICAL']} | "
              f"HIGH={summary['severity_breakdown']['HIGH']} | "
              f"MEDIUM={summary['severity_breakdown']['MEDIUM']} | "
              f"LOW={summary['severity_breakdown']['LOW']}")
        print("─" * 70)
        print("  REGULATORY RISK SCORES:")
        for fw, score in report["regulatory_risk"]["framework_scores"].items():
            bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
            print(f"    {fw:<25} {bar} {score:.1f}/100")
        print("─" * 70)
        print("  TOP RECOMMENDATIONS:")
        for i, rec in enumerate(report["recommendations"][:3], 1):
            print(f"  {i}. [{rec['priority']}] {rec['attribute']} / {rec['affected_group']}")
            print(f"     → {rec['remediation_steps'][0]}")
            print(f"     Urgency: {rec['regulatory_urgency']}")
        print("═" * 70 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  PLATFORM ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class HealthcareBiasPlatform:
    """
    Top-level orchestrator. Call audit() with a dataset to get a full
    bias audit report, regulatory risk scores, and remediation plan.
    """

    def __init__(self):
        log.info("[Platform] Healthcare AI Bias Detection Platform initialized.")

    def audit(
        self,
        dataset: DatasetProfile,
        frameworks: list[str] | None = None,
    ) -> dict:
        """
        Full audit pipeline:
          1. Detect training data bias
          2. Score regulatory risk
          3. Generate remediation recommendations
          4. Produce & save compliance report
        Returns the full report dict.
        """
        log.info(f"[Platform] Starting audit for dataset '{dataset.name}' ...")

        # Step 1: Bias Detection
        detector = TrainingBiasDetector(dataset)
        metrics = detector.run_all()

        # Step 2: Regulatory Risk
        scorer = RegulatoryRiskScorer(metrics, dataset, frameworks)
        risk_result = scorer.run()

        # Step 3: Remediation
        recommender = RemediationRecommender()
        recommendations = recommender.generate(metrics, risk_result)

        # Step 4: Report
        reporter = ComplianceReportGenerator(
            dataset, metrics, risk_result, recommendations, detector.warnings
        )
        report = reporter.build_report()
        report_path = reporter.save(report)
        reporter.print_summary(report)

        log.info(f"[Platform] Audit complete. Report: {report_path}")
        return report


# ═══════════════════════════════════════════════════════════════════════════════
#  SYNTHETIC DEMO DATA GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_demo_dataset(n: int = 500, seed: int = 42) -> list[dict]:
    """
    Generates a realistic synthetic clinical dataset with intentional bias
    baked in for demonstration:
    - 'race' is severely under-represented for Black and Hispanic patients
    - Positive label rates differ substantially by race
    - Missing data is 3x higher for Medicaid patients
    """
    import random
    random.seed(seed)

    race_dist = [
        ("white", 0.72),
        ("black", 0.08),          # real US pop ~13% — intentionally under-sampled
        ("hispanic", 0.06),       # real US pop ~19% — intentionally under-sampled
        ("asian", 0.09),
        ("other", 0.05),
    ]
    sex_dist = [("male", 0.52), ("female", 0.48)]
    insurance_dist = [("commercial", 0.55), ("medicare", 0.25), ("medicaid", 0.15), ("uninsured", 0.05)]

    # Positive label rates by race (readmission within 30 days)
    positive_rates = {
        "white": 0.18, "black": 0.31, "hispanic": 0.27,
        "asian": 0.14, "other": 0.22,
    }

    records = []
    for i in range(n):
        race = random.choices([r[0] for r in race_dist], weights=[r[1] for r in race_dist])[0]
        sex = random.choices([s[0] for s in sex_dist], weights=[s[1] for s in sex_dist])[0]
        insurance = random.choices(
            [ins[0] for ins in insurance_dist],
            weights=[ins[1] for ins in insurance_dist]
        )[0]
        age = random.randint(18, 90)

        # Introduce missing data bias for Medicaid patients
        missing_prob = 0.35 if insurance == "medicaid" else 0.10

        def val_or_none(v):
            return None if random.random() < missing_prob else v

        label = 1 if random.random() < positive_rates[race] else 0

        records.append({
            "patient_id": f"PT{i:05d}",
            "age": age,
            "sex": sex,
            "race": race,
            "insurance_type": insurance,
            "admission_date": f"{random.randint(2018, 2024)}-{random.randint(1, 12):02d}-01",
            "primary_diagnosis_code": val_or_none(
                random.choice(["E11", "I10", "J45", "F32", "M79", "Z87"])
            ),
            "num_prior_admissions": val_or_none(random.randint(0, 10)),
            "charlson_comorbidity_index": val_or_none(round(random.uniform(0, 8), 1)),
            "length_of_stay_days": val_or_none(random.randint(1, 21)),
            "discharge_disposition": val_or_none(
                random.choice(["home", "snf", "rehab", "ama", "expired"])
            ),
            "readmitted_30_days": label,
        })

    return records


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("TAD Healthcare AI Bias Detection Platform — DEMO RUN")
    log.info("=" * 60)

    # 1. Generate synthetic demo data
    log.info("Generating synthetic clinical training dataset (n=500)...")
    demo_records = _generate_demo_dataset(n=500)

    # 2. Create dataset profile
    dataset = DatasetProfile(
        name="readmission_prediction_v1",
        records=demo_records,
        target_column="readmitted_30_days",
        healthcare_vertical="population_health",
        model_purpose="Predict 30-day hospital readmission risk for care management prioritization",
    )

    # 3. Run full audit
    platform = HealthcareBiasPlatform()
    report = platform.audit(dataset)

    # 4. Emit final business metrics
    summary = report["executive_summary"]
    print("\n📊 BUSINESS INTELLIGENCE SUMMARY")
    print(f"   Audit Revenue Potential (SaaS): $8,500/audit + $2,400/yr monitoring")
    print(f"   Regulatory Fine Avoidance (est): "
          f"{'$2.1M–$21M' if summary['immediate_action_required'] else '$0 at current risk level'}")
    print(f"   Vertical: Population Health | Risk Multiplier: "
          f"{HEALTHCARE_VERTICALS['population_health']['risk_multiplier']}x")
    print(f"   Report saved to: memory/products/bias_reports/")
    print(f"   TAD Pipeline: audit data logged to memory/products/bias_platform.log\n")

    # 5. Exit code reflects audit verdict
    if summary["immediate_action_required"]:
        sys.exit(1)   # Signals to downstream pipeline: do not deploy
    sys.exit(0)