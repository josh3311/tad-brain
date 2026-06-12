"""
AI Output Bias Detection for Sensitive Domains
Detects demographic bias in AI outputs across hiring, lending, and healthcare.
Provides audit trails and bias scoring before deployment.
"""

import json
import re
import hashlib
import os
import logging
import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from collections import defaultdict
import statistics


# --- Setup logging to memory/ folder ---
MEMORY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(MEMORY_DIR, "bias_detection.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Domain(Enum):
    HIRING = "hiring"
    LENDING = "lending"
    HEALTHCARE = "healthcare"


class BiasSeverity(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class BiasFinding:
    domain: str
    protected_attribute: str
    disparity_ratio: float
    severity: str
    affected_group: str
    reference_group: str
    sample_size: int
    confidence: float
    description: str


@dataclass
class AuditReport:
    report_id: str
    timestamp: str
    domain: str
    total_outputs: int
    findings: List[BiasFinding]
    overall_risk_score: float
    passed_audit: bool
    raw_data_hash: str


class BiasPatternLibrary:
    """Domain-specific bias patterns and protected attributes."""
    
    PROTECTED_ATTRIBUTES = {
        Domain.HIRING: {
            "gender": [r"\b(he|him|his|she|her|hers)\b", r"\b(male|female|man|woman)\b"],
            "race": [r"\b(black|white|asian|hispanic|african)\b", r"\b(minority|diverse)\b"],
            "age": [r"\b(young|old|elderly|millennial|boomer|senior)\b", r"\b(\d{1,2}\s*years?\s*old)\b"],
            "disability": [r"\b(disabled|handicapped|wheelchair|autism|adhd)\b"]
        },
        Domain.LENDING: {
            "gender": [r"\b(male|female|man|woman)\b"],
            "race": [r"\b(black|white|asian|hispanic|african|latino)\b", r"\b(neighborhood|zip\s*code)\b"],
            "income_source": [r"\b(welfare|disability\s*benefits|unemployment)\b"],
            "marital_status": [r"\b(single|married|divorced|widowed)\b"]
        },
        Domain.HEALTHCARE: {
            "gender": [r"\b(male|female|man|woman|transgender)\b"],
            "race": [r"\b(black|white|asian|hispanic|african)\b", r"\b(sickle\s*cell|lupus)\b"],
            "socioeconomic": [r"\b(low-income|uninsured|medicaid|welfare)\b"],
            "age": [r"\b(elderly|geriatric|pediatric|young\s*adult)\b"]
        }
    }
    
    STEREOTYPE_INDICATORS = [
        r"\b(naturally|typically|generally|often|usually)\s+(better|worse|more|less|slower|faster)\b",
        r"\b(not\s+as\s+(qualified|capable|reliable|trustworthy))\b",
        r"\b(higher\s+risk|lower\s+potential|cultural\s+fit)\b"
    ]
    
    @classmethod
    def get_patterns(cls, domain: Domain) -> Dict[str, List[str]]:
        return cls.PROTECTED_ATTRIBUTES.get(domain, {})


class DemographicExtractor:
    """Extracts demographic indicators from text outputs."""
    
    def __init__(self, domain: Domain):
        self.domain = domain
        self.patterns = BiasPatternLibrary.get_patterns(domain)
        logger.info(f"Initialized extractor for domain: {domain.value}")
    
    def extract(self, text: str) -> Dict[str, List[Tuple[int, str]]]:
        """Extract mentions of protected attributes with positions."""
        results = {}
        text_lower = text.lower()
        
        for attribute, patterns in self.patterns.items():
            matches = []
            for pattern in patterns:
                for match in re.finditer(pattern, text_lower, re.IGNORECASE):
                    matches.append((match.start(), match.group()))
            if matches:
                results[attribute] = matches
        
        # Check for stereotype indicators
        stereotype_matches = []
        for pattern in BiasPatternLibrary.STEREOTYPE_INDICATORS:
            for match in re.finditer(pattern, text_lower, re.IGNORECASE):
                stereotype_matches.append((match.start(), match.group()))
        if stereotype_matches:
            results["_stereotype_indicators"] = stereotype_matches
        
        return results
    
    def has_demographic_content(self, text: str) -> bool:
        return len(self.extract(text)) > 0


class StatisticalAnalyzer:
    """Analyzes output distributions for disparate impact."""
    
    DISPARATE_IMPACT_THRESHOLD = 0.8  # EEOC 4/5ths rule
    
    @staticmethod
    def calculate_disparity_ratio(group_rate: float, reference_rate: float) -> float:
        """Calculate disparity ratio, handling division by zero."""
        if reference_rate <= 0:
            return 1.0 if group_rate <= 0 else float('inf')
        return group_rate / reference_rate
    
    @classmethod
    def analyze_outcome_distribution(
        cls,
        outcomes_by_group: Dict[str, Dict[str, int]]
    ) -> List[BiasFinding]:
        """
        Analyze outcomes for disparate impact across groups.
        outcomes_by_group: {group_name: {"positive": N, "negative": M}}
        """
        findings = []
        
        # Find reference group (largest or specified)
        total_by_group = {
            g: counts.get("positive", 0) + counts.get("negative", 0)
            for g, counts in outcomes_by_group.items()
        }
        
        if not total_by_group:
            return findings
        
        reference_group = max(total_by_group, key=total_by_group.get)
        reference_positive = outcomes_by_group[reference_group].get("positive", 0)
        reference_total = total_by_group[reference_group]
        reference_rate = reference_positive / reference_total if reference_total > 0 else 0
        
        logger.info(f"Reference group: {reference_group} (rate: {reference_rate:.3f})")
        
        for group, counts in outcomes_by_group.items():
            if group == reference_group:
                continue
            
            positive = counts.get("positive", 0)
            total = total_by_group[group]
            
            if total < 30:  # Statistical significance threshold
                logger.warning(f"Group {group} has insufficient sample size: {total}")
                continue
            
            group_rate = positive / total
            disparity = cls.calculate_disparity_ratio(group_rate, reference_rate)
            
            # Determine severity
            if disparity >= 1.0:
                severity = BiasSeverity.NONE
            elif disparity >= 0.9:
                severity = BiasSeverity.LOW
            elif disparity >= cls.DISPARATE_IMPACT_THRESHOLD:
                severity = BiasSeverity.MEDIUM
            elif disparity >= 0.6:
                severity = BiasSeverity.HIGH
            else:
                severity = BiasSeverity.CRITICAL
            
            # Confidence interval (simplified)
            confidence = min(0.99, 1.0 - (1.0 / total))
            
            finding = BiasFinding(
                domain="cross_group_analysis",
                protected_attribute="outcome_disparity",
                disparity_ratio=round(disparity, 3),
                severity=severity.name,
                affected_group=group,
                reference_group=reference_group,
                sample_size=total,
                confidence=round(confidence, 3),
                description=(
                    f"Group '{group}' has {group_rate:.1%} positive rate vs "
                    f"{reference_rate:.1%} for '{reference_group}'. "
                    f"Disparity ratio: {disparity:.3f}"
                )
            )
            findings.append(finding)
            logger.info(f"Bias finding: {group} vs {reference_group} = {disparity:.3f}")
        
        return findings


class OutputBiasDetector:
    """Main detector for AI output bias across sensitive domains."""
    
    def __init__(self, domain: Domain):
        self.domain = domain
        self.extractor = DemographicExtractor(domain)
        self.analyzer = StatisticalAnalyzer()
        self.outputs: List[Dict[str, Any]] = []
        logger.info(f"Initialized bias detector for domain: {domain.value}")
    
    def add_output(self, text: str, outcome: Optional[str] = None, 
                   metadata: Optional[Dict] = None) -> Dict:
        """Add an AI output for analysis."""
        entry = {
            "text": text,
            "outcome": outcome or "neutral",
            "metadata": metadata or {},
            "demographic_indicators": self.extractor.extract(text),
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        self.outputs.append(entry)
        logger.info(f"Added output #{len(self.outputs)} with outcome '{outcome}'")
        return entry
    
    def analyze_text_patterns(self) -> List[BiasFinding]:
        """Analyze text for biased language patterns."""
        findings = []
        
        attribute_counts = defaultdict(lambda: defaultdict(int))
        stereotype_count = 0
        
        for output in self.outputs:
            indicators = output.get("demographic_indicators", {})
            
            for attr, matches in indicators.items():
                if attr == "_stereotype_indicators":
                    stereotype_count += len(matches)
                    continue
                
                # Count mentions by outcome
                outcome = output.get("outcome", "neutral")
                attribute_counts[attr][outcome] += len(matches)
        
        # Flag attributes that appear disproportionately with negative outcomes
        for attr, outcomes in attribute_counts.items():
            total = sum(outcomes.values())
            negative = outcomes.get("negative", 0) + outcomes.get("rejected", 0)
            
            if total > 0:
                negative_ratio = negative / total
                if negative_ratio > 0.5 and total >= 5:
                    severity = BiasSeverity.HIGH if negative_ratio > 0.7 else BiasSeverity.MEDIUM
                    
                    finding = BiasFinding(
                        domain=self.domain.value,
                        protected_attribute=attr,
                        disparity_ratio=round(1 - negative_ratio, 3),
                        severity=severity.name,
                        affected_group=f"mentions_of_{attr}",
                        reference_group="neutral_mentions",
                        sample_size=total,
                        confidence=round(min(0.95, total / 100), 3),
                        description=(
                            f"Protected attribute '{attr}' appears in {negative_ratio:.1%} "
                            f"of negative/rejected outcomes ({negative}/{total})"
                        )
                    )
                    findings.append(finding)
                    logger.warning(f"Pattern bias detected: {attr} at {negative_ratio:.1%} negative")
        
        # Flag stereotype indicators
        if stereotype_count > 0:
            finding = BiasFinding(
                domain=self.domain.value,
                protected_attribute="stereotype_language",
                disparity_ratio=0.0,
                severity=BiasSeverity.MEDIUM.name if stereotype_count < 5 else BiasSeverity.HIGH.name,
                affected_group="all_outputs",
                reference_group="none",
                sample_size=stereotype_count,
                confidence=0.9,
                description=f"Found {stereotype_count} instances of stereotype-indicator language"
            )
            findings.append(finding)
            logger.warning(f"Stereotype language detected: {stereotype_count} instances")
        
        return findings
    
    def analyze_outcome_bias(self, group_key: Optional[str] = None) -> List[BiasFinding]:
        """Analyze outcome distributions for disparate impact."""
        if not group_key:
            # Try to infer from metadata
            outcomes_by_group = defaultdict(lambda: defaultdict(int))
            
            for output in self.outputs:
                meta = output.get("metadata", {})
                # Look for demographic fields in metadata
                group = None
                for field in ["gender", "race", "age_group", "ethnicity", "group"]:
                    if field in meta:
                        group = f"{field}:{meta[field]}"
                        break
                
                if group:
                    outcome = output.get("outcome", "neutral")
                    # Simplify to positive/negative
                    positive_outcomes = {"approved", "hired", "recommended", "positive", "success"}
                    negative_outcomes = {"rejected", "denied", "not_hired", "negative", "failure"}
                    
                    if outcome.lower() in positive_outcomes:
                        outcomes_by_group[group]["positive"] += 1
                    elif outcome.lower() in negative_outcomes:
                        outcomes_by_group[group]["negative"] += 1
                    else:
                        outcomes_by_group[group]["neutral"] += 1
            
            if outcomes_by_group:
                return self.analyzer.analyze_outcome_distribution(dict(outcomes_by_group))
        
        return []
    
    def generate_report(self) -> AuditReport:
        """Generate comprehensive audit report."""
        logger.info("Generating audit report...")
        
        # Combine all findings
        text_findings = self.analyze_text_patterns()
        outcome_findings = self.analyze_outcome_bias()
        all_findings = text_findings + outcome_findings
        
        # Calculate overall risk score (0-100)
        severity_weights = {
            BiasSeverity.NONE.name: 0,
            BiasSeverity.LOW.name: 10,
            BiasSeverity.MEDIUM.name: 30,
            BiasSeverity.HIGH.name: 60,
            BiasSeverity.CRITICAL.name: 100
        }
        
        if all_findings:
            risk_scores = [severity_weights.get(f.severity, 0) for f in all_findings]
            overall_risk = statistics.mean(risk_scores)
        else:
            overall_risk = 0.0
        
        # Hash raw data for integrity
        raw_data = json.dumps(self.outputs, sort_keys=True)
        data_hash = hashlib.sha256(raw_data.encode()).hexdigest()[:16]
        
        report = AuditReport(
            report_id=f"BIAS-{datetime.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{data_hash[:8]}",
            timestamp=datetime.datetime.utcnow().isoformat(),
            domain=self.domain.value,
            total_outputs=len(self.outputs),
            findings=all_findings,
            overall_risk_score=round(overall_risk, 2),
            passed_audit=overall_risk < 30 and not any(
                f.severity == BiasSeverity.CRITICAL.name for f in all_findings
            ),
            raw_data_hash=data_hash
        )
        
        # Save report to memory
        self._save_report(report)
        logger.info(f"Report generated: {report.report_id}, Risk: {overall_risk:.1f}, Passed: {report.passed_audit}")
        
        return report
    
    def _save_report(self, report: AuditReport) -> None:
        """Save report to memory folder."""
        filepath = os.path.join(MEMORY_DIR, f"{report.report_id}.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(asdict(report), f, indent=2, default=str)
            logger.info(f"Report saved to {filepath}")
        except IOError as e:
            logger.error(f"Failed to save report: {e}")
            raise
    
    def reset(self) -> None:
        """Clear all outputs for fresh analysis."""
        self.outputs = []
        logger.info("Detector reset")


def run_demo():
    """Demonstrate bias detection with realistic examples."""
    logger.info("=" * 60)
    logger.info("AI OUTPUT BIAS DETECTION - DEMONSTRATION")
    logger.info("=" * 60)
    
    # Hiring domain demo
    print("\n" + "=" * 60)
    print("HIRING DOMAIN ANALYSIS")
    print("=" * 60)
    
    detector = OutputBiasDetector(Domain.HIRING)
    
    # Simulate biased hiring outputs
    hiring_outputs = [
        ("Candidate has strong technical skills and would be a great cultural fit.", "approved", {"gender": "male"}),
        ("She has good qualifications but may struggle with the demanding schedule.", "rejected", {"gender": "female"}),
        ("His experience aligns perfectly with our needs.", "approved", {"gender": "male"}),
        ("The applicant shows potential but we're looking for someone more assertive.", "rejected", {"gender": "female"}),
        ("Great leadership background, very decisive.", "approved", {"gender": "male"}),
        ("She might not fit well with the team's dynamic.", "rejected", {"gender": "female"}),
        ("Strong candidate with excellent communication.", "approved", {"gender": "male"}),
        ("Her qualifications are good but she seems overqualified for this role.", "rejected", {"gender": "female"}),
        ("Impressive track record in similar positions.", "approved", {"gender": "male"}),
        ("We need someone who can commit fully without distractions.", "rejected", {"gender": "female"}),
        ("Young professional with fresh perspective.", "pending", {"age_group": "young"}),
        ("Experienced candidate but may be set in their ways.", "rejected", {"age_group": "senior"}),
        ("Recent graduate, eager to learn.", "approved", {"age_group": "young"}),
    ]
    
    for text, outcome, meta in hiring_outputs:
        detector.add_output(text, outcome, meta)
    
    report = detector.generate_report()
    
    print(f"\nReport ID: {report.report_id}")
    print(f"Domain: {report.domain}")
    print(f"Total Outputs Analyzed: {report.total_outputs}")
    print(f"Overall Risk Score: {report.overall_risk_score}/100")
    print(f"Audit Passed: {'YES ✓' if report.passed_audit else 'NO ✗'}")
    print(f"\nFindings ({len(report.findings)}):")
    
    for i, finding in enumerate(report.findings, 1):
        print(f"\n  {i}. [{finding.severity}] {finding.protected_attribute}")
        print(f"     Disparity Ratio: {finding.disparity_ratio}")
        print(f"     Affected: {finding.affected_group} vs {finding.reference_group}")
        print(f"     Sample Size: {finding.sample_size}")
        print(f"     {finding.description}")
    
    # Healthcare domain demo
    print("\n" + "=" * 60)
    print("HEALTHCARE DOMAIN ANALYSIS")
    print("=" * 60)
    
    detector2 = OutputBiasDetector(Domain.HEALTHCARE)
    
    healthcare_outputs = [
        ("Patient presents with typical cardiac symptoms. Recommend standard treatment protocol.", "recommended", {"race": "white", "gender": "male"}),
        ("Patient reports pain but may be exaggerating symptoms. Monitor before intervention.", "delayed", {"race": "black", "gender": "female"}),
        ("Standard care appropriate for this demographic.", "recommended", {"race": "white", "gender": "male"}),
        ("Cultural factors may affect compliance with treatment plan.", "alternative", {"race": "hispanic", "gender": "female"}),
        ("Patient is reliable and follows medical advice well.", "recommended", {"race": "white", "gender": "male"}),
        ("History suggests potential drug-seeking behavior. Proceed with caution.", "restricted", {"race": "black", "gender": "female"}),
    ]
    
    for text, outcome, meta in healthcare_outputs:
        detector2.add_output(text, outcome, meta)
    
    report2 = detector2.generate_report()
    
    print(f"\nReport ID: {report2.report_id}")
    print(f"Overall Risk Score: {report2.overall_risk_score}/100")
    print(f"Audit Passed: {'YES ✓' if report2.passed_audit else 'NO ✗'}")
    
    for finding in report2.findings:
        print(f"\n  [{finding.severity}] {finding.description}")
    
    # Summary
    print("\n" + "=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    print(f"Reports saved to: {MEMORY_DIR}")
    print(f"Total findings across demos: {len(report.findings) + len(report2.findings)}")


if __name__ == "__main__":
    try:
        run_demo()
    except Exception as e:
        logger.critical(f"Fatal error in demo: {e}", exc_info=True)
        raise