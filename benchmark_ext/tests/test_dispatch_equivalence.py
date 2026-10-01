"""V0 — features-off equivalence: on a STOCK AppWorld task, whose grader defines no `evaluate_extended`,
`evaluate_task_extended` reproduces stock `evaluate_task` requirement for requirement. And when a grader does
define one, the wrapper calls that instead, with the trajectory.

The run these grade is built here: a world constructed, one real API call made, then saved. That is enough
output for both graders to read, and it needs nothing on disk but AppWorld's own data.
"""
from __future__ import annotations

import types

from benchmark_ext.evaluate import evaluate_task_extended

TASK = "07b42fd_1"   # a stock task: spotify, follow classical artists with >= 22 followers


def _summary(tracker):
    return (
        tracker.success,
        tracker.pass_count,
        tracker.fail_count,
        frozenset(p["requirement"] for p in tracker.passes),
        frozenset(f["requirement"] for f in tracker.failures),
    )


def _run_and_save(experiment_name: str) -> None:
    from appworld.environment import AppWorld

    world = AppWorld(task_id=TASK, experiment_name=experiment_name, random_seed=1)
    world.execute("print(apis.api_docs.show_app_descriptions())")   # one logged API call
    world.save()
    AppWorld.close_all()


def test_v0_extended_matches_stock_on_a_stock_task(live_root):
    from appworld.environment import AppWorld
    from appworld.evaluator import evaluate_task

    _run_and_save("v0")
    stock_summary = _summary(evaluate_task(TASK, experiment_name="v0", save_report=False))
    AppWorld.close_all()   # drop cached in-memory DBs before re-loading the same task
    assert _summary(evaluate_task_extended(TASK, experiment_name="v0")) == stock_summary


def test_dispatch_prefers_evaluate_extended(monkeypatch, live_root):
    """When a task's module defines evaluate_extended, the wrapper must call THAT (with the
    trajectory), not stock evaluate(). We stub the module loader to isolate the dispatch."""
    import benchmark_ext.evaluate as evaluate_mod

    called = {"stock": 0, "extended": 0, "got_trajectory": False}

    fake_module = types.ModuleType("fake_eval")

    def evaluate(test, **kw):  # stock path
        called["stock"] += 1

    def evaluate_extended(test, trajectory=None, **kw):  # extended path
        called["extended"] += 1
        called["got_trajectory"] = trajectory is not None and len(trajectory.actions) > 0

    fake_module.evaluate = evaluate
    fake_module.evaluate_extended = evaluate_extended
    monkeypatch.setattr(evaluate_mod, "_load_evaluation_module", lambda ground_truth: fake_module)

    _run_and_save("dispatch")
    evaluate_task_extended(TASK, experiment_name="dispatch")
    assert called["extended"] == 1 and called["stock"] == 0
    assert called["got_trajectory"] is True
