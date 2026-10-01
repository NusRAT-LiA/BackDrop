"""evaluate_task_extended — the additive grading wrapper (Patch 1).

Mirrors `appworld.evaluator.evaluate_task` up to building `models` (same loaders, same
`ModelCollectionPair`), then DISPATCHES:
  - if the task's evaluation module defines `evaluate_extended(...)` -> call it with the
    enriched inputs (trajectory, reasoning, task_meta);
  - else -> call stock `evaluate(...)` with the identical arguments.

So a stock task grades byte-identically to `evaluate_task` (validation V0), and a task that
opts in gets the trajectory-aware oracles. No appworld core file is edited.
"""
from __future__ import annotations

import os
from typing import Any

from appworld.apps.lib.apis.local_remote import set_local_date_and_time
from appworld.apps.lib.models.db import get_db_home_path
from appworld.collections.models import ModelCollection, ModelCollectionPair
from appworld.common.constants import DB_VERSION, DEFAULT_EXPERIMENT_NAME
from appworld.common.path_store import path_store
from appworld.evaluator import TestTracker
from appworld.task import Task

from benchmark_ext.category import CategoryTestTracker
from benchmark_ext.trajectory import TrajectoryRecord


def _load_evaluation_module(ground_truth: Any):
    """Load a task's ground_truth/evaluation.py into a FRESH module namespace.

    appworld's `import_module_file` names every evaluation.py the module "evaluation" and, on `force`,
    `importlib.reload`s it INTO the existing namespace WITHOUT clearing it — so symbols from a
    previously-graded task's grader (notably `evaluate_extended`) leak onto a later stock task, making
    our `hasattr(module, "evaluate_extended")` dispatch order-dependent. Loading the file under a
    path-unique name into a fresh module makes grading order-independent (our layer only; core untouched).
    """
    import importlib.util
    import os
    import re

    path = os.path.join(ground_truth.loaded_from_directory, "evaluation.py")
    name = "benchmark_ext_eval__" + re.sub(r"\W+", "_", os.path.abspath(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_task_extended(
    task_id: str,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    suppress_errors: bool = True,
    task_meta: dict[str, Any] | None = None,
) -> TestTracker:
    task = Task.load(task_id=task_id)
    time_freezer = set_local_date_and_time(task.datetime)
    try:
        if task.db_version != DB_VERSION:
            raise Exception(
                f"Task {task_id} db_version {task.db_version} != DB_VERSION {DB_VERSION}."
            )

        output_directory = os.path.join(path_store.experiment_outputs, experiment_name)
        models_start_db_home_path = task.model_collection.from_db_home_path
        models_end_db_home_path_in_memory = get_db_home_path(
            storage_type="memory", type="task_output", task_id=task_id
        )
        models_end_db_home_path_on_disk = os.path.join(
            output_directory, "tasks", task_id, "dbs"
        )
        models_start = task.model_collection
        models_end = ModelCollection.load(
            to_db_home_path=models_end_db_home_path_in_memory,
            from_db_home_path=models_end_db_home_path_on_disk,
            load_apps=task.allowed_apps,
        )
        models = ModelCollectionPair(
            start_db_home_path=models_start_db_home_path,
            start_model_collection=models_start,
            end_db_home_path=models_end_db_home_path_in_memory,
            end_model_collection=models_end,
        )

        ground_truth = task.ground_truth
        assert ground_truth is not None
        evaluation_module = _load_evaluation_module(ground_truth)  # fresh namespace (order-independent)
        main_user = models.start.admin.MainUser.find_one(**task.supervisor)

        if hasattr(evaluation_module, "evaluate_extended"):
            if task_meta is None:  # extended knobs live in ground_truth/private_data.json["extended"]
                from benchmark_ext.task_meta import extended_from_ground_truth

                task_meta = extended_from_ground_truth(ground_truth)
            # CategoryTestTracker yields the per-category profile; test_data=None because the oracle
            # requirements are not in the base task's test_data (would trip the label check).
            test_tracker = CategoryTestTracker(
                test_data=None,
                difficulty=ground_truth.metadata["difficulty"],
                suppress_errors=suppress_errors,
            )
            # the stock floor labels: what a no-op fails is what "done" means to the generic grader (grader.goal_met)
            test_tracker.stock_test_data = ground_truth.test_data
            trajectory = TrajectoryRecord.from_experiment(task_id, experiment_name)
            evaluation_module.evaluate_extended(
                test=test_tracker,
                public_data=ground_truth.public_data,
                private_data=ground_truth.private_data,
                main_user=main_user,
                models=models,
                ground_truth_answer=ground_truth.answer,
                trajectory=trajectory,
                reasoning=trajectory.messages or trajectory.interactions,
                task_meta=task_meta or {},
            )
        else:
            # IDENTICAL to stock evaluate_task's call — this is what V0 verifies.
            test_tracker = TestTracker(
                test_data=ground_truth.test_data,
                difficulty=ground_truth.metadata["difficulty"],
                suppress_errors=suppress_errors,
            )
            evaluation_module.evaluate(
                test=test_tracker,
                public_data=ground_truth.public_data,
                private_data=ground_truth.private_data,
                main_user=main_user,
                models=models,
                ground_truth_answer=ground_truth.answer,
            )
    finally:
        time_freezer.stop()

    return test_tracker
