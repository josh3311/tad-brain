#!/usr/bin/env python3
"""
ai_token_cost_tracker.py — TAD Module
Parses and stores LLM API call logs into memory/outreach/ai_token_cost_tracker.json
Run with --test for self-check mode.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TRACKER_PATH = Path("memory/outreach/ai_token_cost_tracker.json")

# Cost per 1K tokens (input, output) in USD — extend as needed
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o":                {"input": 0.005,   "output": 0.015},
    "gpt-4o-mini":           {"input": 0.000150,"output": 0.000600},
    "gpt-4-turbo":           {"input": 0.010,   "output": 0.030},
    "gpt-3.5-turbo":         {"input": 0.0005,  "output": 0.0015},
    "claude-3-5-sonnet":     {"input": 0.003,   "output": 0.015},
    "claude-3-opus":         {"input": 0.015,   "output": 0.075},
    "claude-3-haiku":        {"input": 0.00025, "output": 0.00125},
    "gemini-1.5-pro":        {"input": 0.00125, "output": 0.005},
    "kimi":                  {"input": 0.0014,  "output": 0.0014},
    "deepseek-chat":         {"input": 0.00014, "output": 0.00028},
}

UNKNOWN_MODEL_FALLBACK = {"input": 0.002, "output": 0.002}


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _load_tracker() -> dict:
    """Load existing tracker file or return a fresh structure."""
    if TRACKER_PATH.exists():
        try:
            with open(TRACKER_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Validate top-level keys
            if "meta" not in data or "calls" not in data:
                raise ValueError("Malformed tracker file — rebuilding.")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            print(f"[ai_token_cost_tracker] WARNING: {e}")

    return {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": None,
            "total_calls": 0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "total_cost_usd": 0.0,
            "currency": "USD",
        },
        "calls": [],
    }


def _save_tracker(data: dict) -> None:
    """Persist tracker to disk atomically."""
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = TRACKER_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(TRACKER_PATH)


# ---------------------------------------------------------------------------
# Core: compute cost
# ---------------------------------------------------------------------------

def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """
    Return USD cost for one API call.
    Pricing is per-1K tokens.
    """
    pricing = MODEL_PRICING.get(model.lower().strip(), UNKNOWN_MODEL_FALLBACK)
    cost = (tokens_in / 1000.0) * pricing["input"] + \
           (tokens_out / 1000.0) * pricing["output"]
    return round(cost, 8)


# ---------------------------------------------------------------------------
# Core: log one call
# ---------------------------------------------------------------------------

def log_call(
    model: str,
    tokens_in: int,
    tokens_out: int,
    *,
    timestamp: str | None = None,
    call_id: str | None = None,
    tags: list[str] | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Parse and store one LLM API call.

    Parameters
    ----------
    model       : model identifier, e.g. "gpt-4o"
    tokens_in   : prompt / input token count
    tokens_out  : completion / output token count
    timestamp   : ISO-8601 string; defaults to UTC now
    call_id     : unique id; auto-generated if omitted
    tags        : optional list of string labels
    extra       : arbitrary metadata dict stored verbatim

    Returns
    -------
    The call record dict that was written to disk.
    """
    if tokens_in < 0 or tokens_out < 0:
        raise ValueError("Token counts must be non-negative.")
    if not model:
        raise ValueError("model must be a non-empty string.")

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    cid = call_id or str(uuid.uuid4())
    cost = compute_cost(model, tokens_in, tokens_out)

    record = {
        "call_id":    cid,
        "timestamp":  ts,
        "model":      model,
        "tokens_in":  tokens_in,
        "tokens_out": tokens_out,
        "tokens_total": tokens_in + tokens_out,
        "cost_usd":   cost,
        "tags":       tags or [],
        "extra":      extra or {},
    }

    data = _load_tracker()
    data["calls"].append(record)

    m = data["meta"]
    m["last_updated"]    = datetime.now(timezone.utc).isoformat()
    m["total_calls"]     += 1
    m["total_tokens_in"] += tokens_in
    m["total_tokens_out"]+= tokens_out
    m["total_cost_usd"]   = round(m["total_cost_usd"] + cost, 8)

    _save_tracker(data)
    return record


# ---------------------------------------------------------------------------
# Core: bulk ingest raw log list
# ---------------------------------------------------------------------------

def ingest_log_list(entries: list[dict]) -> list[dict]:
    """
    Ingest a list of raw log dicts.
    Each dict must have: model, tokens_in, tokens_out
    Optional keys: timestamp, call_id, tags, extra

    Returns list of stored records.
    """
    stored = []
    for i, entry in enumerate(entries):
        try:
            rec = log_call(
                model      = entry["model"],
                tokens_in  = int(entry["tokens_in"]),
                tokens_out = int(entry["tokens_out"]),
                timestamp  = entry.get("timestamp"),
                call_id    = entry.get("call_id"),
                tags       = entry.get("tags"),
                extra      = entry.get("extra"),
            )
            stored.append(rec)
        except (KeyError, ValueError) as e:
            print(f"[ai_token_cost_tracker] SKIP entry {i}: {e}")
    return stored


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_summary() -> dict:
    """Return the meta block from the tracker."""
    return _load_tracker()["meta"]


def get_calls(
    model: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return call records, optionally filtered by model, newest first."""
    calls = _load_tracker()["calls"]
    if model:
        calls = [c for c in calls if c["model"] == model.lower().strip()]
    calls = list(reversed(calls))
    if limit:
        calls = calls[:limit]
    return calls


# ---------------------------------------------------------------------------
# NEW FEATURE: aggregated cost summary
# ---------------------------------------------------------------------------

def _parse_day(timestamp: str) -> str:
    """
    Extract the UTC date string (YYYY-MM-DD) from an ISO-8601 timestamp.

    Handles:
      - timestamps with UTC offset  "2026-01-15T12:00:00+00:00"
      - timestamps with Z suffix    "2026-01-15T12:00:00Z"
      - naive timestamps             "2026-01-15T12:00:00"
      - date-only strings            "2026-01-15"

    Returns "unknown" if the timestamp cannot be parsed.
    """
    if not timestamp:
        return "unknown"
    # Normalise Z → +00:00 so fromisoformat handles it on Python < 3.11
    normalised = timestamp.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalised)
        # Convert to UTC so days are always aligned to the same timezone
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        # Fall back: grab the first 10 characters if they look like a date
        if len(timestamp) >= 10 and timestamp[4] == "-" and timestamp[7] == "-":
            return timestamp[:10]
        return "unknown"


def summary() -> dict:
    """
    Return aggregated cost statistics across all logged calls.

    Returns
    -------
    {
        "total_cost": float,          # sum of all cost_usd values
        "by_model": {                 # per-model breakdown
            "<model>": {
                "calls":       int,
                "tokens_in":   int,
                "tokens_out":  int,
                "cost_usd":    float,
            },
            ...
        },
        "by_day": {                   # per-UTC-day breakdown
            "YYYY-MM-DD": {
                "calls":       int,
                "tokens_in":   int,
                "tokens_out":  int,
                "cost_usd":    float,
            },
            ...
        },
    }
    """
    calls = _load_tracker()["calls"]

    total_cost: float = 0.0
    by_model: dict[str, dict] = {}
    by_day:   dict[str, dict] = {}

    def _blank_bucket() -> dict:
        return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    for call in calls:
        model  = call.get("model", "unknown")
        day    = _parse_day(call.get("timestamp", ""))
        tin    = call.get("tokens_in",  0)
        tout   = call.get("tokens_out", 0)
        cost   = call.get("cost_usd",   0.0)

        total_cost = round(total_cost + cost, 8)

        # --- by_model ---
        if model not in by_model:
            by_model[model] = _blank_bucket()
        bm = by_model[model]
        bm["calls"]      += 1
        bm["tokens_in"]  += tin
        bm["tokens_out"] += tout
        bm["cost_usd"]    = round(bm["cost_usd"] + cost, 8)

        # --- by_day ---
        if day not in by_day:
            by_day[day] = _blank_bucket()
        bd = by_day[day]
        bd["calls"]      += 1
        bd["tokens_in"]  += tin
        bd["tokens_out"] += tout
        bd["cost_usd"]    = round(bd["cost_usd"] + cost, 8)

    return {
        "total_cost": total_cost,
        "by_model":   by_model,
        "by_day":     by_day,
    }


# ---------------------------------------------------------------------------
# --test self-check
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """Self-contained test suite. Uses an isolated temp tracker path."""
    import tempfile

    global TRACKER_PATH
    original_path = TRACKER_PATH

    with tempfile.TemporaryDirectory() as tmp_dir:
        TRACKER_PATH = Path(tmp_dir) / "memory/outreach/ai_token_cost_tracker.json"

        passed = 0
        failed = 0

        def ok(label: str) -> None:
            nonlocal passed
            passed += 1
            print(f"  ✓ {label}")

        def fail(label: str, reason: str) -> None:
            nonlocal failed
            failed += 1
            print(f"  ✗ {label}: {reason}")

        print("\n[TAD] ai_token_cost_tracker — self-check\n")

        # ------------------------------------------------------------------
        # T1: compute_cost known model
        # ------------------------------------------------------------------
        label = "T1: compute_cost gpt-4o"
        try:
            cost = compute_cost("gpt-4o", 1000, 500)
            expected = round((1.0 * 0.005) + (0.5 * 0.015), 8)  # 0.0125
            assert abs(cost - expected) < 1e-9, f"got {cost}, want {expected}"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T2: compute_cost unknown model uses fallback
        # ------------------------------------------------------------------
        label = "T2: compute_cost unknown model fallback"
        try:
            cost = compute_cost("mystery-model-9000", 500, 500)
            expected = round((0.5 * 0.002) + (0.5 * 0.002), 8)
            assert abs(cost - expected) < 1e-9, f"got {cost}"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T3: log_call creates file and record
        # ------------------------------------------------------------------
        label = "T3: log_call creates tracker file"
        try:
            assert not TRACKER_PATH.exists(), "file should not exist yet"
            rec = log_call("claude-3-5-sonnet", 800, 200)
            assert TRACKER_PATH.exists(), "tracker file not created"
            assert rec["model"] == "claude-3-5-sonnet"
            assert rec["tokens_in"] == 800
            assert rec["tokens_out"] == 200
            assert rec["tokens_total"] == 1000
            assert isinstance(rec["call_id"], str) and len(rec["call_id"]) == 36
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T4: log_call meta totals accumulate correctly
        # ------------------------------------------------------------------
        label = "T4: meta totals accumulate"
        try:
            log_call("gpt-4o-mini", 400, 100)
            s = get_summary()
            assert s["total_calls"] == 2, f"calls={s['total_calls']}"
            assert s["total_tokens_in"] == 1200
            assert s["total_tokens_out"] == 300
            assert s["total_cost_usd"] > 0
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T5: explicit timestamp and call_id are preserved
        # ------------------------------------------------------------------
        label = "T5: explicit timestamp + call_id preserved"
        try:
            ts  = "2026-01-15T12:00:00+00:00"
            cid = "test-call-0001"
            rec = log_call("kimi", 100, 100, timestamp=ts, call_id=cid)
            assert rec["timestamp"] == ts, f"ts={rec['timestamp']}"
            assert rec["call_id"] == cid, f"id={rec['call_id']}"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T6: tags and extra stored verbatim
        # ------------------------------------------------------------------
        label = "T6: tags and extra stored verbatim"
        try:
            rec = log_call(
                "deepseek-chat", 300, 150,
                tags=["outreach", "scan"],
                extra={"agent": "market_agent", "run_id": "abc"},
            )
            assert rec["tags"] == ["outreach", "scan"]
            assert rec["extra"]["agent"] == "market_agent"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T7: negative token count raises ValueError
        # ------------------------------------------------------------------
        label = "T7: negative tokens raises ValueError"
        try:
            try:
                log_call("gpt-4o", -1, 100)
                fail(label, "no exception raised")
            except ValueError:
                ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T8: get_calls filter by model
        # ------------------------------------------------------------------
        label = "T8: get_calls filter by model"
        try:
            calls = get_calls(model="kimi")
            assert len(calls) == 1, f"got {len(calls)}"
            assert calls[0]["model"] == "kimi"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T9: get_calls limit
        # ------------------------------------------------------------------
        label = "T9: get_calls limit"
        try:
            all_calls = get_calls()
            limited   = get_calls(limit=2)
            assert len(limited) == 2, f"got {len(limited)}"
            assert len(all_calls) > 2
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T10: ingest_log_list bulk ingest
        # ------------------------------------------------------------------
        label = "T10: ingest_log_list bulk"
        try:
            before = get_summary()["total_calls"]
            raw_logs = [
                {"model": "gpt-3.5-turbo", "tokens_in": 200, "tokens_out": 80},
                {"model": "gemini-1.5-pro", "tokens_in": 500, "tokens_out": 300,
                 "tags": ["batch"], "extra": {"source": "test"}},
                {"model": "bad-entry"},   # missing tokens — should be skipped
            ]
            stored = ingest_log_list(raw_logs)
            after = get_summary()["total_calls"]
            assert len(stored) == 2, f"stored={len(stored)}"
            assert after == before + 2, f"calls went {before}->{after}"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T11: tracker JSON is valid after all writes
        # ------------------------------------------------------------------
        label = "T11: tracker JSON valid on disk"
        try:
            with open(TRACKER_PATH, "r") as f:
                data = json.load(f)
            assert "meta" in data and "calls" in data
            assert isinstance(data["calls"], list)
            assert data["meta"]["total_calls"] == len(data["calls"])
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T12: cost_usd in every record is a float >= 0
        # ------------------------------------------------------------------
        label = "T12: cost_usd non-negative float in every record"
        try:
            calls = get_calls()
            bad = [c for c in calls if not isinstance(c["cost_usd"], float) or c["cost_usd"] < 0]
            assert not bad, f"{len(bad)} bad records"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T13: summary() top-level keys present
        # ------------------------------------------------------------------
        label = "T13: summary() returns required top-level keys"
        try:
            agg = summary()
            assert "total_cost" in agg, "missing total_cost"
            assert "by_model"   in agg, "missing by_model"
            assert "by_day"     in agg, "missing by_day"
            assert isinstance(agg["total_cost"], float), "total_cost not float"
            assert isinstance(agg["by_model"],   dict),  "by_model not dict"
            assert isinstance(agg["by_day"],     dict),  "by_day not dict"
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T14: summary() total_cost matches sum of individual records
        # ------------------------------------------------------------------
        label = "T14: summary() total_cost matches per-record sum"
        try:
            calls = get_calls()
            expected_total = round(sum(c["cost_usd"] for c in calls), 8)
            agg = summary()
            assert abs(agg["total_cost"] - expected_total) < 1e-7, (
                f"total_cost={agg['total_cost']} expected={expected_total}"
            )
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T15: summary() by_model buckets have correct structure and totals
        # ------------------------------------------------------------------
        label = "T15: summary() by_model bucket structure and totals"
        try:
            agg = summary()
            calls = get_calls()

            # Every model that appears in calls must be in by_model
            models_in_calls = {c["model"] for c in calls}
            assert models_in_calls == set(agg["by_model"].keys()), (
                f"model key mismatch: calls={models_in_calls} "
                f"by_model={set(agg['by_model'].keys())}"
            )

            # Verify bucket fields and value consistency for one known model
            # "kimi" was logged exactly once with 100 in / 100 out
            kimi_bucket = agg["by_model"]["kimi"]
            assert kimi_bucket["calls"]     == 1,   f"calls={kimi_bucket['calls']}"
            assert kimi_bucket["tokens_in"] == 100, f"tokens_in={kimi_bucket['tokens_in']}"
            assert kimi_bucket["tokens_out"]== 100, f"tokens_out={kimi_bucket['tokens_out']}"
            assert isinstance(kimi_bucket["cost_usd"], float)
            assert kimi_bucket["cost_usd"]  >  0

            # Required keys in every bucket
            required_keys = {"calls", "tokens_in", "tokens_out", "cost_usd"}
            for mdl, bucket in agg["by_model"].items():
                missing = required_keys - set(bucket.keys())
                assert not missing, f"model '{mdl}' bucket missing keys: {missing}"

            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T16: summary() by_day buckets have correct structure
        # ------------------------------------------------------------------
        label = "T16: summary() by_day bucket structure"
        try:
            agg = summary()
            required_keys = {"calls", "tokens_in", "tokens_out", "cost_usd"}
            assert len(agg["by_day"]) >= 1, "by_day should have at least one entry"
            for day, bucket in agg["by_day"].items():
                # Day key must look like YYYY-MM-DD or "unknown"
                assert (
                    day == "unknown" or
                    (len(day) == 10 and day[4] == "-" and day[7] == "-")
                ), f"unexpected day key format: '{day}'"
                missing = required_keys - set(bucket.keys())
                assert not missing, f"day '{day}' bucket missing keys: {missing}"
                assert isinstance(bucket["cost_usd"], float)
                assert bucket["calls"] >= 1

            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T17: summary() by_day groups calls on the same day together
        # ------------------------------------------------------------------
        label = "T17: summary() by_day groups same-day calls correctly"
        try:
            # Log two calls with identical explicit dates on a fresh sub-tracker
            # We need a clean slate for predictable counts, so we save/restore
            old_path = TRACKER_PATH
            TRACKER_PATH = Path(tmp_dir) / "memory/outreach/day_test.json"

            log_call("gpt-4o", 100, 50,  timestamp="2030-03-10T08:00:00+00:00")
            log_call("gpt-4o", 200, 100, timestamp="2030-03-10T22:59:59+00:00")
            log_call("gpt-4o", 50,  25,  timestamp="2030-03-11T00:00:01+00:00")

            agg = summary()
            assert "2030-03-10" in agg["by_day"], "expected day 2030-03-10"
            assert "2030-03-11" in agg["by_day"], "expected day 2030-03-11"
            assert agg["by_day"]["2030-03-10"]["calls"] == 2, (
                f"expected 2 calls on 2030-03-10, got {agg['by_day']['2030-03-10']['calls']}"
            )
            assert agg["by_day"]["2030-03-11"]["calls"] == 1, (
                f"expected 1 call on 2030-03-11, got {agg['by_day']['2030-03-11']['calls']}"
            )
            assert abs(
                agg["by_day"]["2030-03-10"]["tokens_in"] - 300
            ) == 0, "tokens_in mismatch for 2030-03-10"

            # Restore tracker path
            TRACKER_PATH = old_path
            ok(label)
        except Exception as e:
            # Always restore path even on failure
            TRACKER_PATH = Path(tmp_dir) / "memory/outreach/ai_token_cost_tracker.json"
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T18: summary() by_model cost sum equals total_cost
        # ------------------------------------------------------------------
        label = "T18: summary() by_model cost sum equals total_cost"
        try:
            agg = summary()
            model_cost_sum = round(
                sum(b["cost_usd"] for b in agg["by_model"].values()), 8
            )
            assert abs(model_cost_sum - agg["total_cost"]) < 1e-7, (
                f"by_model sum={model_cost_sum} total_cost={agg['total_cost']}"
            )
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T19: summary() by_day cost sum equals total_cost
        # ------------------------------------------------------------------
        label = "T19: summary() by_day cost sum equals total_cost"
        try:
            agg = summary()
            day_cost_sum = round(
                sum(b["cost_usd"] for b in agg["by_day"].values()), 8
            )
            assert abs(day_cost_sum - agg["total_cost"]) < 1e-7, (
                f"by_day sum={day_cost_sum} total_cost={agg['total_cost']}"
            )
            ok(label)
        except Exception as e:
            fail(label, str(e))

        # ------------------------------------------------------------------
        # T20: summary() on empty tracker returns zeroed structure
        # ------------------------------------------------------------------
        label = "T20: summary() on empty tracker returns zeroed structure"
        try:
            old_path = TRACKER_PATH
            TRACKER_PATH = Path(tmp_dir) / "memory/outreach/empty_test.json"
            # Do not log anything — file doesn't even exist
            agg = summary()
            assert agg["total_cost"] == 0.0, f"total_cost={agg['total_cost']}"
            assert agg["by_model"]   == {},   f"by_model={agg['by_model']}"
            assert agg["by_day"]     == {},   f"by_day={agg['by_day']}"
            TRACKER_PATH = old_path
            ok(label)
        except Exception as e:
            TRACKER_PATH = Path(tmp_dir) / "memory/outreach/ai_token_cost_tracker.json"
            fail(label, str(e))

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        total = passed + failed
        print(f"\n  Results: {passed}/{total} passed", end="")
        if failed:
            print(f"  ({failed} FAILED)")
            TRACKER_PATH = original_path
            sys.exit(1)
        else:
            print(" — all good ✓")

    TRACKER_PATH = original_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_tests()
    else:
        # Quick demo: log a sample call and print summary
        print("[ai_token_cost_tracker] Logging sample call...")
        rec = log_call(
            model="gpt-4o",
            tokens_in=1500,
            tokens_out=420,
            tags=["demo"],
            extra={"agent": "market_agent"},
        )
        print(f"  Logged: {rec['call_id']} | cost=${rec['cost_usd']:.6f}")
        meta = get_summary()
        print(f"  Tracker summary: {json.dumps(meta, indent=2)}")
        agg = summary()
        print(f"  Aggregated summary: {json.dumps(agg, indent=2)}")
        print(f"  Saved to: {TRACKER_PATH.resolve()}")