"""Provider-agnostic agent adapters: code extraction + the ReAct loop driven by a stub LLM
(no API/SDK needed), proving any `llm: Callable[[messages], str]` plugs into the harness."""
from __future__ import annotations

import os

import pytest

from benchmark_ext.agents import extract_code, litellm_llm, messages_to_prompt, openai_chat_llm, react_agent

GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class _FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}

TASK = "07b42fd_1"


def test_extract_code_variants():
    assert extract_code("think\n```python\nx = 1\n```\ndone") == "x = 1"
    assert extract_code("```\napis.foo()\n```") == "apis.foo()"
    assert extract_code("no code here") == ""


def test_messages_to_prompt_flattens():
    prompt = messages_to_prompt([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}])
    assert "[SYSTEM]" in prompt and "S" in prompt and "[USER]" in prompt and "U" in prompt


@pytest.mark.parametrize("base_url,model", [
    ("https://openrouter.ai/api/v1", "google/gemini-2.5-flash"),
    ("https://api.openai.com/v1", "gpt-4o"),
    ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),  # native Gemini
    ("https://api.deepseek.com/v1", "deepseek-chat"),
    ("https://api.moonshot.cn/v1", "moonshot-v1-8k"),  # Kimi
    ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
])
def test_any_openai_compatible_provider_is_uniform(monkeypatch, base_url, model):
    """Same code path for EVERY provider — only base_url/model/key differ. No SDK, no dict, no adapter."""
    import requests

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    llm = openai_chat_llm(model, base_url=base_url, api_key="k")
    assert llm([{"role": "user", "content": "hi"}]) == "ok"
    assert captured["url"] == base_url.rstrip("/") + "/chat/completions"
    assert captured["json"]["model"] == model
    assert captured["json"]["messages"] == [{"role": "user", "content": "hi"}]  # chat format passes through
    assert captured["headers"]["Authorization"] == "Bearer k"


def test_litellm_llm_routes_by_model_prefix(monkeypatch):
    """The litellm backend (what AppWorld uses) routes by model NAME PREFIX — no base URL/adapter."""
    import sys
    import types

    captured = {}

    class _Resp:
        class _Choice:
            class _Msg:
                content = "ok"

            message = _Msg()

        choices = [_Choice()]

    def completion(model, messages, **kwargs):
        captured.update(model=model, messages=messages)
        return _Resp()

    fake_litellm = types.ModuleType("litellm")
    fake_litellm.completion = completion
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)  # litellm isn't installed; inject a fake

    out = litellm_llm("gemini/gemini-2.5-flash")([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert captured["model"] == "gemini/gemini-2.5-flash"  # routed by prefix, no base_url anywhere
    assert captured["messages"] == [{"role": "user", "content": "hi"}]


def test_llm_config_from_env_is_provider_agnostic(monkeypatch):
    """Set 3 env vars -> `openai_chat_llm()` (no args) runs the SAME against any provider."""
    import requests

    for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-deepseek")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    openai_chat_llm()([{"role": "user", "content": "hi"}])  # no args -> all from env
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["headers"]["Authorization"] == "Bearer sk-deepseek"


def test_missing_config_errors_clearly(monkeypatch):
    for var in ("LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "OPENROUTER_API_KEY",
                "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError):  # no model
        openai_chat_llm(base_url="https://x/v1")
    with pytest.raises(RuntimeError):  # no base_url
        openai_chat_llm("m")
    with pytest.raises(RuntimeError):  # no key (raised at call time)
        openai_chat_llm("m", base_url="https://x/v1")([{"role": "user", "content": "hi"}])


def test_native_gemini_key_via_openai_compat_endpoint(monkeypatch):
    """A NATIVE Gemini API key works through the same helper -> Google's OpenAI-compat endpoint."""
    import requests

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    llm = openai_chat_llm("gemini-2.5-flash", api_key="AIza-native", base_url=GEMINI_OPENAI_BASE_URL)
    llm([{"role": "user", "content": "hi"}])

    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert captured["json"]["model"] == "gemini-2.5-flash"
    assert captured["headers"]["Authorization"] == "Bearer AIza-native"


def test_gemini_api_key_env_var_is_used(monkeypatch):
    """`GEMINI_API_KEY` in the env is picked up automatically (no api_key= needed)."""
    import requests

    for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-from-env")

    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(headers=headers)
        return _FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    openai_chat_llm("gemini-2.5-flash", base_url=GEMINI_OPENAI_BASE_URL)([{"role": "user", "content": "hi"}])
    assert captured["headers"]["Authorization"] == "Bearer AIza-from-env"


def test_react_agent_runs_any_llm_end_to_end(live_root):
    """A stub 'LLM' drives the real env through the ReAct loop; the run is graded and the CoT captured."""
    from benchmark_ext.runner import _logs_dir, run_extended_task

    calls = {"n": 0}

    def stub_llm(messages):
        # any provider adapts to this signature: (list[{role,content}]) -> str
        assert messages[0]["role"] == "system" and "Task:" in messages[1]["content"]
        calls["n"] += 1
        if calls["n"] == 1:
            return "First I read the task.\n```python\nprint(apis.supervisor.show_active_task())\n```"
        return "Now I finish.\n```python\napis.supervisor.complete_task(status='success', answer='done')\n```"

    tracker = run_extended_task(TASK, react_agent(stub_llm, max_steps=5), experiment_name="react_stub")

    assert calls["n"] >= 2          # the LLM was actually driven multiple steps
    assert tracker.total_count > 0  # the task was graded (07b42fd_1 -> stock fallback grader)
    # the CoT was captured for mode 11 (messages.jsonl persisted by the runner)
    messages_path = os.path.join(_logs_dir("react_stub", TASK), "messages.jsonl")
    assert os.path.isfile(messages_path) and os.path.getsize(messages_path) > 0


# ---- Option 3: AppWorld's OWN SimplifiedReActCodeAgent, run on our overlay world -------------

def test_appworld_agent_model_wraps_litellm_and_is_the_real_agent():
    """`appworld_agent(model=…)` constructs AppWorld's REAL SimplifiedReActCodeAgent (not a reimpl),
    wrapping litellm — offline, no key (the adapter injection sidesteps the eager OpenAI() client)."""
    pytest.importorskip("appworld_agents")
    from appworld_agents.code.simplified.react_code_agent import SimplifiedReActCodeAgent

    from benchmark_ext.agents import appworld_agent

    agent = appworld_agent(model="gemini/gemini-2.5-flash", max_steps=4)
    assert callable(agent)
    assert isinstance(agent.simplified_agent, SimplifiedReActCodeAgent)  # reuse, not reimplementation


def test_appworld_agent_runs_real_agent_end_to_end(live_root):
    """A stub 'LLM' drives AppWorld's REAL agent loop on a real env through run_extended_task; the run
    is graded and the CoT captured — same integration as react_agent, but the loop is AppWorld's own."""
    pytest.importorskip("appworld_agents")
    from appworld_agents.code.simplified.react_code_agent import SimplifiedReActCodeAgent

    from benchmark_ext.agents import appworld_agent
    from benchmark_ext.runner import _logs_dir, run_extended_task

    calls = {"n": 0}

    def stub_llm(messages):
        # AppWorld's agent builds the prompt as user/assistant/system turns (not our react framing)
        assert messages and messages[0]["role"] in ("user", "assistant", "system")
        calls["n"] += 1
        if calls["n"] == 1:
            return "Reasoning: inspect the task.\n```python\nprint(apis.supervisor.show_active_task())\n```"
        return "Reasoning: finish.\n```python\napis.supervisor.complete_task(status='success', answer='done')\n```"

    agent = appworld_agent(llm=stub_llm, max_steps=6)
    assert isinstance(agent.simplified_agent, SimplifiedReActCodeAgent)

    tracker = run_extended_task(TASK, agent, experiment_name="aw_agent_stub")

    assert calls["n"] >= 2          # AppWorld's agent was actually driven multiple steps
    assert tracker.total_count > 0  # graded (07b42fd_1 -> stock fallback grader)
    messages_path = os.path.join(_logs_dir("aw_agent_stub", TASK), "messages.jsonl")
    assert os.path.isfile(messages_path) and os.path.getsize(messages_path) > 0


def test_appworld_agent_model_config_path_errors_clearly_without_openai_key(monkeypatch):
    """The full-fidelity `model_config=` path uses AppWorld's exact LanguageModel, which builds an
    OpenAI() client eagerly — without OPENAI_API_KEY our factory raises a clear, actionable error."""
    pytest.importorskip("appworld_agents")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    from benchmark_ext.agents import appworld_agent

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        appworld_agent(model_config={"name": "gemini/gemini-2.5-flash", "client_name": "litellm"})
