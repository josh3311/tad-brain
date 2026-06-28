#!/usr/bin/env python3
"""
skills/learned/parse_token_cost_data.py
TAD Learned Skill — Parse and Normalize Token Cost Data

Reads memory/outreach/ai_token_cost_tracker.json and displays:
  - Total cost across all records
  - Cost per model breakdown
  - Date range of tracked data
  - Cost comparison: most/least expensive models + budget overrun flags

Run normally:  python skills/learned/parse_token_cost_data.py
Self-check:    python skills/learned/parse_token_cost_data.py --test
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Any

# ── Path resolution (works from any cwd) ──────────────────────────────────────
SKILL_FILE   = Path(__file__).resolve()

def _find_project_root(skill_file: Path) -> Path:
    """
    Walk up from the skill file's directory until we find a plausible
    project root (contains a 'memory' folder or we reach the filesystem root).
    Falls back to the directory the script lives in if nothing is found.
    """
    candidate = skill_file.parent
    while True:
        if (candidate / "memory").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:          # filesystem root
            break
        candidate = parent
    # Last resort: use the script's own directory
    return skill_file.parent

PROJECT_ROOT = _find_project_root(SKILL_FILE)
DEFAULT_DATA = PROJECT_ROOT / "memory" / "outreach" / "ai_token_cost_tracker.json"


# ── Default budget thresholds ─────────────────────────────────────────────────
DEFAULT_THRESHOLDS: dict[str, float] = {
    "__total__":          10.00,
    "claude":              5.00,
    "gpt-4":               4.00,
    "gemini":              2.00,
}


# ── Schema normalizer ─────────────────────────────────────────────────────────
def normalize_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    """
    Accept any reasonable field-name variant and return a canonical record:
      {
        "model":         str,
        "date":          str   (ISO date or empty),
        "input_tokens":  int,
        "output_tokens": int,
        "total_tokens":  int,
        "cost_usd":      float,
      }
    Returns None if the record cannot be meaningfully parsed.
    """
    def pick(d: dict, *keys, default=None):
        for k in keys:
            if k in d:
                return d[k]
        return default

    model = pick(raw,
                 "model", "model_name", "modelName", "Model",
                 default="unknown")

    date_raw = pick(raw,
                    "date", "timestamp", "created_at", "Date",
                    default="")
    date_str = ""
    if date_raw:
        try:
            dt = datetime.fromisoformat(str(date_raw).replace("Z", "+00:00"))
            date_str = dt.date().isoformat()
        except ValueError:
            date_str = str(date_raw)[:10]

    input_tokens  = int(pick(raw,
                             "input_tokens", "prompt_tokens",
                             "inputTokens", "in_tokens", default=0) or 0)
    output_tokens = int(pick(raw,
                             "output_tokens", "completion_tokens",
                             "outputTokens", "out_tokens", default=0) or 0)
    total_tokens  = int(pick(raw,
                             "total_tokens", "totalTokens",
                             default=input_tokens + output_tokens) or 0)

    cost_raw = pick(raw,
                    "cost_usd", "cost", "total_cost", "costUSD",
                    "price_usd", "amount_usd", default=None)
    if cost_raw is None:
        rate_in  = float(pick(raw, "cost_per_1k_input",  "rate_in",  default=0) or 0)
        rate_out = float(pick(raw, "cost_per_1k_output", "rate_out", default=0) or 0)
        if rate_in or rate_out:
            cost_raw = (input_tokens / 1000 * rate_in +
                        output_tokens / 1000 * rate_out)
        else:
            cost_raw = 0.0

    cost_usd = float(cost_raw or 0.0)

    if not model and not total_tokens and cost_usd == 0.0:
        return None

    return {
        "model":         str(model),
        "date":          date_str,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "total_tokens":  total_tokens,
        "cost_usd":      cost_usd,
    }


# ── Core parser ───────────────────────────────────────────────────────────────
def parse_token_cost_file(filepath: Path) -> list[dict[str, Any]]:
    """
    Load the JSON file (array or dict-of-arrays) and return
    a list of normalized records.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        raw_data = json.load(fh)

    if isinstance(raw_data, list):
        records_raw = raw_data
    elif isinstance(raw_data, dict):
        list_values = [v for v in raw_data.values() if isinstance(v, list)]
        if list_values:
            records_raw = list_values[0]
        else:
            records_raw = [raw_data]
    else:
        raise ValueError(f"Unexpected JSON structure: {type(raw_data)}")

    normalized = []
    for raw in records_raw:
        if not isinstance(raw, dict):
            continue
        rec = normalize_record(raw)
        if rec is not None:
            normalized.append(rec)

    return normalized


# ── Stats calculator ──────────────────────────────────────────────────────────
def compute_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Return summary statistics:
      total_cost, total_tokens, per_model breakdown, date_range
    """
    if not records:
        return {
            "record_count":   0,
            "total_cost_usd": 0.0,
            "total_tokens":   0,
            "date_range":     {"earliest": "n/a", "latest": "n/a"},
            "per_model":      {},
        }

    total_cost   = 0.0
    total_tokens = 0
    dates: list[str] = []
    per_model: dict[str, dict[str, float | int]] = defaultdict(lambda: {
        "record_count":   0,
        "input_tokens":   0,
        "output_tokens":  0,
        "total_tokens":   0,
        "total_cost_usd": 0.0,
    })

    for r in records:
        total_cost   += r["cost_usd"]
        total_tokens += r["total_tokens"]
        if r["date"]:
            dates.append(r["date"])

        m = per_model[r["model"]]
        m["record_count"]   += 1
        m["input_tokens"]   += r["input_tokens"]
        m["output_tokens"]  += r["output_tokens"]
        m["total_tokens"]   += r["total_tokens"]
        m["total_cost_usd"] += r["cost_usd"]

    for m_data in per_model.values():
        tt   = m_data["total_tokens"]
        cost = m_data["total_cost_usd"]
        m_data["cost_per_1k_tokens"] = round((cost / tt * 1000), 6) if tt else 0.0
        m_data["total_cost_usd"]     = round(cost, 6)

    dates_sorted = sorted(set(dates))

    return {
        "record_count":   len(records),
        "total_cost_usd": round(total_cost,   6),
        "total_tokens":   total_tokens,
        "date_range": {
            "earliest": dates_sorted[0]  if dates_sorted else "n/a",
            "latest":   dates_sorted[-1] if dates_sorted else "n/a",
        },
        "per_model": dict(per_model),
    }


# ── Cost comparison ───────────────────────────────────────────────────────────
def compare_model_costs(
    stats: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Analyse per-model cost data and return a comparison report.
    """
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS

    per_model = stats.get("per_model", {})

    # ── Rank models by total cost (desc) ──────────────────────────────────────
    ranked = sorted(
        [
            {
                "model":              name,
                "total_cost_usd":     md["total_cost_usd"],
                "cost_per_1k_tokens": md["cost_per_1k_tokens"],
            }
            for name, md in per_model.items()
        ],
        key=lambda x: x["total_cost_usd"],
        reverse=True,
    )

    models_with_spend = [m for m in ranked if m["total_cost_usd"] > 0]
    models_with_rate  = [m for m in ranked if m["cost_per_1k_tokens"] > 0]

    most_expensive_model  = ranked[0]["model"]             if ranked              else None
    least_expensive_model = models_with_spend[-1]["model"] if models_with_spend  else None

    rate_ranked        = sorted(models_with_rate,
                                key=lambda x: x["cost_per_1k_tokens"],
                                reverse=True)
    highest_rate_model = rate_ranked[0]["model"]  if rate_ranked else None
    lowest_rate_model  = rate_ranked[-1]["model"] if rate_ranked else None

    # ── Budget overrun detection ───────────────────────────────────────────────
    overruns: list[dict[str, Any]] = []

    total_limit = thresholds.get("__total__")
    if total_limit is not None:
        spent = stats.get("total_cost_usd", 0.0)
        if spent > total_limit:
            over_by = round(spent - total_limit, 6)
            overruns.append({
                "scope":     "__total__",
                "spent_usd": round(spent, 6),
                "limit_usd": round(total_limit, 6),
                "over_by":   over_by,
                "pct_over":  round(over_by / total_limit * 100, 2),
            })

    for model_name, md in per_model.items():
        model_lower = model_name.lower()
        for tkey, tlimit in thresholds.items():
            if tkey == "__total__":
                continue
            if tkey.lower() in model_lower or model_lower == tkey.lower():
                spent = md["total_cost_usd"]
                if spent > tlimit:
                    over_by = round(spent - tlimit, 6)
                    overruns.append({
                        "scope":     model_name,
                        "spent_usd": round(spent, 6),
                        "limit_usd": round(tlimit, 6),
                        "over_by":   over_by,
                        "pct_over":  round(over_by / tlimit * 100, 2),
                    })
                break

    seen_scopes: set[str] = set()
    unique_overruns = []
    for o in overruns:
        if o["scope"] not in seen_scopes:
            seen_scopes.add(o["scope"])
            unique_overruns.append(o)

    return {
        "most_expensive_model":  most_expensive_model,
        "least_expensive_model": least_expensive_model,
        "highest_rate_model":    highest_rate_model,
        "lowest_rate_model":     lowest_rate_model,
        "ranked_by_total_cost":  ranked,
        "budget_overruns":       unique_overruns,
        "thresholds_used":       thresholds,
    }


# ── Display ───────────────────────────────────────────────────────────────────
def display_stats(stats: dict[str, Any], source_path: Path) -> None:
    sep  = "─" * 60
    sep2 = "═" * 60

    print(f"\n{sep2}")
    print("  TAD · AI Token Cost Tracker — Summary")
    print(f"  Source : {source_path}")
    print(sep2)
    print(f"  Records parsed : {stats['record_count']:>10,}")
    print(f"  Total tokens   : {stats['total_tokens']:>10,}")
    print(f"  Total cost     : ${stats['total_cost_usd']:>12,.6f} USD")
    dr = stats["date_range"]
    print(f"  Date range     :  {dr['earliest']}  →  {dr['latest']}")
    print(sep)

    if stats["per_model"]:
        print("  Cost per Model")
        print(sep)
        sorted_models = sorted(
            stats["per_model"].items(),
            key=lambda kv: kv[1]["total_cost_usd"],
            reverse=True,
        )
        col_w = max(len(m) for m, _ in sorted_models) + 2
        header = (f"  {'Model':<{col_w}} {'Records':>8}  "
                  f"{'Tokens':>12}  {'Cost (USD)':>14}  {'$/1K tok':>10}")
        print(header)
        print(f"  {sep}")
        for model_name, md in sorted_models:
            print(
                f"  {model_name:<{col_w}} "
                f"{md['record_count']:>8,}  "
                f"{md['total_tokens']:>12,}  "
                f"${md['total_cost_usd']:>13,.6f}  "
                f"${md['cost_per_1k_tokens']:>9,.6f}"
            )
    else:
        print("  (no model data)")

    print(sep2)
    print()


def display_comparison(comparison: dict[str, Any]) -> None:
    """Pretty-print the cost comparison / budget overrun report."""
    sep  = "─" * 60
    sep2 = "═" * 60

    print(f"{sep2}")
    print("  TAD · AI Token Cost Tracker — Cost Comparison")
    print(sep2)

    def _fmt(val: str | None) -> str:
        return val if val else "(none)"

    print(f"  Most expensive model  (total $) : {_fmt(comparison['most_expensive_model'])}")
    print(f"  Least expensive model (total $) : {_fmt(comparison['least_expensive_model'])}")
    print(f"  Highest rate model    ($/1K tok): {_fmt(comparison['highest_rate_model'])}")
    print(f"  Lowest  rate model    ($/1K tok): {_fmt(comparison['lowest_rate_model'])}")
    print(sep)

    ranked = comparison["ranked_by_total_cost"]
    if ranked:
        print("  Ranked by Total Cost (descending)")
        print(sep)
        col_w = max(len(r["model"]) for r in ranked) + 2
        print(f"  {'Model':<{col_w}} {'Total Cost':>14}  {'$/1K Tokens':>13}  Rank")
        print(f"  {sep}")
        for i, r in enumerate(ranked, 1):
            tag = "  ← most expensive" if i == 1 and len(ranked) > 1 else ""
            if i == len(ranked) and r["total_cost_usd"] > 0 and len(ranked) > 1:
                tag = "  ← least expensive"
            print(
                f"  {r['model']:<{col_w}} "
                f"${r['total_cost_usd']:>13,.6f}  "
                f"${r['cost_per_1k_tokens']:>12,.6f}  "
                f"#{i}{tag}"
            )
        print(sep)
    else:
        print("  (no models to rank)")

    overruns = comparison["budget_overruns"]
    thresholds = comparison["thresholds_used"]
    print("  Budget Thresholds")
    print(sep)
    for k, v in thresholds.items():
        label = "TOTAL" if k == "__total__" else k
        print(f"  {label:<30} limit: ${v:,.4f} USD")
    print(sep)

    if overruns:
        print(f"  ⚠  BUDGET OVERRUNS DETECTED ({len(overruns)})")
        print(sep)
        for o in overruns:
            scope = "TOTAL" if o["scope"] == "__total__" else o["scope"]
            print(
                f"  ✗  {scope}"
                f"\n       Spent  : ${o['spent_usd']:,.6f} USD"
                f"\n       Limit  : ${o['limit_usd']:,.6f} USD"
                f"\n       Over by: ${o['over_by']:,.6f} USD  ({o['pct_over']:.1f}% over)"
            )
    else:
        print("  ✓  All models are within budget thresholds.")

    print(sep2)
    print()


# ── Self-test ─────────────────────────────────────────────────────────────────
SAMPLE_DATA = [
    {
        "model": "claude-3-5-sonnet",
        "date": "2026-06-20",
        "input_tokens": 1500,
        "output_tokens": 500,
        "cost_usd": 0.006,
    },
    {
        "model_name": "gpt-4o",
        "timestamp": "2026-06-21T14:30:00Z",
        "prompt_tokens": 2000,
        "completion_tokens": 800,
        "cost": 0.035,
    },
    {
        "model": "claude-3-5-sonnet",
        "date": "2026-06-22",
        "input_tokens": 3000,
        "output_tokens": 1200,
        "cost_usd": 0.012,
    },
    {
        "model": "gemini-1.5-pro",
        "date": "2026-06-23",
        "inputTokens": 500,
        "outputTokens": 200,
        "cost_per_1k_input": 0.0035,
        "cost_per_1k_output": 0.0105,
    },
    {
        # Malformed / empty — should be skipped
        "model": "",
        "cost_usd": 0,
    },
]


def run_tests() -> bool:
    print("\n── TAD Skill Self-Test: parse_token_cost_data ──────────────────")
    passed = 0
    failed = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  ✓  {name}")
            passed += 1
        else:
            print(f"  ✗  {name}  {detail}")
            failed += 1

    # Test 1 — normalize_record handles standard schema
    r1 = normalize_record(SAMPLE_DATA[0])
    check("normalize standard record — model",   r1 and r1["model"] == "claude-3-5-sonnet")
    check("normalize standard record — tokens",  r1 and r1["total_tokens"] == 2000)
    check("normalize standard record — cost",    r1 and abs(r1["cost_usd"] - 0.006) < 1e-9)
    check("normalize standard record — date",    r1 and r1["date"] == "2026-06-20")

    # Test 2 — alternate field names (gpt-4o entry)
    r2 = normalize_record(SAMPLE_DATA[1])
    check("normalize alt field names — model",   r2 and r2["model"] == "gpt-4o")
    check("normalize alt field names — tokens",  r2 and r2["input_tokens"] == 2000)
    check("normalize alt field names — date",    r2 and r2["date"] == "2026-06-21")

    # Test 3 — derived cost from per-1k rates
    r4 = normalize_record(SAMPLE_DATA[3])
    expected_cost = (500 / 1000 * 0.0035) + (200 / 1000 * 0.0105)
    check("derive cost from per-1k rates",
          r4 and abs(r4["cost_usd"] - expected_cost) < 1e-9,
          f"got {r4['cost_usd'] if r4 else 'None'}, expected {expected_cost}")

    # Test 4 — skip empty/malformed record
    r5 = normalize_record(SAMPLE_DATA[4])
    check("skip empty record",                   r5 is None)

    # Test 5 — compute_stats over sample dataset
    records = [normalize_record(d) for d in SAMPLE_DATA]
    records = [r for r in records if r is not None]
    stats   = compute_stats(records)

    check("stats — correct record count",        stats["record_count"] == 4)
    check("stats — total tokens > 0",            stats["total_tokens"] > 0)
    check("stats — total cost > 0",              stats["total_cost_usd"] > 0)
    check("stats — per_model has entries",       len(stats["per_model"]) == 3)
    check("stats — date range earliest",         stats["date_range"]["earliest"] == "2026-06-20")
    check("stats — date range latest",           stats["date_range"]["latest"]   == "2026-06-23")

    # Test 6 — claude model aggregation
    claude = stats["per_model"].get("claude-3-5-sonnet", {})
    check("claude — 2 records aggregated",       claude.get("record_count") == 2)
    check("claude — tokens summed",              claude.get("total_tokens") == 6200)
    check("claude — cost summed",
          abs(claude.get("total_cost_usd", 0) - 0.018) < 1e-9,
          f"got {claude.get('total_cost_usd')}")

    # Test 7 — empty records list
    empty_stats = compute_stats([])
    check("empty records — safe stats",          empty_stats["record_count"] == 0)
    check("empty records — n/a dates",           empty_stats["date_range"]["earliest"] == "n/a")

    # Test 8 — parse from a temp JSON file
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(SAMPLE_DATA[:3], tf)
        tmp_path = Path(tf.name)
    try:
        file_records = parse_token_cost_file(tmp_path)
        check("file parse — returns list",       isinstance(file_records, list))
        check("file parse — skips malformed",    len(file_records) == 3)
    finally:
        tmp_path.unlink(missing_ok=True)

    # ── Test 9 — compare_model_costs: basic structure ─────────────────────────
    print("\n  [cost comparison tests]")
    comparison = compare_model_costs(stats, thresholds=DEFAULT_THRESHOLDS)

    check("comparison — returns dict",
          isinstance(comparison, dict))
    check("comparison — has required keys",
          all(k in comparison for k in (
              "most_expensive_model", "least_expensive_model",
              "highest_rate_model",   "lowest_rate_model",
              "ranked_by_total_cost", "budget_overruns",
              "thresholds_used",
          )))

    check("comparison — most expensive is gpt-4o",
          comparison["most_expensive_model"] == "gpt-4o",
          f"got {comparison['most_expensive_model']!r}")

    check("comparison — least expensive is gemini-1.5-pro",
          comparison["least_expensive_model"] == "gemini-1.5-pro",
          f"got {comparison['least_expensive_model']!r}")

    # ── Test 10 — ranked list ordering ───────────────────────────────────────
    ranked = comparison["ranked_by_total_cost"]
    check("ranked — has 3 entries",              len(ranked) == 3)
    check("ranked — descending order",
          ranked[0]["total_cost_usd"] >= ranked[1]["total_cost_usd"] >= ranked[2]["total_cost_usd"])
    check("ranked — each entry has model key",
          all("model" in r for r in ranked))
    check("ranked — each entry has cost_per_1k_tokens",
          all("cost_per_1k_tokens" in r for r in ranked))

    # ── Test 11 — budget overrun detection (overrun case) ────────────────────
    tight_thresholds: dict[str, float] = {
        "__total__": 0.01,
        "gpt-4":     0.01,
        "claude":    0.001,
        "gemini":   10.00,
    }
    comp_tight = compare_model_costs(stats, thresholds=tight_thresholds)
    overruns = comp_tight["budget_overruns"]
    overrun_scopes = {o["scope"] for o in overruns}

    check("overrun — __total__ flagged",
          "__total__" in overrun_scopes,
          f"scopes: {overrun_scopes}")
    check("overrun — gpt-4o flagged",
          "gpt-4o" in overrun_scopes,
          f"scopes: {overrun_scopes}")
    check("overrun — claude flagged",
          "claude-3-5-sonnet" in overrun_scopes,
          f"scopes: {overrun_scopes}")
    check("overrun — gemini NOT flagged (within budget)",
          "gemini-1.5-pro" not in overrun_scopes,
          f"scopes: {overrun_scopes}")

    # ── Test 12 — overrun amounts are correct ────────────────────────────────
    gpt_overrun = next((o for o in overruns if o["scope"] == "gpt-4o"), None)
    check("overrun — gpt-4o over_by is positive",
          gpt_overrun is not None and gpt_overrun["over_by"] > 0,
          f"overrun entry: {gpt_overrun}")
    if gpt_overrun:
        expected_over = round(0.035 - 0.01, 6)
        check("overrun — gpt-4o over_by value correct",
              abs(gpt_overrun["over_by"] - expected_over) < 1e-6,
              f"got {gpt_overrun['over_by']}, expected {expected_over}")
        check("overrun — pct_over > 0",
              gpt_overrun["pct_over"] > 0)

    # ── Test 13 — no overruns when budget is generous ─────────────────────────
    generous_thresholds: dict[str, float] = {
        "__total__": 999.00,
        "claude":    999.00,
        "gpt-4":     999.00,
        "gemini":    999.00,
    }
    comp_generous = compare_model_costs(stats, thresholds=generous_thresholds)
    check("no overruns with generous budget",
          len(comp_generous["budget_overruns"]) == 0,
          f"got overruns: {comp_generous['budget_overruns']}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  Results: {passed} passed, {failed} failed")
    print("── End Self-Test ────────────────────────────────────────────────\n")
    return failed == 0


# ── CLI entry point ───────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse and display AI token cost tracking data."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in self-tests and exit.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_DATA,
        help=f"Path to the JSON data file (default: {DEFAULT_DATA})",
    )
    parser.add_argument(
        "--thresholds",
        type=str,
        default=None,
        help='JSON string of budget thresholds, e.g. \'{"__total__": 5.0, "gpt-4": 2.0}\'',
    )
    args = parser.parse_args()

    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    # Parse optional thresholds override
    thresholds = DEFAULT_THRESHOLDS
    if args.thresholds:
        try:
            thresholds = json.loads(args.thresholds)
        except json.JSONDecodeError as exc:
            print(f"ERROR: Could not parse --thresholds JSON: {exc}", file=sys.stderr)
            sys.exit(1)

    data_path = args.file
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    try:
        records = parse_token_cost_file(data_path)
    except Exception as exc:
        print(f"ERROR reading {data_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    stats      = compute_stats(records)
    comparison = compare_model_costs(stats, thresholds=thresholds)

    display_stats(stats, data_path)
    display_comparison(comparison)


if __name__ == "__main__":
    main()