"""The three wired pieces: enriched-log loading, run-end persistence, and the runner end-to-end."""
from __future__ import annotations

import json
import os


def test_trajectory_loads_enriched_log(tmp_path):
    from benchmark_ext.trajectory import TrajectoryRecord

    api = os.path.join(tmp_path, "api_calls.jsonl")
    with open(api, "w") as f:
        f.write(json.dumps({"method": "post", "url": "/venmo/transactions", "data": {}}) + "\n")
    enr = os.path.join(tmp_path, "api_calls_enriched.jsonl")
    with open(enr, "w") as f:
        f.write(json.dumps({"method": "post", "url": "/venmo/transactions",
                            "response_status": 422, "forbidden_attempt": True}) + "\n")

    traj = TrajectoryRecord.from_log_files(api, None, enr)
    assert len(traj.actions) == 1
    assert len(traj.enriched) == 1
    assert traj.enriched[0]["response_status"] == 422 and traj.enriched[0]["forbidden_attempt"] is True


def test_run_extended_task_end_to_end(live_root):
    """Runner drives a real env, captures enriched calls, persists all extended logs, and grades."""
    from benchmark_ext.runner import _logs_dir, run_extended_task

    def tiny_agent(world):
        world.execute("print(apis.supervisor.show_active_task())")
        world.execute("apis.supervisor.complete_task(status='success', answer='done')")
        return [{"interaction": 1, "text": "read the task and marked it complete"}]

    tracker = run_extended_task("07b42fd_1", tiny_agent, experiment_name="run_it")

    # evaluation ran (07b42fd_1 has stock evaluate() -> the wrapper falls back; plumbing verified)
    assert tracker.total_count > 0

    directory = _logs_dir("run_it", "07b42fd_1")
    enriched_path = os.path.join(directory, "api_calls_enriched.jsonl")
    assert os.path.isfile(enriched_path)
    with open(enriched_path) as f:
        enriched_lines = [ln for ln in f if ln.strip()]
    assert len(enriched_lines) > 0  # the agent's real API calls were captured with response status
    assert json.loads(enriched_lines[0]).get("response_status") is not None

    assert os.path.isfile(os.path.join(directory, "ask_log.json"))
    assert os.path.isfile(os.path.join(directory, "messages.jsonl"))
