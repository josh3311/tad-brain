"""
audit_trail_logger.py — AI Model Audit Trail Logger
TAD AI Compliance Module | Immutable JSON audit log for AI interactions

Captures: model name, version, prompts, outputs → append-only JSONL log
Run with --test for self-check mode
"""

import json
import hashlib
import os
import sys
import time
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_LOG_PATH = Path("memory/audit/audit_trail.jsonl")
LOG_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Core Logger
# ---------------------------------------------------------------------------

class AuditTrailLogger:
    """
    Append-only audit trail for AI model interactions.

    Each entry is a single JSON line (JSONL) written with:
      - Unique entry ID
      - UTC timestamp (ISO 8601)
      - Model name + version
      - Prompt (full text)
      - Output (full text)
      - SHA-256 hash of the entry content (tamper-evidence)
      - Sequential entry index

    The file is opened in append mode per write — no entry is ever
    overwritten or deleted by this module.
    """

    def __init__(self, log_path: Path = DEFAULT_LOG_PATH):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._entry_count = self._count_existing_entries()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        model_name: str,
        model_version: str,
        prompt: str,
        output: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        Record one AI interaction.  Returns the full entry dict.

        Parameters
        ----------
        model_name    : e.g. "claude-3-5-sonnet"
        model_version : e.g. "20241022"
        prompt        : the exact prompt sent to the model
        output        : the exact output received from the model
        session_id    : optional caller-supplied session/run identifier
        metadata      : optional dict of extra compliance fields
        """
        self._entry_count += 1

        entry = {
            "log_version":   LOG_VERSION,
            "entry_id":      str(uuid.uuid4()),
            "entry_index":   self._entry_count,
            "session_id":    session_id or str(uuid.uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "unix_ts":       time.time(),
            "model": {
                "name":    model_name,
                "version": model_version,
            },
            "prompt":        prompt,
            "output":        output,
            "metadata":      metadata or {},
        }

        # Tamper-evidence hash — computed over stable fields, not the hash field itself
        entry["content_hash"] = self._hash_entry(entry)

        self._append(entry)
        return entry

    def verify_log(self) -> dict:
        """
        Re-read every entry, recompute its hash, and confirm nothing changed.

        Returns
        -------
        {
          "ok": bool,
          "total": int,
          "corrupt": [ { "entry_index": …, "entry_id": …, "reason": … } ]
        }
        """
        result = {"ok": True, "total": 0, "corrupt": []}

        if not self.log_path.exists():
            return result

        with open(self.log_path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                result["total"] += 1

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as exc:
                    result["ok"] = False
                    result["corrupt"].append({
                        "line":   lineno,
                        "reason": f"JSON decode error: {exc}",
                    })
                    continue

                stored_hash = entry.get("content_hash", "")
                # Recompute without the stored hash field
                recomputed   = self._hash_entry(
                    {k: v for k, v in entry.items() if k != "content_hash"}
                )

                if stored_hash != recomputed:
                    result["ok"] = False
                    result["corrupt"].append({
                        "entry_index": entry.get("entry_index"),
                        "entry_id":    entry.get("entry_id"),
                        "reason":      "hash mismatch — entry may have been tampered with",
                    })

        return result

    def tail(self, n: int = 5) -> list:
        """Return the last *n* entries as dicts (for display/debug)."""
        entries = []
        if not self.log_path.exists():
            return entries
        with open(self.log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries[-n:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, entry: dict) -> None:
        """Write one JSON line — append only, never truncate."""
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _hash_entry(entry: dict) -> str:
        """
        SHA-256 of the canonical JSON representation.
        Keys are sorted so ordering differences don't affect the hash.
        The 'content_hash' key is excluded before hashing.
        """
        clean = {k: v for k, v in entry.items() if k != "content_hash"}
        canonical = json.dumps(clean, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _count_existing_entries(self) -> int:
        """Count valid lines already in the log (for sequential indexing)."""
        if not self.log_path.exists():
            return 0
        count = 0
        with open(self.log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count


# ---------------------------------------------------------------------------
# Convenience wrapper — single-call logging
# ---------------------------------------------------------------------------

def log_interaction(
    model_name: str,
    model_version: str,
    prompt: str,
    output: str,
    log_path: Path = DEFAULT_LOG_PATH,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    One-shot helper.  Creates a logger, writes the entry, returns it.
    Usage::

        from audit_trail_logger import log_interaction
        entry = log_interaction(
            model_name="claude-3-5-sonnet",
            model_version="20241022",
            prompt="Summarise this contract…",
            output="The contract states…",
        )
    """
    logger = AuditTrailLogger(log_path)
    return logger.log(
        model_name=model_name,
        model_version=model_version,
        prompt=prompt,
        output=output,
        session_id=session_id,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Self-check / --test mode
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """
    Lightweight self-check — no external dependencies required.
    Writes to a temp log, verifies hashes, checks tamper detection,
    then cleans up.
    """
    import tempfile

    print("=" * 60)
    print("  TAD AuditTrailLogger — self-check")
    print("=" * 60)

    tmp_dir  = Path(tempfile.mkdtemp())
    log_path = tmp_dir / "test_audit.jsonl"
    logger   = AuditTrailLogger(log_path)

    # ── Test 1: basic write + read back ──────────────────────────────
    print("\n[1] Writing 3 audit entries …", end=" ")
    entries = []
    interactions = [
        ("gpt-4o",              "2024-11-20", "What is 2+2?",          "4"),
        ("claude-3-5-sonnet",   "20241022",   "Summarise GDPR Art 5.", "GDPR Art 5 covers …"),
        ("gemini-1.5-pro",      "001",        "Draft NDA clause.",     "Confidential information means …"),
    ]
    for name, ver, prompt, output in interactions:
        e = logger.log(
            model_name=name,
            model_version=ver,
            prompt=prompt,
            output=output,
            metadata={"test": True},
        )
        entries.append(e)

    assert log_path.exists(), "Log file not created"
    with open(log_path) as fh:
        lines = [l for l in fh if l.strip()]
    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"
    print("PASS")

    # ── Test 2: sequential index ──────────────────────────────────────
    print("[2] Verifying sequential entry_index …", end=" ")
    for i, e in enumerate(entries, 1):
        assert e["entry_index"] == i, f"index mismatch at pos {i}"
    print("PASS")

    # ── Test 3: content_hash present and unique ───────────────────────
    print("[3] Checking content_hash uniqueness …", end=" ")
    hashes = [e["content_hash"] for e in entries]
    assert len(hashes) == len(set(hashes)), "duplicate hashes detected"
    assert all(len(h) == 64 for h in hashes), "unexpected hash length"
    print("PASS")

    # ── Test 4: verify_log passes on clean file ───────────────────────
    print("[4] verify_log on untouched file …", end=" ")
    result = logger.verify_log()
    assert result["ok"],     f"Verification failed: {result['corrupt']}"
    assert result["total"] == 3
    print("PASS")

    # ── Test 5: tamper detection ──────────────────────────────────────
    print("[5] Tamper detection — mutating one entry …", end=" ")
    with open(log_path, "r") as fh:
        raw_lines = fh.readlines()

    # Alter the output field of the first entry
    first     = json.loads(raw_lines[0])
    first["output"] = "TAMPERED OUTPUT"
    raw_lines[0] = json.dumps(first) + "\n"

    with open(log_path, "w") as fh:
        fh.writelines(raw_lines)

    result = logger.verify_log()
    assert not result["ok"],        "Expected tamper to be detected"
    assert len(result["corrupt"]) == 1
    assert result["corrupt"][0]["entry_index"] == 1
    print("PASS")

    # ── Test 6: tail() ───────────────────────────────────────────────
    print("[6] tail(2) returns last 2 entries …", end=" ")
    # Restore clean file for tail test
    log_path.unlink()
    logger2 = AuditTrailLogger(log_path)
    for name, ver, prompt, output in interactions:
        logger2.log(model_name=name, model_version=ver, prompt=prompt, output=output)
    tail = logger2.tail(2)
    assert len(tail) == 2
    assert tail[-1]["model"]["name"] == "gemini-1.5-pro"
    print("PASS")

    # ── Test 7: persistence across instances ─────────────────────────
    print("[7] Entry count persists across logger instances …", end=" ")
    logger3 = AuditTrailLogger(log_path)   # new instance, same file
    e = logger3.log("new-model", "v1", "hello", "world")
    assert e["entry_index"] == 4, f"Expected index 4, got {e['entry_index']}"
    print("PASS")

    # ── Test 8: convenience wrapper ───────────────────────────────────
    print("[8] log_interaction() one-shot wrapper …", end=" ")
    e = log_interaction(
        model_name="mistral-large",
        model_version="2",
        prompt="Is this compliant?",
        output="Yes, based on …",
        log_path=log_path,
    )
    assert e["model"]["name"] == "mistral-large"
    assert "content_hash" in e
    print("PASS")

    # Cleanup
    log_path.unlink(missing_ok=True)
    tmp_dir.rmdir()

    print("\n" + "=" * 60)
    print("  ALL TESTS PASSED ✓")
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="TAD AI — Audit Trail Logger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Run self-check
  python audit_trail_logger.py --test

  # Log one interaction from the command line
  python audit_trail_logger.py \\
      --model-name claude-3-5-sonnet \\
      --model-version 20241022 \\
      --prompt "Summarise GDPR" \\
      --output "GDPR covers data protection …"

  # Verify the integrity of an existing log
  python audit_trail_logger.py --verify

  # Show last 5 entries
  python audit_trail_logger.py --tail 5
        """,
    )
    p.add_argument("--test",          action="store_true",  help="run self-check and exit")
    p.add_argument("--verify",        action="store_true",  help="verify log integrity and exit")
    p.add_argument("--tail",          type=int, metavar="N", help="print last N entries and exit")
    p.add_argument("--log-path",      default=str(DEFAULT_LOG_PATH), help="path to audit log file")
    p.add_argument("--model-name",    help="model name to log")
    p.add_argument("--model-version", help="model version to log")
    p.add_argument("--prompt",        help="prompt text to log")
    p.add_argument("--output",        help="model output to log")
    p.add_argument("--session-id",    help="optional session identifier")
    return p


def main() -> None:
    parser = _build_cli()
    args   = parser.parse_args()

    if args.test:
        _run_tests()
        sys.exit(0)

    log_path = Path(args.log_path)
    logger   = AuditTrailLogger(log_path)

    if args.verify:
        result = logger.verify_log()
        status = "✓ CLEAN" if result["ok"] else "✗ CORRUPT"
        print(f"\nAudit log: {log_path}")
        print(f"Status   : {status}")
        print(f"Entries  : {result['total']}")
        if result["corrupt"]:
            print("\nCorrupt entries:")
            for c in result["corrupt"]:
                print(f"  {json.dumps(c)}")
        sys.exit(0 if result["ok"] else 1)

    if args.tail is not None:
        entries = logger.tail(args.tail)
        print(f"\nLast {args.tail} entries from {log_path}:\n")
        for e in entries:
            print(json.dumps(e, indent=2))
        sys.exit(0)

    # Log a single interaction from CLI args
    required = ["model_name", "model_version", "prompt", "output"]
    missing  = [f"--{r.replace('_','-')}" for r in required if not getattr(args, r)]
    if missing:
        print(f"Error: missing required arguments: {', '.join(missing)}")
        parser.print_help()
        sys.exit(1)

    entry = logger.log(
        model_name=args.model_name,
        model_version=args.model_version,
        prompt=args.prompt,
        output=args.output,
        session_id=args.session_id,
    )
    print(f"\nLogged entry #{entry['entry_index']} → {log_path}")
    print(f"  entry_id  : {entry['entry_id']}")
    print(f"  timestamp : {entry['timestamp_utc']}")
    print(f"  model     : {entry['model']['name']} v{entry['model']['version']}")
    print(f"  hash      : {entry['content_hash'][:16]}…")


if __name__ == "__main__":
    main()