#!/usr/bin/env python3
"""
token_cost_parser.py — TAD AI
Parse and normalize token cost data from memory/outreach/ai_token_cost_tracker.json
into a unified schema (input/output tokens, model, cost per 1K tokens).

Usage:
    python token_cost_parser.py              # normal run
    python token_cost_parser.py --test       # self-check mode
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Schema target
# ---------------------------------------------------------------------------
# {
#   "model":               str,
#   "provider":            str,
#   "input_cost_per_1k":   float,   # USD per 1 000 input tokens
#   "output_cost_per_1k":  float,   # USD per 1 000 output tokens
#   "context_window":      int | None,
#   "notes":               str,
#   "raw_source":          dict     # original record, unmodified
# }

DEFAULT_PATH = Path("memory/outreach/ai_token_cost_tracker.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any, fallback: float = 0.0) -> float:
    """Best-effort conversion to float; handles None, '', '$0.002', etc."""
    if value is None:
        return fallback
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return fallback


def _to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        # accept "128k", "128000", 128000, etc.
        s = str(value).lower().replace(",", "").strip()
        if s.endswith("k"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("m"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _cost_per_1k(raw_cost: Any, unit: str = "per_1k") -> float:
    """
    Normalise cost to per-1 000-tokens regardless of how it was stored.
    unit hints: 'per_1k', 'per_1m', 'per_token'
    """
    cost = _to_float(raw_cost)
    unit = str(unit).lower()
    if "1m" in unit or "million" in unit:
        return cost / 1_000
    if "per_token" in unit or unit == "token":
        return cost * 1_000
    # default: already per 1k
    return cost


# ---------------------------------------------------------------------------
# Field-name aliases — covers common variations in the wild
# ---------------------------------------------------------------------------

_MODEL_KEYS = ("model", "model_name", "name", "model_id")
_PROVIDER_KEYS = ("provider", "vendor", "company", "org")
_INPUT_COST_KEYS = (
    "input_cost_per_1k", "input_cost", "prompt_cost",
    "prompt_price", "input_price", "cost_input",
    "input_cost_per_1m", "prompt_cost_per_1m",
)
_OUTPUT_COST_KEYS = (
    "output_cost_per_1k", "output_cost", "completion_cost",
    "completion_price", "output_price", "cost_output",
    "output_cost_per_1m", "completion_cost_per_1m",
)
_CONTEXT_KEYS = ("context_window", "context_length", "max_tokens", "window")
_NOTES_KEYS = ("notes", "note", "description", "comment", "details")


def _first(record: dict, keys: tuple, default: Any = None) -> Any:
    """Return the value of the first matching key in *record*."""
    for k in keys:
        if k in record:
            return record[k]
    return default


def _detect_unit(record: dict, cost_key: str) -> str:
    """Guess the cost unit from the key name or a sibling 'unit' field."""
    unit_field = record.get("unit") or record.get("cost_unit") or ""
    if unit_field:
        return str(unit_field).lower()
    if "1m" in cost_key or "million" in cost_key:
        return "per_1m"
    if "per_token" in cost_key:
        return "per_token"
    return "per_1k"


# ---------------------------------------------------------------------------
# Core normaliser
# ---------------------------------------------------------------------------

def normalize_record(record: dict) -> dict:
    """
    Accept one raw record (any shape) and return a normalised schema dict.
    """
    # -- model
    model = str(_first(record, _MODEL_KEYS, "unknown")).strip()

    # -- provider (fall back to extracting from model name)
    provider = str(_first(record, _PROVIDER_KEYS, "")).strip()
    if not provider:
        # heuristic: "gpt-4" → "openai", "claude-*" → "anthropic", etc.
        m = model.lower()
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
            provider = "openai"
        elif m.startswith("claude"):
            provider = "anthropic"
        elif m.startswith("gemini") or m.startswith("palm"):
            provider = "google"
        elif m.startswith("mistral") or m.startswith("mixtral"):
            provider = "mistral"
        elif m.startswith("llama") or m.startswith("meta"):
            provider = "meta"
        elif m.startswith("command"):
            provider = "cohere"
        else:
            provider = "unknown"

    # -- input cost
    input_raw_key = next(
        (k for k in _INPUT_COST_KEYS if k in record), None
    )
    input_raw_val = record.get(input_raw_key) if input_raw_key else None
    input_unit = _detect_unit(record, input_raw_key or "")
    input_cost_per_1k = _cost_per_1k(input_raw_val, input_unit)

    # -- output cost
    output_raw_key = next(
        (k for k in _OUTPUT_COST_KEYS if k in record), None
    )
    output_raw_val = record.get(output_raw_key) if output_raw_key else None
    output_unit = _detect_unit(record, output_raw_key or "")
    output_cost_per_1k = _cost_per_1k(output_raw_val, output_unit)

    # -- context window
    context_window = _to_int_or_none(_first(record, _CONTEXT_KEYS))

    # -- notes
    notes = str(_first(record, _NOTES_KEYS, "")).strip()

    return {
        "model": model,
        "provider": provider,
        "input_cost_per_1k": round(input_cost_per_1k, 8),
        "output_cost_per_1k": round(output_cost_per_1k, 8),
        "context_window": context_window,
        "notes": notes,
        "raw_source": record,
    }


# ---------------------------------------------------------------------------
# Loader — handles list, dict-of-lists, dict-of-dicts, nested wrapper keys
# ---------------------------------------------------------------------------

def _unwrap_to_list(data: Any) -> list[dict]:
    """
    The JSON file might be:
      - a list of records                         → use directly
      - {"models": [...]}                         → unwrap "models" key
      - {"data": [...]}                           → unwrap "data" key
      - {"openai": [...], "anthropic": [...]}     → flatten all lists
      - {"gpt-4": {...}, "claude-3": {...}}       → inject key as model name
    """
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]

    if isinstance(data, dict):
        # single wrapper key containing a list
        for wrapper in ("models", "data", "records", "costs", "pricing"):
            if wrapper in data and isinstance(data[wrapper], list):
                return [r for r in data[wrapper] if isinstance(r, dict)]

        # dict of lists (keyed by provider or category)
        all_records: list[dict] = []
        for key, val in data.items():
            if isinstance(val, list):
                for r in val:
                    if isinstance(r, dict):
                        # inject provider hint if not present
                        if not any(k in r for k in _PROVIDER_KEYS):
                            r = {**r, "provider": key}
                        all_records.append(r)
            elif isinstance(val, dict):
                # dict-of-dicts: key = model name
                record = {**val}
                if not any(k in record for k in _MODEL_KEYS):
                    record["model"] = key
                all_records.append(record)

        if all_records:
            return all_records

    return []


def load_and_parse(filepath: Path = DEFAULT_PATH) -> list[dict]:
    """
    Load the tracker JSON and return a list of normalised records.
    Raises FileNotFoundError if the file does not exist.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Tracker file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    raw_records = _unwrap_to_list(data)
    normalised = [normalize_record(r) for r in raw_records]
    return normalised


def print_summary(records: list[dict]) -> None:
    """Pretty-print a summary table to stdout."""
    if not records:
        print("No records found.")
        return

    header = f"{'MODEL':<30} {'PROVIDER':<12} {'IN $/1K':>10} {'OUT $/1K':>10} {'CTX WIN':>10}"
    print(header)
    print("-" * len(header))
    for r in records:
        ctx = str(r["context_window"]) if r["context_window"] else "—"
        print(
            f"{r['model']:<30} "
            f"{r['provider']:<12} "
            f"{r['input_cost_per_1k']:>10.6f} "
            f"{r['output_cost_per_1k']:>10.6f} "
            f"{ctx:>10}"
        )
    print(f"\nTotal records: {len(records)}")


# ---------------------------------------------------------------------------
# Self-check / test mode
# ---------------------------------------------------------------------------

_SAMPLE_DATA_CASES: list[tuple[str, Any, dict]] = [
    # (description, raw_record, expected_subset)
    (
        "Standard per-1k keys",
        {
            "model": "gpt-4o",
            "provider": "openai",
            "input_cost_per_1k": 0.005,
            "output_cost_per_1k": 0.015,
            "context_window": 128000,
        },
        {"model": "gpt-4o", "provider": "openai",
         "input_cost_per_1k": 0.005, "output_cost_per_1k": 0.015,
         "context_window": 128000},
    ),
    (
        "Per-million cost keys + string dollar values",
        {
            "model_name": "claude-3-opus",
            "prompt_cost_per_1m": "$15.00",
            "completion_cost_per_1m": "$75.00",
            "context_length": "200k",
        },
        {"model": "claude-3-opus", "provider": "anthropic",
         "input_cost_per_1k": 0.015, "output_cost_per_1k": 0.075,
         "context_window": 200_000},
    ),
    (
        "Provider inferred from model name",
        {"name": "gemini-1.5-pro", "input_cost": 0.0035, "output_cost": 0.0105},
        {"provider": "google"},
    ),
    (
        "Context window as '128k' string",
        {"model": "test-model", "max_tokens": "128k",
         "input_cost_per_1k": 0.001, "output_cost_per_1k": 0.002},
        {"context_window": 128_000},
    ),
    (
        "Missing costs default to 0.0",
        {"model": "free-model"},
        {"input_cost_per_1k": 0.0, "output_cost_per_1k": 0.0},
    ),
]

_UNWRAP_CASES: list[tuple[str, Any, int]] = [
    # (description, raw_json, expected_record_count)
    ("Plain list", [{"model": "a"}, {"model": "b"}], 2),
    ("Wrapper key 'models'", {"models": [{"model": "x"}, {"model": "y"}, {"model": "z"}]}, 3),
    ("Dict-of-lists (provider-keyed)", {"openai": [{"model": "gpt-4"}], "anthropic": [{"model": "claude-3"}]}, 2),
    ("Dict-of-dicts (model-keyed)", {"gpt-3.5": {"input_cost_per_1k": 0.001}, "gpt-4": {"input_cost_per_1k": 0.01}}, 2),
]


def _assert_subset(actual: dict, expected: dict, label: str) -> None:
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if isinstance(exp_val, float):
            assert abs(act_val - exp_val) < 1e-9, (
                f"[{label}] {key}: expected {exp_val}, got {act_val}"
            )
        else:
            assert act_val == exp_val, (
                f"[{label}] {key}: expected {exp_val!r}, got {act_val!r}"
            )


def run_tests() -> None:
    print("=" * 60)
    print("TAD token_cost_parser — self-check mode")
    print("=" * 60)

    # --- normalize_record tests
    print("\n[1] normalize_record() tests")
    passed = 0
    for desc, raw, expected in _SAMPLE_DATA_CASES:
        try:
            result = normalize_record(raw)
            _assert_subset(result, expected, desc)
            print(f"  ✓  {desc}")
            passed += 1
        except AssertionError as exc:
            print(f"  ✗  {desc}\n     {exc}")

    # --- _unwrap_to_list tests
    print("\n[2] _unwrap_to_list() tests")
    for desc, raw, count in _UNWRAP_CASES:
        records = _unwrap_to_list(raw)
        try:
            assert len(records) == count, f"expected {count} records, got {len(records)}"
            print(f"  ✓  {desc}")
            passed += 1
        except AssertionError as exc:
            print(f"  ✗  {desc} — {exc}")

    # --- round-trip with synthetic file
    print("\n[3] Round-trip load_and_parse() with synthetic JSON")
    import tempfile
    synthetic = {
        "models": [
            {"model": "gpt-4o-mini", "provider": "openai",
             "input_cost_per_1k": 0.00015, "output_cost_per_1k": 0.0006,
             "context_window": 128000, "notes": "fast and cheap"},
            {"model_name": "claude-3-haiku", "provider": "anthropic",
             "prompt_cost_per_1m": "0.25", "completion_cost_per_1m": "1.25",
             "context_length": "200k"},
        ]
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(synthetic, tmp)
        tmp_path = Path(tmp.name)

    try:
        records = load_and_parse(tmp_path)
        assert len(records) == 2, f"expected 2, got {len(records)}"
        r0 = records[0]
        assert r0["model"] == "gpt-4o-mini"
        assert r0["input_cost_per_1k"] == 0.00015
        r1 = records[1]
        assert r1["model"] == "claude-3-haiku"
        assert abs(r1["input_cost_per_1k"] - 0.00025) < 1e-9, r1["input_cost_per_1k"]
        assert r1["context_window"] == 200_000
        print("  ✓  Round-trip load + parse + schema validation")
        passed += 1
        print("\n  Parsed output:")
        print_summary(records)
    except AssertionError as exc:
        print(f"  ✗  Round-trip failed: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)

    total = len(_SAMPLE_DATA_CASES) + len(_UNWRAP_CASES) + 1
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} passed")
    if passed < total:
        sys.exit(1)
    print("All tests passed ✓")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    if "--test" in sys.argv:
        run_tests()
        return

    # normal run: parse the real tracker file
    filepath = DEFAULT_PATH
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            filepath = Path(arg)

    try:
        records = load_and_parse(filepath)
        print(f"Loaded {len(records)} records from {filepath}\n")
        print_summary(records)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("Tip: run with --test to verify the module without a real file.")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Could not parse JSON — {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()