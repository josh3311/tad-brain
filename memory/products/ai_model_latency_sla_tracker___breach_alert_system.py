"""
AI Model Latency SLA Tracker & Breach Alert System
===================================================
Production-grade monitoring system that tracks latency SLAs across multiple
AI API providers (OpenAI, Anthropic, Cohere, Google, Mistral), detects
breaches in real time, fires alerts via multiple channels, and generates
executive-ready SLA compliance reports.

Author: TAD Build Agent
Date: 2026-06-28
Revenue model: B2B SaaS — $49/mo (Starter), $199/mo (Pro), $799/mo (Enterprise)
"""

import os
import sys
import json
import time
import uuid
import logging
import asyncio
import hashlib
import smtplib
import statistics
import threading
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict, deque
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum

import urllib.request
import urllib.error
import urllib.parse

# ── Directory bootstrap ──────────────────────────────────────────────────────
BASE_DIR = Path("memory/products/ai_latency_sla_tracker")
LOGS_DIR = BASE_DIR / "logs"
REPORTS_DIR = BASE_DIR / "reports"
ALERTS_DIR = BASE_DIR / "alerts"
METRICS_DIR = BASE_DIR / "metrics"
CONFIG_PATH = BASE_DIR / "config.json"
BREACHES_DB = BASE_DIR / "breaches.jsonl"
METRICS_DB = BASE_DIR / "metrics_history.jsonl"

for d in [BASE_DIR, LOGS_DIR, REPORTS_DIR, ALERTS_DIR, METRICS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Logging ──────────────────────────────────────────────────────────────────
log_file = LOGS_DIR / f"sla_tracker_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("SLATracker")


# ── Enums & Constants ────────────────────────────────────────────────────────
class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    COHERE = "cohere"
    GOOGLE = "google"
    MISTRAL = "mistral"
    MOCK = "mock"  # for testing without real API keys


class SeverityLevel(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    DOWN = "down"


class AlertChannel(str, Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"
    CONSOLE = "console"
    FILE = "file"


# SLA thresholds in milliseconds — sensible defaults, fully configurable
DEFAULT_SLA_THRESHOLDS = {
    Provider.OPENAI: {
        "p50_ms": 800,
        "p95_ms": 3000,
        "p99_ms": 8000,
        "error_rate_pct": 1.0,
        "availability_pct": 99.5,
    },
    Provider.ANTHROPIC: {
        "p50_ms": 1200,
        "p95_ms": 5000,
        "p99_ms": 12000,
        "error_rate_pct": 1.0,
        "availability_pct": 99.5,
    },
    Provider.COHERE: {
        "p50_ms": 600,
        "p95_ms": 2500,
        "p99_ms": 6000,
        "error_rate_pct": 2.0,
        "availability_pct": 99.0,
    },
    Provider.GOOGLE: {
        "p50_ms": 700,
        "p95_ms": 2800,
        "p99_ms": 7000,
        "error_rate_pct": 1.0,
        "availability_pct": 99.5,
    },
    Provider.MISTRAL: {
        "p50_ms": 900,
        "p95_ms": 3500,
        "p99_ms": 9000,
        "error_rate_pct": 2.0,
        "availability_pct": 99.0,
    },
    Provider.MOCK: {
        "p50_ms": 500,
        "p95_ms": 1500,
        "p99_ms": 3000,
        "error_rate_pct": 1.0,
        "availability_pct": 99.9,
    },
}

PROVIDER_PROBE_URLS = {
    Provider.OPENAI: "https://api.openai.com/v1/models",
    Provider.ANTHROPIC: "https://api.anthropic.com/v1/models",
    Provider.COHERE: "https://api.cohere.ai/v1/models",
    Provider.GOOGLE: "https://generativelanguage.googleapis.com/v1/models",
    Provider.MISTRAL: "https://api.mistral.ai/v1/models",
}


# ── Data Classes ─────────────────────────────────────────────────────────────
@dataclass
class LatencyMeasurement:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    provider: str = ""
    model: str = ""
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    latency_ms: float = 0.0
    success: bool = True
    http_status: int = 200
    error_msg: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    probe_type: str = "health"  # health | inference | custom

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SLABreach:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    provider: str = ""
    breach_type: str = ""  # p50 | p95 | p99 | error_rate | availability | down
    severity: str = SeverityLevel.WARNING.value
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    measured_value: float = 0.0
    threshold_value: float = 0.0
    window_minutes: int = 5
    alert_sent: bool = False
    resolved: bool = False
    resolved_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def human_summary(self) -> str:
        return (
            f"[{self.severity.upper()}] {self.provider} SLA BREACH — {self.breach_type}: "
            f"measured={self.measured_value:.1f} vs threshold={self.threshold_value:.1f} "
            f"(window={self.window_minutes}min) @ {self.timestamp_utc}"
        )


@dataclass
class ProviderStats:
    provider: str = ""
    window_minutes: int = 5
    sample_count: int = 0
    success_count: int = 0
    error_count: int = 0
    latencies_ms: list = field(default_factory=list)
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    mean_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    error_rate_pct: float = 0.0
    availability_pct: float = 100.0
    status: str = SeverityLevel.OK.value
    computed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("latencies_ms", None)  # don't bloat JSON with raw samples
        return d


# ── Configuration Manager ────────────────────────────────────────────────────
class ConfigManager:
    """
    Loads, validates, and hot-reloads configuration from config.json.
    Falls back to sensible defaults if the file is missing or malformed.
    """

    DEFAULT_CONFIG = {
        "version": "1.0",
        "probe_interval_seconds": 60,
        "measurement_window_minutes": 5,
        "providers_enabled": [Provider.MOCK.value],
        "api_keys": {},
        "sla_thresholds": {
            k.value: v for k, v in DEFAULT_SLA_THRESHOLDS.items()
        },
        "alert_channels": [AlertChannel.CONSOLE.value, AlertChannel.FILE.value],
        "email": {
            "enabled": False,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "",
            "password": "",
            "from_addr": "",
            "to_addrs": [],
        },
        "webhooks": [],
        "report_schedule_hours": 24,
        "consecutive_breach_before_alert": 2,
        "cooldown_minutes_between_alerts": 15,
    }

    def __init__(self):
        self._config = {}
        self._load()

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r") as f:
                    loaded = json.load(f)
                self._config = {**self.DEFAULT_CONFIG, **loaded}
                logger.info("Configuration loaded from %s", CONFIG_PATH)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Config load failed (%s) — using defaults", e)
                self._config = dict(self.DEFAULT_CONFIG)
        else:
            self._config = dict(self.DEFAULT_CONFIG)
            self._save()
            logger.info("Default config written to %s", CONFIG_PATH)

    def _save(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self._config, f, indent=2)
        except OSError as e:
            logger.error("Config save failed: %s", e)

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def get_threshold(self, provider: str, metric: str) -> float:
        thresholds = self._config.get("sla_thresholds", {})
        provider_t = thresholds.get(
            provider, DEFAULT_SLA_THRESHOLDS.get(Provider.MOCK, {})
        )
        return provider_t.get(metric, 9999)

    def reload(self):
        self._load()


# ── Latency Probe Engine ─────────────────────────────────────────────────────
class LatencyProbe:
    """
    Fires HTTP probes at each enabled provider, measures round-trip latency,
    and returns a LatencyMeasurement. Uses urllib only — no extra deps.
    """

    TIMEOUT_SECONDS = 15

    def __init__(self, config: ConfigManager):
        self.config = config

    def probe_provider(self, provider: str) -> LatencyMeasurement:
        """Route to the correct probe method by provider."""
        if provider == Provider.MOCK.value:
            return self._mock_probe(provider)
        return self._http_probe(provider)

    def _http_probe(self, provider: str) -> LatencyMeasurement:
        """
        Real HTTP probe. For providers that require auth we send the API key
        in the appropriate header. A 401/403 still gives us latency data —
        we flag it as an auth error but record the round-trip time.
        """
        provider_enum = Provider(provider)
        url = PROVIDER_PROBE_URLS.get(provider_enum, "")
        api_keys = self.config.get("api_keys", {})
        key = api_keys.get(provider, "")

        headers = {"User-Agent": "TAD-SLATracker/1.0"}
        if provider == Provider.OPENAI.value and key:
            headers["Authorization"] = f"Bearer {key}"
        elif provider == Provider.ANTHROPIC.value and key:
            headers["x-api-key"] = key
            headers["anthropic-version"] = "2023-06-01"
        elif provider in (Provider.COHERE.value, Provider.MISTRAL.value) and key:
            headers["Authorization"] = f"Bearer {key}"
        elif provider == Provider.GOOGLE.value and key:
            url = f"{url}?key={key}"

        m = LatencyMeasurement(provider=provider, model="probe", probe_type="health")
        start = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as resp:
                _ = resp.read()
                m.http_status = resp.status
                m.latency_ms = (time.perf_counter() - start) * 1000
                m.success = resp.status < 400
        except urllib.error.HTTPError as e:
            m.latency_ms = (time.perf_counter() - start) * 1000
            m.http_status = e.code
            # 401/403 = auth issue but endpoint is reachable — still latency data
            m.success = e.code not in (500, 502, 503, 504)
            m.error_msg = f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            m.latency_ms = (time.perf_counter() - start) * 1000
            m.success = False
            m.http_status = 0
            m.error_msg = str(e.reason)
        except Exception as e:
            m.latency_ms = (time.perf_counter() - start) * 1000
            m.success = False
            m.error_msg = str(e)

        return m

    def _mock_probe(self, provider: str) -> LatencyMeasurement:
        """
        Simulates realistic latency measurements with occasional spikes and errors.
        Used for demo, CI, and development without spending real API budget.
        """
        import random

        m = LatencyMeasurement(provider=provider, model="mock-gpt-4", probe_type="health")

        # Simulate realistic bimodal distribution: fast baseline + occasional spikes
        base = random.gauss(400, 80)
        spike = random.random() < 0.08  # 8% spike probability
        if spike:
            base += random.uniform(2000, 8000)

        error = random.random() < 0.03  # 3% error rate
        if error:
            m.success = False
            m.http_status = random.choice([500, 503, 429])
            m.error_msg = f"Simulated error {m.http_status}"
            base *= 1.5

        m.latency_ms = max(10, base)
        m.http_status = m.http_status if not m.success else 200
        time.sleep(m.latency_ms / 1000 * 0.05)  # minimal sleep, don't block for full sim
        return m


# ── Metrics Store ────────────────────────────────────────────────────────────
class MetricsStore:
    """
    Rolling in-memory buffer (per provider) + persistent JSONL append log.
    Provides percentile calculations over configurable time windows.
    """

    MAX_IN_MEMORY = 1000  # per provider

    def __init__(self, config: ConfigManager):
        self.config = config
        self._lock = threading.Lock()
        # {provider: deque of LatencyMeasurement}
        self._buffers: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.MAX_IN_MEMORY)
        )

    def record(self, measurement: LatencyMeasurement):
        with self._lock:
            self._buffers[measurement.provider].append(measurement)
        self._persist(measurement)

    def _persist(self, m: LatencyMeasurement):
        try:
            with open(METRICS_DB, "a") as f:
                f.write(json.dumps(m.to_dict()) + "\n")
        except OSError as e:
            logger.error("Metrics persist failed: %s", e)

    def get_stats(self, provider: str, window_minutes: int = 5) -> ProviderStats:
        """Compute SLA-relevant stats over the last N minutes."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stats = ProviderStats(provider=provider, window_minutes=window_minutes)

        with self._lock:
            buf = list(self._buffers.get(provider, []))

        recent = [
            m for m in buf
            if datetime.fromisoformat(m.timestamp_utc) >= cutoff
        ]

        if not recent:
            stats.status = SeverityLevel.DOWN.value
            return stats

        stats.sample_count = len(recent)
        stats.success_count = sum(1 for m in recent if m.success)
        stats.error_count = stats.sample_count - stats.success_count
        stats.latencies_ms = [m.latency_ms for m in recent if m.success]
        stats.error_rate_pct = (stats.error_count / stats.sample_count) * 100
        stats.availability_pct = (stats.success_count / stats.sample_count) * 100

        if stats.latencies_ms:
            sorted_lat = sorted(stats.latencies_ms)
            n = len(sorted_lat)
            stats.p50_ms = sorted_lat[int(n * 0.50)]
            stats.p95_ms = sorted_lat[int(n * 0.95)]
            stats.p99_ms = sorted_lat[min(int(n * 0.99), n - 1)]
            stats.mean_ms = statistics.mean(sorted_lat)
            stats.min_ms = sorted_lat[0]
            stats.max_ms = sorted_lat[-1]
        else:
            # All samples errored — latency data unavailable but errors are real
            stats.p50_ms = 0
            stats.p95_ms = 0
            stats.p99_ms = 0

        # Determine overall status
        p95_thresh = self.config.get_threshold(provider, "p95_ms")
        p99_thresh = self.config.get_threshold(provider, "p99_ms")
        err_thresh = self.config.get_threshold(provider, "error_rate_pct")
        avail_thresh = self.config.get_threshold(provider, "availability_pct")

        if stats.availability_pct < avail_thresh * 0.9:
            stats.status = SeverityLevel.DOWN.value
        elif stats.p99_ms > p99_thresh or stats.error_rate_pct > err_thresh * 2:
            stats.status = SeverityLevel.CRITICAL.value
        elif stats.p95_ms > p95_thresh or stats.error_rate_pct > err_thresh:
            stats.status = SeverityLevel.WARNING.value
        else:
            stats.status = SeverityLevel.OK.value

        return stats


# ── SLA Breach Detector ──────────────────────────────────────────────────────
class SLABreachDetector:
    """
    Evaluates provider stats against configured thresholds.
    Tracks consecutive breach counts to avoid alert storms.
    Enforces cooldown between repeated alerts for the same provider+breach_type.
    """

    def __init__(self, config: ConfigManager):
        self.config = config
        # {(provider, breach_type): consecutive_count}
        self._consecutive: dict[tuple, int] = defaultdict(int)
        # {(provider, breach_type): last_alert_time}
        self._last_alert: dict[tuple, datetime] = {}

    def evaluate(self, stats: ProviderStats) -> list[SLABreach]:
        """Return list of new SLABreach objects detected in this evaluation cycle."""
        breaches = []
        p = stats.provider
        cfg = self.config

        checks = [
            ("p50_ms", stats.p50_ms, cfg.get_threshold(p, "p50_ms"), SeverityLevel.WARNING),
            ("p95_ms", stats.p95_ms, cfg.get_threshold(p, "p95_ms"), SeverityLevel.WARNING),
            ("p99_ms", stats.p99_ms, cfg.get_threshold(p, "p99_ms"), SeverityLevel.CRITICAL),
            ("error_rate_pct", stats.error_rate_pct, cfg.get_threshold(p, "error_rate_pct"), SeverityLevel.CRITICAL),
            ("availability_pct", stats.availability_pct, cfg.get_threshold(p, "availability_pct"), SeverityLevel.CRITICAL),
        ]

        for breach_type, measured, threshold, base_severity in checks:
            if stats.sample_count < 3:
                continue  # not enough data

            # Availability: breach when measured < threshold (lower = worse)
            # Everything else: breach when measured > threshold (higher = worse)
            is_breach = (
                measured < threshold
                if breach_type == "availability_pct"
                else measured > threshold
            )

            key = (p, breach_type)
            if is_breach:
                self._consecutive[key] += 1
            else:
                self._consecutive[key] = 0

            min_consecutive = cfg.get("consecutive_breach_before_alert", 2)
            if self._consecutive[key] < min_consecutive:
                continue

            # Cooldown check
            cooldown = timedelta(minutes=cfg.get("cooldown_minutes_between_alerts", 15))
            last = self._last_alert.get(key)
            if last and datetime.now(timezone.utc) - last < cooldown:
                continue

            # Escalate severity for sustained/extreme breaches
            severity = base_severity
            if breach_type == "availability_pct" and measured < threshold * 0.9:
                severity = SeverityLevel.DOWN
            elif breach_type in ("p99_ms", "error_rate_pct") and measured > threshold * 2:
                severity = SeverityLevel.DOWN

            breach = SLABreach(
                provider=p,
                breach_type=breach_type,
                severity=severity.value,
                measured_value=measured,
                threshold_value=threshold,
                window_minutes=stats.window_minutes,
            )
            breaches.append(breach)
            self._last_alert[key] = datetime.now(timezone.utc)

        return breaches

    def persist_breaches(self, breaches: list[SLABreach]):
        for b in breaches:
            try:
                with open(BREACHES_DB, "a") as f:
                    f.write(json.dumps(b.to_dict()) + "\n")
            except OSError as e:
                logger.error("Breach persist failed: %s", e)


# ── Alert Engine ─────────────────────────────────────────────────────────────
class AlertEngine:
    """
    Fires breach alerts over configured channels: console, file, email, webhook.
    Each channel is tried independently — failure on one doesn't block others.
    """

    def __init__(self, config: ConfigManager):
        self.config = config

    def fire(self, breach: SLABreach):
        channels = self.config.get("alert_channels", [AlertChannel.CONSOLE.value])
        logger.warning("ALERT FIRING: %s", breach.human_summary())

        for channel in channels:
            try:
                if channel == AlertChannel.CONSOLE.value:
                    self._console_alert(breach)
                elif channel == AlertChannel.FILE.value:
                    self._file_alert(breach)
                elif channel == AlertChannel.EMAIL.value:
                    self._email_alert(breach)
                elif channel == AlertChannel.WEBHOOK.value:
                    self._webhook_alert(breach)
            except Exception as e:
                logger.error("Alert channel %s failed: %s", channel, e)

        breach.alert_sent = True

    def _console_alert(self, breach: SLABreach):
        severity_icons = {
            SeverityLevel.OK.value: "✅",
            SeverityLevel.WARNING.value: "⚠️",
            SeverityLevel.CRITICAL.value: "🔴",
            SeverityLevel.DOWN.value: "💀",
        }
        icon = severity_icons.get(breach.severity, "❓")
        print(f"\n{'='*70}")
        print(f"{icon}  SLA BREACH ALERT  {icon}")
        print(f"Provider   : {breach.provider.upper()}")
        print(f"Breach Type: {breach.breach_type}")
        print(f"Severity   : {breach.severity.upper()}")
        print(f"Measured   : {breach.measured_value:.2f}")
        print(f"Threshold  : {breach.threshold_value:.2f}")
        print(f"Window     : {breach.window_minutes} min")
        print(f"Time       : {breach.timestamp_utc}")
        print(f"{'='*70}\n")

    def _file_alert(self, breach: SLABreach):
        alert_file = ALERTS_DIR / f"alert_{breach.id}.json"
        with open(alert_file, "w") as f:
            json.dump(breach.to_dict(), f, indent=2)
        logger.info("Alert written to %s", alert_file)

    def _email_alert(self, breach: SLABreach):
        email_cfg = self.config.get("email", {})
        if not email_cfg.get("enabled") or not email_cfg.get("to_addrs"):
            return

        subject = f"[{breach.severity.upper()}] SLA Breach: {breach.provider} — {breach.breach_type}"
        body = f"""
SLA BREACH DETECTED
===================
Provider    : {breach.provider}
Breach Type : {breach.breach_type}
Severity    : {breach.severity.upper()}
Measured    : {breach.measured_value:.2f}
Threshold   : {breach.threshold_value:.2f}
Window      : {breach.window_minutes} minutes
Detected At : {breach.timestamp_utc}
Breach ID   : {breach.id}

Action Required: Investigate {breach.provider} API performance immediately.
Dashboard: http://localhost:8080/dashboard

-- TAD SLA Tracker
        """.strip()

        msg = MIMEMultipart()
        msg["From"] = email_cfg["from_addr"]
        msg["To"] = ", ".join(email_cfg["to_addrs"])
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
                server.starttls()
                server.login(email_cfg["username"], email_cfg["password"])
                server.sendmail(
                    email_cfg["from_addr"],
                    email_cfg["to_addrs"],
                    msg.as_string(),
                )
            logger.info("Email alert sent to %s", email_cfg["to_addrs"])
        except smtplib.SMTPException as e:
            logger.error("SMTP send failed: %s", e)

    def _webhook_alert(self, breach: SLABreach):
        webhooks = self.config.get("webhooks", [])
        payload = json.dumps(
            {
                "event": "sla_breach",
                "breach": breach.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode("utf-8")

        for wh in webhooks:
            url = wh.get("url", "") if isinstance(wh, dict) else str(wh)
            if not url:
                continue
            try:
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "TAD-SLATracker/1.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    logger.info("Webhook %s responded %s", url, resp.status)
            except Exception as e:
                logger.error("Webhook %s failed: %s", url, e)


# ── Report Generator ─────────────────────────────────────────────────────────
class ReportGenerator:
    """
    Produces executive-ready SLA compliance reports in JSON and human-readable
    text formats. Designed to be shared directly with paying customers.
    """

    def __init__(self, config: ConfigManager, metrics_store: MetricsStore):
        self.config = config
        self.metrics = metrics_store

    def generate_report(
        self,
        providers: list[str],
        window_hours: int = 24,
        report_title: str = "SLA Compliance Report",
    ) -> dict:
        now = datetime.now(timezone.utc)
        report_id = hashlib.md5(
            f"{now.isoformat()}{report_title}".encode()
        ).hexdigest()[:8]

        provider_summaries = {}
        overall_health = SeverityLevel.OK.value
        breach_count = 0

        for provider in providers:
            stats = self.metrics.get_stats(provider, window_minutes=window_hours * 60)
            provider_summaries[provider] = stats.to_dict()

            if stats.status in (SeverityLevel.CRITICAL.value, SeverityLevel.DOWN.value):
                overall_health = SeverityLevel.CRITICAL.value
            elif stats.status == SeverityLevel.WARNING.value and overall_health == SeverityLevel.OK.value:
                overall_health = SeverityLevel.WARNING.value

        # Count breaches from persistent store within window
        try:
            cutoff = now - timedelta(hours=window_hours)
            if BREACHES_DB.exists():
                with open(BREACHES_DB, "r") as f:
                    for line in f:
                        try:
                            b = json.loads(line)
                            ts = datetime.fromisoformat(b.get("timestamp_utc", "2000-01-01"))
                            if ts >= cutoff:
                                breach_count += 1
                        except (json.JSONDecodeError, ValueError):
                            pass
        except OSError:
            pass

        report = {
            "report_id": report_id,
            "title": report_title,
            "generated_at": now.isoformat(),
            "window_hours": window_hours,
            "overall_health": overall_health,
            "total_breaches_in_window": breach_count,
            "providers_monitored": len(providers),
            "provider_summaries": provider_summaries,
            "recommendations": self._generate_recommendations(provider_summaries),
        }

        # Persist report
        report_file = REPORTS_DIR / f"report_{report_id}_{now.strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Human-readable version
        txt_file = report_file.with_suffix(".txt")
        self._write_text_report(report, txt_file)

        logger.info("Report %s generated: %s", report_id, report_file)
        return report

    def _generate_recommendations(self, summaries: dict) -> list[str]:
        recs = []
        for provider, s in summaries.items():
            if s.get("availability_pct", 100) < 99.0:
                recs.append(
                    f"{provider}: Add fallback routing — availability below 99% over report window."
                )
            if s.get("p99_ms", 0) > 10000:
                recs.append(
                    f"{provider}: P99 latency exceeds 10s — consider request timeouts & retry with exponential backoff."
                )
            if s.get("error_rate_pct", 0) > 3.0:
                recs.append(
                    f"{provider}: Error rate {s['error_rate_pct']:.1f}% — implement circuit breaker pattern."
                )
        if not recs:
            recs.append("All providers operating within SLA. No action required.")
        return recs

    def _write_text_report(self, report: dict, path: Path):
        lines = [
            "=" * 72,
            f"  {report['title']}",
            f"  Generated : {report['generated_at']}",
            f"  Report ID : {report['report_id']}",
            f"  Window    : {report['window_hours']}h",
            f"  Overall   : {report['overall_health'].upper()}",
            f"  Breaches  : {report['total_breaches_in_window']}",
            "=" * 72,
            "",
        ]
        for provider, s in report["provider_summaries"].items():
            lines += [
                f"  [{s.get('status', 'unknown').upper()}] {provider.upper()}",
                f"    Samples      : {s.get('sample_count', 0)}",
                f"    P50 Latency  : {s.get('p50_ms', 0):.0f}ms",
                f"    P95 Latency  : {s.get('p95_ms', 0):.0f}ms",
                f"    P99 Latency  : {s.get('p99_ms', 0):.0f}ms",
                f"    Error Rate   : {s.get('error_rate_pct', 0):.2f}%",
                f"    Availability : {s.get('availability_pct', 100):.2f}%",
                "",
            ]
        lines += ["Recommendations:", "-" * 40]
        for rec in report.get("recommendations", []):
            lines.append(f"  • {rec}")
        lines += ["", "=" * 72, "Powered by TAD SLA Tracker  |  tad.ai/sla", "=" * 72]

        try:
            path.write_text("\n".join(lines))
        except OSError as e:
            logger.error("Text report write failed: %s", e)


# ── Dashboard Renderer (terminal) ────────────────────────────────────────────
class TerminalDashboard:
    """
    Renders a live status table in the terminal.
    Refreshes every cycle — works over SSH, CI logs, etc.
    """

    STATUS_ICONS = {
        SeverityLevel.OK.value: "✅ OK      ",
        SeverityLevel.WARNING.value: "⚠️  WARNING ",
        SeverityLevel.CRITICAL.value: "🔴 CRITICAL",
        SeverityLevel.DOWN.value: "💀 DOWN    ",
    }

    def render(self, all_stats: dict[str, ProviderStats]):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"\n{'─'*74}")
        print(f"  TAD AI Latency SLA Tracker  |  {ts}")
        print(f"{'─'*74}")
        header = f"{'Provider':<14} {'Status':<14} {'P50ms':>7} {'P95ms':>7} {'P99ms':>7} {'ErrRate':>8} {'Avail':>7} {'Samples':>8}"
        print(header)
        print(f"{'─'*74}")

        for provider, stats in sorted(all_stats.items()):
            icon = self.STATUS_ICONS.get(stats.status, "❓ UNKNOWN ")
            print(
                f"{provider:<14} {icon:<14} {stats.p50_ms:>7.0f} {stats.p95_ms:>7.0f} "
                f"{stats.p99_ms:>7.0f} {stats.error_rate_pct:>7.2f}% {stats.availability_pct:>6.2f}% {stats.sample_count:>8}"
            )

        print(f"{'─'*74}\n")


# ── Main Orchestrator ────────────────────────────────────────────────────────
class SLATrackerOrchestrator:
    """
    Ties all components together. Runs the probe loop, evaluates breaches,
    fires alerts, and schedules reports. Thread-safe.
    """

    def __init__(self, config: ConfigManager):
        self.config = config
        self.probe = LatencyProbe(config)
        self.metrics = MetricsStore(config)
        self.detector = SLABreachDetector(config)
        self.alerter = AlertEngine(config)
        self.reporter = ReportGenerator(config, self.metrics)
        self.dashboard = TerminalDashboard()
        self._running = False
        self._cycle = 0
        self._last_report = datetime.now(timezone.utc)

    def probe_all_providers(self) -> dict[str, LatencyMeasurement]:
        """Fire probes at all enabled providers concurrently using threads."""
        providers = self.config.get("providers_enabled", [Provider.MOCK.value])
        results = {}

        def probe_one(p: str):
            try:
                m = self.probe.probe_provider(p)
                self.metrics.record(m)
                results[p] = m
                status = "OK" if m.success else f"ERROR({m.error_msg[:40]})"
                logger.info("Probe %s → %.0fms [%s]", p, m.latency_ms, status)
            except Exception as e:
                logger.error("Probe %s crashed: %s", p, traceback.format_exc())

        threads = [threading.Thread(target=probe_one, args=(p,), daemon=True) for p in providers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        return results

    def evaluate_slas(self) -> dict[str, ProviderStats]:
        providers = self.config.get("providers_enabled", [])
        window = self.config.get("measurement_window_minutes", 5)
        all_stats = {}

        for provider in providers:
            try:
                stats = self.metrics.get_stats(provider, window_minutes=window)
                all_stats[provider] = stats
                breaches = self.detector.evaluate(stats)
                if breaches:
                    self.detector.persist_breaches(breaches)
                    for breach in breaches:
                        self.alerter.fire(breach)
                    logger.warning(
                        "%d SLA breach(es) detected for %s", len(breaches), provider
                    )
            except Exception as e:
                logger.error("SLA eval failed for %s: %s", provider, e)

        return all_stats

    def _maybe_generate_report(self, all_stats: dict[str, ProviderStats]):
        schedule_hours = self.config.get("report_schedule_hours", 24)
        if datetime.now(timezone.utc) - self._last_report >= timedelta(hours=schedule_hours):
            providers = list(all_stats.keys())
            self.reporter.generate_report(
                providers,
                window_hours=schedule_hours,
                report_title="Automated SLA Compliance Report",
            )
            self._last_report = datetime.now(timezone.utc)

    def run_once(self):
        """Single probe+evaluate cycle. Useful for testing or one-shot checks."""
        self._cycle += 1
        logger.info("=== Cycle %d ===", self._cycle)
        self.probe_all_providers()
        all_stats = self.evaluate_slas()
        self.dashboard.render(all_stats)
        self._maybe_generate_report(all_stats)
        return all_stats

    def run_loop(self, max_cycles: Optional[int] = None):
        """
        Continuous monitoring loop.
        max_cycles=None → run forever until KeyboardInterrupt.
        max_cycles=N    → run N cycles then return (for demos/tests).
        """
        interval = self.config.get("probe_interval_seconds", 60)
        self._running = True
        logger.info(
            "SLA Tracker started. Interval=%ds, providers=%s",
            interval,
            self.config.get("providers_enabled"),
        )

        cycle = 0
        try:
            while self._running:
                if max_cycles is not None and cycle >= max_cycles:
                    break
                self.run_once()
                cycle += 1
                if max_cycles is None or cycle < max_cycles:
                    logger.info("Sleeping %ds until next probe cycle…", interval)
                    time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt — stopping tracker.")
        finally:
            self._running = False
            logger.info("SLA Tracker stopped after %d cycles.", cycle)

    def stop(self):
        self._running = False


# ── CLI Entrypoint ────────────────────────────────────────────────────────────
def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║       TAD  AI Model Latency SLA Tracker & Breach Alert System   ║
║       Revenue model: $49/$199/$799 per month (B2B SaaS)         ║
║       TAM: $150M–$250M  |  Score: 29/40 (CEO APPROVED)          ║
╚══════════════════════════════════════════════════════════════════╝
    """)


def demo_mode():
    """
    Full demo using Mock provider — no API keys required.
    Runs 5 probe cycles at 5-second intervals, generates a report,
    and shows breach detection in action.
    """
    print_banner()
    print("Starting DEMO MODE (Mock provider — no API keys needed)")
    print(f"Logs    → {LOGS_DIR}")
    print(f"Reports → {REPORTS_DIR}")
    print(f"Alerts  → {ALERTS_DIR}")
    print()

    cfg = ConfigManager()

    # Demo config: fast cycles, low thresholds to trigger visible breaches
    demo_overrides = {
        "probe_interval_seconds": 5,
        "measurement_window_minutes": 1,
        "providers_enabled": [Provider.MOCK.value],
        "alert_channels": [AlertChannel.CONSOLE.value, AlertChannel.FILE.value],
        "consecutive_breach_before_alert": 1,
        "cooldown_minutes_between_alerts": 0,
        "sla_thresholds": {
            Provider.MOCK.value: {
                "p50_ms": 350,   # deliberately tight to show breach detection
                "p95_ms": 800,
                "p99_ms": 2000,
                "error_rate_pct": 2.0,
                "availability_pct": 98.0,
            }
        },
    }
    # Patch config in-memory for demo
    cfg._config.update(demo_overrides)

    tracker = SLATrackerOrchestrator(cfg)

    print("Running 5 probe cycles (each cycle probes all providers)…\n")
    for i in range(5):
        print(f"── Cycle {i+1}/5 ──────────────────────────")
        tracker.run_once()
        if i < 4:
            time.sleep(3)

    # Generate final report
    print("\nGenerating final SLA compliance report…")
    report = tracker.reporter.generate_report(
        providers=[Provider.MOCK.value],
        window_hours=1,
        report_title="Demo SLA Report — TAD AI Latency Tracker",
    )

    print(f"\nReport ID : {report['report_id']}")
    print(f"Health    : {report['overall_health'].upper()}")
    print(f"Breaches  : {report['total_breaches_in_window']}")
    print(f"Saved to  : {REPORTS_DIR}\n")

    for rec in report.get("recommendations", []):
        print(f"  💡 {rec}")

    print("\nDemo complete. To run in production mode, configure your API keys in:")
    print(f"  {CONFIG_PATH}")
    print("Then run: python ai_model_latency_sla_tracker___breach_alert_system.py --run\n")


def production_mode():
    """
    Continuous production run. Reads API keys from config.json.
    Set probe_interval_seconds to 60 for real-time monitoring.
    """
    print_banner()
    cfg = ConfigManager()
    tracker = SLATrackerOrchestrator(cfg)
    tracker.run_loop()  # runs until Ctrl+C


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TAD AI Latency SLA Tracker & Breach Alert System"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run in production mode (continuous loop, reads config.json for API keys)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Generate a one-shot SLA report from historical data and exit",
    )
    parser.add_argument(
        "--providers",
        nargs="+",
        default=None,
        help="Override providers list (e.g. --providers mock openai)",
    )
    args = parser.parse_args()

    if args.run:
        if args.providers:
            cfg = ConfigManager()
            cfg._config["providers_enabled"] = args.providers
        production_mode()
    elif args.report_only:
        cfg = ConfigManager()
        providers = args.providers or cfg.get("providers_enabled", [Provider.MOCK.value])
        ms = MetricsStore(cfg)
        rg = ReportGenerator(cfg, ms)
        r = rg.generate_report(providers, window_hours=24, report_title="On-Demand SLA Report")
        print(json.dumps(r, indent=2))
    else:
        # Default: demo mode — works with zero configuration
        demo_mode()