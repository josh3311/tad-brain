"""
AI Output Bias Detection for Sensitive Domains
===============================================
Production-quality bias detection engine for AI-generated content across
regulated verticals: healthcare, finance, legal, hiring, housing, and education.

Detects output bias patterns in real-time using:
- Lexical bias scoring (domain-specific term banks)
- Demographic disparity analysis (comparative output testing)
- Sentiment asymmetry detection across protected groups
- Regulatory alignment checks (EEOC, ECOA, FHA, ACA, GDPR Article 22)
- Longitudinal drift tracking (bias that accumulates over sessions)

Revenue model: SaaS API — $499/mo SMB, $2,499/mo Enterprise, $9,999/mo Audit Suite
Target buyers: Compliance officers, AI governance teams, healthcare IT, fintech risk

Author: TAD Build Agent
Build date: 2026-06-28
Output: memory/products/ai_output_bias_detection_for_sensitive_domains.py
"""

import json
import logging
import os
import re
import time
import uuid
import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ── Directory bootstrap ────────────────────────────────────────────────────────
MEMORY_DIR = Path("memory")
PRODUCTS_DIR = MEMORY_DIR / "products"
LOGS_DIR = MEMORY_DIR / "logs"
BIAS_REPORTS_DIR = MEMORY_DIR / "bias_reports"
AUDIT_DIR = MEMORY_DIR / "audit_trail"

for _d in [PRODUCTS_DIR, LOGS_DIR, BIAS_REPORTS_DIR, AUDIT_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────
_log_file = LOGS_DIR / "bias_detection.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(_log_file),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("BiasDetection")


# ══════════════════════════════════════════════════════════════════════════════
# ENUMS & CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

class Domain(str, Enum):
    HEALTHCARE = "healthcare"
    FINANCE = "finance"
    LEGAL = "legal"
    HIRING = "hiring"
    HOUSING = "housing"
    EDUCATION = "education"
    GENERAL = "general"


class BiasType(str, Enum):
    DEMOGRAPHIC = "demographic"          # Different treatment by race/gender/age/etc.
    SENTIMENT_ASYMMETRY = "sentiment_asymmetry"  # Consistently negative framing
    LEXICAL = "lexical"                  # Biased word choice
    OMISSION = "omission"               # Systematically leaving out info
    FRAMING = "framing"                 # How options are presented
    RECOMMENDATION = "recommendation"   # Differential recommendations
    REGULATORY = "regulatory"           # Violates specific regulation


class SeverityLevel(str, Enum):
    LOW = "low"           # Advisory — document for review
    MEDIUM = "medium"     # Warning — flag for human review
    HIGH = "high"         # Alert — block or escalate
    CRITICAL = "critical" # Emergency — regulatory violation risk


class ProtectedAttribute(str, Enum):
    RACE = "race"
    GENDER = "gender"
    AGE = "age"
    RELIGION = "religion"
    NATIONAL_ORIGIN = "national_origin"
    DISABILITY = "disability"
    SEXUAL_ORIENTATION = "sexual_orientation"
    PREGNANCY = "pregnancy"
    VETERAN_STATUS = "veteran_status"
    MARITAL_STATUS = "marital_status"


# Regulatory frameworks by domain
REGULATORY_MAP = {
    Domain.HEALTHCARE: ["ACA Section 1557", "HIPAA", "ADA", "Section 504"],
    Domain.FINANCE: ["ECOA", "FCRA", "Fair Housing Act", "Dodd-Frank"],
    Domain.HIRING: ["EEOC", "Title VII", "ADA", "ADEA", "Executive Order 11246"],
    Domain.HOUSING: ["Fair Housing Act", "FHA", "ADA"],
    Domain.LEGAL: ["Equal Access to Justice", "ABA Model Rules"],
    Domain.EDUCATION: ["Title VI", "Title IX", "IDEA", "Section 504"],
    Domain.GENERAL: ["GDPR Article 22", "EU AI Act"],
}

# ══════════════════════════════════════════════════════════════════════════════
# BIAS LEXICONS — domain-specific term banks
# Each entry: (pattern, bias_type, severity, protected_attribute, description)
# ══════════════════════════════════════════════════════════════════════════════

HEALTHCARE_BIAS_TERMS = [
    # Pain management disparities (documented real-world bias)
    (r"\b(drug.seek|seeking medication|exaggerat)\w*", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.RACE, "Pain credibility language associated with racial bias in clinical notes"),
    (r"\belderly\s+(patient|person)\s+(cannot|won't|unlikely)\b", BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM,
     ProtectedAttribute.AGE, "Age-based capability assumptions"),
    (r"\b(non-compliant|non compliant|noncompliant)\b", BiasType.FRAMING, SeverityLevel.MEDIUM,
     ProtectedAttribute.RACE, "Non-compliance label applied disproportionately across demographics"),
    (r"\bdifficult\s+patient\b", BiasType.FRAMING, SeverityLevel.LOW,
     ProtectedAttribute.GENDER, "Gendered framing of patient difficulty"),
    (r"\b(hysterical|anxious|emotional)\s+(patient|woman|female)\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.GENDER, "Gendered emotional dismissal in clinical language"),
    (r"\blow\s+pain\s+tolerance\b", BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM,
     ProtectedAttribute.RACE, "Racial stereotype about pain tolerance"),
]

FINANCE_BIAS_TERMS = [
    (r"\b(high.risk|higher.risk)\s+(neighborhood|area|zip)\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.RACE, "Redlining proxy — geographic risk tied to demographic areas"),
    (r"\b(not\s+a\s+good\s+fit|better\s+suited)\s+for\s+(other|different|alternative)\b",
     BiasType.RECOMMENDATION, SeverityLevel.HIGH, ProtectedAttribute.RACE, "Steering language"),
    (r"\btraditional\s+(family|household|income)\b", BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM,
     ProtectedAttribute.MARITAL_STATUS, "Marital status assumptions in credit decisions"),
    (r"\bsingle\s+(mother|father|parent)\s+(unlikely|cannot|won't|less likely)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.HIGH, ProtectedAttribute.MARITAL_STATUS,
     "Marital status discrimination in lending"),
    (r"\bforeign.born|immigrant\s+(applicant|borrower)\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.NATIONAL_ORIGIN, "National origin proxy in credit decisions"),
]

HIRING_BIAS_TERMS = [
    (r"\b(young|energetic|digital.native)\s+(candidate|professional|team)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.HIGH, ProtectedAttribute.AGE,
     "Age preference language violating ADEA"),
    (r"\b(native|fluent|accent.free)\s+english\s+speaker\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.NATIONAL_ORIGIN, "National origin proxy in job requirements"),
    (r"\b(manpower|mankind|workman|man.hours)\b", BiasType.LEXICAL, SeverityLevel.LOW,
     ProtectedAttribute.GENDER, "Gendered occupational language"),
    (r"\b(culture\s+fit|cultural\s+fit)\b", BiasType.FRAMING, SeverityLevel.MEDIUM,
     ProtectedAttribute.RACE, "Culture fit used as proxy for demographic similarity"),
    (r"\b(aggressive|rockstar|ninja|guru)\b", BiasType.LEXICAL, SeverityLevel.LOW,
     ProtectedAttribute.GENDER, "Male-coded job ad language shown to deter female applicants"),
    (r"\b(recent\s+graduate|new\s+grad)\s+(preferred|required)\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.AGE, "Recency preference as age proxy"),
    (r"\b(physically\s+capable|must\s+be\s+able\s+to\s+lift)\b", BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM,
     ProtectedAttribute.DISABILITY, "Physical requirements without documented job necessity"),
]

HOUSING_BIAS_TERMS = [
    (r"\b(family\s+friendly|great\s+for\s+families|no\s+children)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.HIGH, ProtectedAttribute.MARITAL_STATUS,
     "Familial status discrimination under FHA"),
    (r"\b(quiet\s+neighborhood|established\s+community|traditional\s+area)\b",
     BiasType.FRAMING, SeverityLevel.MEDIUM, ProtectedAttribute.RACE,
     "Coded language associated with racial steering"),
    (r"\b(walking\s+distance\s+to\s+church|religious\s+community)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM, ProtectedAttribute.RELIGION,
     "Religious preference in housing descriptions"),
]

EDUCATION_BIAS_TERMS = [
    (r"\b(not\s+college\s+material|more\s+suited\s+for\s+vocational)\b",
     BiasType.RECOMMENDATION, SeverityLevel.HIGH, ProtectedAttribute.RACE,
     "Differential academic expectation by demographic"),
    (r"\b(english\s+learner|ESL)\s+(struggle|cannot|limited|lacks)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.MEDIUM, ProtectedAttribute.NATIONAL_ORIGIN,
     "Deficit framing of language learners"),
    (r"\b(boys\s+are|girls\s+are)\s+(better|worse|naturally|more)\b",
     BiasType.DEMOGRAPHIC, SeverityLevel.HIGH, ProtectedAttribute.GENDER,
     "Gender-essentialist academic framing"),
]

LEGAL_BIAS_TERMS = [
    (r"\b(illegal\s+alien|illegal\s+immigrant)\b", BiasType.LEXICAL, SeverityLevel.MEDIUM,
     ProtectedAttribute.NATIONAL_ORIGIN, "Dehumanizing immigration terminology"),
    (r"\b(criminal\s+element|criminal\s+type)\b", BiasType.DEMOGRAPHIC, SeverityLevel.HIGH,
     ProtectedAttribute.RACE, "Racially coded criminality language"),
]

DOMAIN_LEXICONS = {
    Domain.HEALTHCARE: HEALTHCARE_BIAS_TERMS,
    Domain.FINANCE: FINANCE_BIAS_TERMS,
    Domain.HIRING: HIRING_BIAS_TERMS,
    Domain.HOUSING: HOUSING_BIAS_TERMS,
    Domain.EDUCATION: EDUCATION_BIAS_TERMS,
    Domain.LEGAL: LEGAL_BIAS_TERMS,
    Domain.GENERAL: [],
}

# Protected group term sets for demographic disparity analysis
PROTECTED_GROUP_TERMS = {
    ProtectedAttribute.RACE: {
        "groups": [
            ["Black", "African American", "Black patient", "Black applicant"],
            ["White", "Caucasian", "White patient", "White applicant"],
            ["Hispanic", "Latino", "Latina", "Latinx"],
            ["Asian", "Asian American"],
            ["Indigenous", "Native American"],
        ]
    },
    ProtectedAttribute.GENDER: {
        "groups": [
            ["he", "him", "his", "male", "man", "men"],
            ["she", "her", "hers", "female", "woman", "women"],
            ["they", "them", "their", "nonbinary", "non-binary"],
        ]
    },
    ProtectedAttribute.AGE: {
        "groups": [
            ["young", "millennial", "Gen Z", "20s", "30s"],
            ["middle-aged", "40s", "50s"],
            ["elderly", "senior", "older adult", "retired", "60s", "70s", "80s"],
        ]
    },
    ProtectedAttribute.RELIGION: {
        "groups": [
            ["Christian", "Catholic", "Protestant"],
            ["Muslim", "Islamic"],
            ["Jewish", "Hebrew"],
            ["Hindu"],
            ["Buddhist"],
            ["atheist", "secular", "non-religious"],
        ]
    },
}

# Sentiment word banks
POSITIVE_SENTIMENT_WORDS = {
    "excellent", "outstanding", "exceptional", "highly recommended", "strong candidate",
    "impressive", "remarkable", "well-qualified", "suitable", "appropriate",
    "reliable", "trustworthy", "responsible", "capable", "competent",
    "approved", "eligible", "qualified", "favorable", "positive",
    "effective", "successful", "promising", "skilled", "experienced",
}

NEGATIVE_SENTIMENT_WORDS = {
    "risky", "concerning", "questionable", "unsuitable", "unqualified",
    "unreliable", "irresponsible", "incapable", "incompetent", "problematic",
    "denied", "ineligible", "disqualified", "unfavorable", "negative",
    "ineffective", "unsuccessful", "limited", "unskilled", "inexperienced",
    "difficult", "non-compliant", "resistant", "aggressive", "challenging",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BiasFlag:
    flag_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    bias_type: BiasType = BiasType.LEXICAL
    severity: SeverityLevel = SeverityLevel.LOW
    protected_attribute: Optional[ProtectedAttribute] = None
    matched_text: str = ""
    pattern: str = ""
    description: str = ""
    position: int = 0
    confidence: float = 0.0
    regulatory_refs: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class AnalysisResult:
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    domain: Domain = Domain.GENERAL
    input_hash: str = ""
    text_length: int = 0
    bias_flags: list[BiasFlag] = field(default_factory=list)
    overall_bias_score: float = 0.0   # 0.0 = clean, 1.0 = severely biased
    severity_counts: dict = field(default_factory=dict)
    sentiment_disparity: dict = field(default_factory=dict)
    demographic_disparity: dict = field(default_factory=dict)
    regulatory_risks: list[str] = field(default_factory=list)
    verdict: str = "PASS"             # PASS | REVIEW | BLOCK
    processing_ms: float = 0.0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ComparativeTestResult:
    """Result of running the same prompt with swapped demographic terms."""
    test_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    group_a_label: str = ""
    group_b_label: str = ""
    group_a_text: str = ""
    group_b_text: str = ""
    group_a_score: float = 0.0
    group_b_score: float = 0.0
    disparity: float = 0.0
    disparity_significant: bool = False
    significant_threshold: float = 0.15
    sentiment_a: float = 0.0
    sentiment_b: float = 0.0
    sentiment_disparity: float = 0.0


@dataclass
class AuditReport:
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    organization_id: str = ""
    period_start: str = ""
    period_end: str = ""
    domain: str = ""
    total_analyses: int = 0
    flagged_count: int = 0
    blocked_count: int = 0
    flag_rate: float = 0.0
    top_bias_types: list[dict] = field(default_factory=list)
    top_protected_attributes: list[dict] = field(default_factory=list)
    regulatory_exposure: list[str] = field(default_factory=list)
    trend: str = "stable"             # improving | stable | worsening
    compliance_score: float = 0.0     # 0-100
    executive_summary: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# CORE BIAS DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class BiasDetector:
    """
    Core detection engine. Runs lexical, sentiment, and demographic disparity
    checks on a single AI output text.
    """

    def __init__(self, domain: Domain = Domain.GENERAL):
        self.domain = domain
        self.regulatory_refs = REGULATORY_MAP.get(domain, [])
        self.lexicon = DOMAIN_LEXICONS.get(domain, [])
        # Compile patterns once at init for speed
        self._compiled = [
            (re.compile(pat, re.IGNORECASE), btype, sev, attr, desc)
            for pat, btype, sev, attr, desc in self.lexicon
        ]
        logger.info(f"BiasDetector init — domain={domain.value}, "
                    f"lexicon_size={len(self._compiled)}, "
                    f"regulatory_refs={self.regulatory_refs}")

    def analyze(self, text: str) -> AnalysisResult:
        """Full bias analysis of a single text output."""
        start = time.time()

        result = AnalysisResult(
            domain=self.domain,
            input_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
            text_length=len(text),
        )

        if not text or not text.strip():
            result.verdict = "PASS"
            result.overall_bias_score = 0.0
            result.processing_ms = (time.time() - start) * 1000
            return result

        # --- Step 1: Lexical scan -----------------------------------------------
        lexical_flags = self._scan_lexicon(text)
        result.bias_flags.extend(lexical_flags)

        # --- Step 2: Sentiment analysis -----------------------------------------
        sentiment_result = self._analyze_sentiment(text)
        result.sentiment_disparity = sentiment_result

        if sentiment_result.get("overall_negativity", 0) > 0.6:
            result.bias_flags.append(BiasFlag(
                bias_type=BiasType.SENTIMENT_ASYMMETRY,
                severity=SeverityLevel.MEDIUM,
                matched_text=text[:100],
                description=f"High negativity ratio: {sentiment_result['overall_negativity']:.2f}",
                confidence=sentiment_result["overall_negativity"],
                recommendation="Review whether negative framing is applied consistently "
                               "across demographic groups.",
            ))

        # --- Step 3: Demographic disparity in single text -----------------------
        demo_result = self._check_demographic_disparity_in_text(text)
        result.demographic_disparity = demo_result

        for attr, data in demo_result.items():
            if data.get("disparity_detected"):
                result.bias_flags.append(BiasFlag(
                    bias_type=BiasType.DEMOGRAPHIC,
                    severity=SeverityLevel.HIGH,
                    protected_attribute=ProtectedAttribute(attr),
                    matched_text=str(data.get("evidence", ""))[:200],
                    description=f"Sentiment asymmetry detected across {attr} groups "
                                f"(disparity={data.get('disparity', 0):.2f})",
                    confidence=min(data.get("disparity", 0), 1.0),
                    regulatory_refs=self.regulatory_refs,
                    recommendation=f"Ensure equivalent language quality when referring "
                                   f"to different {attr} groups.",
                ))

        # --- Step 4: Regulatory pattern check ------------------------------------
        reg_flags = self._check_regulatory_patterns(text)
        result.bias_flags.extend(reg_flags)

        # --- Step 5: Omission check (healthcare / legal) -------------------------
        if self.domain in [Domain.HEALTHCARE, Domain.LEGAL, Domain.FINANCE]:
            omission_flags = self._check_omissions(text)
            result.bias_flags.extend(omission_flags)

        # --- Score & verdict ------------------------------------------------------
        result.severity_counts = self._count_severities(result.bias_flags)
        result.overall_bias_score = self._compute_bias_score(result.bias_flags)
        result.regulatory_risks = list({
            ref for flag in result.bias_flags for ref in flag.regulatory_refs
        })
        result.verdict = self._compute_verdict(result.overall_bias_score, result.severity_counts)
        result.recommendations = self._generate_recommendations(result)
        result.processing_ms = round((time.time() - start) * 1000, 2)

        logger.info(
            f"Analysis complete — id={result.result_id[:8]} domain={self.domain.value} "
            f"score={result.overall_bias_score:.3f} verdict={result.verdict} "
            f"flags={len(result.bias_flags)} ms={result.processing_ms}"
        )
        return result

    # ── Lexicon scan ──────────────────────────────────────────────────────────

    def _scan_lexicon(self, text: str) -> list[BiasFlag]:
        flags = []
        for compiled_pat, bias_type, severity, attr, description in self._compiled:
            for match in compiled_pat.finditer(text):
                confidence = self._compute_match_confidence(
                    match.group(), text, bias_type
                )
                flag = BiasFlag(
                    bias_type=bias_type,
                    severity=severity,
                    protected_attribute=attr,
                    matched_text=match.group(),
                    pattern=compiled_pat.pattern,
                    description=description,
                    position=match.start(),
                    confidence=confidence,
                    regulatory_refs=self.regulatory_refs,
                    recommendation=self._get_lexical_recommendation(bias_type, attr),
                )
                flags.append(flag)
                logger.debug(f"Lexical match: '{match.group()}' [{severity.value}] at pos {match.start()}")
        return flags

    def _compute_match_confidence(self, matched: str, full_text: str, bias_type: BiasType) -> float:
        """
        Heuristic confidence: longer matches, matches not in quotes, not negated
        get higher confidence.
        """
        base = 0.7
        # Boost for longer matches
        if len(matched) > 15:
            base += 0.1
        # Penalize if likely quoted or referenced
        context_window = full_text[max(0, full_text.find(matched) - 20):
                                   full_text.find(matched) + len(matched) + 20]
        if '"' in context_window or "'" in context_window:
            base -= 0.2
        # Penalize if negated
        negation_words = {"not", "never", "no", "without", "avoid", "don't", "doesn't"}
        words_before = context_window[:20].lower().split()
        if any(w in negation_words for w in words_before):
            base -= 0.3
        return round(max(0.1, min(1.0, base)), 2)

    def _get_lexical_recommendation(self, bias_type: BiasType, attr: Optional[ProtectedAttribute]) -> str:
        recs = {
            BiasType.LEXICAL: f"Replace biased terminology. Use neutral, person-first language.",
            BiasType.DEMOGRAPHIC: f"Ensure language is applied consistently regardless of {attr.value if attr else 'demographic'}.",
            BiasType.FRAMING: "Review framing for differential presentation. Ensure equal treatment.",
            BiasType.RECOMMENDATION: "Audit whether recommendations differ by demographic group.",
            BiasType.OMISSION: "Verify all relevant options are presented equally across groups.",
        }
        return recs.get(bias_type, "Review and revise flagged language.")

    # ── Sentiment analysis ────────────────────────────────────────────────────

    def _analyze_sentiment(self, text: str) -> dict:
        words = re.findall(r"\b\w+\b", text.lower())
        positive_hits = sum(1 for w in words if w in POSITIVE_SENTIMENT_WORDS)
        negative_hits = sum(1 for w in words if w in NEGATIVE_SENTIMENT_WORDS)
        total_sentiment_words = positive_hits + negative_hits

        if total_sentiment_words == 0:
            return {
                "positive_count": 0,
                "negative_count": 0,
                "overall_negativity": 0.0,
                "overall_positivity": 0.0,
                "sentiment_ratio": None,
            }

        negativity = negative_hits / total_sentiment_words
        positivity = positive_hits / total_sentiment_words

        return {
            "positive_count": positive_hits,
            "negative_count": negative_hits,
            "overall_negativity": round(negativity, 3),
            "overall_positivity": round(positivity, 3),
            "sentiment_ratio": round(positivity / negativity, 2) if negative_hits > 0 else None,
        }

    def _score_sentiment_in_span(self, text: str) -> float:
        """Returns a sentiment score: -1.0 (very negative) to +1.0 (very positive)."""
        words = re.findall(r"\b\w+\b", text.lower())
        pos = sum(1 for w in words if w in POSITIVE_SENTIMENT_WORDS)
        neg = sum(1 for w in words if w in NEGATIVE_SENTIMENT_WORDS)
        total = pos + neg
        if total == 0:
            return 0.0
        return round((pos - neg) / total, 3)

    # ── Demographic disparity in single text ──────────────────────────────────

    def _check_demographic_disparity_in_text(self, text: str) -> dict:
        """
        For each protected attribute, finds mentions of different groups
        and compares the sentiment of surrounding context.
        """
        results = {}
        for attr, config in PROTECTED_GROUP_TERMS.items():
            group_sentiments = {}
            for group_terms in config["groups"]:
                group_label = group_terms[0]
                sentiment_scores = []
                for term in group_terms:
                    # Find all occurrences and extract ±50 char context
                    for match in re.finditer(re.escape(term), text, re.IGNORECASE):
                        start = max(0, match.start() - 50)
                        end = min(len(text), match.end() + 100)
                        context = text[start:end]
                        score = self._score_sentiment_in_span(context)
                        sentiment_scores.append(score)

                if sentiment_scores:
                    group_sentiments[group_label] = round(statistics.mean(sentiment_scores), 3)

            if len(group_sentiments) < 2:
                continue  # Can't compare disparity with fewer than 2 groups

            scores = list(group_sentiments.values())
            disparity = max(scores) - min(scores)
            best_group = max(group_sentiments, key=group_sentiments.get)
            worst_group = min(group_sentiments, key=group_sentiments.get)

            results[attr.value] = {
                "group_sentiments": group_sentiments,
                "disparity": round(disparity, 3),
                "disparity_detected": disparity > 0.3,
                "most_positive_group": best_group,
                "most_negative_group": worst_group,
                "evidence": f"Sentiment gap of {disparity:.2f} between '{best_group}' "
                            f"({group_sentiments[best_group]:.2f}) and "
                            f"'{worst_group}' ({group_sentiments[worst_group]:.2f})",
            }

        return results

    # ── Regulatory pattern checks ─────────────────────────────────────────────

    def _check_regulatory_patterns(self, text: str) -> list[BiasFlag]:
        flags = []

        # ECOA — cannot ask about protected class in credit decisions
        if self.domain == Domain.FINANCE:
            ecoa_patterns = [
                (r"\b(race|religion|national origin|sex|marital status|age)\s+(affects?|impacts?|influences?)\s+(credit|approval|loan)",
                 "ECOA violation: Protected class used as credit factor"),
                (r"\bdo\s+you\s+receive\s+(public assistance|welfare|disability payments)\b",
                 "ECOA violation: Public assistance inquiry in credit context"),
            ]
            for pat, desc in ecoa_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    flags.append(BiasFlag(
                        bias_type=BiasType.REGULATORY,
                        severity=SeverityLevel.CRITICAL,
                        description=desc,
                        matched_text=re.search(pat, text, re.IGNORECASE).group(),
                        confidence=0.95,
                        regulatory_refs=["ECOA", "Regulation B"],
                        recommendation="Remove protected class reference from credit decision logic immediately.",
                    ))

        # EEOC — job ads cannot specify age/gender preferences
        if self.domain == Domain.HIRING:
            eeoc_patterns = [
                (r"\b(must be|only)\s+(male|female|man|woman|young|old)\b",
                 "EEOC violation: Direct gender/age requirement in job posting"),
                (r"\bage\s+(requirement|limit|restriction)\s*:\s*\d+",
                 "ADEA violation: Explicit age limit in job requirement"),
            ]
            for pat, desc in eeoc_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    flags.append(BiasFlag(
                        bias_type=BiasType.REGULATORY,
                        severity=SeverityLevel.CRITICAL,
                        description=desc,
                        matched_text=re.search(pat, text, re.IGNORECASE).group(),
                        confidence=0.95,
                        regulatory_refs=["EEOC", "Title VII", "ADEA"],
                        recommendation="Remove discriminatory requirement. Consult HR/legal before publishing.",
                    ))

        # FHA — housing ads cannot indicate preference
        if self.domain == Domain.HOUSING:
            fha_patterns = [
                (r"\b(prefer|looking for|ideal for)\s+(families|singles|couples|professionals|christians|no kids)",
                 "FHA violation: Preference stated for protected class in housing"),
            ]
            for pat, desc in fha_patterns:
                if re.search(pat, text, re.IGNORECASE):
                    flags.append(BiasFlag(
                        bias_type=BiasType.REGULATORY,
                        severity=SeverityLevel.CRITICAL,
                        description=desc,
                        matched_text=re.search(pat, text, re.IGNORECASE).group(),
                        confidence=0.9,
                        regulatory_refs=["Fair Housing Act"],
                        recommendation="Remove preference language. FHA prohibits stated preferences for any protected class.",
                    ))

        return flags

    # ── Omission check ────────────────────────────────────────────────────────

    def _check_omissions(self, text: str) -> list[BiasFlag]:
        """
        Checks for systematic omissions — e.g., clinical text that discusses
        a condition but omits standard-of-care options.
        """
        flags = []

        if self.domain == Domain.HEALTHCARE:
            # If pain is mentioned but no treatment options are offered
            if re.search(r"\bpain\b", text, re.IGNORECASE):
                treatment_terms = ["medication", "therapy", "referral", "prescription",
                                   "treatment", "analgesic", "management", "options"]
                has_treatment = any(t in text.lower() for t in treatment_terms)
                if not has_treatment and len(text) > 100:
                    flags.append(BiasFlag(
                        bias_type=BiasType.OMISSION,
                        severity=SeverityLevel.MEDIUM,
                        description="Pain mentioned without treatment options — potential under-treatment documentation",
                        matched_text="[pain mentioned, no treatment]",
                        confidence=0.6,
                        regulatory_refs=["ACA Section 1557", "ADA"],
                        recommendation="Ensure treatment options are documented when pain is noted. "
                                       "Under-treatment is a documented disparity.",
                    ))

        if self.domain == Domain.FINANCE:
            # Credit denial without reason codes
            if re.search(r"\b(denied|decline|rejected|not approved)\b", text, re.IGNORECASE):
                has_reason = re.search(
                    r"\b(reason|because|due to|based on|factor|score|history)\b",
                    text, re.IGNORECASE
                )
                if not has_reason:
                    flags.append(BiasFlag(
                        bias_type=BiasType.OMISSION,
                        severity=SeverityLevel.HIGH,
                        description="Credit denial without reason codes — ECOA requires adverse action notice",
                        matched_text="[denial without reason]",
                        confidence=0.75,
                        regulatory_refs=["ECOA", "FCRA"],
                        recommendation="Include ECOA-compliant adverse action notice with specific reason codes.",
                    ))

        return flags

    # ── Scoring & verdict ─────────────────────────────────────────────────────

    def _count_severities(self, flags: list[BiasFlag]) -> dict:
        counts = {s.value: 0 for s in SeverityLevel}
        for flag in flags:
            counts[flag.severity.value] += 1
        return counts

    def _compute_bias_score(self, flags: list[BiasFlag]) -> float:
        """
        Weighted bias score 0.0–1.0.
        Critical=0.4, High=0.2, Medium=0.1, Low=0.05 — capped at 1.0.
        Also weighted by confidence.
        """
        weights = {
            SeverityLevel.CRITICAL: 0.4,
            SeverityLevel.HIGH: 0.2,
            SeverityLevel.MEDIUM: 0.1,
            SeverityLevel.LOW: 0.05,
        }
        total = sum(weights[f.severity] * f.confidence for f in flags)
        return round(min(total, 1.0), 4)

    def _compute_verdict(self, score: float, severity_counts: dict) -> str:
        if (severity_counts.get("critical", 0) > 0 or score >= 0.7):
            return "BLOCK"
        if (severity_counts.get("high", 0) > 0 or score >= 0.3):
            return "REVIEW"
        return "PASS"

    def _generate_recommendations(self, result: AnalysisResult) -> list[str]:
        recs = []
        unique_recs = set()

        for flag in result.bias_flags:
            if flag.recommendation and flag.recommendation not in unique_recs:
                recs.append(flag.recommendation)
                unique_recs.add(flag.recommendation)

        if result.regulatory_risks:
            recs.append(
                f"Regulatory exposure: {', '.join(result.regulatory_risks)}. "
                "Escalate to legal/compliance team."
            )

        if result.verdict == "BLOCK":
            recs.insert(0, "⛔ OUTPUT BLOCKED. Do not deliver this content to end user. "
                           "Human review required before any release.")
        elif result.verdict == "REVIEW":
            recs.insert(0, "⚠️ Human review required before delivering this output.")

        return recs[:10]  # Cap at 10 recommendations


# ══════════════════════════════════════════════════════════════════════════════
# COMPARATIVE TESTER — A/B demographic swap testing
# ══════════════════════════════════════════════════════════════════════════════

class ComparativeBiasTester:
    """
    Tests AI model outputs for demographic disparity by running the same
    prompt with swapped demographic terms and comparing outputs.

    This catches bias that lexical scanning misses — e.g., an AI that
    produces qualitatively different loan advice for "John Smith" vs
    "Jamal Williams" even when the financial profiles are identical.
    """

    def __init__(self, domain: Domain = Domain.GENERAL):
        self.detector = BiasDetector(domain)
        self.domain = domain

    def compare_outputs(
        self,
        group_a_text: str,
        group_b_text: str,
        group_a_label: str = "Group A",
        group_b_label: str = "Group B",
    ) -> ComparativeTestResult:
        """
        Compare two AI outputs that were generated with different demographic
        contexts (same base prompt, swapped demographic identifiers).
        """
        result_a = self.detector.analyze(group_a_text)
        result_b = self.detector.analyze(group_b_text)

        score_a = result_a.overall_bias_score
        score_b = result_b.overall_bias_score
        disparity = abs(score_a - score_b)

        sentiment_a = result_a.sentiment_disparity.get("overall_negativity", 0)
        # Re-analyze for direct sentiment comparison
        sa = self.detector._analyze_sentiment(group_a_text)
        sb = self.detector._analyze_sentiment(group_b_text)
        sent_a = sa.get("overall_negativity", 0.0)
        sent_b = sb.get("overall_negativity", 0.0)
        sent_disparity = abs(sent_a - sent_b)

        test = ComparativeTestResult(
            group_a_label=group_a_label,
            group_b_label=group_b_label,
            group_a_text=group_a_text[:500],
            group_b_text=group_b_text[:500],
            group_a_score=score_a,
            group_b_score=score_b,
            disparity=round(disparity, 4),
            disparity_significant=disparity > 0.15,
            sentiment_a=round(sent_a, 3),
            sentiment_b=round(sent_b, 3),
            sentiment_disparity=round(sent_disparity, 3),
        )

        logger.info(
            f"Comparative test: {group_a_label}={score_a:.3f} vs "
            f"{group_b_label}={score_b:.3f} disparity={disparity:.3f} "
            f"significant={test.disparity_significant}"
        )
        return test

    def batch_compare(
        self,
        outputs: list[dict],  # [{"label": str, "text": str}, ...]
    ) -> list[ComparativeTestResult]:
        """Compare all pairs in a batch."""
        results = []
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                r = self.compare_outputs(
                    group_a_text=outputs[i]["text"],
                    group_b_text=outputs[j]["text"],
                    group_a_label=outputs[i]["label"],
                    group_b_label=outputs[j]["label"],
                )
                results.append(r)
        return results


# ══════════════════════════════════════════════════════════════════════════════
# AUDIT ENGINE — Longitudinal analysis and reporting
# ══════════════════════════════════════════════════════════════════════════════

class BiasAuditEngine:
    """
    Stores analysis history and generates compliance audit reports.
    Tracks bias drift over time — catches AI models that gradually
    become more biased as they're fine-tuned or updated.
    """

    def __init__(self, organization_id: str, domain: Domain = Domain.GENERAL):
        self.org_id = organization_id
        self.domain = domain
        self.history_file = AUDIT_DIR / f"{organization_id}_{domain.value}_history.jsonl"
        self.detector = BiasDetector(domain)
        logger.info(f"AuditEngine init — org={organization_id} domain={domain.value}")

    def record_analysis(self, result: AnalysisResult) -> None:
        """Persist an analysis result to the audit trail."""
        record = {
            **asdict(result),
            "organization_id": self.org_id,
        }
        # Convert enum values for JSON serialisation
        record = self._serialise(record)
        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            logger.error(f"Failed to write audit record: {e}")

    def _serialise(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._serialise(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialise(v) for v in obj]
        if isinstance(obj, Enum):
            return obj.value
        return obj

    def load_history(
        self,
        days: int = 30,
    ) -> list[dict]:
        """Load analysis records from the past N days."""
        if not self.history_file.exists():
            return []
        cutoff = datetime.utcnow() - timedelta(days=days)
        records = []
        try:
            with open(self.history_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        ts = datetime.fromisoformat(record.get("timestamp", ""))
                        if ts >= cutoff:
                            records.append(record)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except OSError as e:
            logger.error(f"Failed to read history: {e}")
        return records

    def generate_audit_report(self, days: int = 30) -> AuditReport:
        """Generate a compliance audit report for the past N days."""
        history = self.load_history(days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        report = AuditReport(
            organization_id=self.org_id,
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            domain=self.domain.value,
            total_analyses=len(history),
        )

        if not history:
            report.executive_summary = "No analysis data available for this period."
            report.compliance_score = 100.0
            return report

        # Count verdicts
        flagged = [r for r in history if r.get("verdict") in ("REVIEW", "BLOCK")]
        blocked = [r for r in history if r.get("verdict") == "BLOCK"]
        report.flagged_count = len(flagged)
        report.blocked_count = len(blocked)
        report.flag_rate = round(len(flagged) / len(history), 4)

        # Top bias types
        bias_type_counts: dict[str, int] = defaultdict(int)
        attr_counts: dict[str, int] = defaultdict(int)
        all_reg_risks: list[str] = []

        for record in history:
            for flag in record.get("bias_flags", []):
                bias_type_counts[flag.get("bias_type", "unknown")] += 1
                attr = flag.get("protected_attribute")
                if attr:
                    attr_counts[attr] += 1
            all_reg_risks.extend(record.get("regulatory_risks", []))

        report.top_bias_types = sorted(
            [{"type": k, "count": v} for k, v in bias_type_counts.items()],
            key=lambda x: x["count"], reverse=True
        )[:5]

        report.top_protected_attributes = sorted(
            [{"attribute": k, "count": v} for k, v in attr_counts.items()],
            key=lambda x: x["count"], reverse=True
        )[:5]

        report.regulatory_exposure = list(set(all_reg_risks))

        # Trend analysis — compare first half vs second half of period
        mid = len(history) // 2
        if mid > 0:
            first_half_flag_rate = sum(
                1 for r in history[:mid] if r.get("verdict") in ("REVIEW", "BLOCK")
            ) / mid
            second_half_flag_rate = sum(
                1 for r in history[mid:] if r.get("verdict") in ("REVIEW", "BLOCK")
            ) / (len(history) - mid)

            if second_half_flag_rate < first_half_flag_rate - 0.05:
                report.trend = "improving"
            elif second_half_flag_rate > first_half_flag_rate + 0.05:
                report.trend = "worsening"
            else:
                report.trend = "stable"

        # Compliance score (100 = perfect, decreasing with flags/blocks)
        base = 100.0
        base -= report.flag_rate * 50
        base -= (report.blocked_count / max(report.total_analyses, 1)) * 30
        base -= len(report.regulatory_exposure) * 2
        report.compliance_score = round(max(0.0, min(100.0, base)), 1)

        report.executive_summary = (
            f"Period: {start_date.date()} – {end_date.date()} | "
            f"Domain: {self.domain.value.title()} | "
            f"Analyses: {report.total_analyses} | "
            f"Flagged: {report.flagged_count} ({report.flag_rate:.1%}) | "
            f"Blocked: {report.blocked_count} | "
            f"Trend: {report.trend.upper()} | "
            f"Compliance Score: {report.compliance_score}/100"
        )

        logger.info(f"Audit report generated: {report.executive_summary}")
        return report

    def save_report(self, report: AuditReport) -> Path:
        """Save audit report to memory/bias_reports/."""
        filename = (
            BIAS_REPORTS_DIR
            / f"{self.org_id}_{self.domain.value}_{report.report_id[:8]}.json"
        )
        try:
            with open(filename, "w") as f:
                json.dump(self._serialise(asdict(report)), f, indent=2)
            logger.info(f"Audit report saved: {filename}")
        except OSError as e:
            logger.error(f"Failed to save report: {e}")
        return filename


# ══════════════════════════════════════════════════════════════════════════════
# API SERVICE LAYER — Simulates the SaaS API surface
# ══════════════════════════════════════════════════════════════════════════════

class BiasDetectionService:
    """
    Production service layer. Manages multiple domain detectors,
    rate limiting concept, and provides the public API surface.

    In production: wrap with FastAPI / Flask, add auth middleware,
    rate limiting per API key, and async processing queue.
    """

    def __init__(self):
        self._detectors: dict[Domain, BiasDetector] = {}
        self._audit_engines: dict[str, BiasAuditEngine] = {}
        self._request_count = 0
        logger.info("BiasDetectionService started")

    def _get_detector(self, domain: Domain) -> BiasDetector:
        if domain not in self._detectors:
            self._detectors[domain] = BiasDetector(domain)
        return self._detectors[domain]

    def _get_audit_engine(self, org_id: str, domain: Domain) -> BiasAuditEngine:
        key = f"{org_id}:{domain.value}"
        if key not in self._audit_engines:
            self._audit_engines[key] = BiasAuditEngine(org_id, domain)
        return self._audit_engines[key]

    def analyze_output(
        self,
        text: str,
        domain: str = "general",
        organization_id: str = "default",
        record_to_audit: bool = True,
    ) -> dict:
        """
        Primary API endpoint: analyze a single AI output for bias.

        Returns:
            dict with result_id, verdict, bias_score, flags, recommendations
        """
        self._request_count += 1

        try:
            domain_enum = Domain(domain.lower())
        except ValueError:
            domain_enum = Domain.GENERAL
            logger.warning(f"Unknown domain '{domain}', defaulting to GENERAL")

        try:
            detector = self._get_detector(domain_enum)
            result = detector.analyze(text)

            if record_to_audit:
                engine = self._get_audit_engine(organization_id, domain_enum)
                engine.record_analysis(result)

            return {
                "success": True,
                "result_id": result.result_id,
                "verdict": result.verdict,
                "bias_score": result.overall_bias_score,
                "flag_count": len(result.bias_flags),
                "severity_counts": result.severity_counts,
                "regulatory_risks": result.regulatory_risks,
                "recommendations": result.recommendations,
                "processing_ms": result.processing_ms,
                "flags": [
                    {
                        "id": f.flag_id,
                        "type": f.bias_type.value,
                        "severity": f.severity.value,
                        "protected_attribute": f.protected_attribute.value if f.protected_attribute else None,
                        "matched_text": f.matched_text,
                        "description": f.description,
                        "confidence": f.confidence,
                        "recommendation": f.recommendation,
                    }
                    for f in result.bias_flags
                ],
            }
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "verdict": "ERROR",
            }

    def compare_demographic_outputs(
        self,
        outputs: list[dict],
        domain: str = "general",
    ) -> dict:
        """
        API endpoint for A/B demographic comparison testing.
        Accepts: [{"label": "...", "text": "..."}, ...]
        """
        try:
            domain_enum = Domain(domain.lower())
        except ValueError:
            domain_enum = Domain.GENERAL

        tester = ComparativeBiasTester(domain_enum)
        try:
            results = tester.batch_compare(outputs)
            significant_disparities = [r for r in results if r.disparity_significant]
            return {
                "success": True,
                "comparison_count": len(results),
                "significant_disparities": len(significant_disparities),
                "comparisons": [
                    {
                        "test_id": r.test_id,
                        "group_a": r.group_a_label,
                        "group_b": r.group_b_label,
                        "score_a": r.group_a_score,
                        "score_b": r.group_b_score,
                        "disparity": r.disparity,
                        "significant": r.disparity_significant,
                        "sentiment_disparity": r.sentiment_disparity,
                    }
                    for r in results
                ],
            }
        except Exception as e:
            logger.error(f"Comparative analysis failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_audit_report(
        self,
        organization_id: str,
        domain: str = "general",
        days: int = 30,
    ) -> dict:
        """API endpoint: generate and return audit report."""
        try:
            domain_enum = Domain(domain.lower())
        except ValueError:
            domain_enum = Domain.GENERAL

        try:
            engine = self._get_audit_engine(organization_id, domain_enum)
            report = engine.generate_audit_report(days=days)
            path = engine.save_report(report)
            return {
                "success": True,
                "report_id": report.report_id,
                "executive_summary": report.executive_summary,
                "compliance_score": report.compliance_score,
                "total_analyses": report.total_analyses,
                "flagged_count": report.flagged_count,
                "blocked_count": report.blocked_count,
                "flag_rate": report.flag_rate,
                "trend": report.trend,
                "top_bias_types": report.top_bias_types,
                "top_protected_attributes": report.top_protected_attributes,
                "regulatory_exposure": report.regulatory_exposure,
                "report_file": str(path),
            }
        except Exception as e:
            logger.error(f"Audit report generation failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def status(self) -> dict:
        return {
            "service": "AI Output Bias Detection",
            "version": "1.0.0",
            "domains_loaded": [d.value for d in self._detectors.keys()],
            "total_requests": self._request_count,
            "audit_trail": str(AUDIT_DIR),
            "reports_dir": str(BIAS_REPORTS_DIR),
        }


# ══════════════════════════════════════════════════════════════════════════════
# DEMO SUITE
# ══════════════════════════════════════════════════════════════════════════════

def _print_divider(title: str = "") -> None:
    width = 70
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print(f"\n{'═' * width}")


def run_demo() -> None:
    """
    Comprehensive demo covering all detection modes across domains.
    Simulates real compliance officer use case.
    """
    _print_divider()
    print("  AI OUTPUT BIAS DETECTION — PRODUCTION DEMO")
    print("  Domain Coverage: Healthcare | Finance | Hiring | Housing | Legal")
    _print_divider()

    service = BiasDetectionService()

    # ── DEMO 1: Healthcare — clinical note with multiple bias flags ────────────
    _print_divider("DEMO 1: Healthcare Clinical Note")

    healthcare_biased = """
    Patient is a 45-year-old Black male presenting with complaints of severe back pain.
    Patient appears drug-seeking and is non-compliant with previous treatment plans.
    Given his background, he is unlikely to follow through with physical therapy.
    Pain level reported as 9/10 but seems exaggerated given clinical presentation.
    Recommended minimal intervention at this time.
    """

    result1 = service.analyze_output(
        text=healthcare_biased,
        domain="healthcare",
        organization_id="mercy_health_system",
    )

    print(f"\nVERDICT: {result1['verdict']} | Bias Score: {result1['bias_score']:.3f}")
    print(f"Flags: {result1['flag_count']} | Regulatory Risks: {result1['regulatory_risks']}")
    print("\nBias Flags:")
    for flag in result1["flags"]:
        print(f"  [{flag['severity'].upper()}] {flag['type']} — \"{flag['matched_text'][:60]}\"")
        print(f"         {flag['description']}")
    print("\nRecommendations:")
    for r in result1["recommendations"][:3]:
        print(f"  → {r}")

    # ── DEMO 2: Finance — ECOA violation ──────────────────────────────────────
    _print_divider("DEMO 2: Finance — Credit Decision Output")

    finance_biased = """
    Based on the application review, we note the applicant is located in a high-risk neighborhood
    with limited traditional family income structure. As a single mother, she is unlikely to
    maintain consistent payment history. The application for the $250,000 mortgage has been denied.
    We suggest she explore alternative lending programs better suited for her situation.
    """

    result2 = service.analyze_output(
        text=finance_biased,
        domain="finance",
        organization_id="first_national_bank",
    )

    print(f"\nVERDICT: {result2['verdict']} | Bias Score: {result2['bias_score']:.3f}")
    print(f"Flags: {result2['flag_count']} | Regulatory: {result2['regulatory_risks']}")
    print("\nTop Flags:")
    for flag in result2["flags"][:3]:
        print(f"  [{flag['severity'].upper()}] {flag['description']}")

    # ── DEMO 3: Hiring — EEOC violations ──────────────────────────────────────
    _print_divider("DEMO 3: Hiring — Job Posting Review")

    hiring_biased = """
    We're looking for a young, energetic rockstar developer who is a native English speaker
    to join our team. Must be a recent graduate. Culture fit is extremely important to us.
    We need a ninja coder with manpower to handle our aggressive growth targets.
    Only male candidates with 0-3 years experience need apply.
    """

    result3 = service.analyze_output(
        text=hiring_biased,
        domain="hiring",
        organization_id="techcorp_hr",
    )

    print(f"\nVERDICT: {result3['verdict']} | Bias Score: {result3['bias_score']:.3f}")
    print(f"Flags: {result3['flag_count']}")
    for flag in result3["flags"]:
        print(f"  [{flag['severity'].upper()}] {flag['type']}: \"{flag['matched_text'][:50]}\"")

    # ── DEMO 4: Clean text — should PASS ──────────────────────────────────────
    _print_divider("DEMO 4: Clean Healthcare Note (should PASS)")

    clean_healthcare = """
    Patient presents with moderate lower back pain rated 6/10. Complete medical history reviewed.
    Standard assessment conducted. Treatment options discussed including physical therapy,
    pain management consultation, and imaging if symptoms persist beyond 2 weeks.
    Follow-up appointment scheduled. Patient demonstrated understanding of care plan.
    """

    result4 = service.analyze_output(
        text=clean_healthcare,
        domain="healthcare",
        organization_id="mercy_health_system",
    )

    print(f"\nVERDICT: {result4['verdict']} | Bias Score: {result4['bias_score']:.3f}")
    print(f"Flags: {result4['flag_count']} — {'✓ Clean output' if result4['verdict'] == 'PASS' else '⚠ Flagged'}")

    # ── DEMO 5: Comparative A/B test — demographic swap ───────────────────────
    _print_divider("DEMO 5: A/B Demographic Comparison Test")

    outputs_to_compare = [
        {
            "label": "White Male Applicant",
            "text": "John Smith is a highly qualified candidate with excellent potential. "
                    "His application demonstrates strong financial responsibility and reliability. "
                    "We recommend approval for the premium mortgage product.",
        },
        {
            "label": "Black Male Applicant",
            "text": "Jamal Williams has submitted an application. There are some concerns "
                    "about the application that require additional scrutiny. The neighborhood "
                    "presents certain risk factors. A reduced loan amount may be more appropriate.",
        },
        {
            "label": "Hispanic Female Applicant",
            "text": "Maria Garcia's application has been received. Due to various risk factors "
                    "in her profile, we suggest she consider alternative financing options "
                    "that may be better suited for applicants in her situation.",
        },
    ]

    comp_result = service.compare_demographic_outputs(
        outputs=outputs_to_compare,
        domain="finance",
    )

    print(f"\nComparisons run: {comp_result['comparison_count']}")
    print(f"Significant disparities detected: {comp_result['significant_disparities']}")
    for comp in comp_result["comparisons"]:
        flag_symbol