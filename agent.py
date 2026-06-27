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
import threading
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

from tad_encoding import force_utf8
force_utf8()

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

# v1.0: holds the raw structured data (opportunities/pnl/health) from the
# last agent run so _trigger_visual can render a real chart, not just text.
_LAST_CHART_DATA = {"agent_type": None, "data": None}

# v1.0.1: the pending visual the GUI should display on the main thread
# after run_task() returns. kind: "market" | "finance" | "ops" | "report" | None
_LAST_VISUAL = {"kind": None, "data": None, "text": None, "user_input": None}


# ── Agent identification ──────────────────────────────────────────────────────

def identify_agent(user_input: str) -> str:
    """
    Identify which agent should handle this task.
    Uses intent detection — not just keyword matching.
    Prioritises the MOST SPECIFIC match, not just any match.
    """
    text = user_input.lower().strip()

    # ── Priority 0: Agent named explicitly ────────────────────────────────
    # If the user names an agent ("use CSEO", "market agent", ...), that wins
    # over everything — these must NEVER fall through to conversation, where
    # Kimi/Haiku would role-play the agent and fabricate an execution log.
    if "cseo" in text or "self-fix" in text or "self fix" in text:
        print(f"[router] Identified agent: cseo (named explicitly)")
        return "cseo"
    NAMED_AGENTS = {
        "market agent":    "market",
        "decision agent":  "decision",
        "finance agent":   "finance",
        "ops agent":       "ops",
        "build agent":     "build",
        "marketing agent": "marketing",
        "ceo agent":       "ceo",
    }
    for name, agent in NAMED_AGENTS.items():
        if name in text:
            print(f"[router] Identified agent: {agent} (named explicitly)")
            return agent

    # ── Priority 1: Explicit agent commands ──────────────────────────────
    # These are unambiguous — always route here first
    if any(p in text for p in ["run cseo", "cseo evolution", "evolve tad", "fix all broken"]):
        print(f"[router] Identified agent: cseo (explicit command)")
        return "cseo"

    if any(p in text for p in ["run a market scan", "market scan", "find opportunities",
                                "scan for loopholes", "find niches"]):
        print(f"[router] Identified agent: market (explicit command)")
        return "market"

    if any(p in text for p in ["run marketing", "run marketing agent", "launch marketing",
                                "marketing campaign", "start outreach"]):
        print(f"[router] Identified agent: marketing (explicit command)")
        return "marketing"

    if any(p in text for p in ["ask ceo", "ceo decision", "ceo report"]):
        print(f"[router] Identified agent: ceo (explicit command)")
        return "ceo"

    if any(p in text for p in ["score this opportunity", "score this:", "evaluate this opportunity",
                                "should we build", "go or no go"]):
        print(f"[router] Identified agent: decision (explicit command)")
        return "decision"

    if any(p in text for p in ["p&l report", "profit and loss", "invoice", "financial report",
                                "how much revenue", "finance report"]):
        print(f"[router] Identified agent: finance (explicit command)")
        return "finance"

    if any(p in text for p in ["health check", "system health", "ops check", "what is running",
                                "agent status", "system status"]):
        print(f"[router] Identified agent: ops (explicit command)")
        return "ops"

    if any(p in text for p in ["ceo briefing", "daily briefing", "morning briefing",
                                "what should i focus", "today's priorities"]):
        print(f"[router] Identified agent: ceo (explicit command)")
        return "ceo"

    # ── Priority 2: Build requests ────────────────────────────────────────
    # Only route to build if explicitly asking to build/code something NEW
    build_phrases = ["build me", "build a ", "create a script", "write a script",
                     "code a ", "develop a ", "write me a ", "create a module",
                     "write a module", "build the ", "create the "]
    if any(p in text for p in build_phrases):
        print(f"[router] Identified agent: build (explicit build request)")
        return "build"

    # ── Priority 3: Conversational — route to Claude, NOT agents ─────────
    # These are questions/requests that should be answered in conversation
    conversational_signals = [
        "look into", "analyze", "analyse", "explain", "what happened",
        "why is", "how does", "tell me", "what is", "can you",
        "help me", "i want you to", "could you", "please", "fix the",
        "fix my", "fix this", "look at", "check", "review",
        "what do you think", "is there", "are there", "show me",
        "investigate", "find out", "figure out", "understand",
    ]
    if any(p in text for p in conversational_signals):
        print(f"[router] Identified agent: general (conversational request — routing to Claude)")
        return "general"

    # ── Priority 4: Score keyword matches ─────────────────────────────────
    scores = {}
    for agent, keywords in AGENT_ROUTES.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[agent] = score

    if scores:
        best = max(scores, key=scores.get)
        # Only trust keyword match if score is 2+
        # Score of 1 is too ambiguous
        if scores[best] >= 2:
            print(f"[router] Identified agent: {best} (score: {scores[best]})")
            return best

    # ── Default: general Claude conversation ─────────────────────────────
    print(f"[router] Identified agent: general (default — Claude handles this)")
    return "general"


# ── Action command detection ──────────────────────────────────────────────────

def _is_action_command(user_input: str) -> str:
    """
    Detect imperative "change the codebase" commands before identify_agent() runs.
    Returns "cseo" to route to the real CSEO executor, or "" to fall through.

    Root cause of fabrication: "implement that skill", "fix the routing",
    "apply the new routing" hit Priority-3 conversational_signals → Kimi/Haiku
    role-plays the agent and invents fake execution logs / fake commits.
    Catching them here prevents identify_agent() from seeing them at all.
    """
    text = user_input.lower().strip()

    # Pure question starters are conversational — never action commands
    QUESTION_STARTS = (
        "how ", "what ", "why ", "when ", "where ", "which ", "who ",
        "is there", "are there", "do you", "does ",
        "can you explain", "could you explain",
        "explain ", "tell me about", "tell me what",
        "show me what", "what do you think",
    )
    if any(text.startswith(q) for q in QUESTION_STARTS):
        return ""

    # Imperative verbs that mean "execute a code/system change"
    CSEO_PHRASES = [
        "implement that", "implement this", "implement the ", "implement it",
        "implement a ",   "implement now",
        "wire up",        "wire the ",      "wire in ",       "wire it",
        "apply the",      "apply that",     "apply this",     "apply it",
        "refactor the",   "refactor this",  "refactor that",
        "rebuild the",    "rebuild this",
        "rewrite the",    "rewrite this",
        "patch the",      "patch this",     "patch it",
    ]
    if any(p in text for p in CSEO_PHRASES):
        return "cseo"

    # "fix the <code artifact>" — caught before Priority-3 strips it
    if re.search(r"\bfix the\b", text):
        CODE_TARGETS = [
            "agent", "routing", "bug", "code", "module", "skill",
            "script", "function", "error", "crash",
            "marketing", "build", "finance", "market", "decision",
            "ops", "ceo", "cseo", "loop", "pipeline",
        ]
        if any(t in text for t in CODE_TARGETS):
            return "cseo"

    return ""


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
        _LAST_CHART_DATA["agent_type"] = "market"
        _LAST_CHART_DATA["data"]       = opps
        if opps:
            summary = f"Found {len(opps)} opportunities. Top: {opps[0].get('name')} — Score {opps[0].get('total_score')}/40"
        else:
            summary = "No qualifying opportunities found this scan. Expanding search..."
        return summary
    except Exception as e:
        print(f"[agent] Market Agent error: {e}")
        return f"Market Agent error: {str(e)} — did not run"


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
        print(f"[agent] Decision Agent error: {e}")
        return f"Decision Agent error: {str(e)} — did not run"


def run_finance_agent(user_input: str, status_callback=None) -> str:
    """Run Finance Agent for money-related tasks."""
    _status(status_callback, "Finance Agent processing...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from finance_agent import get_financial_summary, generate_pnl
        if "p&l" in user_input.lower() or "report" in user_input.lower():
            pnl = generate_pnl()
            _LAST_CHART_DATA["agent_type"] = "finance"
            _LAST_CHART_DATA["data"]       = pnl
            return f"P&L Report — Revenue: ${pnl.get('total_revenue'):.2f} | Expenses: ${pnl.get('total_expenses'):.2f} | Profit: ${pnl.get('net_profit'):.2f} | Margin: {pnl.get('profit_margin')}"
        else:
            summary = get_financial_summary()
            _LAST_CHART_DATA["agent_type"] = "finance"
            _LAST_CHART_DATA["data"]       = {
                "total_revenue":  summary.get("monthly_revenue", 0),
                "total_expenses": summary.get("monthly_revenue", 0) - summary.get("monthly_profit", 0),
                "net_profit":     summary.get("monthly_profit", 0),
                "profit_margin":  summary.get("profit_margin", "0%"),
            }
            return f"Financial Status — Monthly Revenue: ${summary.get('monthly_revenue', 0):.2f} | Profit: ${summary.get('monthly_profit', 0):.2f} | Margin: {summary.get('profit_margin', '0%')} | Unpaid Invoices: {summary.get('unpaid_invoices', 0)}"
    except Exception as e:
        print(f"[agent] Finance Agent error: {e}")
        return f"Finance Agent error: {str(e)} — did not run"


def run_ops_agent(user_input: str, status_callback=None) -> str:
    """Run Ops Agent for system health checks."""
    _status(status_callback, "Ops Agent checking system health...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from ops_agent import run_full_health_check, get_system_status
        health = run_full_health_check()
        status = get_system_status()
        issues = health.get("issue_count", 0)
        _LAST_CHART_DATA["agent_type"] = "ops"
        _LAST_CHART_DATA["data"]       = health
        return f"System Status: {status} | Agents checked: {len(health.get('agents', {}))} | Issues: {issues}"
    except Exception as e:
        print(f"[agent] Ops Agent error: {e}")
        return f"Ops Agent error: {str(e)} — did not run"


def run_cseo_agent(user_input: str, status_callback=None) -> str:
    """Run the REAL CSEO evolution cycle and report its output verbatim.

    No LLM fallback here on purpose: if run_evolution_cycle() can't run,
    we say so plainly. Letting Kimi role-play the CSEO is how fabricated
    execution logs (fake commits, fake metrics) reached chat."""
    _status(status_callback, "CSEO Agent running evolution cycle...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from cseo_agent import run_evolution_cycle
        result = run_evolution_cycle()
    except Exception as e:
        print(f"[agent] CSEO Agent error: {e}")
        return f"CSEO error: {e} — evolution cycle did NOT run."

    status = result.get("status", "")
    if status == "error":
        return f"CSEO error: {result.get('reason', 'unknown')} — no skills were built."
    if status == "no_gaps":
        return ("CSEO ran a real evolution cycle: 0 gaps and 0 bugs found — "
                "nothing to fix this cycle.")

    built   = result.get("skills_built", 0)
    failed  = result.get("skills_failed", 0)
    gaps    = result.get("gaps_found", 0)
    gc      = result.get("game_changers", [])
    lines   = [f"CSEO evolution cycle ran — gaps found: {gaps}, "
               f"skills built: {built}, failed: {failed}."]
    for s in result.get("built_skills", []):
        mark = "✓" if s.get("status") == "success" else "✗"
        lines.append(f"  {mark} {s.get('skill_name', 'unknown')}")
    if gc:
        lines.append(f"🚨 {len(gc)} game-changing discovery flagged for Joshua.")
    if result.get("report_text"):
        lines.append("\n" + result["report_text"])
    return "\n".join(lines)


def run_marketing_agent(user_input: str, status_callback=None) -> str:
    """Run the real Marketing Agent — calls run_outreach_cycle() verbatim.
    No Kimi role-play fallback: if the real function fails, say so plainly."""
    _status(status_callback, "Marketing Agent running outreach cycle...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from marketing_agent import run_outreach_cycle
        # Pull latest built product from build_log, or use a sensible default
        product = {"name": "TAD AI Product", "description": user_input}
        try:
            import json
            build_log_path = ROOT / "memory" / "build_log.json"
            if build_log_path.exists():
                builds = json.loads(build_log_path.read_text(encoding="utf-8")).get("builds", [])
                successful = [b for b in builds if b.get("status") == "success"]
                if successful:
                    latest = successful[-1]
                    product = {
                        "name":        latest.get("opportunity", latest.get("filename", "TAD Product")),
                        "description": f"AI automation tool built by TAD: {latest.get('filename', '')}",
                    }
        except Exception:
            pass
        result = run_outreach_cycle(product)
        leads = result.get("leads_found", 0)
        msgs  = result.get("messages_crafted", 0)
        return f"Marketing cycle complete: {leads} leads found, {msgs} messages crafted for {result.get('product', 'product')}."
    except Exception as e:
        print(f"[agent] Marketing Agent error: {e}")
        return f"Marketing Agent error: {str(e)} — did NOT run"


def run_ceo_agent(user_input: str, status_callback=None) -> str:
    """Run the real CEO Agent for chat-triggered decision requests.
    Returns real output verbatim — no Kimi role-play fallback."""
    _status(status_callback, "CEO Agent processing decision...")
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from ceo_agent import generate_daily_summary, make_decision
        # Briefing / summary requests
        if any(p in user_input.lower() for p in ["briefing", "summary", "report", "daily"]):
            summary = generate_daily_summary()
            return summary
        # Decision on a specific item
        result = make_decision({"request": user_input}, "chat_request")
        decision = result.get("decision", "UNKNOWN")
        reasoning = result.get("reasoning", "")
        action = result.get("action", "")
        return f"CEO Decision: {decision}\n{reasoning}\nNext: {action}"
    except Exception as e:
        print(f"[agent] CEO Agent error: {e}")
        return f"CEO Agent error: {str(e)} — did NOT run"


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
    """
    Stash visual info for the GUI to display on the main thread.
    run_task() runs in a background thread (tad_gui.py's _run_agent),
    so we can't safely create Tk windows here — the GUI calls
    get_last_visual() after run_task() returns and schedules display
    via self.after(0, ...).
    """
    chart_data = _LAST_CHART_DATA.get("data") if _LAST_CHART_DATA.get("agent_type") == agent_type else None

    if chart_data is not None:
        _LAST_VISUAL["kind"]       = agent_type   # "market" | "finance" | "ops"
        _LAST_VISUAL["data"]       = chart_data
        _LAST_VISUAL["text"]       = response
        _LAST_VISUAL["user_input"] = user_input
    elif agent_type in VISUAL_TRIGGERS:
        _LAST_VISUAL["kind"]       = "report"
        _LAST_VISUAL["data"]       = None
        _LAST_VISUAL["text"]       = response
        _LAST_VISUAL["user_input"] = user_input
    else:
        _LAST_VISUAL["kind"] = None

    # Reset chart data slot so a stale chart isn't reused next time
    _LAST_CHART_DATA["agent_type"] = None
    _LAST_CHART_DATA["data"]       = None


def get_last_visual() -> dict | None:
    """Called by tad_gui.py on the main thread after run_task() returns."""
    if _LAST_VISUAL["kind"] is None:
        return None
    visual = dict(_LAST_VISUAL)
    _LAST_VISUAL["kind"] = None
    return visual


# ── Main task router ──────────────────────────────────────────────────────────

def run_task(user_input: str, status_callback=None) -> str:
    """
    Main entry point. Identifies the right agent and routes the task.
    Checks learned skill library before routing.
    """
    _status(status_callback, "identifying agent...")

    # Check skill library first
    try:
        sys.path.insert(0, str(AGENTS_DIR))
        from skill_library import find_skill_for_task, auto_learn_from_task
        matching_skill = find_skill_for_task(user_input)
        if matching_skill:
            _status(status_callback, f"using skill: {matching_skill['name']}")
    except Exception:
        matching_skill = None
        auto_learn_from_task = None

    # Priority -1: action commands bypass identify_agent() entirely.
    # "implement that skill", "fix the routing", "apply the new routing" all
    # hit Priority-3 conversational_signals without this check and get
    # role-played by Kimi/Haiku as fake execution logs.
    _action = _is_action_command(user_input)
    if _action:
        agent_type = _action
        _status(status_callback, f"action command detected → {_action} agent (bypassing router)...")
        print(f"[router] _is_action_command → {_action} (action command bypassed identify_agent)")
    else:
        agent_type = identify_agent(user_input)
        _status(status_callback, f"{agent_type} agent activated...")

    # Route to the correct agent — every call goes through the
    # observability wrapper so memory/metrics.json tracks all agents
    from skills.tad_observability import observe_call

    if agent_type == "market" or agent_type == "research":
        runner = lambda: run_market_agent(user_input, status_callback)
    elif agent_type == "decision":
        runner = lambda: run_decision_agent(user_input, status_callback)
    elif agent_type == "finance":
        runner = lambda: run_finance_agent(user_input, status_callback)
    elif agent_type == "ops":
        runner = lambda: run_ops_agent(user_input, status_callback)
    elif agent_type == "cseo":
        runner = lambda: run_cseo_agent(user_input, status_callback)
    elif agent_type == "marketing":
        runner = lambda: run_marketing_agent(user_input, status_callback)
    elif agent_type == "ceo":
        runner = lambda: run_ceo_agent(user_input, status_callback)
    else:
        # build, general — use Kimi with skill file
        runner = lambda: _run_kimi_with_skill(user_input, agent_type, status_callback)

    raw = observe_call(agent_type, runner)

    # Shape response through Conversation Engine — EXCEPT for real execution
    # reports. These agents return factual data (metrics, decisions, health);
    # re-narrating through Haiku risks fabricated or distorted numbers.
    # Return verbatim. Only pure conversational responses go through shaping.
    VERBATIM_AGENTS = {"cseo", "market", "decision", "finance", "ops",
                       "marketing", "ceo"}
    if agent_type in VERBATIM_AGENTS:
        final = raw
    else:
        _status(status_callback, "shaping response...")
        final = _shape_response(raw, user_input)

    # Save to memory
    _save_run(user_input, final, agent_type)

    # Update THE_MONKEY.md
    update_monkey(task_type=agent_type, completed_item="", new_files=[])

    # Trigger visual for complex tasks
    _trigger_visual(final, agent_type, user_input)

    # Auto-learn from completed task
    try:
        from skill_library import auto_learn_from_task
        if auto_learn_from_task and final and len(final) > 50:
            threading.Thread(
                target=auto_learn_from_task,
                args=(user_input, final, True),
                daemon=True
            ).start()
    except Exception:
        pass

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