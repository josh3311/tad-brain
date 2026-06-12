"""config_providers helpers return expected types on mocked API responses."""
import json
from types import SimpleNamespace

import config_providers


def _fake_claude(text):
    """Stand-in for the anthropic client: messages.create → .content[0].text"""
    response = SimpleNamespace(content=[SimpleNamespace(text=text)])
    return SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))


def _fake_kimi(text):
    """Stand-in for the OpenAI client: chat.completions.create → choices[0].message.content"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response))
    )


def test_claude_chat_returns_str(monkeypatch):
    monkeypatch.setattr(config_providers, "claude", _fake_claude("hello there"))
    out = config_providers.claude_chat("system", "user")
    assert isinstance(out, str)
    assert out == "hello there"


def test_claude_chat_returns_empty_string_on_error(monkeypatch):
    def boom(**kw):
        raise RuntimeError("api down")

    fake = SimpleNamespace(messages=SimpleNamespace(create=boom))
    monkeypatch.setattr(config_providers, "claude", fake)
    out = config_providers.claude_chat("system", "user")
    assert out == ""


def test_claude_json_strips_fences_and_returns_valid_json(monkeypatch):
    fenced = '```json\n{"status": "working"}\n```'
    monkeypatch.setattr(config_providers, "claude", _fake_claude(fenced))
    out = config_providers.claude_json("system", "user")
    assert isinstance(out, str)
    assert json.loads(out) == {"status": "working"}


def test_kimi_code_extracts_python_fence(monkeypatch):
    raw = "Here is the code:\n```python\ndef add(a, b):\n    return a + b\n```"
    monkeypatch.setattr(config_providers, "kimi", _fake_kimi(raw))
    out = config_providers.kimi_code("system", "user")
    assert isinstance(out, str)
    assert out.startswith("def add")
    assert "```" not in out


def test_kimi_code_returns_raw_when_no_fence(monkeypatch):
    monkeypatch.setattr(config_providers, "kimi", _fake_kimi("x = 1"))
    out = config_providers.kimi_code("system", "user")
    assert out == "x = 1"


def test_kimi_code_returns_empty_string_on_error(monkeypatch):
    def boom(**kw):
        raise RuntimeError("api down")

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=boom))
    )
    monkeypatch.setattr(config_providers, "kimi", fake)
    assert config_providers.kimi_code("system", "user") == ""
