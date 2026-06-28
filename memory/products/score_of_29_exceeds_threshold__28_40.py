"""
AI Model SLA Visibility Monitor
================================
Real-time SLA tracking and alerting for AI model latency.
Solves: AI teams have no real-time SLA visibility for model latency.

Business Logic:
- Tracks p50/p95/p99 latency per model endpoint
- Evaluates SLA compliance windows (rolling 5-min, 1-hour, 24-hour)
- Fires alerts when SLA thresholds are breached
- Persists metrics to memory/ for TAD pipeline consumption
- Exposes a simple dashboard summary

Author: TAD Build Agent
Date: 2026-06-28
"""

import json
import logging
import math
import os
import random
import statistics
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MEMORY_DIR = Path("memory/products")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = MEMORY_DIR / "sla_monitor.log"
METRICS_FILE = MEMORY_DIR / "sla_metrics.json"
ALERTS_FILE = MEMORY_DIR / "sla_alerts.jsonl"
STATE_FILE = MEMORY_DIR / "sla_state.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("sla_monitor")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SLAPolicy:
    """SLA contract for a single model endpoint."""

    model_id: str
    p50_budget_ms: float = 500.0   # 50th percentile must be under this
    p95_budget_ms: float = 1500.0  # 95th percentile must be under this
    p99_budget_ms: float = 3000.0  # 99th percentile must be under this
    error_rate_max: float = 0.02   # 2 % error rate ceiling
    window_seconds: int = 300      # rolling window for evaluation (5 min)


@dataclass
class LatencySample:
    """One completed model call."""

    model_id: str
    request_id: str
    latency_ms: float
    is_error: bool
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SLAWindow:
    """Computed SLA metrics for a time window."""

    model_id: str
    window_label: str          # "5min" | "1hour" | "24hour"
    sample_count: int
    error_count: int
    error_rate: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    sla_ok: bool
    violations: List[str]
    evaluated_at: str


@dataclass
class SLAAlert:
    """Fired when an SLA window is in breach."""

    alert_id: str
    model_id: str
    severity: str              # "warning" | "critical"
    message: str
    violations: List[str]
    p50_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    fired_at: str


# ---------------------------------------------------------------------------
# Percentile helper (no numpy needed)
# ---------------------------------------------------------------------------


def percentile(data: List[float], pct: float) -> float:
    """Return the *pct*-th percentile of *data* (0-100 scale)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = (pct / 100) * (len(sorted_data) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_data[lower]
    fraction = index - lower
    return sorted_data[lower] * (1 - fraction) + sorted_data[upper] * fraction


# ---------------------------------------------------------------------------
# In-memory sample store (ring buffer per model)
# ---------------------------------------------------------------------------


class SampleStore:
    """
    Thread-safe-ish ring buffer of LatencySamples per model.
    We keep up to 24 hours of samples.  Older entries are evicted lazily.
    """

    MAX_AGE_SECONDS = 86_400  # 24 hours

    def __init__(self) -> None:
        self._buffers: Dict[str, Deque[LatencySample]] = {}

    def record(self, sample: LatencySample) -> None:
        buf = self._buffers.setdefault(sample.model_id, deque())
        buf.append(sample)
        self._evict(sample.model_id)

    def _evict(self, model_id: str) -> None:
        cutoff = time.time() - self.MAX_AGE_SECONDS
        buf = self._buffers.get(model_id, deque())
        while buf and buf[0].timestamp < cutoff:
            buf.popleft()

    def samples_in_window(
        self, model_id: str, window_seconds: int
    ) -> List[LatencySample]:
        cutoff = time.time() - window_seconds
        return [
            s for s in self._buffers.get(model_id, [])
            if s.timestamp >= cutoff
        ]

    def all_model_ids(self) -> List[str]:
        return list(self._buffers.keys())

    def serialize(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for model_id, buf in self._buffers.items():
            result[model_id] = [asdict(s) for s in buf]
        return result

    def load(self, data: Dict[str, Any]) -> None:
        for model_id, samples in data.items():
            self._buffers[model_id] = deque(
                LatencySample(**s) for s in samples
            )


# ---------------------------------------------------------------------------
# SLA Evaluator
# ---------------------------------------------------------------------------


class SLAEvaluator:
    """
    Evaluates SLA compliance for all registered models across three windows.
    """

    WINDOWS: List[Tuple[str, int]] = [
        ("5min", 300),
        ("1hour", 3600),
        ("24hour", 86_400),
    ]

    def __init__(
        self,
        store: SampleStore,
        policies: Dict[str, SLAPolicy],
    ) -> None:
        self._store = store
        self._policies = policies

    def evaluate(self, model_id: str) -> List[SLAWindow]:
        policy = self._policies.get(model_id, SLAPolicy(model_id=model_id))
        results: List[SLAWindow] = []

        for label, seconds in self.WINDOWS:
            samples = self._store.samples_in_window(model_id, seconds)
            if not samples:
                continue

            latencies = [s.latency_ms for s in samples if not s.is_error]
            errors = [s for s in samples if s.is_error]
            error_rate = len(errors) / len(samples) if samples else 0.0

            if latencies:
                p50 = percentile(latencies, 50)
                p95 = percentile(latencies, 95)
                p99 = percentile(latencies, 99)
            else:
                p50 = p95 = p99 = 0.0

            violations: List[str] = []
            if p50 > policy.p50_budget_ms:
                violations.append(
                    f"p50 {p50:.0f}ms > budget {policy.p50_budget_ms:.0f}ms"
                )
            if p95 > policy.p95_budget_ms:
                violations.append(
                    f"p95 {p95:.0f}ms > budget {policy.p95_budget_ms:.0f}ms"
                )
            if p99 > policy.p99_budget_ms:
                violations.append(
                    f"p99 {p99:.0f}ms > budget {policy.p99_budget_ms:.0f}ms"
                )
            if error_rate > policy.error_rate_max:
                violations.append(
                    f"error_rate {error_rate:.1%} > max {policy.error_rate_max:.1%}"
                )

            results.append(
                SLAWindow(
                    model_id=model_id,
                    window_label=label,
                    sample_count=len(samples),
                    error_count=len(errors),
                    error_rate=error_rate,
                    p50_ms=round(p50, 2),
                    p95_ms=round(p95, 2),
                    p99_ms=round(p99, 2),
                    sla_ok=len(violations) == 0,
                    violations=violations,
                    evaluated_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        return results


# ---------------------------------------------------------------------------
# Alert Engine
# ---------------------------------------------------------------------------


class AlertEngine:
    """
    Converts SLA window violations into structured alerts.
    Implements simple cool-down to avoid alert storms (60 s per model/window).
    """

    COOLDOWN_SECONDS = 60

    def __init__(self) -> None:
        self._last_alert: Dict[str, float] = {}

    def process(self, windows: List[SLAWindow]) -> List[SLAAlert]:
        alerts: List[SLAAlert] = []
        for w in windows:
            if w.sla_ok:
                continue
            key = f"{w.model_id}:{w.window_label}"
            now = time.time()
            if now - self._last_alert.get(key, 0) < self.COOLDOWN_SECONDS:
                continue  # still in cool-down
            self._last_alert[key] = now

            # Determine severity: critical if p99 or error_rate violated
            critical_keywords = ["p99", "error_rate"]
            severity = (
                "critical"
                if any(
                    any(kw in v for kw in critical_keywords)
                    for v in w.violations
                )
                else "warning"
            )

            alert = SLAAlert(
                alert_id=str(uuid.uuid4()),
                model_id=w.model_id,
                severity=severity,
                message=(
                    f"[{severity.upper()}] {w.model_id} SLA breach "
                    f"in {w.window_label} window — "
                    f"{len(w.violations)} violation(s)"
                ),
                violations=w.violations,
                p50_ms=w.p50_ms,
                p95_ms=w.p95_ms,
                p99_ms=w.p99_ms,
                error_rate=w.error_rate,
                fired_at=datetime.now(timezone.utc).isoformat(),
            )
            alerts.append(alert)
            log.warning("🚨 %s", alert.message)
            for v in w.violations:
                log.warning("   → %s", v)

        return alerts

    def persist(self, alerts: List[SLAAlert]) -> None:
        if not alerts:
            return
        try:
            with ALERTS_FILE.open("a") as fh:
                for a in alerts:
                    fh.write(json.dumps(asdict(a)) + "\n")
            log.info("Persisted %d alert(s) → %s", len(alerts), ALERTS_FILE)
        except OSError as exc:
            log.error("Failed to persist alerts: %s", exc)


# ---------------------------------------------------------------------------
# Metrics Snapshot Writer
# ---------------------------------------------------------------------------


def write_metrics_snapshot(
    windows_by_model: Dict[str, List[SLAWindow]]
) -> None:
    """Write current metrics to METRICS_FILE for downstream consumers."""
    snapshot: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {},
    }
    for model_id, windows in windows_by_model.items():
        snapshot["models"][model_id] = [asdict(w) for w in windows]

    try:
        with METRICS_FILE.open("w") as fh:
            json.dump(snapshot, fh, indent=2)
        log.debug("Metrics snapshot written → %s", METRICS_FILE)
    except OSError as exc:
        log.error("Failed to write metrics snapshot: %s", exc)


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------


def print_dashboard(
    windows_by_model: Dict[str, List[SLAWindow]],
    alerts: List[SLAAlert],
) -> None:
    bar = "=" * 70
    print(f"\n{bar}")
    print("  AI MODEL SLA VISIBILITY DASHBOARD")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(bar)

    if not windows_by_model:
        print("  No data yet.\n")
        return

    for model_id, windows in windows_by_model.items():
        print(f"\n  Model: {model_id}")
        for w in windows:
            status = "✅ OK" if w.sla_ok else "❌ BREACH"
            print(
                f"    [{w.window_label:8s}] {status}  "
                f"n={w.sample_count:4d}  "
                f"p50={w.p50_ms:7.1f}ms  "
                f"p95={w.p95_ms:7.1f}ms  "
                f"p99={w.p99_ms:7.1f}ms  "
                f"err={w.error_rate:.1%}"
            )
            for v in w.violations:
                print(f"         ⚠  {v}")

    if alerts:
        print(f"\n  Active Alerts ({len(alerts)}):")
        for a in alerts:
            print(f"    🚨 [{a.severity.upper()}] {a.model_id}: {a.message}")

    print(f"\n{bar}\n")


# ---------------------------------------------------------------------------
# Main Monitor class
# ---------------------------------------------------------------------------


class SLAMonitor:
    """
    Orchestrates sample ingestion, SLA evaluation, alerting, and persistence.

    Typical usage:
        monitor = SLAMonitor()
        monitor.register_policy(SLAPolicy(model_id="gpt-4o", p95_budget_ms=1200))
        monitor.record(LatencySample(model_id="gpt-4o", ...))
        report = monitor.evaluate_all()
    """

    def __init__(self) -> None:
        self._store = SampleStore()
        self._policies: Dict[str, SLAPolicy] = {}
        self._evaluator: Optional[SLAEvaluator] = None
        self._alerter = AlertEngine()
        self._load_state()

    def register_policy(self, policy: SLAPolicy) -> None:
        self._policies[policy.model_id] = policy
        self._evaluator = SLAEvaluator(self._store, self._policies)
        log.info("Registered SLA policy for model '%s'", policy.model_id)

    def record(self, sample: LatencySample) -> None:
        self._store.record(sample)
        log.debug(
            "Recorded sample: model=%s latency=%.1fms error=%s",
            sample.model_id,
            sample.latency_ms,
            sample.is_error,
        )

    def evaluate_all(self) -> Dict[str, Any]:
        """Run full evaluation cycle; returns summary dict."""
        if self._evaluator is None:
            self._evaluator = SLAEvaluator(self._store, self._policies)

        model_ids = list(
            set(list(self._policies.keys()) + self._store.all_model_ids())
        )

        windows_by_model: Dict[str, List[SLAWindow]] = {}
        for mid in model_ids:
            windows = self._evaluator.evaluate(mid)
            if windows:
                windows_by_model[mid] = windows

        all_alerts: List[SLAAlert] = []
        for windows in windows_by_model.values():
            alerts = self._alerter.process(windows)
            all_alerts.extend(alerts)

        self._alerter.persist(all_alerts)
        write_metrics_snapshot(windows_by_model)
        self._save_state()

        return {
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "models_evaluated": len(windows_by_model),
            "total_alerts_fired": len(all_alerts),
            "windows": {
                mid: [asdict(w) for w in wlist]
                for mid, wlist in windows_by_model.items()
            },
            "alerts": [asdict(a) for a in all_alerts],
        }

    # ------------------------------------------------------------------
    # State persistence (survive restarts)
    # ------------------------------------------------------------------

    def _save_state(self) -> None:
        try:
            state = {
                "policies": {
                    mid: asdict(p) for mid, p in self._policies.items()
                },
                "samples": self._store.serialize(),
                "alerter_cooldowns": self._alerter._last_alert,
            }
            with STATE_FILE.open("w") as fh:
                json.dump(state, fh)
        except OSError as exc:
            log.warning("Could not save state: %s", exc)

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            with STATE_FILE.open() as fh:
                state = json.load(fh)
            for mid, pdata in state.get("policies", {}).items():
                self._policies[mid] = SLAPolicy(**pdata)
            self._store.load(state.get("samples", {}))
            self._alerter._last_alert = state.get("alerter_cooldowns", {})
            self._evaluator = SLAEvaluator(self._store, self._policies)
            log.info(
                "State restored: %d policies, models=%s",
                len(self._policies),
                list(self._policies.keys()),
            )
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
            log.warning("Could not load state (starting fresh): %s", exc)


# ---------------------------------------------------------------------------
# Synthetic load simulator (for demos / self-test)
# ---------------------------------------------------------------------------


def simulate_model_traffic(
    monitor: SLAMonitor,
    model_id: str,
    n_requests: int = 200,
    base_latency_ms: float = 400.0,
    spike_probability: float = 0.05,
    error_probability: float = 0.015,
) -> None:
    """
    Inject realistic synthetic traffic into the monitor.
    Includes occasional latency spikes and errors to trigger SLA breaches.
    """
    log.info(
        "Simulating %d requests for model '%s' …", n_requests, model_id
    )
    now = time.time()

    for i in range(n_requests):
        # Distribute timestamps over the past 30 minutes
        ts = now - random.uniform(0, 1800)

        is_error = random.random() < error_probability
        if is_error:
            latency_ms = random.uniform(50, 200)  # fast fails
        elif random.random() < spike_probability:
            latency_ms = random.gauss(base_latency_ms * 6, base_latency_ms)
        else:
            latency_ms = max(10.0, random.gauss(base_latency_ms, base_latency_ms * 0.25))

        sample = LatencySample(
            model_id=model_id,
            request_id=str(uuid.uuid4()),
            latency_ms=round(latency_ms, 2),
            is_error=is_error,
            timestamp=ts,
            metadata={"seq": i},
        )
        monitor._store.record(sample)

    log.info("Simulation complete for '%s'.", model_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("Starting AI Model SLA Visibility Monitor")

    monitor = SLAMonitor()

    # Register SLA policies for three hypothetical model endpoints
    monitor.register_policy(
        SLAPolicy(
            model_id="gpt-4o",
            p50_budget_ms=500,
            p95_budget_ms=1200,
            p99_budget_ms=2500,
            error_rate_max=0.02,
        )
    )
    monitor.register_policy(
        SLAPolicy(
            model_id="claude-3-opus",
            p50_budget_ms=800,
            p95_budget_ms=2000,
            p99_budget_ms=4000,
            error_rate_max=0.03,
        )
    )
    monitor.register_policy(
        SLAPolicy(
            model_id="llama-3-70b",
            p50_budget_ms=300,
            p95_budget_ms=900,
            p99_budget_ms=2000,
            error_rate_max=0.01,  # strict — will likely breach in sim
        )
    )

    # Simulate traffic (healthy + some spiky)
    simulate_model_traffic(
        monitor,
        model_id="gpt-4o",
        n_requests=300,
        base_latency_ms=400,
        spike_probability=0.04,
        error_probability=0.018,
    )
    simulate_model_traffic(
        monitor,
        model_id="claude-3-opus",
        n_requests=150,
        base_latency_ms=700,
        spike_probability=0.02,
        error_probability=0.01,
    )
    simulate_model_traffic(
        monitor,
        model_id="llama-3-70b",
        n_requests=500,
        base_latency_ms=250,
        spike_probability=0.08,   # frequent spikes → will breach p99
        error_probability=0.025,  # above error budget → will breach
    )

    # Run evaluation cycle
    report = monitor.evaluate_all()

    # Print dashboard
    windows_by_model: Dict[str, List[SLAWindow]] = {}
    for mid, wlist in report["windows"].items():
        windows_by_model[mid] = [SLAWindow(**w) for w in wlist]

    alerts = [SLAAlert(**a) for a in report["alerts"]]
    print_dashboard(windows_by_model, alerts)

    # Summary
    log.info(
        "Evaluation complete. Models=%d | Alerts=%d | Metrics → %s | Alerts → %s",
        report["models_evaluated"],
        report["total_alerts_fired"],
        METRICS_FILE,
        ALERTS_FILE,
    )

    # Demonstrate live recording path
    log.info("Demonstrating live single-request recording …")
    live_sample = LatencySample(
        model_id="gpt-4o",
        request_id=str(uuid.uuid4()),
        latency_ms=4200.0,  # deliberate violation
        is_error=False,
    )
    monitor.record(live_sample)
    monitor.evaluate_all()
    log.info("Live recording demo complete.")


if __name__ == "__main__":
    main()