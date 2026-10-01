"""An agent id is one configuration: model, temperature, steps, prompt. The per-call timeout and retry count are
transport settings, recorded in every manifest; changing them does not make a different agent (the five hung
requests of pass 5 were re-run with a 900 s limit under the pass's own agent id)."""
import json
import os

import pytest

from benchmark_ext import store


def _config(**over):
    base = {"scaffold": "s", "model": "m", "temperature": 0.0, "max_steps": 50, "max_output_length": None, "random_seed": 1,
            "prompt_file": "p", "prompt_sha1": "abc", "llm_timeout_s": 300.0, "llm_retries": 10}
    return {**base, **over}


def test_transport_settings_may_differ_but_the_agent_may_not(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RESULTS", str(tmp_path))
    store.register_agent("a1", _config())
    store.register_agent("a1", _config(llm_timeout_s=900.0, llm_retries=5))          # allowed
    assert json.load(open(os.path.join(tmp_path, "a1", "agent.json")))["llm_timeout_s"] == 300.0   # the first registration stands
    with pytest.raises(SystemExit):
        store.register_agent("a1", _config(max_steps=40))                             # a different agent
