"""Every agent module must import cleanly (no API calls at import time)."""
import importlib

import pytest

AGENT_MODULES = [
    "market_agent",
    "decision_agent",
    "ceo_agent",
    "finance_agent",
    "ops_agent",
    "cseo_agent",
    "build_agent",
    "marketing_agent",
    "conversation_engine",
]

CORE_MODULES = [
    "config_providers",
    "agent",
    "scheduler",
]


@pytest.mark.parametrize("module_name", AGENT_MODULES + CORE_MODULES)
def test_module_imports_cleanly(module_name):
    mod = importlib.import_module(module_name)
    assert mod is not None
