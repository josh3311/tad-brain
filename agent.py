"""
TAD — Sovereign Agent Core v0.4
Phase 3 — Agent Routing Update

Changes from v0.3:
- Routes tasks to the correct department agent by type
- Loads the right skill file from skills/agents/
- CEO Agent handles decisions
- Market Agent handles opportunity scans
- Decision Agent handles scoring
- Build Agent handles code tasks
- Marketing Agent handles leads and outreach
- Finance Agent handles money and invoicing
- Ops Agent handles system health
- CSEO Agent handles evolution tasks
- Conversation Engine shapes every response
- Visual Engine triggers for complex explanations
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

ROOT        = Path(__file__).parent
MONKEY_PATH = ROOT / "THE_MONKEY.md"
MEMORY_PATH = ROOT / "memory" / "history.jsonl"
AGENTS_DIR  = ROOT / "skills"

# ── Agent routing map ─────────────────────────────────────────────────────────
# Maps task keywords → agent skill file name

AGENT_ROUTES = {
    "market":      ["market", "scan", "loophole", "niche",
                    "trend", "gap", "industry", "competitor",
                    "what is profitable", "best ai", "look up",
                    "investigate", "what are the"],
    "decision":    ["score this", "evaluate this", "should we build",
                    "is it worth", "assess this", "rate this",
                    "score:", "decision on", "approve or kill",
                    "score this opportunity", "rate this opportunity",
                    "evaluate this opportunity", "is this worth building"],
    "build":       ["build", "code", "create a module", "write a script",
                    "develop", "program", "fix this bug", "debug"],
    "marketing":   ["find leads", "outreach", "prospect", "pitch",
                    "follow up", "cold email", "linkedin"],
    "finance":     ["invoice", "p&l", "profit and loss", "balance sheet",
                    "revenue report", "expense", "finance report",
                    "how much money", "payment", "financial"],
    "ops":         ["system health", "health check", "system status",
                    "what is running", "agent status", "log check",
                    "ops report", "monitor"],
    "cseo":        ["evolve tad", "learn new skill", "improve tad",
                    "upgrade capability", "self evolve",
                    "evolution cycle", "new capability"],
    "ceo":         ["what should i do", "big decision", "strategy",
                    "priority today", "approve", "go or no go"],
    "research":    ["research", "analyze", "analyse", "search for",
                    "find information", "investigate", "look into"],
}

# Agent skill files
AGENT_SKILLS = {
    "market":    "market_agent.md",
    "decision":  "decision_agent.md",
    "build":     "build_agent.md",
    "marketing": "marketing_agent.md",
    "finance":   "finance_agent.md",
    "ops":       "ops_agent.md",
    "cseo":      "cseo_agent.md",
    "ceo":       "ceo_agent.md",
    "research":  "market_agent.md",  # research uses market agent skill
    "general":   "ceo_agent.md",     # general falls back to CEO
}

# Visual triggers — these task types get visual engine treatment
VISUAL_TRIGGERS = ["research", "market", "finance", "build", "cseo"]


# ── Agent identification ──────────────────────────────────────────────────────

def identify_agent(user_input: str) -> str:
    """
    Identify which agent should handle this task.
    Returns agent type string.
    """
    text = user_input.lower()

    # Score each agent route
    scores = {}
    for agent, keywords in AGENT_ROUTES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[agent] = score

    if scores:
        best = max(scores, key=scores.get)
        print(f"[router] Identified agent: {best} (score: {scores[best]})")
        return best

    return "general"


def load_agent_skill(agent_type: str) -> str:
    """Load the skill file for the identified agent."""
    skill_file = AGENT_SKILLS.get(agent_type, "ceo_agent.md")
    skill_path = AGENTS_DIR / skill_file

    if skill_path.exists():
        print(f"[agent] Loaded skill: {skill_file}")
        return skill_path.read_text(encoding="utf-8")

    # Fallback to legacy skill loader
    try:
        from skills.skill_loader import get_skill_for_task
        return get_skill_for_task(agent_type)
    except Exception:
        return ""


# ── Core agent functions ──────────────────────────────────────────────────────

def read_monkey() -> str:
    if MONKEY_PATH.exists():
        return MONKEY_PATH.read_text(encoding="utf-8")
    return ""


def update_monkey(task_type: str, completed_item: str, new_files: list = None):
    if not MONKEY_PATH.exists():
        return
    content = MONKEY_PATH.read_text(encoding="utf-8")
    today   = datetime.now().strftime("%Y-%m-%d")
    content = re.sub(r"# Last updated:.*", f"# Last updated: {today}", content)

    if completed_item:
        content = content.replace(
            f"- [ ] {completed_item}",
            f"- [x] {completed_item} ✓ {today}"
        )
    if new_files:
        for filepath in new_files:
            if filepath and filepath not in content:
                entry = f"- workflows/{filepath}"
                content = content.replace(
                    "### Working capabilities",
                    f"{entry}\n### Working capabilities"
                )
    MONKEY_PATH.write_text(content, encoding="utf-8")
    print(f"[monkey] Updated THE_MONKEY.md — {today}")


# ── Agent-specific runners ────────────────────────────────────────────────────

def run_market_agent(user_input: str, status_callback=None) -> str:
    """Run a full market scan via Market Agent."""
    _status(status_callback, "Market Agent scanning for loopholes...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from market_agent import run_full_scan
        report = run_full_scan(focus_area=user_input)
        opps   = report.get("opportunities", [])
        if opps:
            summary = f"Found {len(opps)} opportunities. Top: {opps[0].get('name')} — Score {opps[0].get('total_score')}/40"
        else:
            summary = "No qualifying opportunities found this scan. Expanding search..."
        return summary
    except Exception as e:
        print(f"[agent] Market Agent import error: {e}")
        return _run_kimi_with_skill(user_input, "market", status_callback)


def run_decision_agent(user_input: str, status_callback=None) -> str:
    """Run Decision Agent scoring."""
    _status(status_callback, "Decision Agent scoring opportunity...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from decision_agent import score_opportunity
        # Extract opportunity data from input
        opp = {"name": user_input, "problem": user_input}
        result = score_opportunity(opp)
        return f"Decision: {result.get('decision')} — Score {result.get('total_score')}/40. {result.get('reasoning')}"
    except Exception as e:
        print(f"[agent] Decision Agent import error: {e}")
        return _run_kimi_with_skill(user_input, "decision", status_callback)


def run_finance_agent(user_input: str, status_callback=None) -> str:
    """Run Finance Agent for money-related tasks."""
    _status(status_callback, "Finance Agent processing...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from finance_agent import get_financial_summary, generate_pnl
        if "p&l" in user_input.lower() or "report" in user_input.lower():
            pnl = generate_pnl()
            return f"P&L Report — Revenue: ${pnl.get('total_revenue'):.2f} | Expenses: ${pnl.get('total_expenses'):.2f} | Profit: ${pnl.get('net_profit'):.2f} | Margin: {pnl.get('profit_margin')}"
        else:
            summary = get_financial_summary()
            return f"Financial Status — Monthly Revenue: ${summary.get('monthly_revenue', 0):.2f} | Profit: ${summary.get('monthly_profit', 0):.2f} | Margin: {summary.get('profit_margin', '0%')} | Unpaid Invoices: {summary.get('unpaid_invoices', 0)}"
    except Exception as e:
        print(f"[agent] Finance Agent import error: {e}")
        return _run_kimi_with_skill(user_input, "finance", status_callback)


def run_ops_agent(user_input: str, status_callback=None) -> str:
    """Run Ops Agent for system health checks."""
    _status(status_callback, "Ops Agent checking system health...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from ops_agent import run_full_health_check, get_system_status
        health = run_full_health_check()
        status = get_system_status()
        issues = health.get("issue_count", 0)
        return f"System Status: {status} | Agents checked: {len(health.get('agents', {}))} | Issues: {issues}"
    except Exception as e:
        print(f"[agent] Ops Agent import error: {e}")
        return _run_kimi_with_skill(user_input, "ops", status_callback)


def run_cseo_agent(user_input: str, status_callback=None) -> str:
    """Run CSEO evolution cycle."""
    _status(status_callback, "CSEO Agent running evolution cycle...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from cseo_agent import run_evolution_cycle
        result = run_evolution_cycle()
        built  = result.get("skills_built", 0)
        report = result.get("report_text", "Evolution cycle complete.")
        return f"CSEO built {built} new skills this cycle.\n\n{report}"
    except Exception as e:
        print(f"[agent] CSEO Agent import error: {e}")
        return _run_kimi_with_skill(user_input, "cseo", status_callback)


# ── Kimi fallback with skill ──────────────────────────────────────────────────

def _run_kimi_with_skill(user_input: str, agent_type: str,
                          status_callback=None) -> str:
    """
    Fallback: run Kimi with the agent's skill file as system prompt.
    Used when direct agent import fails.
    """
    from tools.registry import SCHEMAS, call as tool_call

    skill_content  = load_agent_skill(agent_type)
    monkey_content = read_monkey()

    system = f"""You are TAD AI's {agent_type.upper()} agent.
{skill_content[:2000] if skill_content else ''}

PROJECT STATE:
{monkey_content[:1500] if monkey_content else ''}

Respond as this specific agent. Stay in your lane.
Be direct, specific, and actionable."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_input},
    ]

    saved_files = []

    for iteration in range(10):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=SCHEMAS,
            tool_choice="auto",
            max_tokens=4096,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            _status(status_callback, f"running {fn_name}...")
            result = tool_call(fn_name, fn_args)
            if fn_name == "file_write":
                saved_files.append(fn_args.get("filename", ""))
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      str(result),
            })

    return "Task completed — check workflows folder for full report."


# ── Response shaping via Conversation Engine ──────────────────────────────────

def _shape_response(raw: str, message: str) -> str:
    """Shape response through Conversation Engine for human feel."""
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from conversation_engine import process_message
        result = process_message(message, raw)
        return result.get("shaped_response", raw)
    except Exception:
        return raw


# ── Visual trigger ────────────────────────────────────────────────────────────

def _trigger_visual(response: str, agent_type: str, user_input: str):
    """Trigger Visual Engine for complex explanations — must run on main thread."""
    try:
        from tad_visual import show_research_report
        if agent_type in VISUAL_TRIGGERS:
            # Schedule on main thread to avoid Tcl threading errors
            import threading
            if threading.current_thread() is threading.main_thread():
                show_research_report(response, user_input)
            else:
                # Pass back via queue — tad_gui.py will display it
                print(f"[agent] Visual queued for main thread")
    except Exception as e:
        print(f"[agent] Visual trigger error: {e}")


# ── Main task router ──────────────────────────────────────────────────────────

def run_task(user_input: str, status_callback=None) -> str:
    """
    Main entry point. Identifies the right agent and routes the task.
    """
    _status(status_callback, "identifying agent...")

    agent_type = identify_agent(user_input)
    _status(status_callback, f"{agent_type} agent activated...")

    # Route to the correct agent
    if agent_type == "market" or agent_type == "research":
        raw = run_market_agent(user_input, status_callback)

    elif agent_type == "decision":
        raw = run_decision_agent(user_input, status_callback)

    elif agent_type == "finance":
        raw = run_finance_agent(user_input, status_callback)

    elif agent_type == "ops":
        raw = run_ops_agent(user_input, status_callback)

    elif agent_type == "cseo":
        raw = run_cseo_agent(user_input, status_callback)

    else:
        # CEO, build, marketing, general — all use Kimi with skill file
        raw = _run_kimi_with_skill(user_input, agent_type, status_callback)

    # Shape response through Conversation Engine
    _status(status_callback, "shaping response...")
    final = _shape_response(raw, user_input)

    # Save to memory
    _save_run(user_input, final, agent_type)

    # Update THE_MONKEY.md
    update_monkey(task_type=agent_type, completed_item="", new_files=[])

    # Trigger visual for complex tasks
    _trigger_visual(final, agent_type, user_input)

    return final


# ── Helpers ───────────────────────────────────────────────────────────────────

def _status(callback, msg: str):
    print(f"[agent] {msg}")
    if callback:
        try:
            callback(msg)
        except Exception:
            pass


def _save_run(query: str, result: str, task_type: str = "general"):
    MEMORY_PATH.parent.mkdir(exist_ok=True)
    entry = {
        "ts":        datetime.now().isoformat(),
        "type":      "agent_task",
        "task_type": task_type,
        "agent":     task_type,
        "query":     query,
        "result":    result[:500],
    }
    with open(MEMORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("TAD AI — Agent Router Test")
    print("=" * 40)

    test_inputs = [
        "research the best AI loopholes in the market right now",
        "what is the system health status",
        "generate a P&L report",
        "score this opportunity: AI receptionist for dental offices",
    ]

    for inp in test_inputs:
        agent = identify_agent(inp)
        print(f"Input: {inp[:50]}")
        print(f"Routes to: {agent} agent")
        print("-" * 40)