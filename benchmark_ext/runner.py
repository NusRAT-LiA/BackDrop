"""run_extended_task — the harness that runs a task through the full overlay and grades it.

Flow:
  construct AppWorld  ->  install_overlay (enrichment + faults)  ->  install_ask_channel
  ->  run the agent loop  ->  persist extended logs  ->  evaluate_task_extended  ->  TestTracker

Additive: uses only public appworld entry points + our overlay. Nothing in appworld core changes.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

from appworld.common.path_store import path_store

from benchmark_ext.ask_channel import install_ask_channel
from benchmark_ext.evaluate import evaluate_task_extended
from benchmark_ext.overlay import install_overlay
from benchmark_ext.reasoning import write_messages
from benchmark_ext.task_meta import load_task_meta


def _logs_dir(experiment_name: str, task_id: str) -> str:
    return os.path.join(path_store.experiment_outputs, experiment_name, "tasks", task_id, "logs")


def persist_extended_logs(
    world: Any, experiment_name: str, task_id: str, messages: list[dict[str, Any]] | None = None
) -> str:
    """Dump the run artifacts the extended oracles need (stock logs are written by appworld)."""
    directory = _logs_dir(experiment_name, task_id)
    os.makedirs(directory, exist_ok=True)

    enriched = getattr(world.requester, "enriched_records", [])
    with open(os.path.join(directory, "api_calls_enriched.jsonl"), "w") as f:
        for record in enriched:
            f.write(json.dumps(record, default=str) + "\n")

    with open(os.path.join(directory, "ask_log.json"), "w") as f:
        json.dump(getattr(world, "ask_log", []), f, default=str)

    if messages is not None:
        write_messages(os.path.join(directory, "messages.jsonl"), messages)
    return directory


def _without_ellipsis(value: Any) -> Any:
    """`...` typed by the agent as an API argument survives in the request log as Python's Ellipsis, which
    FastAPI's encoder cannot serialize; AppWorld's request tracker then fails to save and the run is lost
    after the fact. Replace it with its source text so the log is written and the run grades."""
    if value is Ellipsis:
        return "..."
    if isinstance(value, dict):
        return {k: _without_ellipsis(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_without_ellipsis(v) for v in value)
    return value


def sanitize_request_log(world: Any) -> int:
    """Scrub Ellipsis out of every request the world's tracker recorded. Returns how many requests changed."""
    changed = 0
    try:   # AppWorld keeps the tracker on its requester; nothing else on the world is touched (its `apis`
        tracker = world.requester.request_tracker   # namespace raises on unknown attribute names)
        requests = tracker.requests
    except Exception:
        return 0
    if not isinstance(requests, list):
        return 0
    for i, request in enumerate(requests):
        cleaned = _without_ellipsis(request)
        if cleaned is not request and cleaned != request:
            requests[i] = cleaned
            changed += 1
    return changed


def run_extended_task(
    task_id: str,
    agent: Callable[[Any], list[dict[str, Any]] | None],
    *,
    experiment_name: str = "benchmark_ext",
    fault_plan: Any = None,
    simulator: Any = None,
    task_meta: dict[str, Any] | None = None,
    pre_run: Callable[[Any], None] | None = None,
    post_run: Callable[[Any], None] | None = None,
) -> Any:
    """Run `agent(world)` on the task under the full overlay, then grade with the extended stack.

    `agent(world)` drives `world.execute(...)` and returns its per-interaction reasoning messages
    (list of {interaction, text}) or None.
    """
    from appworld.environment import AppWorld

    if task_meta is None:
        task_meta = load_task_meta(task_id)
    # a `fault` trap module declares fault_specs in task_meta -> build the runtime FaultPlan (mode 10)
    if fault_plan is None and task_meta.get("fault_specs"):
        from benchmark_ext.faults import FaultPlan, FaultSpec

        fault_plan = FaultPlan([FaultSpec(**spec) for spec in task_meta["fault_specs"]])

    world = AppWorld(task_id=task_id, experiment_name=experiment_name, random_seed=1)
    install_overlay(world, fault_plan=fault_plan, cue_markers=task_meta.get("cue_markers"))
    # a `clarify` trap declares an unknowable-but-askable item (mode 6 ask-path) -> build the scripted
    # persona: it KNOWS the load-bearing answer (so asking is right) and knows nothing else (so asking
    # a resolvable question self-serves to "check your own records"). This encodes resolvability.
    if simulator is None and task_meta.get("clarify"):
        from benchmark_ext.user_simulator import Persona, UserSimulator

        clarify = task_meta["clarify"]
        key = clarify.get("question_key", "")
        simulator = UserSimulator(Persona(knowledge={key: clarify.get("answer", "")}, load_bearing={key}))
    if simulator is not None:
        install_ask_channel(world, simulator)
    if pre_run is not None:   # experiments: intervene on the world BEFORE the agent (e.g. a counterfactual swap)
        pre_run(world)

    messages = agent(world) or []

    if post_run is not None:  # experiments: read world state AFTER the agent, before it is persisted/closed
        post_run(world)
    doc = getattr(world, "ask_supervisor_doc", None)
    if doc is not None:  # the ask-channel docs row is a runtime affordance, not task state: never persist it
        try:
            doc.delete()
        except Exception:
            pass
    sanitize_request_log(world)  # a bare `...` in an agent's arguments would otherwise sink the stock log save
    world.save()  # persist the final DBs + stock logs
    persist_extended_logs(world, experiment_name, task_id, messages=messages)
    AppWorld.close_all()  # free the in-memory DBs before re-loading for evaluation

    return evaluate_task_extended(task_id, experiment_name=experiment_name, task_meta=task_meta)
