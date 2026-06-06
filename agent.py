"""
TAD — Sovereign Agent Core v0.3
- Reads THE_MONKEY.md before every task
- Uses skill_loader to pick right skill file
- Updates THE_MONKEY.md after every completed task
- LLM router ready
- Launches visual popup after research tasks
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

MONKEY_PATH = Path("THE_MONKEY.md")
MEMORY_PATH = Path("memory/history.jsonl")

AGENT_SYSTEM = """You are TAD's task execution brain — Joshua's sovereign business agent.

You have been given a SKILL FILE with exact instructions for this task.
Follow the skill instructions precisely.

You also have TAD's PROJECT STATE from THE_MONKEY.md.
Use it to understand what is already built and what is needed next.

RULES:
1. Always use web_search to get real current data first
2. Always use file_write to save your report before responding
3. Filename format: [topic]-[date].md where date is today in YYYY-MM-DD format
4. Return a concise summary after saving — under 5 sentences
5. Speak like Joshua's smart business partner, not a corporate assistant"""


def read_monkey() -> str:
    if MONKEY_PATH.exists():
        return MONKEY_PATH.read_text(encoding="utf-8")
    return ""


def update_monkey(task_type: str, completed_item: str, new_files: list = None):
    if not MONKEY_PATH.exists():
        return
    content = MONKEY_PATH.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
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


def route_to_provider(task_type: str):
    routes = {
        "research": ("kimi", "kimi-k2.6"),
        "business": ("kimi", "kimi-k2.6"),
        "coding":   ("kimi", "kimi-k2.6"),
        "general":  ("kimi", "kimi-k2.6"),
    }
    provider, model = routes.get(task_type, ("kimi", "kimi-k2.6"))
    print(f"[router] Task: {task_type} → {provider}/{model}")
    return client, model


def run_task(user_input: str, status_callback=None) -> str:
    from tools.registry import SCHEMAS, call as tool_call
    from tad_visual import show_research_report

    # Load skill
    _status(status_callback, "loading skill...")
    skill_content = ""
    category = "general"
    try:
        from skills.skill_loader import get_skill_for_task, find_skill
        skill_content = get_skill_for_task(user_input)
        category, _ = find_skill(user_input)
    except Exception as e:
        print(f"[agent] skill_loader error: {e}")

    # Read project state
    _status(status_callback, "reading project state...")
    monkey_content = read_monkey()

    # Route to provider
    routed_client, routed_model = route_to_provider(category)

    # Build system prompt
    system = AGENT_SYSTEM
    if skill_content:
        system += f"\n\n---\nSKILL FILE:\n{skill_content}"
    if monkey_content:
        system += f"\n\n---\nPROJECT STATE:\n{monkey_content[:2000]}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_input},
    ]

    _status(status_callback, "searching the web...")

    saved_files = []

    for iteration in range(10):
        response = routed_client.chat.completions.create(
            model=routed_model,
            messages=messages,
            tools=SCHEMAS,
            tool_choice="auto",
            max_tokens=4096,
        )

        msg = response.choices[0].message

        if not msg.tool_calls:
            final = msg.content or ""
            _save_run(user_input, final, category)
            update_monkey(task_type=category, completed_item="", new_files=saved_files)

            # Launch visual popup for research/business tasks
            if category in ["research", "business"]:
                try:
                    show_research_report(final, user_input)
                except Exception as e:
                    print(f"[agent] visual error: {e}")

            return final

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

        _status(status_callback, "analyzing results...")

    return "Task completed — check your workflows folder for the full report."


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
        "query":     query,
        "result":    result[:500],
    }
    with open(MEMORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")