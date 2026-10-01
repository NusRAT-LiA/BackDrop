"""The results store: run directories, done-ness, selectors, and the derived index (no AppWorld, no model)."""
from __future__ import annotations

import json
import os

import pytest

from benchmark_ext import store


def test_scenario_of_reads_anchor_instance_and_variant():
    assert store.scenario_of("83a7951_compound") == {"anchor": "83a7951", "instance": 1, "variant": "compound"}
    assert store.scenario_of("83a7951c_ablauth") == {"anchor": "83a7951", "instance": 3, "variant": "ablauth"}
    assert store.scenario_of("fb05fedb_twin")["instance"] == 2


def test_selectors_cover_the_standing_set():
    c, t, a = store.select_tasks("compounds"), store.select_tasks("twins"), store.select_tasks("ablations")
    assert c and t and a and all(x.endswith("_compound") for x in c) and all(x.endswith("_twin") for x in t)
    assert set(store.select_tasks("compounds,twins")) == set(c) | set(t)
    assert len(store.select_tasks("all")) >= len(c) + len(t) + len(a)
    with pytest.raises(SystemExit):
        store.select_tasks("nonsense")


def test_done_index_and_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "RESULTS", str(tmp_path))
    agent, task = "react_test", "83a7951_compound"
    assert not store.is_done(agent, task, 1)
    d = store.run_dir(agent, task, 1)
    store.write_json(os.path.join(d, "manifest.json"), {"agent_id": agent, "task_id": task, "attempt": 1, "status": "ok", "model": "m",
                                                        "scenario": store.scenario_of(task), "steps": 7, "tokens": {"total": 1234}, "duration_s": 9.5, "commits": {"appworld_extend": "abc"}})
    store.write_json(os.path.join(d, "verdict.json"), {"graded_at": "t", "stock": {"success": False, "passes": [1, 2], "failures": [3]},
                                                       "extended": {"modes_fired": [4, 10], "signals": {"reachable_success": False, "claimed_success": True}}})
    assert store.is_done(agent, task, 1)
    path = store.rebuild_index()
    rows = [json.loads(l) for l in open(path)]
    assert rows == store.index_rows() and rows[0]["modes_fired"] == [4, 10] and rows[0]["variant"] == "compound" and rows[0]["stock_failed"] == 1
    assert "| react_test | compound | 1 | 0% | 0% | 2.00 | 1,234 |" in store.summary(rows)
    store.register_agent(agent, {"model": "m"})
    with pytest.raises(SystemExit):
        store.register_agent(agent, {"model": "other"})
