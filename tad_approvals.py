"""
TAD — Approval Gate v1.0
Phase 4 — Big decision approvals

When TAD wants to make a big decision it cannot self-approve,
it pauses and asks Joshua via a popup.

Triggers:
- New department being added to TAD AI
- Financial commitment above $500
- Sending outreach to more than 50 leads at once
- Deleting or restructuring core files
- Game-changing discovery from CSEO Agent
- Any action flagged as high-risk by Decision Agent

Joshua sees:
- What TAD wants to do
- Why TAD recommends it
- Risk level
- Two buttons: Approve or Reject
- TAD waits — never acts without approval on big decisions
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime

ROOT   = Path(__file__).parent
MEMORY = ROOT / "memory"

# ── Pending approvals queue ───────────────────────────────────────────────────

_pending: list[dict]  = []
_lock                 = threading.Lock()
_approval_log         = MEMORY / "approval_log.json"


def _log_approval(request: dict, decision: str):
    """Log every approval decision permanently."""
    MEMORY.mkdir(exist_ok=True)
    log = {"approvals": []}
    if _approval_log.exists():
        try:
            log = json.loads(_approval_log.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Strip non-serializable callbacks before saving
    safe_request = {
        k: v for k, v in request.items()
        if k not in ("on_approve", "on_reject") and not callable(v)
    }

    log["approvals"].append({
        "request":    safe_request,
        "decision":   decision,
        "decided_at": datetime.now().isoformat(),
    })
    _approval_log.write_text(json.dumps(log, indent=2), encoding="utf-8")


# ── Approval request ──────────────────────────────────────────────────────────

def request_approval(
    action: str,
    reasoning: str,
    risk_level: str = "medium",
    agent: str = "TAD",
    on_approve=None,
    on_reject=None,
    auto_timeout: int = 0,
) -> dict:
    """
    Request Joshua's approval for a big decision.

    action      — what TAD wants to do (1-2 sentences)
    reasoning   — why TAD recommends this
    risk_level  — "low", "medium", "high", "critical"
    agent       — which agent is requesting (CEO, CSEO, etc.)
    on_approve  — callback when Joshua approves
    on_reject   — callback when Joshua rejects
    auto_timeout — seconds before auto-rejecting (0 = wait forever)

    Returns request dict with id.
    """
    request = {
        "id":          f"approval_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "action":      action,
        "reasoning":   reasoning,
        "risk_level":  risk_level,
        "agent":       agent,
        "requested_at": datetime.now().isoformat(),
        "status":      "pending",
        "on_approve":  on_approve,
        "on_reject":   on_reject,
    }

    with _lock:
        _pending.append(request)

    print(f"[Approvals] Request queued: {request['id']} — {action[:50]}")

    # Show popup
    _show_approval_popup(request, auto_timeout)

    return request


def _show_approval_popup(request: dict, auto_timeout: int = 0):
    """Show the approval gate popup to Joshua."""
    def _launch():
        try:
            import customtkinter as ctk

            # Risk colors
            risk_colors = {
                "low":      "#1d9e75",
                "medium":   "#ef9f27",
                "high":     "#e24b4a",
                "critical": "#ff0000",
            }
            risk_color = risk_colors.get(request.get("risk_level", "medium"), "#ef9f27")

            win = ctk.CTkToplevel()
            win.title("TAD — Decision Required")
            win.geometry("640x420+200+150")
            win.configure(fg_color="#0d0d0f")
            win.attributes("-topmost", True)
            win.resizable(False, False)

            # Top bar
            top = ctk.CTkFrame(win, fg_color="#141418", corner_radius=0, height=48)
            top.pack(fill="x")
            top.pack_propagate(False)

            ctk.CTkLabel(
                top, text=f"TAD  ·  Decision Required  ·  {request.get('agent', 'TAD')}",
                font=("Courier", 12), text_color="#7f77dd"
            ).pack(side="left", padx=16, pady=12)

            risk_badge = ctk.CTkLabel(
                top,
                text=f"  {request.get('risk_level', 'medium').upper()} RISK  ",
                font=("Courier", 11, "bold"),
                fg_color=risk_color,
                text_color="#ffffff",
                corner_radius=6,
            )
            risk_badge.pack(side="right", padx=16, pady=10)

            # Scroll area
            scroll = ctk.CTkScrollableFrame(win, fg_color="#0d0d0f")
            scroll.pack(fill="both", expand=True)

            # Header
            ctk.CTkLabel(
                scroll,
                text="TAD needs your approval",
                font=("Courier", 16, "bold"),
                text_color="#ef9f27"
            ).pack(anchor="w", padx=24, pady=(20, 8))

            # Action
            ctk.CTkLabel(
                scroll, text="Proposed action:",
                font=("Courier", 11), text_color="#555566"
            ).pack(anchor="w", padx=24, pady=(8, 2))

            ctk.CTkLabel(
                scroll,
                text=request.get("action", ""),
                font=("Courier", 13, "bold"),
                text_color="#e0e0f0",
                wraplength=560,
                justify="left"
            ).pack(anchor="w", padx=24, pady=(0, 12))

            # Reasoning
            ctk.CTkLabel(
                scroll, text="Why TAD recommends this:",
                font=("Courier", 11), text_color="#555566"
            ).pack(anchor="w", padx=24, pady=(4, 2))

            ctk.CTkLabel(
                scroll,
                text=request.get("reasoning", ""),
                font=("Courier", 11),
                text_color="#8a8a9e",
                wraplength=560,
                justify="left"
            ).pack(anchor="w", padx=24, pady=(0, 8))

            # Timeout indicator
            timeout_label = None
            if auto_timeout > 0:
                timeout_label = ctk.CTkLabel(
                    scroll,
                    text=f"Auto-rejecting in {auto_timeout}s if no response",
                    font=("Courier", 10),
                    text_color="#e24b4a"
                )
                timeout_label.pack(anchor="w", padx=24, pady=(4, 8))

            # Buttons
            btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
            btn_row.pack(fill="x", padx=24, pady=16)

            def _approve():
                request["status"] = "approved"
                _log_approval(request, "approved")
                print(f"[Approvals] APPROVED: {request['id']}")
                if request.get("on_approve"):
                    threading.Thread(
                        target=request["on_approve"],
                        daemon=True
                    ).start()
                win.destroy()

            def _reject():
                request["status"] = "rejected"
                _log_approval(request, "rejected")
                print(f"[Approvals] REJECTED: {request['id']}")
                if request.get("on_reject"):
                    request["on_reject"]()
                win.destroy()

            ctk.CTkButton(
                btn_row,
                text="✓  Approve — TAD execute",
                font=("Courier", 13, "bold"),
                height=48, width=260,
                fg_color="#1a2820",
                hover_color="#2a3830",
                text_color="#1d9e75",
                corner_radius=8,
                command=_approve
            ).pack(side="left", padx=(0, 16))

            ctk.CTkButton(
                btn_row,
                text="✕  Reject",
                font=("Courier", 13),
                height=48, width=140,
                fg_color="#2a1010",
                hover_color="#3a2020",
                text_color="#e24b4a",
                corner_radius=8,
                command=_reject
            ).pack(side="left")

            # Auto-timeout countdown
            if auto_timeout > 0 and timeout_label:
                def _countdown(remaining):
                    if remaining <= 0:
                        if request["status"] == "pending":
                            _reject()
                        return
                    if timeout_label.winfo_exists():
                        timeout_label.configure(
                            text=f"Auto-rejecting in {remaining}s if no response"
                        )
                        win.after(1000, lambda: _countdown(remaining - 1))

                win.after(1000, lambda: _countdown(auto_timeout - 1))

            # TTS notification
            def _notify():
                try:
                    import pyttsx3
                    engine = pyttsx3.init()
                    engine.setProperty("rate", 170)
                    voices = engine.getProperty("voices")
                    if len(voices) > 1:
                        engine.setProperty("voice", voices[1].id)
                    engine.say(f"Joshua, TAD needs your approval. {request.get('action', '')[:100]}")
                    engine.runAndWait()
                except Exception:
                    pass

            threading.Thread(target=_notify, daemon=True).start()

            win.mainloop()

        except Exception as e:
            print(f"[Approvals] Popup error: {e}")
            # Fallback — CLI approval
            print(f"\n{'='*50}")
            print(f"TAD APPROVAL REQUIRED")
            print(f"Agent: {request.get('agent')}")
            print(f"Risk: {request.get('risk_level').upper()}")
            print(f"Action: {request.get('action')}")
            print(f"Reason: {request.get('reasoning')}")
            print(f"{'='*50}")
            answer = input("Approve? (y/n): ").strip().lower()
            if answer == "y":
                request["status"] = "approved"
                _log_approval(request, "approved")
                if request.get("on_approve"):
                    request["on_approve"]()
            else:
                request["status"] = "rejected"
                _log_approval(request, "rejected")
                if request.get("on_reject"):
                    request["on_reject"]()

    threading.Thread(target=_launch, daemon=True).start()


# ── Approval helpers ──────────────────────────────────────────────────────────

def get_pending() -> list:
    """Return list of pending approvals."""
    with _lock:
        return [r for r in _pending if r.get("status") == "pending"]


def get_approval_history(limit: int = 20) -> list:
    """Return recent approval decisions."""
    if not _approval_log.exists():
        return []
    try:
        log = json.loads(_approval_log.read_text(encoding="utf-8"))
        return log.get("approvals", [])[-limit:]
    except Exception:
        return []


def flag_to_joshua(action: str, reasoning: str,
                   risk_level: str = "high",
                   agent: str = "TAD",
                   on_approve=None, on_reject=None):
    """
    Shortcut used by all agents to flag a decision to Joshua.
    This is the standard way any agent requests approval.

    Usage in any agent:
        from tad_approvals import flag_to_joshua

        flag_to_joshua(
            action="Add new department: Data Analytics Division",
            reasoning="CSEO found a pattern that requires dedicated data analysis",
            risk_level="high",
            agent="CSEO",
            on_approve=lambda: create_new_department(),
            on_reject=lambda: log_rejection()
        )
    """
    return request_approval(
        action=action,
        reasoning=reasoning,
        risk_level=risk_level,
        agent=agent,
        on_approve=on_approve,
        on_reject=on_reject,
    )


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD Approvals — Test Mode")
    print("=" * 40)
    print("Simulating 2 approval requests...\n")

    def on_approve_1():
        print("✓ Action 1 approved — executing...")

    def on_reject_1():
        print("✗ Action 1 rejected — TAD will not proceed")

    def on_approve_2():
        print("✓ Game-changing discovery approved — CSEO proceeding...")

    # Test 1 — Medium risk
    flag_to_joshua(
        action="Send outreach to 47 HVAC companies in Ontario",
        reasoning="Market scan found 47 businesses matching our ideal customer profile. All have 10+ employees and no AI receptionist.",
        risk_level="medium",
        agent="CRO Agent",
        on_approve=on_approve_1,
        on_reject=on_reject_1,
    )

    time.sleep(2)

    # Test 2 — Critical (game-changing discovery)
    flag_to_joshua(
        action="Add new division: TAD Data Intelligence — scrapes and analyzes industry data autonomously",
        reasoning="CSEO discovered a pattern: 78% of our best opportunities come from public job posting data. Building a dedicated scraper division could triple opportunity discovery speed.",
        risk_level="critical",
        agent="CSEO Agent",
        on_approve=on_approve_2,
    )

    print("\nWaiting for your decisions...")
    try:
        while True:
            pending = get_pending()
            if not pending:
                print("\nAll decisions made.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass

    print("\nApproval history:")
    for entry in get_approval_history():
        r = entry.get("request", {})
        print(f"  {entry.get('decision').upper()}: {r.get('action', '')[:60]}")