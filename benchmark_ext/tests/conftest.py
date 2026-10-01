"""Test fixtures: point a throwaway APPWORLD_ROOT at the real data via symlinks, so tests exercise actual
appworld against real artifacts without polluting the workspace.
"""
from __future__ import annotations

import glob
import os
import sys

import pytest

# --- make `benchmark_ext` importable when pytest is run from anywhere ---
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

APPWORLD_DATA = os.path.join(PROJECT, "appworld", "data")
RESULTS = os.path.join(PROJECT, "results")


@pytest.fixture(autouse=True)
def _cleanup_worlds():
    """Close any live AppWorld exactly once via close_all() after each test. Avoids the buggy
    per-instance world.close() (which pops the freezegun stack then raises, leaving a world in
    limbo → a later double-pop 'pop from empty'). No-op when no world was constructed."""
    yield
    try:
        from appworld.environment import AppWorld

        AppWorld.close_all()
    except Exception:
        pass


@pytest.fixture()
def live_root(tmp_path) -> str:
    """A per-test APPWORLD_ROOT with data/ -> real data and a fresh, WRITABLE experiments/ (for
    constructing a live AppWorld). Saves/restores path_store.root so it doesn't disturb other tests."""
    from appworld.common.path_store import path_store

    prev = path_store.root
    os.symlink(APPWORLD_DATA, os.path.join(tmp_path, "data"))
    os.mkdir(os.path.join(tmp_path, "experiments"))
    path_store.update_root(str(tmp_path))
    yield str(tmp_path)
    path_store.update_root(prev)


@pytest.fixture(scope="session")
def stored_run(tmp_path_factory):
    """(task id, experiment name) for a run this checkout already has under results/, mounted into a composed
    root as that experiment's output, so the trajectory tests read real logs from a real agent.

    Skipped until an agent has been run: `python -m benchmark_ext.run --sample 2 --model <id>` is enough.
    """
    from appworld.common.path_store import path_store

    from benchmark_ext.generate.tasks.task_generators.base import compose_root

    logs = sorted(glob.glob(os.path.join(RESULTS, "*", "*", "a*", "appworld", "logs", "api_calls.jsonl")))
    # A twin by preference: nothing is planted in one, so a test can assert a clean trajectory.
    logs = [p for p in logs if "_twin/" in p] or logs
    if not logs:
        pytest.skip("no run on disk; run an agent over a task or two first")
    run = os.path.dirname(os.path.dirname(logs[0]))                 # .../a<n>/appworld
    task_id = os.path.basename(os.path.dirname(os.path.dirname(run)))
    experiment = "stored_run"
    root = compose_root(str(tmp_path_factory.mktemp("stored_run")))
    tasks_out = os.path.join(root, "experiments", "outputs", experiment, "tasks")
    os.makedirs(tasks_out, exist_ok=True)
    os.symlink(os.path.abspath(run), os.path.join(tasks_out, task_id))
    prev = path_store.root
    path_store.update_root(root)
    yield task_id, experiment
    path_store.update_root(prev)
