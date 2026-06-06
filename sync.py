"""
TAD GitHub Sync
Pushes skills/, memory/profile.json, THE_MONKEY.md to private GitHub repo.
TAD travels with you to any machine.

Setup: python sync.py setup
Push:  python sync.py push
Pull:  python sync.py pull
"""

import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

REPO_NAME    = "tad-brain"
GITHUB_USER  = os.getenv("GITHUB_USERNAME", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

SYNC_TARGETS = [
    "skills/",
    "memory/profile.json",
    "THE_MONKEY.md",
    "config/providers.py",
    "tools/registry.py",
    "agent.py",
    "scheduler.py",
    "tad_visual.py",
    "night_mode.py",
    "code_executor.py",
    "requirements.txt",
]

NEVER_PUSH = [
    ".env",
    "memory/history.jsonl",
    "memory/morning_briefing.json",
    "memory/overnight_report.json",
    "memory/overnight_log.jsonl",
    ".venv/",
    "__pycache__/",
    "*.pyc",
]


def _run(cmd: list, cwd: str = ".") -> tuple:
    try:
        result = subprocess.run(
            cmd, cwd=cwd,
            capture_output=True, text=True, timeout=60
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def setup():
    """One-time setup — connects TAD to GitHub."""
    print("\nTAD GitHub Sync — Setup")
    print("=" * 40)

    if not GITHUB_USER or not GITHUB_TOKEN:
        print("\nMissing credentials in .env")
        print("Add these two lines to C:\\TAD\\.env:")
        print("  GITHUB_USERNAME=your_github_username")
        print("  GITHUB_TOKEN=ghp_your_token_here")
        print("\nThen run: python sync.py setup")
        return False

    repo_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{REPO_NAME}.git"

    # Init git if needed
    if not Path(".git").exists():
        ok, out = _run(["git", "init"])
        if not ok:
            print(f"Git init failed: {out}")
            return False
        print("✓ Git initialized")

    # Set git identity
    _run(["git", "config", "user.email", "tad@local"])
    _run(["git", "config", "user.name",  "TAD Agent"])
    print("✓ Git identity set")

    # Create/update .gitignore
    gitignore = Path(".gitignore")
    current   = gitignore.read_text() if gitignore.exists() else ""
    additions = [item for item in NEVER_PUSH if item not in current]
    if additions:
        with open(gitignore, "a") as f:
            f.write("\n# TAD private files — never push\n")
            for a in additions:
                f.write(a + "\n")
        print("✓ .gitignore updated")

    # Set remote
    ok, _ = _run(["git", "remote", "get-url", "origin"])
    if ok:
        _run(["git", "remote", "set-url", "origin", repo_url])
        print(f"✓ Remote updated")
    else:
        ok, out = _run(["git", "remote", "add", "origin", repo_url])
        if not ok:
            print(f"Remote add failed: {out}")
            return False
        print(f"✓ Remote set → github.com/{GITHUB_USER}/{REPO_NAME}")

    print(f"\n✓ Setup complete")
    print(f"  Run: python sync.py push")
    return True


def push(message: str = None):
    """Push TAD files to GitHub."""
    if not GITHUB_USER or not GITHUB_TOKEN:
        print("[sync] No credentials — run: python sync.py setup")
        return False

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg   = message or f"TAD sync — {today}"

    # Stage targets
    for target in SYNC_TARGETS:
        if Path(target.rstrip("/")).exists():
            ok, out = _run(["git", "add", target])
            if ok:
                print(f"[sync] Staged: {target}")

    # Check for changes
    ok, out = _run(["git", "status", "--porcelain"])
    if not out.strip():
        print("[sync] Nothing changed — already up to date")
        return True

    # Commit
    _run(["git", "commit", "-m", msg])

    # Push — try main then master
    ok, out = _run(["git", "push", "-u", "origin", "main", "--force"])
    if not ok:
        ok, out = _run(["git", "push", "-u", "origin", "master", "--force"])

    if ok:
        print(f"[sync] ✓ Pushed to github.com/{GITHUB_USER}/{REPO_NAME}")
        return True
    else:
        print(f"[sync] Push failed: {out[:300]}")
        print(f"[sync] Make sure this repo exists: github.com/{GITHUB_USER}/{REPO_NAME}")
        return False


def pull():
    """Pull latest TAD brain from GitHub."""
    ok, out = _run(["git", "pull", "origin", "main"])
    if not ok:
        ok, out = _run(["git", "pull", "origin", "master"])
    if ok:
        print("[sync] ✓ Pulled latest from GitHub")
        return True
    else:
        print(f"[sync] Pull failed: {out[:200]}")
        return False


def auto_sync(message: str = None):
    """Silent auto-push called by night_mode.py after each build."""
    try:
        push(message)
    except Exception as e:
        print(f"[sync] Auto-sync error: {e}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "setup":
        setup()
    elif cmd == "push":
        push()
    elif cmd == "pull":
        pull()
    else:
        print("Usage: python sync.py [setup|push|pull]")