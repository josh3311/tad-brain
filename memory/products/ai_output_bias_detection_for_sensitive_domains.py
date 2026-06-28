"""
AI Output Bias Detection for Sensitive Domains
===============================================
Production-quality bias detection engine for AI outputs across regulated verticals:
healthcare, finance, legal, hiring, housing, and education.

Detects demographic bias, disparate impact, sentiment disparities, and representation
gaps in AI-generated text. Provides compliance-grade audit trails and actionable
remediation recommendations.

Author: TAD Build Agent
Build Date: 2026-06-28
Target: memory/products/ai_output_bias_detection_for_sensitive_domains.py
"""

import os
import re
import json
import math
import uuid
import logging
import hashlib
import statistics
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory bootstrap
# ---------------------------------------------------------------------------
MEMORY_DIR = Path("memory")
PRODUCTS_DIR = MEMORY_DIR / "products"
LOG_DIR = MEMORY_DIR / "logs"
AUDIT_DIR = MEMORY_DIR / "bias_audits"

for _d in [MEMORY_DIR, PRODUCTS_DIR, LOG_DIR, AUDIT_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "bias_detection.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("BiasDetector")

# ---------------------------------------------------------------------------
# Domain definitions — protected attributes + sensitive term lexicons
# ---------------------------------------------------------------------------
DOMAIN_CONFIG: dict[str, dict] = {
    "healthcare": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "sex", "age", "disability",
            "religion", "national_origin", "socioeconomic_status",
        ],
        "sensitive_terms": {
            "race": ["black", "white", "hispanic", "latino", "asian", "native", "indigenous",
                     "african american", "caucasian", "minority", "marginalized"],
            "gender": ["woman", "man", "female", "male", "transgender", "nonbinary",
                       "she", "he", "her", "him", "they"],
            "age": ["elderly", "old", "young", "aging", "geriatric", "pediatric",
                    "senior", "adolescent", "millennial"],
            "disability": ["disabled", "handicapped", "impaired", "wheelchair",
                           "deaf", "blind", "mentally ill", "neurodivergent"],
        },
        "compliance_frameworks": ["HIPAA", "ACA Section 1557", "ADA", "CMS Non-Discrimination"],
        "bias_threshold": 0.15,
    },
    "finance": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "age", "marital_status",
            "national_origin", "religion", "disability",
        ],
        "sensitive_terms": {
            "race": ["black", "white", "hispanic", "asian", "minority", "urban", "suburban"],
            "gender": ["woman", "man", "female", "male", "single mother", "single father"],
            "age": ["young", "old", "elderly", "retiree", "student", "millennial"],
            "socioeconomic": ["poor", "wealthy", "low-income", "high-income", "subprime"],
        },
        "compliance_frameworks": ["ECOA", "Fair Housing Act", "CFPB Guidelines", "FCRA"],
        "bias_threshold": 0.10,
    },
    "hiring": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "age", "disability", "pregnancy",
            "religion", "national_origin", "sexual_orientation", "veteran_status",
        ],
        "sensitive_terms": {
            "gender": ["woman", "man", "female", "male", "mother", "father",
                       "maternity", "paternity", "he", "she", "they"],
            "age": ["young", "energetic", "digital native", "old", "experienced veteran",
                    "recent graduate", "over-qualified"],
            "race": ["diverse", "minority", "underrepresented", "urban", "suburban"],
            "disability": ["able-bodied", "disabled", "wheelchair", "impaired"],
        },
        "compliance_frameworks": ["Title VII", "ADEA", "ADA", "EEOC Guidelines", "OFCCP"],
        "bias_threshold": 0.12,
    },
    "legal": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "age", "religion",
            "national_origin", "disability", "socioeconomic_status",
        ],
        "sensitive_terms": {
            "race": ["black", "white", "hispanic", "asian", "minority", "thug",
                     "gang", "urban", "immigrant"],
            "gender": ["woman", "man", "female", "male", "emotional", "aggressive"],
            "socioeconomic": ["poor", "homeless", "low-income", "welfare", "public defender"],
        },
        "compliance_frameworks": ["Equal Justice", "6th Amendment", "ABA Model Rules"],
        "bias_threshold": 0.10,
    },
    "housing": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "familial_status", "national_origin",
            "religion", "disability", "age",
        ],
        "sensitive_terms": {
            "race": ["black", "white", "hispanic", "asian", "neighborhood", "urban",
                     "suburban", "gentrification", "minority"],
            "family": ["children", "family", "single parent", "pregnant"],
            "disability": ["disabled", "wheelchair", "accessible", "service animal"],
        },
        "compliance_frameworks": ["Fair Housing Act", "HUD Guidelines", "ADA"],
        "bias_threshold": 0.12,
    },
    "education": {
        "protected_attributes": [
            "race", "ethnicity", "gender", "disability", "language",
            "socioeconomic_status", "religion", "national_origin",
        ],
        "sensitive_terms": {
            "race": ["black", "white", "hispanic", "asian", "minority",
                     "achievement gap", "at-risk"],
            "gender": ["boy", "girl", "male", "female", "he", "she"],
            "disability": ["learning disability", "special needs", "IEP", "504"],
            "socioeconomic": ["low-income", "free lunch", "Title I", "underprivileged"],
        },
        "compliance_frameworks": ["FERPA", "IDEA", "Title IX", "Title VI", "ADA Section 504"],
        "bias_threshold": 0.15,
    },
}

# ---------------------------------------------------------------------------
# Sentiment word lists (lightweight — no external NLP dependency required)
# ---------------------------------------------------------------------------
POSITIVE_WORDS = frozenset([
    "excellent", "outstanding", "exceptional", "superior", "strong", "capable",
    "skilled", "qualified", "competent", "reliable", "effective", "efficient",
    "talented", "proficient", "successful", "accomplished", "promising",
    "recommended", "approved", "eligible", "deserving", "suitable",
])

NEGATIVE_WORDS = frozenset([
    "poor", "weak", "inadequate", "unqualified", "risky", "problematic",
    "concerning", "unreliable", "ineffective", "unsuitable", "ineligible",
    "denied", "rejected", "failure", "lacking", "insufficient", "substandard",
    "questionable", "doubtful", "unlikely", "struggling", "difficult",
])

HEDGE_WORDS = frozenset([
    "might", "may", "could", "perhaps", "possibly", "likely", "unlikely",
    "seems", "appears", "suggests", "tends", "generally", "typically",
    "usually", "often", "sometimes", "rarely",
])

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BiasSignal:
    """A single detected bias indicator."""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    signal_type: str = ""          # "sentiment_disparity" | "representation_gap" | "stereotyping" | "disparate_impact"
    protected_attribute: str = ""
    severity: str = ""             # "critical" | "high" | "medium" | "low"
    severity_score: float = 0.0    # 0.0–1.0
    evidence: str = ""
    affected_groups: list[str] = field(default_factory=list)
    recommendation: str = ""
    compliance_risk: list[str] = field(default_factory=list)


@dataclass
class BiasReport:
    """Full bias audit report for one AI output."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    domain: str = ""
    input_hash: str = ""           # SHA-256 of original text (privacy-preserving)
    text_length: int = 0
    overall_bias_score: float = 0.0   # 0.0 (clean) – 1.0 (severely biased)
    risk_level: str = ""              # "PASS" | "REVIEW" | "FAIL"
    signals: list[BiasSignal] = field(default_factory=list)
    sentiment_by_group: dict[str, float] = field(default_factory=dict)
    representation_counts: dict[str, int] = field(default_factory=dict)
    compliance_frameworks: list[str] = field(default_factory=list)
    remediation_required: bool = False
    remediation_suggestions: list[str] = field(default_factory=list)
    auditor_notes: str = ""


@dataclass
class BatchSummary:
    """Aggregated summary across multiple outputs."""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: str = ""
    total_outputs: int = 0
    passed: int = 0
    review: int = 0
    failed: int = 0
    avg_bias_score: float = 0.0
    top_signals: list[str] = field(default_factory=list)
    highest_risk_outputs: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Core detector
# ---------------------------------------------------------------------------

class BiasDetector:
    """
    Production bias detector for AI-generated text in regulated domains.
    
    Runs five detection passes:
      1. Representation analysis — are protected groups mentioned equitably?
      2. Sentiment disparity — do different groups receive different sentiment?
      3. Stereotype pattern matching — flags known stereotyping phrases
      4. Hedge asymmetry — are hedge words applied unevenly across groups?
      5. Disparate impact proxy — outcome-language analysis by group
    """

    # Known stereotyping patterns (regex → attribute → description)
    STEREOTYPE_PATTERNS: list[tuple[str, str, str]] = [
        # Gender stereotypes
        (r"\b(women|females?)\b.{0,40}\b(emotional|irrational|nurturing|caring|gentle)\b",
         "gender", "Female-emotional stereotype"),
        (r"\b(men|males?)\b.{0,40}\b(aggressive|assertive|dominant|strong)\b",
         "gender", "Male-dominance stereotype"),
        (r"\b(men|males?)\b.{0,60}\b(better|superior|stronger).{0,30}\b(lead|manag|tech|engineer)\b",
         "gender", "Male-competence stereotype in technical domains"),
        # Age stereotypes
        (r"\b(older|elderly|senior)\b.{0,50}\b(struggle|difficult|slow|resistant|technophob)\b",
         "age", "Age-based technology struggle stereotype"),
        (r"\b(young|millennial)\b.{0,40}\b(lazy|entitled|narciss)\b",
         "age", "Youth-laziness stereotype"),
        # Race stereotypes
        (r"\b(urban|inner.?city)\b.{0,40}\b(crime|violent|danger|risk)\b",
         "race", "Racial proxy language linking urban areas to crime"),
        (r"\b(asian)\b.{0,50}\b(model minority|always good at math|naturally)\b",
         "race", "Model minority stereotype"),
        # Disability stereotypes
        (r"\b(disabled|handicapped)\b.{0,50}\b(burden|dependent|limited|unable)\b",
         "disability", "Disability-as-burden framing"),
        # Socioeconomic
        (r"\b(poor|low.?income)\b.{0,40}\b(criminal|lazy|uneducat|motivat)\b",
         "socioeconomic_status", "Poverty-character stereotype"),
    ]

    # Outcome language that may signal disparate impact when group-adjacent
    OUTCOME_NEGATIVE_PROXIES = frozenset([
        "denied", "rejected", "ineligible", "high risk", "not recommended",
        "declined", "flagged", "unsuitable", "disqualified", "not approved",
        "additional review", "further scrutiny",
    ])
    OUTCOME_POSITIVE_PROXIES = frozenset([
        "approved", "eligible", "qualified", "recommended", "low risk",
        "accepted", "suitable", "selected", "granted", "fast-tracked",
    ])

    def __init__(self, domain: str):
        if domain not in DOMAIN_CONFIG:
            raise ValueError(
                f"Unknown domain '{domain}'. "
                f"Valid: {list(DOMAIN_CONFIG.keys())}"
            )
        self.domain = domain
        self.config = DOMAIN_CONFIG[domain]
        self.threshold = self.config["bias_threshold"]
        logger.info(f"BiasDetector initialized | domain={domain} | threshold={self.threshold}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, text: str, context: Optional[str] = None) -> BiasReport:
        """
        Analyze a single AI output for bias.

        Args:
            text: The AI-generated text to analyze.
            context: Optional contextual note for the audit trail.

        Returns:
            BiasReport with full findings.
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty.")

        report = BiasReport(
            domain=self.domain,
            input_hash=hashlib.sha256(text.encode()).hexdigest(),
            text_length=len(text),
            compliance_frameworks=self.config["compliance_frameworks"],
            auditor_notes=context or "",
        )

        lower_text = text.lower()

        # Five detection passes
        self._pass_representation(report, lower_text)
        self._pass_sentiment_disparity(report, lower_text)
        self._pass_stereotype_patterns(report, text, lower_text)
        self._pass_hedge_asymmetry(report, lower_text)
        self._pass_disparate_impact_proxies(report, lower_text)

        # Score aggregation
        report.overall_bias_score = self._aggregate_score(report.signals)
        report.risk_level = self._risk_level(report.overall_bias_score)
        report.remediation_required = report.risk_level in ("REVIEW", "FAIL")

        if report.remediation_required:
            report.remediation_suggestions = self._build_remediation(report)

        self._save_report(report)
        logger.info(
            f"Analysis complete | id={report.report_id} | "
            f"score={report.overall_bias_score:.3f} | risk={report.risk_level} | "
            f"signals={len(report.signals)}"
        )
        return report

    def analyze_batch(self, texts: list[str]) -> BatchSummary:
        """
        Analyze multiple AI outputs and return aggregated summary.

        Args:
            texts: List of AI-generated texts.

        Returns:
            BatchSummary with aggregate statistics.
        """
        if not texts:
            raise ValueError("texts list cannot be empty.")

        summary = BatchSummary(domain=self.domain, total_outputs=len(texts))
        scores: list[float] = []
        signal_counter: dict[str, int] = defaultdict(int)

        for i, text in enumerate(texts):
            try:
                report = self.analyze(text, context=f"batch item {i+1}/{len(texts)}")
                scores.append(report.overall_bias_score)
                if report.risk_level == "PASS":
                    summary.passed += 1
                elif report.risk_level == "REVIEW":
                    summary.review += 1
                else:
                    summary.failed += 1
                    summary.highest_risk_outputs.append(report.report_id)

                for sig in report.signals:
                    signal_counter[sig.signal_type] += 1
            except Exception as exc:
                logger.warning(f"Batch item {i+1} failed analysis: {exc}")
                summary.total_outputs -= 1  # Don't count errored items

        summary.avg_bias_score = statistics.mean(scores) if scores else 0.0
        summary.top_signals = [
            s for s, _ in sorted(signal_counter.items(), key=lambda x: -x[1])
        ][:5]

        self._save_batch_summary(summary)
        logger.info(
            f"Batch complete | total={summary.total_outputs} | "
            f"passed={summary.passed} | review={summary.review} | "
            f"failed={summary.failed} | avg_score={summary.avg_bias_score:.3f}"
        )
        return summary

    def compare_outputs(
        self, group_a_text: str, group_b_text: str,
        group_a_label: str = "Group A", group_b_label: str = "Group B"
    ) -> dict:
        """
        Directly compare two AI outputs for the same scenario but different demographic groups.
        Classic A/B bias audit: present identical prompts with only demographic variable changed.

        Returns dict with disparity analysis.
        """
        report_a = self.analyze(group_a_text, context=f"compare: {group_a_label}")
        report_b = self.analyze(group_b_text, context=f"compare: {group_b_label}")

        score_delta = abs(report_a.overall_bias_score - report_b.overall_bias_score)
        sentiment_a = self._overall_sentiment_score(group_a_text.lower())
        sentiment_b = self._overall_sentiment_score(group_b_text.lower())
        sentiment_delta = abs(sentiment_a - sentiment_b)

        result = {
            "comparison_id": str(uuid.uuid4()),
            "domain": self.domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "group_a": {
                "label": group_a_label,
                "report_id": report_a.report_id,
                "bias_score": report_a.overall_bias_score,
                "risk_level": report_a.risk_level,
                "sentiment": round(sentiment_a, 4),
            },
            "group_b": {
                "label": group_b_label,
                "report_id": report_b.report_id,
                "bias_score": report_b.overall_bias_score,
                "risk_level": report_b.risk_level,
                "sentiment": round(sentiment_b, 4),
            },
            "disparity": {
                "bias_score_delta": round(score_delta, 4),
                "sentiment_delta": round(sentiment_delta, 4),
                "disparate_treatment_detected": (
                    score_delta > self.threshold or sentiment_delta > 0.2
                ),
                "higher_bias_group": (
                    group_a_label if report_a.overall_bias_score >= report_b.overall_bias_score
                    else group_b_label
                ),
            },
            "compliance_flags": self.config["compliance_frameworks"] if (
                score_delta > self.threshold
            ) else [],
        }

        # Persist comparison
        comp_path = AUDIT_DIR / f"comparison_{result['comparison_id'][:8]}.json"
        try:
            comp_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Could not save comparison: {exc}")

        return result

    # ------------------------------------------------------------------
    # Detection passes
    # ------------------------------------------------------------------

    def _pass_representation(self, report: BiasReport, lower_text: str) -> None:
        """
        Count mentions of each group within each protected attribute.
        Flag extreme representation imbalances (one group dominates or is absent).
        """
        counts: dict[str, dict[str, int]] = {}
        sensitive_terms = self.config.get("sensitive_terms", {})

        for attribute, terms in sensitive_terms.items():
            counts[attribute] = {}
            for term in terms:
                pattern = r"\b" + re.escape(term) + r"\b"
                hits = len(re.findall(pattern, lower_text))
                if hits > 0:
                    counts[attribute][term] = hits
                    report.representation_counts[term] = hits

        for attribute, term_counts in counts.items():
            if not term_counts:
                continue
            values = list(term_counts.values())
            if len(values) < 2:
                continue
            max_v, min_v = max(values), min(values)
            if max_v == 0:
                continue
            imbalance_ratio = (max_v - min_v) / max_v
            if imbalance_ratio > 0.75:
                dominant = max(term_counts, key=term_counts.get)
                absent = [t for t, c in term_counts.items() if c == min_v]
                severity_score = min(imbalance_ratio, 1.0)
                report.signals.append(BiasSignal(
                    signal_type="representation_gap",
                    protected_attribute=attribute,
                    severity=self._severity_label(severity_score),
                    severity_score=severity_score,
                    evidence=(
                        f"'{dominant}' mentioned {max_v}x vs "
                        f"{absent[:3]} mentioned {min_v}x "
                        f"(imbalance={imbalance_ratio:.0%})"
                    ),
                    affected_groups=absent[:3],
                    recommendation=(
                        f"Ensure equitable representation of all {attribute} groups. "
                        f"Review why '{dominant}' dominates coverage."
                    ),
                    compliance_risk=self.config["compliance_frameworks"],
                ))

    def _pass_sentiment_disparity(self, report: BiasReport, lower_text: str) -> None:
        """
        Measure sentiment valence in sentences containing each group term.
        Flag if one group consistently receives more negative framing.
        """
        sentences = re.split(r"[.!?\n]+", lower_text)
        sensitive_terms = self.config.get("sensitive_terms", {})

        group_sentiments: dict[str, list[float]] = defaultdict(list)

        for sentence in sentences:
            for attribute, terms in sensitive_terms.items():
                for term in terms:
                    if re.search(r"\b" + re.escape(term) + r"\b", sentence):
                        score = self._sentence_sentiment(sentence)
                        group_sentiments[term].append(score)

        group_avg: dict[str, float] = {}
        for term, scores in group_sentiments.items():
            if scores:
                group_avg[term] = statistics.mean(scores)

        report.sentiment_by_group = {k: round(v, 4) for k, v in group_avg.items()}

        # Compare within each attribute
        for attribute, terms in sensitive_terms.items():
            attr_scores = {t: group_avg[t] for t in terms if t in group_avg}
            if len(attr_scores) < 2:
                continue
            best = max(attr_scores.values())
            worst = min(attr_scores.values())
            delta = best - worst

            if delta > 0.25:
                negative_group = min(attr_scores, key=attr_scores.get)
                positive_group = max(attr_scores, key=attr_scores.get)
                severity_score = min(delta / 0.8, 1.0)
                report.signals.append(BiasSignal(
                    signal_type="sentiment_disparity",
                    protected_attribute=attribute,
                    severity=self._severity_label(severity_score),
                    severity_score=severity_score,
                    evidence=(
                        f"Sentiment gap of {delta:.2f} between "
                        f"'{positive_group}' (+{group_avg[positive_group]:.2f}) and "
                        f"'{negative_group}' ({group_avg[negative_group]:.2f})"
                    ),
                    affected_groups=[negative_group],
                    recommendation=(
                        f"Review tone applied to '{negative_group}'. "
                        f"Ensure consistent, neutral framing across all {attribute} groups."
                    ),
                    compliance_risk=self.config["compliance_frameworks"],
                ))

    def _pass_stereotype_patterns(
        self, report: BiasReport, original_text: str, lower_text: str
    ) -> None:
        """Match known stereotyping regex patterns."""
        for pattern, attribute, description in self.STEREOTYPE_PATTERNS:
            matches = re.findall(pattern, lower_text, re.IGNORECASE | re.DOTALL)
            if matches:
                # Find the original text snippet for evidence
                first_match = re.search(
                    pattern, lower_text, re.IGNORECASE | re.DOTALL
                )
                snippet = ""
                if first_match:
                    start = max(0, first_match.start() - 20)
                    end = min(len(lower_text), first_match.end() + 20)
                    snippet = f"…{lower_text[start:end]}…"

                severity_score = min(0.4 + (len(matches) - 1) * 0.15, 1.0)
                report.signals.append(BiasSignal(
                    signal_type="stereotyping",
                    protected_attribute=attribute,
                    severity=self._severity_label(severity_score),
                    severity_score=severity_score,
                    evidence=f"{description} | {len(matches)} instance(s) | '{snippet}'",
                    affected_groups=[attribute],
                    recommendation=(
                        f"Remove or rephrase stereotype-reinforcing language. "
                        f"Replace with factual, individual-focused framing."
                    ),
                    compliance_risk=self.config["compliance_frameworks"],
                ))

    def _pass_hedge_asymmetry(self, report: BiasReport, lower_text: str) -> None:
        """
        Detect asymmetric hedge/uncertainty language applied to different demographic groups.
        E.g., 'she might qualify' vs 'he qualifies'.
        """
        sentences = re.split(r"[.!?\n]+", lower_text)
        sensitive_terms = self.config.get("sensitive_terms", {})

        hedged_by_group: dict[str, int] = defaultdict(int)
        sentence_by_group: dict[str, int] = defaultdict(int)

        for sentence in sentences:
            has_hedge = any(
                re.search(r"\b" + re.escape(h) + r"\b", sentence)
                for h in HEDGE_WORDS
            )
            for attribute, terms in sensitive_terms.items():
                for term in terms:
                    if re.search(r"\b" + re.escape(term) + r"\b", sentence):
                        sentence_by_group[term] += 1
                        if has_hedge:
                            hedged_by_group[term] += 1

        hedge_rates: dict[str, float] = {}
        for term, count in sentence_by_group.items():
            if count >= 2:  # Need at least 2 sentences to measure rate
                hedge_rates[term] = hedged_by_group[term] / count

        if len(hedge_rates) < 2:
            return

        for attribute, terms in sensitive_terms.items():
            attr_rates = {t: hedge_rates[t] for t in terms if t in hedge_rates}
            if len(attr_rates) < 2:
                continue
            max_rate = max(attr_rates.values())
            min_rate = min(attr_rates.values())
            if max_rate - min_rate > 0.40:
                high_hedge_group = max(attr_rates, key=attr_rates.get)
                severity_score = min((max_rate - min_rate) / 0.8, 1.0)
                report.signals.append(BiasSignal(
                    signal_type="hedge_asymmetry",
                    protected_attribute=attribute,
                    severity=self._severity_label(severity_score * 0.7),  # slightly softer
                    severity_score=severity_score * 0.7,
                    evidence=(
                        f"'{high_hedge_group}' sentences hedged at {max_rate:.0%} "
                        f"vs other groups at {min_rate:.0%}"
                    ),
                    affected_groups=[high_hedge_group],
                    recommendation=(
                        f"Apply consistent confidence language across all {attribute} groups. "
                        f"Uncertainty language should reflect facts, not group membership."
                    ),
                    compliance_risk=self.config["compliance_frameworks"],
                ))

    def _pass_disparate_impact_proxies(self, report: BiasReport, lower_text: str) -> None:
        """
        Detect outcome language (approved/denied/high-risk) appearing
        disproportionately near certain group terms.
        """
        WINDOW = 150  # characters each side
        sensitive_terms = self.config.get("sensitive_terms", {})

        positive_by_group: dict[str, int] = defaultdict(int)
        negative_by_group: dict[str, int] = defaultdict(int)

        for attribute, terms in sensitive_terms.items():
            for term in terms:
                for match in re.finditer(r"\b" + re.escape(term) + r"\b", lower_text):
                    start = max(0, match.start() - WINDOW)
                    end = min(len(lower_text), match.end() + WINDOW)
                    window_text = lower_text[start:end]

                    for pos in self.OUTCOME_POSITIVE_PROXIES:
                        if pos in window_text:
                            positive_by_group[term] += 1
                    for neg in self.OUTCOME_NEGATIVE_PROXIES:
                        if neg in window_text:
                            negative_by_group[term] += 1

        for attribute, terms in sensitive_terms.items():
            neg_counts = {t: negative_by_group[t] for t in terms if negative_by_group[t] > 0}
            pos_counts = {t: positive_by_group[t] for t in terms if positive_by_group[t] > 0}

            if not neg_counts and not pos_counts:
                continue

            # Check if negative outcomes cluster around specific groups
            all_terms_with_outcomes = set(neg_counts) | set(pos_counts)
            if len(all_terms_with_outcomes) < 2:
                continue

            for term in neg_counts:
                neg = neg_counts.get(term, 0)
                pos = pos_counts.get(term, 0)
                total = neg + pos
                if total < 2:
                    continue
                negative_rate = neg / total
                if negative_rate > 0.70:
                    severity_score = min(negative_rate, 1.0)
                    report.signals.append(BiasSignal(
                        signal_type="disparate_impact",
                        protected_attribute=attribute,
                        severity=self._severity_label(severity_score),
                        severity_score=severity_score,
                        evidence=(
                            f"'{term}' co-occurs with negative outcome language "
                            f"{neg}x vs positive {pos}x "
                            f"(negative rate={negative_rate:.0%})"
                        ),
                        affected_groups=[term],
                        recommendation=(
                            f"Review whether outcome language associated with '{term}' "
                            f"reflects legitimate criteria or proxy discrimination. "
                            f"Consider disparate impact legal analysis under "
                            f"{', '.join(self.config['compliance_frameworks'][:2])}."
                        ),
                        compliance_risk=self.config["compliance_frameworks"],
                    ))

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _sentence_sentiment(self, sentence: str) -> float:
        """
        Lightweight sentiment score: -1.0 (very negative) to +1.0 (very positive).
        Does not require external NLP libraries.
        """
        words = re.findall(r"\b\w+\b", sentence)
        if not words:
            return 0.0
        pos = sum(1 for w in words if w in POSITIVE_WORDS)
        neg = sum(1 for w in words if w in NEGATIVE_WORDS)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / max(len(words), 1) * 3  # scale up, clamp below

    def _overall_sentiment_score(self, lower_text: str) -> float:
        """Aggregate sentiment across all sentences."""
        sentences = re.split(r"[.!?\n]+", lower_text)
        scores = [self._sentence_sentiment(s) for s in sentences if s.strip()]
        return statistics.mean(scores) if scores else 0.0

    def _aggregate_score(self, signals: list[BiasSignal]) -> float:
        """
        Compute overall bias score from detected signals.
        Uses diminishing returns formula so adding minor signals
        doesn't artificially inflate above 1.0.
        """
        if not signals:
            return 0.0
        # Weight critical > high > medium > low
        weight_map = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.15}
        raw = sum(weight_map.get(s.severity, 0.2) * s.severity_score for s in signals)
        # Sigmoid-like compression into [0, 1]
        return 1.0 - math.exp(-raw * 0.8)

    def _severity_label(self, score: float) -> str:
        if score >= 0.75:
            return "critical"
        elif score >= 0.50:
            return "high"
        elif score >= 0.25:
            return "medium"
        return "low"

    def _risk_level(self, score: float) -> str:
        if score < self.threshold:
            return "PASS"
        elif score < self.threshold * 2.5:
            return "REVIEW"
        return "FAIL"

    # ------------------------------------------------------------------
    # Remediation
    # ------------------------------------------------------------------

    def _build_remediation(self, report: BiasReport) -> list[str]:
        suggestions: list[str] = []

        signal_types = {s.signal_type for s in report.signals}
        high_severity = [s for s in report.signals if s.severity in ("critical", "high")]

        if "sentiment_disparity" in signal_types:
            suggestions.append(
                "Audit tone calibration: run outputs through neutral rewriting guidelines "
                "ensuring identical sentiment framing for equivalent scenarios across all groups."
            )
        if "representation_gap" in signal_types:
            suggestions.append(
                "Implement representation quotas in prompt engineering: "
                "explicitly instruct the model to reference all relevant groups proportionally."
            )
        if "stereotyping" in signal_types:
            suggestions.append(
                "Add stereotype filter to post-processing pipeline: "
                "maintain a blocked-phrase list derived from audit findings and validate each output."
            )
        if "disparate_impact" in signal_types:
            suggestions.append(
                "Conduct disparate impact statistical analysis across production outputs. "
                "Document business necessity justification for any differential outcomes "
                f"as required under {', '.join(self.config['compliance_frameworks'][:2])}."
            )
        if "hedge_asymmetry" in signal_types:
            suggestions.append(
                "Standardize confidence language: use fixed uncertainty templates "
                "applied uniformly regardless of demographic context."
            )

        if high_severity:
            suggestions.append(
                f"URGENT: {len(high_severity)} critical/high severity signal(s) detected. "
                "Halt production use of this output until human compliance review is complete."
            )

        suggestions.append(
            f"Schedule compliance review against: {', '.join(self.config['compliance_frameworks'])}. "
            "Document findings in your AI governance register."
        )

        return suggestions

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_report(self, report: BiasReport) -> None:
        path = AUDIT_DIR / f"report_{report.report_id[:8]}_{self.domain}.json"
        try:
            path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
            logger.debug(f"Report saved: {path}")
        except OSError as exc:
            logger.warning(f"Could not save report: {exc}")

    def _save_batch_summary(self, summary: BatchSummary) -> None:
        path = AUDIT_DIR / f"batch_{summary.batch_id[:8]}_{self.domain}.json"
        try:
            path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
            logger.debug(f"Batch summary saved: {path}")
        except OSError as exc:
            logger.warning(f"Could not save batch summary: {exc}")


# ---------------------------------------------------------------------------
# Report renderer (human-readable console output)
# ---------------------------------------------------------------------------

class ReportRenderer:
    """Renders BiasReport and BatchSummary to human-readable console output."""

    SEVERITY_ICONS = {
        "critical": "🔴",
        "high":     "🟠",
        "medium":   "🟡",
        "low":      "🟢",
    }
    RISK_ICONS = {"PASS": "✅", "REVIEW": "⚠️ ", "FAIL": "❌"}

    @classmethod
    def render_report(cls, report: BiasReport) -> str:
        lines = [
            "",
            "═" * 68,
            f"  AI OUTPUT BIAS DETECTION REPORT",
            f"  Domain: {report.domain.upper()} | Risk: {cls.RISK_ICONS.get(report.risk_level, '?')} {report.risk_level}",
            "═" * 68,
            f"  Report ID  : {report.report_id[:16]}…",
            f"  Timestamp  : {report.timestamp}",
            f"  Input hash : {report.input_hash[:32]}…",
            f"  Text length: {report.text_length} chars",
            f"  Bias score : {report.overall_bias_score:.4f}  (threshold: {DOMAIN_CONFIG[report.domain]['bias_threshold']})",
            f"  Compliance : {', '.join(report.compliance_frameworks)}",
            "",
        ]

        if report.signals:
            lines.append(f"  SIGNALS DETECTED ({len(report.signals)}):")
            lines.append("  " + "─" * 64)
            for sig in sorted(report.signals, key=lambda s: -s.severity_score):
                icon = cls.SEVERITY_ICONS.get(sig.severity, "•")
                lines.append(
                    f"  {icon} [{sig.severity.upper()}] {sig.signal_type.replace('_', ' ').title()}"
                    f" — {sig.protected_attribute}"
                )
                lines.append(f"      Evidence: {sig.evidence[:120]}")
                lines.append(f"      Fix: {sig.recommendation[:120]}")
                lines.append("")
        else:
            lines.append("  ✅ No bias signals detected.")
            lines.append("")

        if report.sentiment_by_group:
            lines.append("  SENTIMENT BY GROUP:")
            for group, score in sorted(
                report.sentiment_by_group.items(), key=lambda x: x[1]
            ):
                bar_len = int((score + 1) * 10)
                bar = "█" * max(bar_len, 0) + "░" * max(20 - bar_len, 0)
                lines.append(f"    {group:<20} {bar} {score:+.3f}")
            lines.append("")

        if report.remediation_required:
            lines.append("  REMEDIATION REQUIRED:")
            lines.append("  " + "─" * 64)
            for i, suggestion in enumerate(report.remediation_suggestions, 1):
                lines.append(f"  {i}. {suggestion}")
            lines.append("")

        lines.append("═" * 68)
        return "\n".join(lines)

    @classmethod
    def render_batch_summary(cls, summary: BatchSummary) -> str:
        pass_rate = (summary.passed / summary.total_outputs * 100) if summary.total_outputs else 0
        lines = [
            "",
            "═" * 68,
            f"  BATCH BIAS AUDIT SUMMARY — {summary.domain.upper()}",
            "═" * 68,
            f"  Batch ID   : {summary.batch_id[:16]}…",
            f"  Timestamp  : {summary.timestamp}",
            f"  Total      : {summary.total_outputs}",
            f"  ✅ PASS    : {summary.passed}  ({pass_rate:.0f}%)",
            f"  ⚠️  REVIEW  : {summary.review}",
            f"  ❌ FAIL    : {summary.failed}",
            f"  Avg score  : {summary.avg_bias_score:.4f}",
        ]
        if summary.top_signals:
            lines.append(f"  Top signals: {', '.join(summary.top_signals)}")
        if summary.highest_risk_outputs:
            lines.append(f"  High-risk IDs: {summary.highest_risk_outputs[:3]}")
        lines.append("═" * 68)
        return "\n".join(lines)

    @classmethod
    def render_comparison(cls, comparison: dict) -> str:
        disp = comparison["disparity"]
        flag = "⚠️  DISPARATE TREATMENT DETECTED" if disp["disparate_treatment_detected"] else "✅ No significant disparity"
        lines = [
            "",
            "═" * 68,
            "  A/B DEMOGRAPHIC COMPARISON AUDIT",
            "═" * 68,
            f"  {comparison['group_a']['label']:<30} {comparison['group_b']['label']}",
            f"  Bias score:  {comparison['group_a']['bias_score']:.4f}{'':>20}{comparison['group_b']['bias_score']:.4f}",
            f"  Sentiment:   {comparison['group_a']['sentiment']:+.4f}{'':>20}{comparison['group_b']['sentiment']:+.4f}",
            f"  Risk level:  {comparison['group_a']['risk_level']:<30}{comparison['group_b']['risk_level']}",
            "",
            f"  Score delta    : {disp['bias_score_delta']:.4f}",
            f"  Sentiment delta: {disp['sentiment_delta']:.4f}",
            f"  Verdict        : {flag}",
        ]
        if comparison["compliance_flags"]:
            lines.append(f"  Compliance risk: {', '.join(comparison['compliance_flags'])}")
        lines.append("═" * 68)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

def _run_demo() -> None:
    print("\n" + "▓" * 68)
    print("  TAD BUILD AGENT — AI Output Bias Detection Demo")
    print("  Domain: Healthcare + Hiring")
    print("▓" * 68)

    # ── Healthcare demo ────────────────────────────────────────────────
    healthcare_detector = BiasDetector("healthcare")

    biased_healthcare_output = """
    The elderly patient appears to be struggling with her medication regimen,
    which is typical for older women who tend to be emotionally overwhelmed
    by complex treatment plans. Black patients in urban areas generally show
    lower compliance rates and may require additional monitoring. The young
    male patient should recover quickly given his strong constitution.
    She might benefit from simplified instructions, though compliance is uncertain.
    The disabled patient will likely be a burden on the care team.
    We recommend expedited discharge for the high-income patient and
    additional review for the low-income patient before approving coverage.
    """

    print("\n[1] Healthcare — Biased Output Analysis")
    report = healthcare_detector.analyze(
        biased_healthcare_output,
        context="Demo: flagged healthcare AI output"
    )
    print(ReportRenderer.render_report(report))

    # ── Hiring demo ────────────────────────────────────────────────────
    hiring_detector = BiasDetector("hiring")

    male_candidate_output = """
    John is an exceptionally qualified candidate with outstanding leadership potential.
    His technical skills are superior and he is clearly suited for the senior engineer role.
    We strongly recommend immediate approval for this candidate.
    """

    female_candidate_output = """
    Jane might be a suitable candidate, though she could perhaps struggle with
    the technical demands. She appears to be capable but we're uncertain whether
    her skills are sufficient for the senior engineer role.
    She may need additional mentoring support.
    We recommend further review before making a decision.
    """

    print("\n[2] Hiring — A/B Gender Comparison Audit")
    comparison = hiring_detector.compare_outputs(
        male_candidate_output,
        female_candidate_output,
        group_a_label="Male Candidate (John)",
        group_b_label="Female Candidate (Jane)",
    )
    print(ReportRenderer.render_comparison(comparison))

    # ── Finance batch demo ────────────────────────────────────────────
    finance_detector = BiasDetector("finance")

    batch_outputs = [
        "The applicant is approved for a premium mortgage at our best rate. "
        "The suburban homeowner presents an excellent credit profile.",

        "This urban applicant may have high risk factors. "
        "The minority applicant is flagged for additional review. "
        "Loan approval denied pending further documentation.",

        "The young professional qualifies for the standard loan product. "
        "We recommend approval with normal terms.",

        "The elderly applicant might struggle with repayment obligations. "
        "Additional scrutiny required given the applicant's age and income.",
    ]

    print("\n[3] Finance — Batch Bias Audit (4 outputs)")
    batch = finance_detector.analyze_batch(batch_outputs)
    print(ReportRenderer.render_batch_summary(batch))

    print(f"\n  Audit files saved to: {AUDIT_DIR.resolve()}")
    print(f"  Log file: {(LOG_DIR / 'bias_detection.log').resolve()}")
    print("\n" + "▓" * 68 + "\n")


if __name__ == "__main__":
    _run_demo()