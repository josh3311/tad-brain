"""Router classification — 5 sample commands per tier."""
import pytest

from agent import identify_agent

# Tier 1 — explicit agent commands
EXPLICIT = [
    ("run a market scan", "market"),
    ("system health", "ops"),
    ("p&l report for this month", "finance"),
    ("score this opportunity: AI receptionist for dental offices", "decision"),
    ("ceo briefing", "ceo"),
]

# Tier 3 — conversational requests route to general (Claude)
CONVERSATIONAL = [
    ("explain how the scheduler works", "general"),
    ("tell me about yesterday's results", "general"),
    ("why is the gui slow today", "general"),
    ("show me the night logs", "general"),
    ("what do you think about raising prices", "general"),
]

# Tier 4 — keyword scoring (needs 2+ keyword hits for one agent)
KEYWORD = [
    ("industry trends and competitor gaps", "market"),
    ("cold email outreach to linkedin prospects", "marketing"),
    ("unpaid invoice payment expense summary", "finance"),
    ("debug and program the parser module", "build"),
    ("assess this and rate this idea", "decision"),
]


@pytest.mark.parametrize("text,expected", EXPLICIT)
def test_explicit_commands(text, expected):
    assert identify_agent(text) == expected


@pytest.mark.parametrize("text,expected", CONVERSATIONAL)
def test_conversational_routes_to_general(text, expected):
    assert identify_agent(text) == expected


@pytest.mark.parametrize("text,expected", KEYWORD)
def test_keyword_scoring(text, expected):
    assert identify_agent(text) == expected
