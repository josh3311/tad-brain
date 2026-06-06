"""
TAD Skill Loader
Finds and loads the right .md skill file before every task.
If skill doesn't exist, TAD builds it and saves it to skills/learned/
"""

import os
import json
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── Kimi client for skill building ──────────
client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)
MODEL = "kimi-k2.6"

# ── Skill directory map ───────────────────
SKILL_DIRS = {
    "research":    Path("skills/agents/research"),
    "business":    Path("skills/agents/business"),
    "coding":      Path("skills/agents/coding"),
    "universal":   Path("skills/universal"),
    "learned":     Path("skills/learned"),
}

# ── Keyword → skill mapping ───────────────
SKILL_MAP = {
    "market":        ("research",  "market_analysis"),
    "research":      ("research",  "market_analysis"),
    "analyze":       ("research",  "market_analysis"),
    "analyse":       ("research",  "market_analysis"),
    "trend":         ("research",  "market_analysis"),
    "niche":         ("research",  "market_analysis"),
    "opportunity":   ("business",  "opportunity_score"),
    "profitable":    ("business",  "opportunity_score"),
    "score":         ("business",  "opportunity_score"),
    "business idea": ("business",  "opportunity_score"),
    "debug":         ("coding",    "debug"),
    "error":         ("coding",    "debug"),
    "fix":           ("coding",    "debug"),
    "bug":           ("coding",    "debug"),
    "broken":        ("coding",    "debug"),
}


def find_skill(user_input: str) -> tuple[str, str]:
    """
    Match user input to a skill.
    Returns (category, skill_name) or ("universal", "sovereign_system")
    """
    text = user_input.lower()
    for keyword, (category, skill) in SKILL_MAP.items():
        if keyword in text:
            return category, skill
    return "universal", "sovereign_system"


def load_skill(category: str, skill_name: str) -> str:
    """
    Load skill content from .md file.
    If not found, build it automatically and save to learned/.
    """
    # Check known locations first
    skill_path = SKILL_DIRS.get(category, Path("skills")) / f"{skill_name}.md"

    if skill_path.exists():
        content = skill_path.read_text(encoding="utf-8")
        print(f"[skill_loader] Loaded: {skill_path}")
        return content

    # Check learned folder as fallback
    learned_path = SKILL_DIRS["learned"] / f"{skill_name}.md"
    if learned_path.exists():
        content = learned_path.read_text(encoding="utf-8")
        print(f"[skill_loader] Loaded from learned: {learned_path}")
        return content

    # Skill not found — build it automatically
    print(f"[skill_loader] Skill '{skill_name}' not found — building it...")
    return _build_skill(skill_name)


def _build_skill(skill_name: str) -> str:
    """
    Ask Kimi to generate a new skill .md file.
    Saves it to skills/learned/ for permanent use.
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """You are TAD's skill builder. 
Create a skill .md file for the given skill name.
Follow this exact structure:

# Skill: [name]

## Purpose
[one sentence]

## Instructions
[numbered steps]

## Tools needed
[list from: web_search, file_write, file_read, code_exec]

## Output format
[how to structure the output]

## Success criteria
[how to know the skill worked]

Return ONLY the markdown content, nothing else."""
                },
                {
                    "role": "user",
                    "content": f"Build a skill file for: {skill_name}"
                }
            ],
            max_tokens=1024,
        )

        skill_content = response.choices[0].message.content

        # Save to learned folder permanently
        learned_path = SKILL_DIRS["learned"] / f"{skill_name}.md"
        learned_path.parent.mkdir(parents=True, exist_ok=True)
        learned_path.write_text(skill_content, encoding="utf-8")

        print(f"[skill_loader] Built and saved new skill: {learned_path}")
        return skill_content

    except Exception as e:
        print(f"[skill_loader] Failed to build skill: {e}")
        return ""


def get_skill_for_task(user_input: str) -> str:
    """
    Main entry point.
    Given user input, find and return the right skill content.
    """
    category, skill_name = find_skill(user_input)
    return load_skill(category, skill_name)


def list_all_skills() -> list:
    """
    Return a list of all available skills across all folders.
    """
    skills = []
    for category, folder in SKILL_DIRS.items():
        if folder.exists():
            for f in folder.glob("*.md"):
                skills.append({
                    "category": category,
                    "name": f.stem,
                    "path": str(f)
                })
    return skills