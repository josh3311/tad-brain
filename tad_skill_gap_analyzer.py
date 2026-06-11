"""TAD Skill Gap Analyzer — core data model and gap calculation."""

from dataclasses import dataclass, field
from typing import Dict
import sys


@dataclass
class Role:
    name: str
    skills: Dict[str, int] = field(default_factory=dict)


@dataclass
class Agent:
    name: str
    skills: Dict[str, int] = field(default_factory=dict)


def compute_skill_gap(role: Role, agent: Agent) -> Dict[str, int]:
    """Return skill gaps as {skill_name: deficit}."""
    gaps = {}
    for skill, required in role.skills.items():
        current = agent.skills.get(skill, 0)
        if required > current:
            gaps[skill] = required - current
    return gaps


def _run_tests() -> None:
    role = Role("Engineer", {"python": 5, "git": 3})
    agent = Agent("Alice", {"python": 3})
    assert compute_skill_gap(role, agent) == {"python": 2, "git": 3}

    agent2 = Agent("Bob", {"python": 5, "git": 4})
    assert compute_skill_gap(role, agent2) == {}

    agent3 = Agent("Charlie", {})
    assert compute_skill_gap(role, agent3) == {"python": 5, "git": 3}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        _run_tests()
        sys.exit(0)