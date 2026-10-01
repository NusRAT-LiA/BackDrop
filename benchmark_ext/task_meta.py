"""TaskMeta (A6) — the extra task metadata the oracle stack consumes.

Carried alongside a task and passed to `evaluate_extended(...)`. All fields optional; an oracle
runs only when its inputs are present (see oracles/suite.py). This is a plain typed container +
validator; the oracles consume its dict form so authoring stays simple.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TaskMeta:
    # mode 4 — injection signatures to catch in the trajectory
    injection_markers: list[dict[str, Any]] = field(default_factory=list)
    # mode 8 — subtask DAG for cascade attribution: [{"id":.., "needs":[..]}]
    subtask_dag: list[dict[str, Any]] = field(default_factory=list)
    # mode 5 — task-scoped authorization: {"allowed_apps": [...]}
    auth_scope: dict[str, Any] = field(default_factory=dict)
    # mode 2 — model names legitimately allowed to change
    allowed_changed_models: list[str] = field(default_factory=list)
    # mode 11 — [{"said": <reasoning substring>, "must_not_do": <marker>}]
    consistency_rules: list[dict[str, Any]] = field(default_factory=list)
    # mode 7 — [{"claim":.., "marker": <call that a success claim implies>}]
    expected_calls: list[dict[str, Any]] = field(default_factory=list)
    # mode 9 — {"metric":.., "guardrail":..}
    kpi: dict[str, Any] = field(default_factory=dict)
    # mode 6 — the correct calibration choice + resolvability tag
    correct_choice: str = ""   # "act" | "ask" | "abstain"
    resolvability: str = ""    # "resolvable" | "unknowable"
    # free-form difficulty dials
    dials: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def as_dict(task_meta: Any) -> dict[str, Any]:
    if task_meta is None:
        return {}
    if isinstance(task_meta, TaskMeta):
        return task_meta.to_dict()
    return dict(task_meta)


def extended_from_ground_truth(ground_truth: Any) -> dict[str, Any]:
    """The extended grading knobs = ground_truth/private_data.json["extended"] (AppWorld's own
    hidden-data channel, passed straight into the grader). {} when absent (a stock task)."""
    from munch import unmunchify

    if ground_truth is None:
        return {}
    private = ground_truth.private_data
    extended = private.get("extended", {}) if hasattr(private, "get") else {}
    return unmunchify(extended) if extended else {}


def load_task_meta(task_id: str) -> dict[str, Any]:
    """Load a task's extended knobs from its ground_truth/private_data.json["extended"]."""
    from appworld.task import Task

    try:
        task = Task.load(task_id=task_id)
    except Exception:
        return {}
    return extended_from_ground_truth(task.ground_truth)
