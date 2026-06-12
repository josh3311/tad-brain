"""
TAD — Observability Skill
Per-agent call metrics: call count, error count, avg response time,
last error message. Persists to memory/metrics.json.

Hooked into agent dispatch via observe_call() — one wrapper in
agent.run_task(), no per-agent edits needed.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT         = Path(__file__).parent.parent
METRICS_PATH = ROOT / "memory" / "metrics.json"

_lock = threading.Lock()


def _load() -> dict:
    if METRICS_PATH.exists():
        try:
            return json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(data: dict):
    METRICS_PATH.parent.mkdir(exist_ok=True)
    METRICS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_call(agent: str, duration_s: float, error: str | None = None):
    """Record one agent call. Thread-safe; updates rolling averages."""
    with _lock:
        data  = _load()
        stats = data.get(agent, {
            "call_count":        0,
            "error_count":       0,
            "total_time_s":      0.0,
            "avg_response_time": 0.0,
            "last_error":        None,
            "last_call":         None,
        })
        stats["call_count"]   += 1
        stats["total_time_s"]  = round(stats.get("total_time_s", 0.0) + duration_s, 3)
        stats["avg_response_time"] = round(
            stats["total_time_s"] / stats["call_count"], 3
        )
        stats["last_call"] = datetime.now().isoformat()
        if error:
            stats["error_count"] += 1
            stats["last_error"]   = str(error)[:300]
        data[agent] = stats
        _save(data)


def observe_call(agent: str, thunk):
    """
    Run a zero-arg callable on behalf of `agent`, timing it and recording
    the outcome to memory/metrics.json. Re-raises any exception after
    logging it so caller behaviour is unchanged.
    """
    start = time.perf_counter()
    try:
        result = thunk()
        record_call(agent, time.perf_counter() - start)
        return result
    except Exception as e:
        record_call(agent, time.perf_counter() - start, error=f"{type(e).__name__}: {e}")
        raise


def get_metrics() -> dict:
    """Return the full metrics snapshot."""
    return _load()


def get_agent_metrics(agent: str) -> dict:
    """Return metrics for one agent (empty dict if never called)."""
    return _load().get(agent, {})


if __name__ == "__main__":
    print("TAD Observability — self test")
    observe_call("self_test", lambda: time.sleep(0.05))
    try:
        observe_call("self_test", lambda: 1 / 0)
    except ZeroDivisionError:
        pass
    print(json.dumps(get_agent_metrics("self_test"), indent=2))
