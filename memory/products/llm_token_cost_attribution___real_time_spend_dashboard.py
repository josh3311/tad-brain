"""
LLM Token Cost Attribution & Real-Time Spend Dashboard
=======================================================
Production-ready B2B SaaS module for tracking, attributing, and visualizing
LLM API costs across OpenAI, Anthropic, and other providers in real time.

Author: TAD Build Agent
Date: 2026-06-28
Target: memory/products/llm_token_cost_attribution___real_time_spend_dashboard.py

Architecture:
  - CostTracker     : intercepts/wraps API calls, logs token usage + cost
  - CostAttributor  : tags spend by project / team / user / feature
  - SpendAggregator : rolls up totals with time-window bucketing
  - AlertEngine     : fires budget alerts via console / webhook
  - Dashboard       : rich terminal UI with live refresh
  - SQLite backend  : persistent, zero-dependency storage
"""

import os
import sys
import json
import time
import math
import uuid
import sqlite3
import logging
import hashlib
import threading
import functools
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from collections import defaultdict

# ── Optional rich UI ──────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ── Optional HTTP for webhook alerts ─────────────────────────────────────────
try:
    import urllib.request
    import urllib.parse
    URLLIB_AVAILABLE = True
except ImportError:
    URLLIB_AVAILABLE = False

# ═════════════════════════════════════════════════════════════════════════════
# PATHS & LOGGING
# ═════════════════════════════════════════════════════════════════════════════

MEMORY_DIR = Path("memory")
PRODUCTS_DIR = MEMORY_DIR / "products"
LOG_DIR = MEMORY_DIR / "logs"
DB_PATH = MEMORY_DIR / "llm_spend.db"

for _d in [MEMORY_DIR, PRODUCTS_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "llm_cost_tracker.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("llm_cost_tracker")

# ═════════════════════════════════════════════════════════════════════════════
# PRICING TABLES  (per 1 000 tokens, USD — update as providers change rates)
# ═════════════════════════════════════════════════════════════════════════════

PRICING: Dict[str, Dict[str, Dict[str, float]]] = {
    "openai": {
        # model_id: {input: $/1k, output: $/1k, cached_input: $/1k}
        "gpt-4o":                {"input": 0.005,   "output": 0.015,  "cached_input": 0.0025},
        "gpt-4o-mini":           {"input": 0.00015, "output": 0.0006, "cached_input": 0.000075},
        "gpt-4-turbo":           {"input": 0.01,    "output": 0.03,   "cached_input": 0.005},
        "gpt-4":                 {"input": 0.03,    "output": 0.06,   "cached_input": 0.015},
        "gpt-3.5-turbo":         {"input": 0.0005,  "output": 0.0015, "cached_input": 0.00025},
        "text-embedding-3-small":{"input": 0.00002, "output": 0.0,    "cached_input": 0.0},
        "text-embedding-3-large":{"input": 0.00013, "output": 0.0,    "cached_input": 0.0},
    },
    "anthropic": {
        "claude-3-5-sonnet-20241022": {"input": 0.003,  "output": 0.015, "cached_input": 0.0003},
        "claude-3-5-haiku-20241022":  {"input": 0.0008, "output": 0.004, "cached_input": 0.00008},
        "claude-3-opus-20240229":     {"input": 0.015,  "output": 0.075, "cached_input": 0.0015},
        "claude-3-sonnet-20240229":   {"input": 0.003,  "output": 0.015, "cached_input": 0.0003},
        "claude-3-haiku-20240307":    {"input": 0.00025,"output": 0.00125,"cached_input": 0.000025},
    },
    "cohere": {
        "command-r-plus": {"input": 0.003, "output": 0.015, "cached_input": 0.0},
        "command-r":      {"input": 0.0005,"output": 0.0015,"cached_input": 0.0},
    },
    "google": {
        "gemini-1.5-pro":   {"input": 0.00125, "output": 0.005,  "cached_input": 0.0003125},
        "gemini-1.5-flash":  {"input": 0.000075,"output": 0.0003, "cached_input": 0.00001875},
        "gemini-1.0-pro":    {"input": 0.0005,  "output": 0.0015, "cached_input": 0.0},
    },
    "mistral": {
        "mistral-large-latest": {"input": 0.002, "output": 0.006, "cached_input": 0.0},
        "mistral-small-latest": {"input": 0.0002,"output": 0.0006,"cached_input": 0.0},
        "mixtral-8x7b":         {"input": 0.0007,"output": 0.0007,"cached_input": 0.0},
    },
}

UNKNOWN_PRICING = {"input": 0.001, "output": 0.002, "cached_input": 0.0}

# ═════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class TokenUsage:
    input_tokens:        int = 0
    output_tokens:       int = 0
    cached_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

@dataclass
class CostEvent:
    event_id:      str
    timestamp:     float
    provider:      str
    model:         str
    project:       str
    team:          str
    user:          str
    feature:       str
    usage:         TokenUsage
    cost_usd:      float
    latency_ms:    float
    request_hash:  str
    metadata:      Dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> Tuple:
        return (
            self.event_id, self.timestamp, self.provider, self.model,
            self.project, self.team, self.user, self.feature,
            self.usage.input_tokens, self.usage.output_tokens,
            self.usage.cached_input_tokens, self.cost_usd,
            self.latency_ms, self.request_hash,
            json.dumps(self.metadata),
        )

@dataclass
class BudgetAlert:
    alert_id:   str
    timestamp:  float
    dimension:  str   # project / team / user / global
    entity:     str
    window:     str   # hourly / daily / monthly
    limit_usd:  float
    actual_usd: float
    percent:    float

    def message(self) -> str:
        return (
            f"🚨 BUDGET ALERT [{self.dimension}:{self.entity}] "
            f"{self.window} spend ${self.actual_usd:.4f} "
            f"({self.percent:.1f}% of ${self.limit_usd:.2f} limit)"
        )

# ═════════════════════════════════════════════════════════════════════════════
# DATABASE LAYER
# ═════════════════════════════════════════════════════════════════════════════

class SpendDatabase:
    """Thread-safe SQLite wrapper for all cost events and alerts."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_schema(self):
        with self._lock:
            c = self._conn()
            c.executescript("""
                CREATE TABLE IF NOT EXISTS cost_events (
                    event_id      TEXT PRIMARY KEY,
                    timestamp     REAL NOT NULL,
                    provider      TEXT NOT NULL,
                    model         TEXT NOT NULL,
                    project       TEXT NOT NULL,
                    team          TEXT NOT NULL,
                    user_id       TEXT NOT NULL,
                    feature       TEXT NOT NULL,
                    input_tokens  INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL,
                    cost_usd      REAL NOT NULL,
                    latency_ms    REAL NOT NULL,
                    request_hash  TEXT NOT NULL,
                    metadata      TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_ce_timestamp  ON cost_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_ce_project    ON cost_events(project);
                CREATE INDEX IF NOT EXISTS idx_ce_team       ON cost_events(team);
                CREATE INDEX IF NOT EXISTS idx_ce_user       ON cost_events(user_id);
                CREATE INDEX IF NOT EXISTS idx_ce_provider   ON cost_events(provider);
                CREATE INDEX IF NOT EXISTS idx_ce_model      ON cost_events(model);

                CREATE TABLE IF NOT EXISTS budget_limits (
                    limit_id   TEXT PRIMARY KEY,
                    dimension  TEXT NOT NULL,
                    entity     TEXT NOT NULL,
                    window     TEXT NOT NULL,
                    limit_usd  REAL NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(dimension, entity, window)
                );

                CREATE TABLE IF NOT EXISTS alerts_log (
                    alert_id   TEXT PRIMARY KEY,
                    timestamp  REAL NOT NULL,
                    dimension  TEXT NOT NULL,
                    entity     TEXT NOT NULL,
                    window     TEXT NOT NULL,
                    limit_usd  REAL NOT NULL,
                    actual_usd REAL NOT NULL,
                    percent    REAL NOT NULL
                );
            """)
            c.commit()

    def insert_event(self, event: CostEvent):
        with self._lock:
            c = self._conn()
            c.execute(
                """INSERT OR IGNORE INTO cost_events VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                event.to_row(),
            )
            c.commit()

    def query_spend(
        self,
        since_ts: float,
        until_ts: Optional[float] = None,
        project: Optional[str] = None,
        team: Optional[str] = None,
        user: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> List[sqlite3.Row]:
        until_ts = until_ts or time.time()
        clauses = ["timestamp >= ?", "timestamp <= ?"]
        params: List[Any] = [since_ts, until_ts]
        if project:   clauses.append("project = ?");  params.append(project)
        if team:      clauses.append("team = ?");     params.append(team)
        if user:      clauses.append("user_id = ?");  params.append(user)
        if provider:  clauses.append("provider = ?"); params.append(provider)
        if model:     clauses.append("model = ?");    params.append(model)
        sql = f"SELECT * FROM cost_events WHERE {' AND '.join(clauses)} ORDER BY timestamp DESC"
        with self._lock:
            return self._conn().execute(sql, params).fetchall()

    def aggregate_spend(
        self,
        since_ts: float,
        group_by: str = "project",
    ) -> List[Dict[str, Any]]:
        """Aggregate total cost grouped by a single dimension."""
        valid_cols = {"project", "team", "user_id", "provider", "model", "feature"}
        if group_by not in valid_cols:
            raise ValueError(f"group_by must be one of {valid_cols}")
        sql = f"""
            SELECT {group_by} as dimension_value,
                   SUM(cost_usd) as total_cost,
                   SUM(input_tokens + output_tokens) as total_tokens,
                   COUNT(*) as num_requests,
                   AVG(latency_ms) as avg_latency_ms
            FROM cost_events
            WHERE timestamp >= ?
            GROUP BY {group_by}
            ORDER BY total_cost DESC
        """
        with self._lock:
            rows = self._conn().execute(sql, [since_ts]).fetchall()
        return [dict(r) for r in rows]

    def set_budget(self, dimension: str, entity: str, window: str, limit_usd: float):
        lid = str(uuid.uuid4())
        with self._lock:
            c = self._conn()
            c.execute(
                """INSERT OR REPLACE INTO budget_limits
                   (limit_id, dimension, entity, window, limit_usd, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (lid, dimension, entity, window, limit_usd, time.time()),
            )
            c.commit()

    def get_budgets(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn().execute("SELECT * FROM budget_limits").fetchall()
        return [dict(r) for r in rows]

    def log_alert(self, alert: BudgetAlert):
        with self._lock:
            c = self._conn()
            c.execute(
                """INSERT OR IGNORE INTO alerts_log VALUES (?,?,?,?,?,?,?,?)""",
                (alert.alert_id, alert.timestamp, alert.dimension,
                 alert.entity, alert.window, alert.limit_usd,
                 alert.actual_usd, alert.percent),
            )
            c.commit()

    def total_spend_since(self, since_ts: float) -> float:
        with self._lock:
            row = self._conn().execute(
                "SELECT SUM(cost_usd) FROM cost_events WHERE timestamp >= ?",
                [since_ts]
            ).fetchone()
        return float(row[0] or 0.0)

# ═════════════════════════════════════════════════════════════════════════════
# COST CALCULATOR
# ═════════════════════════════════════════════════════════════════════════════

def calculate_cost(
    provider: str,
    model: str,
    usage: TokenUsage,
) -> float:
    """Compute exact USD cost for a token usage event."""
    p = PRICING.get(provider.lower(), {})
    rates = p.get(model, None)
    if rates is None:
        # Fuzzy match on model prefix
        for key, val in p.items():
            if model.startswith(key) or key in model:
                rates = val
                break
    if rates is None:
        log.warning(f"No pricing found for {provider}/{model}, using fallback")
        rates = UNKNOWN_PRICING

    cost = (
        usage.input_tokens        / 1000 * rates["input"]
        + usage.output_tokens     / 1000 * rates["output"]
        + usage.cached_input_tokens / 1000 * rates.get("cached_input", 0.0)
    )
    return round(cost, 8)

# ═════════════════════════════════════════════════════════════════════════════
# ATTRIBUTION CONTEXT  (thread-local context manager)
# ═════════════════════════════════════════════════════════════════════════════

_attribution_local = threading.local()

@contextmanager
def attribution_context(
    project: str = "default",
    team: str = "default",
    user: str = "anonymous",
    feature: str = "unknown",
):
    """
    Context manager to tag all LLM calls made within the block.

    Usage:
        with attribution_context(project="search", team="backend", user="alice"):
            response = tracked_openai_call(...)
    """
    _attribution_local.project = project
    _attribution_local.team = team
    _attribution_local.user = user
    _attribution_local.feature = feature
    try:
        yield
    finally:
        _attribution_local.project = "default"
        _attribution_local.team = "default"
        _attribution_local.user = "anonymous"
        _attribution_local.feature = "unknown"

def _current_attribution() -> Dict[str, str]:
    return {
        "project": getattr(_attribution_local, "project", "default"),
        "team":    getattr(_attribution_local, "team",    "default"),
        "user":    getattr(_attribution_local, "user",    "anonymous"),
        "feature": getattr(_attribution_local, "feature", "unknown"),
    }

# ═════════════════════════════════════════════════════════════════════════════
# COST TRACKER  (core recording engine)
# ═════════════════════════════════════════════════════════════════════════════

class CostTracker:
    """
    Central engine that records every LLM API call.
    Provides decorators/wrappers to intercept real API calls,
    and a manual record() method for custom integrations.
    """

    def __init__(self, db: SpendDatabase):
        self.db = db
        self._listeners: List[Callable[[CostEvent], None]] = []
        log.info("CostTracker initialised — DB: %s", db.db_path)

    def add_listener(self, fn: Callable[[CostEvent], None]):
        """Register a callback fired after every cost event is recorded."""
        self._listeners.append(fn)

    def record(
        self,
        provider: str,
        model: str,
        usage: TokenUsage,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        override_attribution: Optional[Dict[str, str]] = None,
    ) -> CostEvent:
        """Record a cost event manually (or from wrapper)."""
        attr = override_attribution or _current_attribution()
        cost = calculate_cost(provider, model, usage)
        req_str = f"{provider}:{model}:{usage.input_tokens}:{usage.output_tokens}:{time.time()}"
        req_hash = hashlib.sha256(req_str.encode()).hexdigest()[:16]

        event = CostEvent(
            event_id     = str(uuid.uuid4()),
            timestamp    = time.time(),
            provider     = provider.lower(),
            model        = model,
            project      = attr["project"],
            team         = attr["team"],
            user         = attr["user"],
            feature      = attr["feature"],
            usage        = usage,
            cost_usd     = cost,
            latency_ms   = latency_ms,
            request_hash = req_hash,
            metadata     = metadata or {},
        )
        self.db.insert_event(event)
        log.debug(
            "Recorded event %s — %s/%s — $%.6f — %d tokens",
            event.event_id, provider, model, cost, usage.total_tokens,
        )
        for fn in self._listeners:
            try:
                fn(event)
            except Exception as exc:
                log.error("Listener error: %s", exc)
        return event

    # ── Decorator for OpenAI-style clients ────────────────────────────────
    def wrap_openai(self, client):
        """
        Wrap an openai.OpenAI client so every chat.completions.create()
        call is automatically tracked.

        Usage:
            import openai
            client = openai.OpenAI(api_key=...)
            client = tracker.wrap_openai(client)
        """
        original_create = client.chat.completions.create

        @functools.wraps(original_create)
        def tracked_create(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                response = original_create(*args, **kwargs)
            except Exception as exc:
                log.error("OpenAI call failed: %s", exc)
                raise
            latency_ms = (time.perf_counter() - t0) * 1000
            try:
                usage = TokenUsage(
                    input_tokens  = response.usage.prompt_tokens,
                    output_tokens = response.usage.completion_tokens,
                    cached_input_tokens = getattr(
                        response.usage, "prompt_tokens_details", None
                    ) and getattr(
                        response.usage.prompt_tokens_details, "cached_tokens", 0
                    ) or 0,
                )
                model = kwargs.get("model", getattr(response, "model", "unknown"))
                self.record("openai", model, usage, latency_ms,
                            metadata={"finish_reason": response.choices[0].finish_reason
                                      if response.choices else "unknown"})
            except Exception as exc:
                log.error("Failed to record OpenAI cost event: %s", exc)
            return response

        client.chat.completions.create = tracked_create
        return client

    # ── Decorator for Anthropic-style clients ────────────────────────────
    def wrap_anthropic(self, client):
        """
        Wrap an anthropic.Anthropic client so every messages.create()
        call is automatically tracked.
        """
        original_create = client.messages.create

        @functools.wraps(original_create)
        def tracked_create(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                response = original_create(*args, **kwargs)
            except Exception as exc:
                log.error("Anthropic call failed: %s", exc)
                raise
            latency_ms = (time.perf_counter() - t0) * 1000
            try:
                u = response.usage
                cached = getattr(u, "cache_read_input_tokens", 0) or 0
                usage = TokenUsage(
                    input_tokens        = u.input_tokens,
                    output_tokens       = u.output_tokens,
                    cached_input_tokens = cached,
                )
                model = kwargs.get("model", getattr(response, "model", "unknown"))
                self.record("anthropic", model, usage, latency_ms,
                            metadata={"stop_reason": response.stop_reason})
            except Exception as exc:
                log.error("Failed to record Anthropic cost event: %s", exc)
            return response

        client.messages.create = tracked_create
        return client

    # ── Generic function decorator ─────────────────────────────────────────
    def track(
        self,
        provider: str,
        model: str,
        extract_usage: Callable[[Any], TokenUsage],
    ):
        """
        Generic decorator for any LLM function that returns a response object.

        Usage:
            @tracker.track("mistral", "mistral-large-latest", my_usage_extractor)
            def call_mistral(...):
                ...
        """
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                result = fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000
                try:
                    usage = extract_usage(result)
                    self.record(provider, model, usage, latency_ms)
                except Exception as exc:
                    log.error("track decorator extraction failed: %s", exc)
                return result
            return wrapper
        return decorator

# ═════════════════════════════════════════════════════════════════════════════
# SPEND AGGREGATOR
# ═════════════════════════════════════════════════════════════════════════════

class SpendAggregator:
    """Compute spend summaries across configurable time windows."""

    WINDOWS = {
        "hourly":  3600,
        "daily":   86400,
        "weekly":  604800,
        "monthly": 2592000,   # 30 days
    }

    def __init__(self, db: SpendDatabase):
        self.db = db

    def _since(self, window: str) -> float:
        secs = self.WINDOWS.get(window, 86400)
        return time.time() - secs

    def total_by_window(self, window: str = "daily") -> float:
        return self.db.total_spend_since(self._since(window))

    def breakdown(
        self,
        window: str = "daily",
        group_by: str = "project",
    ) -> List[Dict[str, Any]]:
        return self.db.aggregate_spend(self._since(window), group_by)

    def provider_comparison(self, window: str = "daily") -> List[Dict[str, Any]]:
        return self.breakdown(window, group_by="provider")

    def model_comparison(self, window: str = "daily") -> List[Dict[str, Any]]:
        return self.breakdown(window, group_by="model")

    def hourly_trend(self, lookback_hours: int = 24) -> List[Dict[str, Any]]:
        """Return per-hour spend buckets for the past N hours."""
        buckets = []
        now = time.time()
        for i in range(lookback_hours - 1, -1, -1):
            start = now - (i + 1) * 3600
            end   = now - i * 3600
            rows  = self.db.query_spend(start, end)
            total = sum(r["cost_usd"] for r in rows)
            dt    = datetime.fromtimestamp(end, tz=timezone.utc)
            buckets.append({
                "hour":   dt.strftime("%Y-%m-%d %H:00"),
                "cost":   round(total, 6),
                "calls":  len(rows),
            })
        return buckets

    def efficiency_report(self, window: str = "daily") -> Dict[str, Any]:
        """
        Identify models with highest cost-per-request and suggest
        cheaper alternatives.
        """
        models = self.breakdown(window, group_by="model")
        report = []
        for m in models:
            model_name = m["dimension_value"]
            cpk = (m["total_cost"] / m["total_tokens"] * 1000) if m["total_tokens"] else 0
            # Find cheapest same-provider alternative
            suggestion = _suggest_cheaper_model(model_name)
            report.append({
                "model":              model_name,
                "total_cost_usd":     round(m["total_cost"], 4),
                "total_tokens":       m["total_tokens"],
                "cost_per_1k_tokens": round(cpk, 6),
                "num_requests":       m["num_requests"],
                "avg_latency_ms":     round(m["avg_latency_ms"], 1),
                "cheaper_alternative": suggestion,
            })
        return {
            "window":        window,
            "generated_at":  datetime.utcnow().isoformat(),
            "models":        report,
        }

def _suggest_cheaper_model(model_name: str) -> Optional[str]:
    """Return a cheaper model suggestion from same provider, if available."""
    suggestions = {
        "gpt-4o":                    "gpt-4o-mini ($0.0006/1k out vs $0.015)",
        "gpt-4":                     "gpt-4o ($0.015/1k out vs $0.06)",
        "gpt-4-turbo":               "gpt-4o ($0.015/1k out vs $0.03)",
        "claude-3-opus-20240229":    "claude-3-5-sonnet ($0.015/1k out vs $0.075)",
        "claude-3-sonnet-20240229":  "claude-3-5-haiku ($0.004/1k out vs $0.015)",
        "mistral-large-latest":      "mistral-small-latest ($0.0006/1k out vs $0.006)",
        "command-r-plus":            "command-r ($0.0015/1k out vs $0.015)",
        "gemini-1.5-pro":            "gemini-1.5-flash ($0.0003/1k out vs $0.005)",
    }
    for key, val in suggestions.items():
        if key in model_name:
            return val
    return None

# ═════════════════════════════════════════════════════════════════════════════
# ALERT ENGINE
# ═════════════════════════════════════════════════════════════════════════════

class AlertEngine:
    """
    Fires budget alerts when spend exceeds configured thresholds.
    Supports console, log, and webhook delivery.
    """

    def __init__(
        self,
        db: SpendDatabase,
        aggregator: SpendAggregator,
        webhook_url: Optional[str] = None,
        alert_threshold_pct: float = 80.0,
    ):
        self.db = db
        self.aggregator = aggregator
        self.webhook_url = webhook_url
        self.threshold_pct = alert_threshold_pct
        self._fired_keys: set = set()   # debounce within session

    def check_all_budgets(self):
        """Evaluate all configured budgets and fire alerts as needed."""
        budgets = self.db.get_budgets()
        for budget in budgets:
            self._check_budget(budget)

    def _check_budget(self, budget: Dict[str, Any]):
        dimension  = budget["dimension"]   # project / team / user / global
        entity     = budget["entity"]
        window     = budget["window"]
        limit_usd  = budget["limit_usd"]

        since_ts = time.time() - SpendAggregator.WINDOWS.get(window, 86400)
        kwargs = {dimension: entity} if dimension != "global" else {}
        rows = self.db.query_spend(since_ts, **kwargs)
        actual = sum(r["cost_usd"] for r in rows)
        pct = (actual / limit_usd * 100) if limit_usd else 0.0

        debounce_key = f"{dimension}:{entity}:{window}:{int(pct // 10)}"
        if pct >= self.threshold_pct and debounce_key not in self._fired_keys:
            alert = BudgetAlert(
                alert_id   = str(uuid.uuid4()),
                timestamp  = time.time(),
                dimension  = dimension,
                entity     = entity,
                window     = window,
                limit_usd  = limit_usd,
                actual_usd = actual,
                percent    = pct,
            )
            self._fire(alert)
            self._fired_keys.add(debounce_key)

    def _fire(self, alert: BudgetAlert):
        msg = alert.message()
        log.warning(msg)
        print(f"\n{'='*60}\n{msg}\n{'='*60}\n")
        self.db.log_alert(alert)
        if self.webhook_url and URLLIB_AVAILABLE:
            self._send_webhook(alert)

    def _send_webhook(self, alert: BudgetAlert):
        payload = json.dumps({
            "text":       alert.message(),
            "alert_id":   alert.alert_id,
            "dimension":  alert.dimension,
            "entity":     alert.entity,
            "window":     alert.window,
            "limit_usd":  alert.limit_usd,
            "actual_usd": alert.actual_usd,
            "percent":    alert.percent,
        }).encode()
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                log.info("Webhook delivered — status %s", resp.status)
        except Exception as exc:
            log.error("Webhook delivery failed: %s", exc)

# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD  (terminal UI — rich if available, ASCII fallback)
# ═════════════════════════════════════════════════════════════════════════════

class SpendDashboard:
    """Real-time spend dashboard with live refresh."""

    def __init__(
        self,
        aggregator: SpendAggregator,
        alert_engine: AlertEngine,
        refresh_secs: float = 5.0,
    ):
        self.aggregator   = aggregator
        self.alert_engine = alert_engine
        self.refresh_secs = refresh_secs
        self.console      = Console() if RICH_AVAILABLE else None

    # ── Main entry point ──────────────────────────────────────────────────
    def run(self, duration_secs: Optional[float] = None):
        """
        Run the live dashboard.
        duration_secs=None → run until Ctrl-C.
        """
        if RICH_AVAILABLE:
            self._run_rich(duration_secs)
        else:
            self._run_ascii(duration_secs)

    def snapshot(self) -> Dict[str, Any]:
        """Return current dashboard data as a dict (useful for API endpoints)."""
        return {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "spend": {
                "hourly":  round(self.aggregator.total_by_window("hourly"),  4),
                "daily":   round(self.aggregator.total_by_window("daily"),   4),
                "weekly":  round(self.aggregator.total_by_window("weekly"),  4),
                "monthly": round(self.aggregator.total_by_window("monthly"), 4),
            },
            "by_project":  self.aggregator.breakdown("daily",  "project"),
            "by_team":     self.aggregator.breakdown("daily",  "team"),
            "by_provider": self.aggregator.provider_comparison("daily"),
            "by_model":    self.aggregator.model_comparison("daily"),
            "hourly_trend":self.aggregator.hourly_trend(24),
            "efficiency":  self.aggregator.efficiency_report("daily"),
        }

    # ── Rich UI ───────────────────────────────────────────────────────────
    def _run_rich(self, duration_secs: Optional[float]):
        end_time = (time.time() + duration_secs) if duration_secs else math.inf
        with Live(self._build_layout(), refresh_per_second=1,
                  console=self.console) as live:
            try:
                while time.time() < end_time:
                    self.alert_engine.check_all_budgets()
                    live.update(self._build_layout())
                    time.sleep(self.refresh_secs)
            except KeyboardInterrupt:
                pass

    def _build_layout(self) -> "Panel":
        snap = self.snapshot()
        now  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # ── Spend summary row ─────────────────────────────────────────────
        summary_table = Table(box=box.SIMPLE, expand=True)
        summary_table.add_column("Window",  style="bold cyan")
        summary_table.add_column("Spend",   style="bold green", justify="right")
        for w in ["hourly", "daily", "weekly", "monthly"]:
            summary_table.add_row(w.title(), f"${snap['spend'][w]:.4f}")

        # ── By project ────────────────────────────────────────────────────
        proj_table = Table(title="💼 By Project (24h)", box=box.ROUNDED, expand=True)
        proj_table.add_column("Project",  style="cyan")
        proj_table.add_column("Cost",     style="green",  justify="right")
        proj_table.add_column("Tokens",   style="yellow", justify="right")
        proj_table.add_column("Requests", style="white",  justify="right")
        for r in snap["by_project"][:8]:
            proj_table.add_row(
                r["dimension_value"],
                f"${r['total_cost']:.4f}",
                f"{r['total_tokens']:,}",
                str(r["num_requests"]),
            )

        # ── By provider ───────────────────────────────────────────────────
        prov_table = Table(title="🔌 By Provider (24h)", box=box.ROUNDED, expand=True)
        prov_table.add_column("Provider", style="magenta")
        prov_table.add_column("Cost",     style="green",  justify="right")
        prov_table.add_column("Tokens",   style="yellow", justify="right")
        for r in snap["by_provider"][:6]:
            prov_table.add_row(
                r["dimension_value"],
                f"${r['total_cost']:.4f}",
                f"{r['total_tokens']:,}",
            )

        # ── Efficiency tips ───────────────────────────────────────────────
        eff_table = Table(title="💡 Efficiency Tips", box=box.SIMPLE, expand=True)
        eff_table.add_column("Model",      style="red")
        eff_table.add_column("Cost/1kTok", style="yellow", justify="right")
        eff_table.add_column("Suggestion", style="green")
        for m in snap["efficiency"]["models"][:5]:
            alt = m["cheaper_alternative"] or "—"
            eff_table.add_row(
                m["model"],
                f"${m['cost_per_1k_tokens']:.5f}",
                alt,
            )

        from rich.columns import Columns
        body = Columns([proj_table, prov_table], equal=True, expand=True)

        content = f"[bold white]LLM Spend Dashboard[/] — {now}\n\n"
        panel = Panel(
            content,
            title="[bold yellow]💰 LLM Token Cost Attribution[/]",
            border_style="bright_blue",
        )
        # Build a simple vertical layout via Group
        from rich.console import Group as RichGroup
        return Panel(
            RichGroup(
                Panel(summary_table, title="📊 Spend Summary", border_style="green"),
                body,
                eff_table,
            ),
            title=f"[bold yellow]💰 LLM Spend Dashboard — {now}[/]",
            border_style="bright_blue",
        )

    # ── ASCII fallback ────────────────────────────────────────────────────
    def _run_ascii(self, duration_secs: Optional[float]):
        end_time = (time.time() + duration_secs) if duration_secs else math.inf
        try:
            while time.time() < end_time:
                self.alert_engine.check_all_budgets()
                self._print_ascii()
                time.sleep(self.refresh_secs)
        except KeyboardInterrupt:
            pass

    def _print_ascii(self):
        snap = self.snapshot()
        sep  = "=" * 60
        print(f"\n{sep}")
        print(f"  LLM Spend Dashboard — {snap['generated_at']}")
        print(sep)
        print("  SPEND SUMMARY")
        for w in ["hourly", "daily", "weekly", "monthly"]:
            print(f"    {w.title():10s}: ${snap['spend'][w]:.4f}")
        print()
        print("  BY PROJECT (24h)")
        for r in snap["by_project"][:6]:
            print(f"    {r['dimension_value']:20s} ${r['total_cost']:.4f}  "
                  f"{r['total_tokens']:>10,} tokens  {r['num_requests']} calls")
        print()
        print("  BY PROVIDER (24h)")
        for r in snap["by_provider"]:
            print(f"    {r['dimension_value']:15s} ${r['total_cost']:.4f}  "
                  f"{r['total_tokens']:>10,} tokens")
        print()
        print("  EFFICIENCY TIPS")
        for m in snap["efficiency"]["models"][:4]:
            alt = m["cheaper_alternative"] or "no suggestion"
            print(f"    {m['model']:35s} ${m['cost_per_1k_tokens']:.5f}/1k → {alt}")
        print(sep)

# ═════════════════════════════════════════════════════════════════════════════
# HIGH-LEVEL FACADE  (the thing a user imports)
# ═════════════════════════════════════════════════════════════════════════════

class LLMCostMonitor:
    """
    Single entry-point for the LLM Cost Attribution system.

    Quick start:
        monitor = LLMCostMonitor()
        client  = openai.OpenAI(api_key=...)
        client  = monitor.wrap_openai(client)

        with monitor.context(project="search", team="backend"):
            response = client.chat.completions.create(...)

        monitor.dashboard()
    """

    def __init__(
        self,
        db_path: Path = DB_PATH,
        webhook_url: Optional[str] = None,
        alert_threshold_pct: float = 80.0,
    ):
        self.db          = SpendDatabase(db_path)
        self.tracker     = CostTracker(self.db)
        self.aggregator  = SpendAggregator(self.db)
        self.alerts      = AlertEngine(
            self.db, self.aggregator, webhook_url, alert_threshold_pct
        )
        self.dash        = SpendDashboard(self.aggregator, self.alerts)
        log.info("LLMCostMonitor ready — db: %s", db_path)

    # Delegation shortcuts
    def wrap_openai(self, client):       return self.tracker.wrap_openai(client)
    def wrap_anthropic(self, client):    return self.tracker.wrap_anthropic(client)
    def context(self, **kwargs):         return attribution_context(**kwargs)

    def record(self, provider: str, model: str, input_tokens: int,
               output_tokens: int, cached_tokens: int = 0,
               latency_ms: float = 0.0, **attrs) -> CostEvent:
        """Manually record a call (for providers without a wrapper)."""
        usage = TokenUsage(input_tokens, output_tokens, cached_tokens)
        override = {k: attrs.get(k, v) for k, v in _current_attribution().items()}
        override.update({k: attrs[k] for k in attrs if k in override})
        return self.tracker.record(provider, model, usage, latency_ms,
                                   override_attribution=override)

    def set_budget(self, dimension: str, entity: str,
                   window: str, limit_usd: float):
        """
        Set a spend budget alert.
        dimension: 'project' | 'team' | 'user' | 'global'
        entity:    name matching the dimension (ignored for 'global')
        window:    'hourly' | 'daily' | 'weekly' | 'monthly'
        """
        self.db.set_budget(dimension, entity, window, limit_usd)
        log.info("Budget set: %s/%s %s ≤ $%.2f", dimension, entity, window, limit_usd)

    def dashboard(self, duration_secs: Optional[float] = None,
                  refresh_secs: float = 5.0):
        self.dash.refresh_secs = refresh_secs
        self.dash.run(duration_secs)

    def snapshot(self) -> Dict[str, Any]:
        return self.dash.snapshot()

    def export_json(self, path: Optional[Path] = None) -> Path:
        snap = self.snapshot()
        out  = path or (PRODUCTS_DIR / f"spend_export_{int(time.time())}.json")
        out.write_text(json.dumps(snap, indent=2))
        log.info("Spend snapshot exported to %s", out)
        return out

# ═════════════════════════════════════════════════════════════════════════════
# DEMO / SELF-TEST
# ═════════════════════════════════════════════════════════════════════════════

def _generate_demo_data(monitor: LLMCostMonitor, num_events: int = 120):
    """Inject realistic fake cost events for demo / self-test."""
    import random

    scenarios = [
        ("openai",     "gpt-4o",                      "search-api",   "ml-team",    "alice"),
        ("openai",     "gpt-4o-mini",                 "summarizer",   "product",    "bob"),
        ("anthropic",  "claude-3-5-sonnet-20241022",  "support-bot",  "cx-team",    "carol"),
        ("anthropic",  "claude-3-5-haiku-20241022",   "classifier",   "data-team",  "dave"),
        ("openai",     "gpt-3.5-turbo",               "legacy-api",   "backend",    "eve"),
        ("google",     "gemini-1.5-flash",            "embedding-svc","infra",      "frank"),
        ("mistral",    "mistral-large-latest",         "code-gen",     "eng",        "grace"),
        ("openai",     "text-embedding-3-small",       "search-api",   "ml-team",    "henry"),
        ("anthropic",  "claude-3-opus-20240229",       "research",     "research",   "iris"),
        ("cohere",     "command-r",                    "rag-pipeline", "data-team",  "jack"),
    ]

    rng = random.Random(42)
    now = time.time()

    for i in range(num_events):
        provider, model, project, team, user = rng.choice(scenarios)
        input_tok   = rng.randint(100, 4000)
        output_tok  = rng.randint(50,  2000)
        cached_tok  = rng.randint(0,   input_tok // 4)
        latency_ms  = rng.uniform(200, 4000)
        # Spread events over past 48 hours
        ts_offset   = rng.uniform(0, 48 * 3600)

        usage = TokenUsage(input_tok, output_tok, cached_tok)
        cost  = calculate_cost(provider, model, usage)
        req_hash = hashlib.sha256(f"{i}:{provider}:{model}".encode()).hexdigest()[:16]

        event = CostEvent(
            event_id     = str(uuid.uuid4()),
            timestamp    = now - ts_offset,
            provider     = provider,
            model        = model,
            project      = project,
            team         = team,
            user         = user,
            feature      = rng.choice(["chat", "embed", "classify", "summarize"]),
            usage        = usage,
            cost_usd     = cost,
            latency_ms   = latency_ms,
            request_hash = req_hash,
            metadata     = {"demo": True, "iteration": i},
        )
        monitor.db.insert_event(event)

    log.info("Demo: injected %d cost events", num_events)


def run_demo():
    """Full end-to-end demo with generated data + dashboard snapshot."""
    print("\n" + "="*60)
    print("  LLM Token Cost Attribution — Demo Run")
    print("="*60 + "\n")

    monitor = LLMCostMonitor(db_path=DB_PATH)

    # Set some example budgets
    monitor.set_budget("project", "search-api",  "daily",  5.00)
    monitor.set_budget("team",    "ml-team",     "daily", 10.00)
    monitor.set_budget("project", "research",    "monthly", 50.00)

    # Generate realistic demo data
    print("Generating demo data...")
    _generate_demo_data(monitor, num_events=150)

    # Manual record example (simulating a call without a wrapper)
    with monitor.context(project="demo-project", team="demo-team",
                         user="demo-user", feature="chat"):
        monitor.record(
            provider="openai", model="gpt-4o",
            input_tokens=1200, output_tokens=450, cached_tokens=200,
            latency_ms=1340.0,
        )

    # Export snapshot
    export_path = monitor.export_json()
    print(f"\n✅ Snapshot exported → {export_path}")

    # Print snapshot summary
    snap = monitor.snapshot()
    print("\n📊 SPEND SUMMARY:")
    for w, v in snap["spend"].items():
        print(f"   {w.title():10s}: ${v:.4f}")

    print("\n📈 TOP PROJECTS (24h):")
    for r in snap["by_project"][:5]:
        print(f"   {r['dimension_value']:20s} ${r['total_cost']:.4f}  "
              f"{r['total_tokens']:>10,} tokens")

    print("\n🔌 BY PROVIDER (24h):")
    for r in snap["by_provider"]:
        print(f"   {r['dimension_value']:15s} ${r['total_cost']:.4f}")

    print("\n💡 EFFICIENCY TIPS:")
    for m in snap["efficiency"]["models"][:4]:
        tip = m["cheaper_alternative"] or "optimal choice"
        print(f"   {m['model']:35s} → {tip}")

    print("\n🚨 Checking budgets...")
    monitor.alerts.check_all_budgets()

    print("\n✅ Demo complete. Run with --dashboard to start live UI.\n")
    return monitor


def run_self_test() -> bool:
    """Syntax + logic self-test. Returns True if all checks pass."""
    errors = []
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_spend.db"
        monitor  = LLMCostMonitor(db_path=test_db)

        # Test 1: Cost calculation
        usage = TokenUsage(1000, 500, 200)
        cost  = calculate_cost("openai", "gpt-4o", usage)
        expected = (1000/1000*0.005) + (500/1000*0.015) + (200/1000*0.0025)
        if abs(cost - expected) > 1e-9:
            errors.append(f"Cost calc wrong: got {cost}, expected {expected}")

        # Test 2: Record event
        with monitor.context(project="test", team="eng", user="tester"):
            ev = monitor.record("anthropic", "claude-3-5-haiku-20241022",
                                500, 200, 0, 850.0)
        if ev.project != "test":
            errors.append("Attribution context not applied")
        if ev.cost_usd <= 0:
            errors.append("Cost is zero after record()")

        # Test 3: DB round-trip
        rows = monitor.db.query_spend(time.time() - 60)
        if len(rows) == 0:
            errors.append("DB query returned no rows after insert")

        # Test 4: Aggregation
        _generate_demo_data(monitor, num_events=20)
        agg = monitor.aggregator.breakdown("daily", "project")
        if not agg:
            errors.append("Aggregation returned empty results")

        # Test 5: Budget + alert
        monitor.set_budget("project", "test", "daily", 0.000001)  # trivially low
        monitor.alerts.alert_threshold_pct = 0.0
        # Should not crash even if budget exceeded
        try:
            monitor.alerts.check_all_budgets()
        except Exception as exc:
            errors.append(f"Alert engine raised: {exc}")

        # Test 6: Snapshot
        snap = monitor.snapshot()
        for key in ["spend", "by_project", "by_provider", "efficiency"]:
            if key not in snap:
                errors.append(f"Snapshot missing key: {key}")

        # Test 7: Export
        out = monitor.export_json(Path(tmpdir) / "export.json")
        if not out.exists():
            errors.append("Export file not created")

    if errors:
        for e in errors:
            log.error("SELF-TEST FAIL: %s", e)
        print(f"\n❌ Self-test FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"   • {e}")
        return False
    else:
        print("\n✅ All self-tests passed.")
        return True


# ═════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LLM Token Cost Attribution & Real-Time Spend Dashboard"
    )
    parser.add_argument("--demo",      action="store_true", help="Run demo with generated data")
    parser.add_argument("--test",      action="store_true", help="Run self-tests")
    parser.add_argument("--dashboard", action="store_true", help="Launch live dashboard")
    parser.add_argument("--export",    action="store_true", help="Export current snapshot to JSON")
    parser.add_argument(
        "--refresh", type=float, default=5.0,
        help="Dashboard refresh interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--webhook", type=str, default=None,
        help="Slack/Teams webhook URL for budget alerts"
    )
    args = parser.parse_args()

    if args.test:
        ok = run_self_test()
        sys.exit(0 if ok else 1)

    if args.demo or (not args.dashboard and not args.export):
        monitor = run_demo()
    else:
        monitor = LLMCostMonitor(webhook_url=args.webhook)

    if args.export:
        path = monitor.export_json()
        print(f"Exported to {path}")

    if args.dashboard:
        print(f"\nStarting dashboard (refresh={args.refresh}s) — Ctrl-C to quit\n")
        monitor.dashboard(refresh_secs=args.refresh)