"""
test_build_smoke.py
TAD AI — Smoke Test Build Module
Opportunity: test_build_smoke (Score: 29, Verdict: GO)
CEO: Joshua Abraham | Agent: TAD (Total Autonomous Director)
Generated: 2026-06-26

Purpose:
    Validates the TAD pipeline end-to-end by running a full smoke test
    against every critical subsystem: logging, opportunity scoring,
    file I/O, API call scaffolding, and agent role execution.
    This module is the canonical health-check for any new TAD deployment.
"""

import os
import sys
import json
import time
import logging
import hashlib
import traceback
import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# CONSTANTS & PATHS
# ---------------------------------------------------------------------------

TAD_ROOT = Path(r"C:\TAD")
MEMORY_DIR = TAD_ROOT / "memory"
LOGS_DIR = MEMORY_DIR / "logs"
RESULTS_DIR = MEMORY_DIR / "results"
BUILDS_DIR = TAD_ROOT / "builds"

MODULE_NAME = "test_build_smoke"
MODULE_VERSION = "1.0.0"
OPPORTUNITY_META = {
    "opportunity_name": MODULE_NAME,
    "total_score": 29,
    "verdict": "GO",
    "timestamp": "2026-06-26T01:18:02.212360",
    "name": MODULE_NAME,
}


# ---------------------------------------------------------------------------
# DIRECTORY BOOTSTRAP
# ---------------------------------------------------------------------------

def bootstrap_directories() -> None:
    """Ensure all required TAD directories exist before anything else runs."""
    for directory in [MEMORY_DIR, LOGS_DIR, RESULTS_DIR, BUILDS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# LOGGING SETUP
# ---------------------------------------------------------------------------

def setup_logger(name: str = MODULE_NAME) -> logging.Logger:
    """
    Configures a dual-handler logger:
      - File handler  → memory/logs/<name>_<date>.log
      - Stream handler → stdout
    Returns a fully configured Logger instance.
    """
    bootstrap_directories()

    log_filename = LOGS_DIR / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger  # already configured; avoid duplicate handlers

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # File handler
    fh = logging.FileHandler(log_filename, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Stream handler
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)

    logger.info("Logger initialised → %s", log_filename)
    return logger


log = setup_logger()


# ---------------------------------------------------------------------------
# RESULT PERSISTENCE
# ---------------------------------------------------------------------------

class ResultStore:
    """
    Persists smoke-test results to memory/results/ as JSON.
    Each run gets a unique file keyed by timestamp + content hash.
    """

    def __init__(self, results_dir: Path = RESULTS_DIR) -> None:
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def save(self, payload: Dict[str, Any]) -> Path:
        raw = json.dumps(payload, indent=2, default=str)
        content_hash = hashlib.sha256(raw.encode()).hexdigest()[:10]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = self.results_dir / f"{MODULE_NAME}_{ts}_{content_hash}.json"
        filename.write_text(raw, encoding="utf-8")
        log.info("Result persisted → %s", filename)
        return filename

    def load_latest(self) -> Optional[Dict[str, Any]]:
        files = sorted(self.results_dir.glob(f"{MODULE_NAME}_*.json"), reverse=True)
        if not files:
            log.warning("No previous results found in %s", self.results_dir)
            return None
        data = json.loads(files[0].read_text(encoding="utf-8"))
        log.info("Loaded previous result from %s", files[0])
        return data


# ---------------------------------------------------------------------------
# SMOKE TEST CASES
# ---------------------------------------------------------------------------

class SmokeTest:
    """
    A single smoke-test case.  Every test must:
      - Return (passed: bool, detail: str)
      - Never raise — catch and report internally
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.passed: Optional[bool] = None
        self.detail: str = ""
        self.elapsed_ms: float = 0.0

    def run(self) -> "SmokeTest":
        raise NotImplementedError

    def _record(self, passed: bool, detail: str, start: float) -> "SmokeTest":
        self.passed = passed
        self.detail = detail
        self.elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        status = "PASS" if passed else "FAIL"
        log.debug("[%s] %s — %s (%.1f ms)", status, self.name, detail, self.elapsed_ms)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "elapsed_ms": self.elapsed_ms,
        }


# ------------------------------------
# Individual test implementations
# ------------------------------------

class TestDirectoryStructure(SmokeTest):
    """Verify all required TAD directories exist."""

    def __init__(self) -> None:
        super().__init__("directory_structure")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            missing = [str(d) for d in [MEMORY_DIR, LOGS_DIR, RESULTS_DIR, BUILDS_DIR] if not d.exists()]
            if missing:
                return self._record(False, f"Missing dirs: {missing}", start)
            return self._record(True, "All required directories present", start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestLoggerWriteable(SmokeTest):
    """Verify the logger can write to the log file without error."""

    def __init__(self) -> None:
        super().__init__("logger_writeable")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            log.debug("Smoke test logger probe — %s", datetime.utcnow().isoformat())
            log_files = list(LOGS_DIR.glob(f"{MODULE_NAME}_*.log"))
            if not log_files:
                return self._record(False, "No log file created", start)
            return self._record(True, f"Log file OK: {log_files[-1].name}", start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestResultStoreSaveLoad(SmokeTest):
    """Verify ResultStore can persist and reload data correctly."""

    def __init__(self) -> None:
        super().__init__("result_store_save_load")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            store = ResultStore()
            probe = {"probe": True, "ts": datetime.utcnow().isoformat(), "value": 42}
            path = store.save(probe)
            if not path.exists():
                return self._record(False, "Saved file does not exist", start)
            reloaded = json.loads(path.read_text(encoding="utf-8"))
            if reloaded.get("value") != 42:
                return self._record(False, "Reloaded data mismatch", start)
            return self._record(True, f"Save/load round-trip OK ({path.name})", start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestOpportunityMetaIntegrity(SmokeTest):
    """Validate that the opportunity metadata has all required fields and correct types."""

    REQUIRED_FIELDS: Dict[str, type] = {
        "opportunity_name": str,
        "total_score": int,
        "verdict": str,
        "timestamp": str,
        "name": str,
    }

    def __init__(self) -> None:
        super().__init__("opportunity_meta_integrity")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            errors: List[str] = []
            for field, expected_type in self.REQUIRED_FIELDS.items():
                if field not in OPPORTUNITY_META:
                    errors.append(f"Missing field: {field}")
                elif not isinstance(OPPORTUNITY_META[field], expected_type):
                    errors.append(
                        f"Field '{field}' expected {expected_type.__name__}, "
                        f"got {type(OPPORTUNITY_META[field]).__name__}"
                    )
            if OPPORTUNITY_META.get("verdict") not in ("GO", "NO_GO", "REVIEW"):
                errors.append(f"Invalid verdict: {OPPORTUNITY_META.get('verdict')}")
            if errors:
                return self._record(False, "; ".join(errors), start)
            return self._record(True, "All metadata fields valid", start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestScoringEngine(SmokeTest):
    """Run the built-in opportunity scoring engine and verify it produces sane output."""

    def __init__(self) -> None:
        super().__init__("scoring_engine")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            engine = OpportunityScorer()
            # Score a synthetic opportunity
            synthetic = {
                "competition_level": "low",
                "pain_intensity": 8,
                "willingness_to_pay": 9,
                "market_size": "medium",
                "ai_loophole_clarity": 7,
            }
            score, breakdown = engine.score(synthetic)
            if not isinstance(score, (int, float)):
                return self._record(False, f"Score type invalid: {type(score)}", start)
            if score < 0 or score > 100:
                return self._record(False, f"Score out of range: {score}", start)
            return self._record(
                True,
                f"Score={score} | Breakdown={breakdown}",
                start,
            )
        except Exception as exc:
            return self._record(False, f"Exception: {exc}\n{traceback.format_exc()}", start)


class TestAgentRoleExecution(SmokeTest):
    """Instantiate each TAD agent role and verify it responds to a ping."""

    def __init__(self) -> None:
        super().__init__("agent_role_execution")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            roles = [
                LoopholeHunterAgent(),
                MarketValidatorAgent(),
                BuildDirectorAgent(),
                RevenueTrackerAgent(),
            ]
            results: List[str] = []
            for role in roles:
                response = role.ping()
                if response.get("status") != "alive":
                    results.append(f"{role.role_name}: DEAD ({response})")
                else:
                    results.append(f"{role.role_name}: alive")
            failed = [r for r in results if "DEAD" in r]
            if failed:
                return self._record(False, " | ".join(failed), start)
            return self._record(True, " | ".join(results), start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestAPICallScaffold(SmokeTest):
    """
    Verify the API call scaffolding handles both success and failure paths
    without leaking exceptions to the caller.
    """

    def __init__(self) -> None:
        super().__init__("api_call_scaffold")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        try:
            client = APICallScaffold(api_key="smoke_test_key", base_url="https://api.example.com")

            # Simulate a successful call (mocked internally)
            ok_result = client.call(endpoint="/ping", payload={}, _mock_success=True)
            if not ok_result.get("success"):
                return self._record(False, f"Mock success path failed: {ok_result}", start)

            # Simulate a failure call
            err_result = client.call(endpoint="/error", payload={}, _mock_success=False)
            if err_result.get("success"):
                return self._record(False, "Mock failure path returned success", start)
            if "error" not in err_result:
                return self._record(False, "Error result missing 'error' key", start)

            return self._record(True, "Success and failure paths both handled correctly", start)
        except Exception as exc:
            return self._record(False, f"Exception: {exc}", start)


class TestFileIOReliability(SmokeTest):
    """Write, read, and delete a temp file in memory/ to confirm filesystem reliability."""

    def __init__(self) -> None:
        super().__init__("file_io_reliability")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        tmp_path = MEMORY_DIR / f"_smoke_probe_{int(time.time())}.tmp"
        try:
            sentinel = f"TAD_SMOKE_{hashlib.md5(str(time.time()).encode()).hexdigest()}"
            tmp_path.write_text(sentinel, encoding="utf-8")

            if not tmp_path.exists():
                return self._record(False, "File not created", start)

            read_back = tmp_path.read_text(encoding="utf-8")
            if read_back != sentinel:
                return self._record(False, f"Content mismatch: {read_back!r}", start)

            tmp_path.unlink()
            if tmp_path.exists():
                return self._record(False, "File not deleted", start)

            return self._record(True, "Write / Read / Delete all succeeded", start)
        except Exception as exc:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return self._record(False, f"Exception: {exc}", start)


class TestPythonDependencies(SmokeTest):
    """Check that all modules imported by this file are available in the environment."""

    REQUIRED_MODULES = [
        "os", "sys", "json", "time", "logging", "hashlib",
        "traceback", "importlib", "datetime", "pathlib", "typing",
    ]

    def __init__(self) -> None:
        super().__init__("python_dependencies")

    def run(self) -> "SmokeTest":
        start = time.perf_counter()
        missing: List[str] = []
        for mod in self.REQUIRED_MODULES:
            try:
                importlib.import_module(mod)
            except ImportError:
                missing.append(mod)
        if missing:
            return self._record(False, f"Missing modules: {missing}", start)
        return self._record(True, f"All {len(self.REQUIRED_MODULES)} modules importable", start)


# ---------------------------------------------------------------------------
# BUSINESS LOGIC — OPPORTUNITY SCORING ENGINE
# ---------------------------------------------------------------------------

class OpportunityScorer:
    """
    Scores an opportunity dict on a 0–100 scale using TAD's weighted rubric.

    Dimensions:
        competition_level    (low=40, medium=20, high=0)
        pain_intensity       (0–10 scale, weight 0.25)
        willingness_to_pay   (0–10 scale, weight 0.20)
        market_size          (large=15, medium=10, small=5)
        ai_loophole_clarity  (0–10 scale, weight 0.10)
    """

    COMPETITION_SCORES = {"low": 40, "medium": 20, "high": 0}
    MARKET_SIZE_SCORES = {"large": 15, "medium": 10, "small": 5}

    def score(self, opportunity: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        breakdown: Dict[str, float] = {}

        # Competition
        comp_raw = str(opportunity.get("competition_level", "high")).lower()
        breakdown["competition"] = float(self.COMPETITION_SCORES.get(comp_raw, 0))

        # Pain intensity (0–10 → 0–25)
        pain = min(max(float(opportunity.get("pain_intensity", 0)), 0), 10)
        breakdown["pain_intensity"] = pain * 2.5

        # Willingness to pay (0–10 → 0–20)
        wtp = min(max(float(opportunity.get("willingness_to_pay", 0)), 0), 10)
        breakdown["willingness_to_pay"] = wtp * 2.0

        # Market size
        market_raw = str(opportunity.get("market_size", "small")).lower()
        breakdown["market_size"] = float(self.MARKET_SIZE_SCORES.get(market_raw, 5))

        # AI loophole clarity (0–10 → 0–10)
        clarity = min(max(float(opportunity.get("ai_loophole_clarity", 0)), 0), 10)
        breakdown["ai_loophole_clarity"] = clarity * 1.0

        total = round(sum(breakdown.values()), 2)
        log.debug("Scorer breakdown: %s → total=%s", breakdown, total)
        return total, breakdown


# ---------------------------------------------------------------------------
# BUSINESS LOGIC — TAD AGENT ROLES
# ---------------------------------------------------------------------------

class TadAgent:
    """Base class for all TAD agent roles."""

    role_name: str = "base_agent"
    version: str = "1.0.0"

    def ping(self) -> Dict[str, Any]:
        return {
            "status": "alive",
            "role": self.role_name,
            "version": self.version,
            "ts": datetime.utcnow().isoformat(),
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError(f"{self.role_name}.execute() not implemented")


class LoopholeHunterAgent(TadAgent):
    """
    Continuously scans the AI landscape for underserved pain points.
    Produces ranked opportunity candidates for the scoring engine.
    """

    role_name = "loophole_hunter"

    PROMPT = (
        "You are the Loophole Hunter. Your sole mission is to identify gaps "
        "in the AI industry where real users are suffering but no good product "
        "exists yet. Output structured opportunity candidates with fields: "
        "name, pain_intensity, competition_level, willingness_to_pay, "
        "market_size, ai_loophole_clarity, evidence_urls."
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        In production this calls an LLM with self.PROMPT.
        Smoke-test path returns a deterministic mock.
        """
        log.info("[%s] Executing hunt task: %s", self.role_name, task.get("query", ""))
        candidates = [
            {
                "name": "ai_context_window_cost_optimizer",
                "pain_intensity": 8,
                "competition_level": "low",
                "willingness_to_pay": 9,
                "market_size": "large",
                "ai_loophole_clarity": 8,
                "evidence_urls": [],
            }
        ]
        return {"status": "success", "candidates": candidates, "agent": self.role_name}


class MarketValidatorAgent(TadAgent):
    """
    Takes loophole candidates from LoopholeHunterAgent and validates
    real market demand via search volume, Reddit/HN signals, and pricing data.
    """

    role_name = "market_validator"

    PROMPT = (
        "You are the Market Validator. Given an opportunity candidate, "
        "research and quantify: search volume trends, community discussion "
        "volume, existing pricing signals, and TAM estimate. Return a "
        "validated_score between 0–100 and a go_no_go recommendation."
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        candidate = task.get("candidate", {})
        log.info("[%s] Validating: %s", self.role_name, candidate.get("name", "unknown"))
        scorer = OpportunityScorer()
        score, breakdown = scorer.score(candidate)
        verdict = "GO" if score >= 25 else "NO_GO"
        return {
            "status": "success",
            "validated_score": score,
            "breakdown": breakdown,
            "verdict": verdict,
            "agent": self.role_name,
        }


class BuildDirectorAgent(TadAgent):
    """
    Takes a validated GO opportunity and orchestrates the build:
    module generation, file structure, test scaffolding, and deployment prep.
    """

    role_name = "build_director"

    PROMPT = (
        "You are the Build Director. Given a validated opportunity, generate "
        "a complete production-quality Python module. Define the exact file "
        "structure, class/function signatures, business logic, error handling, "
        "and logging. Output must be runnable with no placeholders."
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        opportunity = task.get("opportunity", {})
        name = opportunity.get("name", "unnamed")
        log.info("[%s] Directing build for: %s", self.role_name, name)
        build_path = BUILDS_DIR / f"{name}.py"
        return {
            "status": "success",
            "target_file": str(build_path),
            "build_ready": True,
            "agent": self.role_name,
        }


class RevenueTrackerAgent(TadAgent):
    """
    Monitors revenue metrics, MRR growth, churn, and LTV for each
    deployed TAD product. Feeds data back into the opportunity scoring loop.
    """

    role_name = "revenue_tracker"

    PROMPT = (
        "You are the Revenue Tracker. For each live TAD product, track: "
        "MRR, active subscribers, churn rate, LTV, and CAC. Produce a "
        "weekly revenue report and flag products below target thresholds."
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        product = task.get("product", "unknown")
        log.info("[%s] Tracking revenue for: %s", self.role_name, product)
        # Stub — production wires to Stripe / payment gateway API
        mock_metrics = {
            "product": product,
            "mrr": 0.0,
            "active_subscribers": 0,
            "churn_rate": 0.0,
            "ltv": 0.0,
            "cac": 0.0,
            "status": "pre_revenue",
        }
        return {"status": "success", "metrics": mock_metrics, "agent": self.role_name}


# ---------------------------------------------------------------------------
# BUSINESS LOGIC — API CALL SCAFFOLD
# ---------------------------------------------------------------------------

class APICallScaffold:
    """
    Centralised, retry-aware API client used by all TAD agents.

    Features:
    - Configurable retries with exponential back-off
    - Structured error capture (never raises to callers)
    - Full request/response logging at DEBUG level
    - Mock mode for smoke testing (no real network I/O)
    """

    DEFAULT_RETRIES = 3
    BASE_BACKOFF_S = 1.0

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_s: float = 30.0,
        retries: int = DEFAULT_RETRIES,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = retries

    def call(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        method: str = "POST",
        _mock_success: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Makes an API call (or returns a mock result in smoke-test mode).

        Returns:
            {"success": True, "data": {...}}   on success
            {"success": False, "error": "..."}  on failure
        """
        url = f"{self.base_url}{endpoint}"
        log.debug("API %s %s payload=%s", method.upper(), url, payload)

        # --- Mock path (used by smoke tests) ---
        if _mock_success is not None:
            if _mock_success:
                log.debug("API mock SUCCESS for %s", endpoint)
                return {"success": True, "data": {"mock": True, "endpoint": endpoint}}
            else:
                log.debug("API mock FAILURE for %s", endpoint)
                return {"success": False, "error": "Mock failure injected by smoke test"}

        # --- Real network path ---
        attempt = 0
        last_error = ""
        while attempt < self.retries:
            attempt += 1
            try:
                # Import lazily so the module loads even if requests isn't installed
                import urllib.request
                import urllib.error

                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": f"TAD-AI/{MODULE_VERSION}",
                    },
                    method=method.upper(),
                )
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    log.debug("API response (%d): %s", resp.status, body)
                    return {"success": True, "data": body}

            except Exception as exc:
                last_error = str(exc)
                wait = self.BASE_BACKOFF_S * (2 ** (attempt - 1))
                log.warning(
                    "API call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt, self.retries, exc, wait,
                )
                if attempt < self.retries:
                    time.sleep(wait)

        log.error("API call exhausted retries for %s: %s", endpoint, last_error)
        return {"success": False, "error": last_error}


# ---------------------------------------------------------------------------
# SMOKE TEST RUNNER
# ---------------------------------------------------------------------------

class SmokeTestRunner:
    """
    Orchestrates all smoke tests, collects results, persists them,
    and returns a structured summary.
    """

    def __init__(self) -> None:
        self.tests: List[SmokeTest] = [
            TestPythonDependencies(),
            TestDirectoryStructure(),
            TestLoggerWriteable(),
            TestResultStoreSaveLoad(),
            TestOpportunityMetaIntegrity(),
            TestScoringEngine(),
            TestAgentRoleExecution(),
            TestAPICallScaffold(),
            TestFileIOReliability(),
        ]
        self.store = ResultStore()

    def run_all(self) -> Dict[str, Any]:
        log.info("=" * 60)
        log.info("TAD SMOKE TEST — %s v%s", MODULE_NAME, MODULE_VERSION)
        log.info("Opportunity Score: %d | Verdict: %s", OPPORTUNITY_META["total_score"], OPPORTUNITY_META["verdict"])
        log.info("=" * 60)

        suite_start = time.perf_counter()
        outcomes: List[Dict[str, Any]] = []

        for test in self.tests:
            log.info("Running: %s", test.name)
            test.run()
            outcomes.append(test.to_dict())

        suite_elapsed = round((time.perf_counter() - suite_start) * 1000, 2)

        passed = [o for o in outcomes if o["passed"]]
        failed = [o for o in outcomes if not o["passed"]]

        summary = {
            "module": MODULE_NAME,
            "version": MODULE_VERSION,
            "opportunity": OPPORTUNITY_META,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "total": len(outcomes),
            "passed": len(passed),
            "failed": len(failed),
            "suite_elapsed_ms": suite_elapsed,
            "all_passed": len(failed) == 0,
            "tests": outcomes,
        }

        # Persist
        result_path = self.store.save(summary)

        # Print report
        log.info("=" * 60)
        log.info("SMOKE TEST COMPLETE")
        log.info("  Total:  %d", summary["total"])
        log.info("  Passed: %d", summary["passed"])
        log.info("  Failed: %d", summary["failed"])
        log.info("  Time:   %.1f ms", suite_elapsed)
        log.info("  Result: %s", result_path)

        if failed:
            log.warning("FAILED TESTS:")
            for f in failed:
                log.warning("  ✗ %s — %s", f["name"], f["detail"])
        else:
            log.info("ALL TESTS PASSED ✓")

        log.info("=" * 60)
        return summary


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Main entry point.
    Returns 0 on full pass, 1 on any failure (for CI/shell integration).
    """
    bootstrap_directories()
    runner = SmokeTestRunner()
    summary = runner.run_all()
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())