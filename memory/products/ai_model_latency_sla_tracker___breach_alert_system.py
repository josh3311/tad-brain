"""
AI Model Latency SLA Tracker & Breach Alert System
===================================================
Production-ready SLA monitoring for AI API providers (OpenAI, Anthropic, Cohere, etc.)
Tracks latency, uptime, error rates — alerts on SLA breaches via email/webhook/console.

Author: TAD Build Agent
Date: 2026-06-28
Product: memory/products/ai_model_latency_sla_tracker___breach_alert_system.py
"""

import os
import sys
import json
import time
import logging
import smtplib
import hashlib
import statistics
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from collections import deque
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import urllib.request
import urllib.error
import urllib.parse

# ---------------------------------------------------------------------------
# Directory bootstrap
# ---------------------------------------------------------------------------
MEMORY_DIR = Path("memory")
PRODUCTS_DIR = MEMORY_DIR / "products"
LOGS_DIR = MEMORY_DIR / "logs"
DATA_DIR = MEMORY_DIR / "sla_tracker"

for _d in [PRODUCTS_DIR, LOGS_DIR, DATA_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = LOGS_DIR / "sla_tracker.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("SLATracker")

# ---------------------------------------------------------------------------
# SLA Definitions
# ---------------------------------------------------------------------------

@dataclass
class SLAPolicy:
    """SLA thresholds for a single provider/model combination."""
    provider: str
    model: str
    max_p50_ms: float = 800.0       # 50th-percentile latency ceiling
    max_p95_ms: float = 3000.0      # 95th-percentile latency ceiling
    max_p99_ms: float = 8000.0      # 99th-percentile latency ceiling
    max_error_rate_pct: float = 2.0 # error % over rolling window
    min_uptime_pct: float = 99.5    # uptime % over rolling window
    rolling_window_minutes: int = 60
    alert_cooldown_seconds: int = 300  # don't re-alert same breach for 5 min

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.model}"


# Default SLA catalogue — operators can override via sla_config.json
DEFAULT_SLA_POLICIES = [
    SLAPolicy("openai",    "gpt-4o",              max_p50_ms=900,  max_p95_ms=4000),
    SLAPolicy("openai",    "gpt-4o-mini",         max_p50_ms=500,  max_p95_ms=2000),
    SLAPolicy("openai",    "gpt-3.5-turbo",       max_p50_ms=400,  max_p95_ms=1500),
    SLAPolicy("anthropic", "claude-3-5-sonnet",   max_p50_ms=1000, max_p95_ms=5000),
    SLAPolicy("anthropic", "claude-3-haiku",      max_p50_ms=600,  max_p95_ms=2500),
    SLAPolicy("cohere",    "command-r-plus",      max_p50_ms=1200, max_p95_ms=6000),
    SLAPolicy("cohere",    "command-r",           max_p50_ms=800,  max_p95_ms=3500),
    SLAPolicy("google",    "gemini-1.5-pro",      max_p50_ms=1500, max_p95_ms=7000),
    SLAPolicy("google",    "gemini-1.5-flash",    max_p50_ms=700,  max_p95_ms=3000),
    SLAPolicy("mistral",   "mistral-large",       max_p50_ms=1000, max_p95_ms=4500),
    SLAPolicy("mistral",   "mistral-small",       max_p50_ms=600,  max_p95_ms=2500),
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class LatencySample:
    timestamp: float          # unix epoch
    latency_ms: float
    success: bool
    status_code: Optional[int] = None
    error_msg: Optional[str] = None
    token_count: Optional[int] = None


@dataclass
class SLABreachEvent:
    breach_id: str
    provider: str
    model: str
    breach_type: str           # p50_exceeded | p95_exceeded | p99_exceeded | error_rate | uptime
    threshold: float
    actual_value: float
    timestamp: float
    window_minutes: int
    alerted: bool = False


@dataclass
class ProviderStats:
    provider: str
    model: str
    samples: deque = field(default_factory=lambda: deque(maxlen=10_000))
    breach_history: list = field(default_factory=list)
    last_alert_times: dict = field(default_factory=dict)  # breach_type -> epoch

    def add_sample(self, sample: LatencySample):
        self.samples.append(sample)

    def window_samples(self, minutes: int) -> list:
        cutoff = time.time() - (minutes * 60)
        return [s for s in self.samples if s.timestamp >= cutoff]

    def compute_percentile(self, values: list, pct: float) -> Optional[float]:
        if not values:
            return None
        sorted_v = sorted(values)
        idx = max(0, int(len(sorted_v) * pct / 100) - 1)
        return sorted_v[idx]

    def get_metrics(self, window_minutes: int) -> dict:
        window = self.window_samples(window_minutes)
        if not window:
            return {}

        latencies = [s.latency_ms for s in window if s.success]
        errors = [s for s in window if not s.success]
        total = len(window)
        error_count = len(errors)

        result = {
            "sample_count": total,
            "error_count": error_count,
            "error_rate_pct": round((error_count / total) * 100, 2) if total else 0,
            "uptime_pct": round(((total - error_count) / total) * 100, 2) if total else 0,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "mean_ms": None,
            "min_ms": None,
            "max_ms": None,
        }

        if latencies:
            result["p50_ms"] = round(self.compute_percentile(latencies, 50), 1)
            result["p95_ms"] = round(self.compute_percentile(latencies, 95), 1)
            result["p99_ms"] = round(self.compute_percentile(latencies, 99), 1)
            result["mean_ms"] = round(statistics.mean(latencies), 1)
            result["min_ms"] = round(min(latencies), 1)
            result["max_ms"] = round(max(latencies), 1)

        return result


# ---------------------------------------------------------------------------
# Alert channels
# ---------------------------------------------------------------------------

class AlertChannel:
    """Base alert channel."""
    def send(self, breach: SLABreachEvent, policy: SLAPolicy, metrics: dict):
        raise NotImplementedError


class ConsoleAlertChannel(AlertChannel):
    """Prints breach alerts to stdout with formatting."""

    SEVERITY_COLORS = {
        "p99_exceeded":  "\033[91m",   # red
        "error_rate":    "\033[91m",
        "uptime":        "\033[91m",
        "p95_exceeded":  "\033[93m",   # yellow
        "p50_exceeded":  "\033[94m",   # blue
    }
    RESET = "\033[0m"

    def send(self, breach: SLABreachEvent, policy: SLAPolicy, metrics: dict):
        color = self.SEVERITY_COLORS.get(breach.breach_type, "")
        ts = datetime.fromtimestamp(breach.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"\n{color}{'='*64}",
            f"  🚨 SLA BREACH DETECTED — {breach.provider.upper()} / {breach.model}",
            f"{'='*64}{self.RESET}",
            f"  Breach ID   : {breach.breach_id}",
            f"  Type        : {breach.breach_type}",
            f"  Threshold   : {breach.threshold:.1f}",
            f"  Actual      : {breach.actual_value:.1f}",
            f"  Window      : {breach.window_minutes} min",
            f"  Detected at : {ts}",
            f"  --- Current Metrics ---",
            f"  p50={metrics.get('p50_ms','N/A')}ms  p95={metrics.get('p95_ms','N/A')}ms  p99={metrics.get('p99_ms','N/A')}ms",
            f"  Error rate: {metrics.get('error_rate_pct','N/A')}%  Uptime: {metrics.get('uptime_pct','N/A')}%  Samples: {metrics.get('sample_count','N/A')}",
            f"{'='*64}\n",
        ]
        print("\n".join(lines))
        logger.warning("SLA BREACH: %s/%s [%s] actual=%.1f threshold=%.1f",
                       breach.provider, breach.model, breach.breach_type,
                       breach.actual_value, breach.threshold)


class WebhookAlertChannel(AlertChannel):
    """Posts breach JSON to a webhook URL (Slack-compatible)."""

    def __init__(self, webhook_url: str, timeout: int = 10):
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, breach: SLABreachEvent, policy: SLAPolicy, metrics: dict):
        payload = {
            "text": (
                f"🚨 *SLA Breach* — `{breach.provider}/{breach.model}`\n"
                f"*Type:* {breach.breach_type}\n"
                f"*Actual:* {breach.actual_value:.1f} vs threshold {breach.threshold:.1f}\n"
                f"*Window:* {breach.window_minutes}min | "
                f"p50={metrics.get('p50_ms')}ms p95={metrics.get('p95_ms')}ms "
                f"err={metrics.get('error_rate_pct')}%"
            )
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                logger.info("Webhook alert sent, status=%s", resp.status)
        except Exception as exc:
            logger.error("Webhook alert failed: %s", exc)


class EmailAlertChannel(AlertChannel):
    """Sends breach alert emails via SMTP."""

    def __init__(self, smtp_host: str, smtp_port: int, username: str,
                 password: str, from_addr: str, to_addrs: list):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    def send(self, breach: SLABreachEvent, policy: SLAPolicy, metrics: dict):
        ts = datetime.fromtimestamp(breach.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        subject = f"[SLA BREACH] {breach.provider}/{breach.model} — {breach.breach_type}"
        body = f"""
SLA BREACH ALERT
================

Provider  : {breach.provider}
Model     : {breach.model}
Breach    : {breach.breach_type}
Threshold : {breach.threshold:.2f}
Actual    : {breach.actual_value:.2f}
Window    : {breach.window_minutes} minutes
Detected  : {ts}
Breach ID : {breach.breach_id}

CURRENT METRICS ({breach.window_minutes}min window)
---------------------------------------------
p50  : {metrics.get('p50_ms', 'N/A')} ms
p95  : {metrics.get('p95_ms', 'N/A')} ms
p99  : {metrics.get('p99_ms', 'N/A')} ms
Mean : {metrics.get('mean_ms', 'N/A')} ms
Error rate : {metrics.get('error_rate_pct', 'N/A')} %
Uptime     : {metrics.get('uptime_pct', 'N/A')} %
Samples    : {metrics.get('sample_count', 'N/A')}

---
AI Model Latency SLA Tracker | TAD Build System
        """.strip()

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            logger.info("Email alert sent for breach %s", breach.breach_id)
        except Exception as exc:
            logger.error("Email alert failed: %s", exc)


# ---------------------------------------------------------------------------
# SLA Breach Detector
# ---------------------------------------------------------------------------

class SLABreachDetector:
    """Evaluates ProviderStats against SLAPolicy and fires alerts."""

    def __init__(self, channels: list):
        self.channels = channels

    def _breach_id(self, provider: str, model: str, breach_type: str) -> str:
        raw = f"{provider}:{model}:{breach_type}:{int(time.time() // 60)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _cooldown_ok(self, stats: ProviderStats, breach_type: str, cooldown_s: int) -> bool:
        last = stats.last_alert_times.get(breach_type, 0)
        return (time.time() - last) >= cooldown_s

    def _fire(self, breach: SLABreachEvent, policy: SLAPolicy,
              metrics: dict, stats: ProviderStats):
        stats.breach_history.append(breach)
        stats.last_alert_times[breach.breach_type] = time.time()
        breach.alerted = True
        for ch in self.channels:
            try:
                ch.send(breach, policy, metrics)
            except Exception as exc:
                logger.error("Alert channel %s failed: %s", type(ch).__name__, exc)

    def evaluate(self, stats: ProviderStats, policy: SLAPolicy):
        metrics = stats.get_metrics(policy.rolling_window_minutes)
        if not metrics or metrics["sample_count"] < 5:
            return  # not enough data yet

        checks = [
            ("p50_exceeded", metrics.get("p50_ms"), policy.max_p50_ms),
            ("p95_exceeded", metrics.get("p95_ms"), policy.max_p95_ms),
            ("p99_exceeded", metrics.get("p99_ms"), policy.max_p99_ms),
        ]
        for breach_type, actual, threshold in checks:
            if actual is not None and actual > threshold:
                if self._cooldown_ok(stats, breach_type, policy.alert_cooldown_seconds):
                    breach = SLABreachEvent(
                        breach_id=self._breach_id(stats.provider, stats.model, breach_type),
                        provider=stats.provider,
                        model=stats.model,
                        breach_type=breach_type,
                        threshold=threshold,
                        actual_value=actual,
                        timestamp=time.time(),
                        window_minutes=policy.rolling_window_minutes,
                    )
                    self._fire(breach, policy, metrics, stats)

        err_rate = metrics.get("error_rate_pct", 0)
        if err_rate > policy.max_error_rate_pct:
            if self._cooldown_ok(stats, "error_rate", policy.alert_cooldown_seconds):
                breach = SLABreachEvent(
                    breach_id=self._breach_id(stats.provider, stats.model, "error_rate"),
                    provider=stats.provider,
                    model=stats.model,
                    breach_type="error_rate",
                    threshold=policy.max_error_rate_pct,
                    actual_value=err_rate,
                    timestamp=time.time(),
                    window_minutes=policy.rolling_window_minutes,
                )
                self._fire(breach, policy, metrics, stats)

        uptime = metrics.get("uptime_pct", 100)
        if uptime < policy.min_uptime_pct:
            if self._cooldown_ok(stats, "uptime", policy.alert_cooldown_seconds):
                breach = SLABreachEvent(
                    breach_id=self._breach_id(stats.provider, stats.model, "uptime"),
                    provider=stats.provider,
                    model=stats.model,
                    breach_type="uptime",
                    threshold=policy.min_uptime_pct,
                    actual_value=uptime,
                    timestamp=time.time(),
                    window_minutes=policy.rolling_window_minutes,
                )
                self._fire(breach, policy, metrics, stats)


# ---------------------------------------------------------------------------
# Probe implementations (real HTTP calls)
# ---------------------------------------------------------------------------

class ProviderProbe:
    """Base probe. Subclasses call actual API endpoints."""

    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key
        self.timeout = timeout

    def probe(self) -> LatencySample:
        raise NotImplementedError

    def _http_post(self, url: str, headers: dict, body: dict) -> tuple:
        """Returns (status_code, latency_ms, response_body_str)."""
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                latency_ms = (time.perf_counter() - start) * 1000
                body_bytes = resp.read()
                return resp.status, latency_ms, body_bytes.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return exc.code, latency_ms, str(exc.reason)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return None, latency_ms, str(exc)


class OpenAIProbe(ProviderProbe):
    """Probes OpenAI chat completions endpoint."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", timeout: int = 30):
        super().__init__(api_key, timeout)
        self.model = model

    def probe(self) -> LatencySample:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "Reply with exactly: ok"}],
            "max_tokens": 5,
        }
        status, latency_ms, body_str = self._http_post(url, headers, payload)
        success = status == 200
        token_count = None
        if success:
            try:
                resp_json = json.loads(body_str)
                usage = resp_json.get("usage", {})
                token_count = usage.get("total_tokens")
            except Exception:
                pass
        return LatencySample(
            timestamp=time.time(),
            latency_ms=latency_ms,
            success=success,
            status_code=status,
            error_msg=None if success else body_str[:200],
            token_count=token_count,
        )


class AnthropicProbe(ProviderProbe):
    """Probes Anthropic messages endpoint."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307", timeout: int = 30):
        super().__init__(api_key, timeout)
        self.model = model

    def probe(self) -> LatencySample:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "Reply: ok"}],
        }
        status, latency_ms, body_str = self._http_post(url, headers, payload)
        success = status == 200
        token_count = None
        if success:
            try:
                resp_json = json.loads(body_str)
                usage = resp_json.get("usage", {})
                token_count = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            except Exception:
                pass
        return LatencySample(
            timestamp=time.time(),
            latency_ms=latency_ms,
            success=success,
            status_code=status,
            error_msg=None if success else body_str[:200],
            token_count=token_count,
        )


class CohereProbe(ProviderProbe):
    """Probes Cohere chat endpoint."""

    def __init__(self, api_key: str, model: str = "command-r", timeout: int = 30):
        super().__init__(api_key, timeout)
        self.model = model

    def probe(self) -> LatencySample:
        url = "https://api.cohere.ai/v1/chat"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "message": "Reply: ok",
            "max_tokens": 5,
        }
        status, latency_ms, body_str = self._http_post(url, headers, payload)
        success = status == 200
        return LatencySample(
            timestamp=time.time(),
            latency_ms=latency_ms,
            success=success,
            status_code=status,
            error_msg=None if success else body_str[:200],
        )


class SimulatedProbe(ProviderProbe):
    """
    Simulated probe for demo/testing — no real API key needed.
    Generates realistic latency distributions with occasional spikes and errors.
    """

    def __init__(self, provider: str, model: str, base_latency_ms: float = 600.0,
                 error_rate: float = 0.02, spike_prob: float = 0.05):
        super().__init__("simulated", timeout=30)
        self.provider = provider
        self.model = model
        self.base_latency_ms = base_latency_ms
        self.error_rate = error_rate
        self.spike_prob = spike_prob
        self._call_count = 0

    def probe(self) -> LatencySample:
        import random
        self._call_count += 1

        # Simulate degraded period every ~50 calls
        degraded = (self._call_count % 50) in range(40, 50)

        is_error = random.random() < (self.error_rate * (3 if degraded else 1))
        if is_error:
            latency = random.uniform(50, 200)
            return LatencySample(
                timestamp=time.time(),
                latency_ms=latency,
                success=False,
                status_code=random.choice([429, 500, 503]),
                error_msg="Simulated error",
            )

        is_spike = random.random() < self.spike_prob or degraded
        if is_spike:
            latency = self.base_latency_ms * random.uniform(4, 12)
        else:
            # Log-normal distribution for realistic latency
            import math
            mu = math.log(self.base_latency_ms)
            sigma = 0.4
            latency = random.lognormvariate(mu, sigma)

        latency = max(50.0, latency)
        return LatencySample(
            timestamp=time.time(),
            latency_ms=round(latency, 2),
            success=True,
            status_code=200,
            token_count=random.randint(5, 15),
        )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class SLADataStore:
    """Persists breach history and metrics snapshots to disk."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.breach_log = data_dir / "breach_log.jsonl"
        self.metrics_log = data_dir / "metrics_snapshots.jsonl"

    def record_breach(self, breach: SLABreachEvent):
        entry = asdict(breach)
        entry["iso_time"] = datetime.fromtimestamp(
            breach.timestamp, tz=timezone.utc).isoformat()
        try:
            with open(self.breach_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.error("Failed to write breach log: %s", exc)

    def record_metrics_snapshot(self, provider: str, model: str, metrics: dict):
        entry = {
            "provider": provider,
            "model": model,
            "timestamp": time.time(),
            "iso_time": datetime.now(tz=timezone.utc).isoformat(),
            **metrics,
        }
        try:
            with open(self.metrics_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.error("Failed to write metrics snapshot: %s", exc)

    def load_breach_history(self, since_hours: int = 24) -> list:
        cutoff = time.time() - (since_hours * 3600)
        results = []
        if not self.breach_log.exists():
            return results
        try:
            with open(self.breach_log, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("timestamp", 0) >= cutoff:
                        results.append(entry)
        except Exception as exc:
            logger.error("Failed to load breach history: %s", exc)
        return results

    def generate_report(self, since_hours: int = 24) -> str:
        breaches = self.load_breach_history(since_hours)
        lines = [
            f"SLA Breach Report — Last {since_hours}h",
            f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total breaches: {len(breaches)}",
            "=" * 60,
        ]
        by_provider: dict = {}
        for b in breaches:
            key = f"{b['provider']}/{b['model']}"
            by_provider.setdefault(key, []).append(b)

        for key, events in sorted(by_provider.items()):
            lines.append(f"\n{key} — {len(events)} breach(es)")
            breach_types: dict = {}
            for e in events:
                breach_types.setdefault(e["breach_type"], 0)
                breach_types[e["breach_type"]] += 1
            for btype, count in breach_types.items():
                lines.append(f"  {btype}: {count}x")

        if not breaches:
            lines.append("\nNo breaches in this window. ✅")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main Tracker Orchestrator
# ---------------------------------------------------------------------------

class SLATracker:
    """
    Central orchestrator: manages probes, collects samples,
    evaluates SLA, fires alerts, persists data.
    """

    def __init__(
        self,
        policies: list = None,
        channels: list = None,
        probe_interval_seconds: int = 60,
        data_dir: Path = DATA_DIR,
    ):
        self.policies: dict = {p.key: p for p in (policies or DEFAULT_SLA_POLICIES)}
        self.channels = channels or [ConsoleAlertChannel()]
        self.probe_interval = probe_interval_seconds
        self.detector = SLABreachDetector(self.channels)
        self.store = SLADataStore(data_dir)
        self.provider_stats: dict = {}   # key -> ProviderStats
        self.probes: dict = {}           # key -> ProviderProbe
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._threads: list = []

        logger.info("SLATracker initialised with %d policies, %d alert channels",
                    len(self.policies), len(self.channels))

    def register_probe(self, provider: str, model: str, probe: ProviderProbe):
        key = f"{provider}:{model}"
        with self._lock:
            self.probes[key] = probe
            if key not in self.provider_stats:
                self.provider_stats[key] = ProviderStats(provider=provider, model=model)
            if key not in self.policies:
                # auto-create a default policy if none exists
                self.policies[key] = SLAPolicy(provider=provider, model=model)
        logger.info("Probe registered: %s", key)

    def _probe_loop(self, key: str):
        """Background thread: probe → record → evaluate → persist."""
        logger.info("Probe thread started: %s", key)
        while not self._stop_event.is_set():
            probe = self.probes.get(key)
            if probe is None:
                break
            try:
                sample = probe.probe()
                with self._lock:
                    stats = self.provider_stats[key]
                    policy = self.policies[key]
                    stats.add_sample(sample)
                    metrics = stats.get_metrics(policy.rolling_window_minutes)

                # Evaluate outside lock to avoid blocking
                self.detector.evaluate(stats, policy)

                # Persist metrics snapshot every 5 probes
                if len(stats.samples) % 5 == 0:
                    self.store.record_metrics_snapshot(
                        stats.provider, stats.model, metrics)

                # Persist any new breach events
                for breach in stats.breach_history:
                    if not getattr(breach, "_persisted", False):
                        self.store.record_breach(breach)
                        breach._persisted = True

                status = "✓" if sample.success else "✗"
                logger.info("[%s] %s  latency=%.0fms  status=%s",
                            key, status, sample.latency_ms, sample.status_code)

            except Exception as exc:
                logger.error("Probe error for %s: %s\n%s",
                             key, exc, traceback.format_exc())

            self._stop_event.wait(timeout=self.probe_interval)

        logger.info("Probe thread stopped: %s", key)

    def start(self):
        """Launch all probe threads."""
        with self._lock:
            keys = list(self.probes.keys())
        for key in keys:
            t = threading.Thread(target=self._probe_loop, args=(key,),
                                 daemon=True, name=f"probe-{key}")
            t.start()
            self._threads.append(t)
        logger.info("SLATracker started — %d probes running", len(keys))

    def stop(self):
        """Signal all probe threads to stop."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5)
        logger.info("SLATracker stopped.")

    def snapshot(self) -> dict:
        """Return current metrics for all tracked providers."""
        result = {}
        with self._lock:
            for key, stats in self.provider_stats.items():
                policy = self.policies.get(key)
                if policy:
                    metrics = stats.get_metrics(policy.rolling_window_minutes)
                    result[key] = {
                        "metrics": metrics,
                        "breach_count_24h": len([
                            b for b in stats.breach_history
                            if b.timestamp >= time.time() - 86400
                        ]),
                        "policy": {
                            "max_p50_ms": policy.max_p50_ms,
                            "max_p95_ms": policy.max_p95_ms,
                            "max_p99_ms": policy.max_p99_ms,
                            "max_error_rate_pct": policy.max_error_rate_pct,
                        },
                    }
        return result

    def print_dashboard(self):
        """Print a formatted live metrics table."""
        snap = self.snapshot()
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"\n{'─'*80}",
            f"  AI Model SLA Dashboard — {now}",
            f"{'─'*80}",
            f"  {'Provider/Model':<35} {'p50':>7} {'p95':>7} {'p99':>7} {'Err%':>6} {'Up%':>6} {'N':>5}",
            f"  {'─'*35} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*6} {'─'*5}",
        ]
        for key, data in sorted(snap.items()):
            m = data["metrics"]
            if not m:
                continue
            breaches = data["breach_count_24h"]
            flag = " 🚨" if breaches > 0 else " ✅"
            lines.append(
                f"  {key:<35} "
                f"{str(m.get('p50_ms','—')):>7} "
                f"{str(m.get('p95_ms','—')):>7} "
                f"{str(m.get('p99_ms','—')):>7} "
                f"{str(m.get('error_rate_pct','—')):>6} "
                f"{str(m.get('uptime_pct','—')):>6} "
                f"{str(m.get('sample_count','0')):>5}"
                f"{flag}"
            )
        lines.append(f"{'─'*80}\n")
        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_config(config_path: Path = DATA_DIR / "sla_config.json") -> dict:
    """
    Load tracker config from JSON. Creates a default config if missing.
    """
    default_config = {
        "probe_interval_seconds": 60,
        "demo_mode": True,
        "alerts": {
            "console": True,
            "webhook_url": "",
            "email": {
                "enabled": False,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_addr": "",
                "to_addrs": [],
            },
        },
        "providers": {
            "openai": {
                "api_key": "",
                "models": ["gpt-4o-mini"],
            },
            "anthropic": {
                "api_key": "",
                "models": ["claude-3-haiku-20240307"],
            },
            "cohere": {
                "api_key": "",
                "models": ["command-r"],
            },
        },
    }

    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
        logger.info("Created default config at %s", config_path)
        return default_config

    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        logger.info("Loaded config from %s", config_path)
        return cfg
    except Exception as exc:
        logger.warning("Failed to parse config %s: %s — using defaults", config_path, exc)
        return default_config


def build_tracker_from_config(cfg: dict) -> SLATracker:
    """Build and configure a SLATracker from a config dict."""

    # Alert channels
    channels = []
    alert_cfg = cfg.get("alerts", {})

    if alert_cfg.get("console", True):
        channels.append(ConsoleAlertChannel())

    webhook_url = alert_cfg.get("webhook_url", "")
    if webhook_url:
        channels.append(WebhookAlertChannel(webhook_url))

    email_cfg = alert_cfg.get("email", {})
    if email_cfg.get("enabled") and email_cfg.get("username"):
        channels.append(EmailAlertChannel(
            smtp_host=email_cfg["smtp_host"],
            smtp_port=email_cfg["smtp_port"],
            username=email_cfg["username"],
            password=email_cfg["password"],
            from_addr=email_cfg["from_addr"],
            to_addrs=email_cfg["to_addrs"],
        ))

    tracker = SLATracker(
        channels=channels,
        probe_interval_seconds=cfg.get("probe_interval_seconds", 60),
    )

    demo_mode = cfg.get("demo_mode", True)

    if demo_mode:
        # Register simulated probes for demo/testing
        sim_providers = [
            ("openai",    "gpt-4o",           600,  0.01, 0.04),
            ("openai",    "gpt-4o-mini",       400,  0.015, 0.05),
            ("anthropic", "claude-3-5-sonnet", 900,  0.008, 0.03),
            ("anthropic", "claude-3-haiku",    500,  0.02,  0.06),
            ("cohere",    "command-r-plus",    1100, 0.012, 0.04),
            ("google",    "gemini-1.5-flash",  650,  0.018, 0.07),
            ("mistral",   "mistral-large",     950,  0.01,  0.03),
        ]
        for provider, model, base_ms, err_rate, spike_prob in sim_providers:
            probe = SimulatedProbe(provider, model,
                                   base_latency_ms=base_ms,
                                   error_rate=err_rate,
                                   spike_prob=spike_prob)
            tracker.register_probe(provider, model, probe)
        logger.info("Demo mode: %d simulated probes registered", len(sim_providers))
    else:
        # Real API probes
        providers_cfg = cfg.get("providers", {})

        openai_key = providers_cfg.get("openai", {}).get("api_key", "")
        if openai_key:
            for model in providers_cfg["openai"].get("models", []):
                tracker.register_probe("openai", model, OpenAIProbe(openai_key, model))

        anthropic_key = providers_cfg.get("anthropic", {}).get("api_key", "")
        if anthropic_key:
            for model in providers_cfg["anthropic"].get("models", []):
                tracker.register_probe("anthropic", model, AnthropicProbe(anthropic_key, model))

        cohere_key = providers_cfg.get("cohere", {}).get("api_key", "")
        if cohere_key:
            for model in providers_cfg["cohere"].get("models", []):
                tracker.register_probe("cohere", model, CohereProbe(cohere_key, model))

    return tracker


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║       AI Model Latency SLA Tracker & Breach Alert System        ║
║                  TAD Build Agent — 2026-06-28                   ║
╚══════════════════════════════════════════════════════════════════╝
""")

    cfg = load_config()
    tracker = build_tracker_from_config(cfg)

    probe_interval = cfg.get("probe_interval_seconds", 60)
    demo_mode = cfg.get("demo_mode", True)

    if demo_mode:
        # In demo mode use a shorter interval so results appear quickly
        tracker.probe_interval = 5
        logger.info("Demo mode active — probe interval reduced to 5s for fast feedback")
        print("  Mode       : DEMO (simulated probes, no real API keys needed)")
    else:
        print(f"  Mode       : LIVE (real API calls every {probe_interval}s)")

    print(f"  Policies   : {len(tracker.policies)} SLA policies loaded")
    print(f"  Channels   : {[type(c).__name__ for c in tracker.channels]}")
    print(f"  Log file   : {LOG_FILE}")
    print(f"  Data dir   : {DATA_DIR}")
    print("\n  Press Ctrl+C to stop.\n")

    tracker.start()

    # Dashboard refresh loop
    dashboard_interval = 15 if demo_mode else 30
    next_dashboard = time.time() + dashboard_interval

    try:
        while True:
            now = time.time()
            if now >= next_dashboard:
                tracker.print_dashboard()
                # Print 24h report every hour
                if int(now) % 3600 < dashboard_interval:
                    report = tracker.store.generate_report(since_hours=24)
                    print(report)
                next_dashboard = now + dashboard_interval
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nShutting down SLA Tracker...")
        tracker.stop()

        # Final dashboard and report
        tracker.print_dashboard()
        report = tracker.store.generate_report(since_hours=1)
        print(report)

        report_path = DATA_DIR / f"final_report_{int(time.time())}.txt"
        report_path.write_text(report, encoding="utf-8")
        print(f"\n  Final report saved to: {report_path}")
        print("  Goodbye.\n")


if __name__ == "__main__":
    main()