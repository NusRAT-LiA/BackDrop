"""Live integration against a REAL AppWorld env — the overlay wiring exercised end to end on the stock
task 07b42fd_1: enrichment reads a real status, and a seeded fault raises like a real error.

World cleanup is handled once by the autouse `_cleanup_worlds` fixture (close_all), never the
buggy per-instance world.close().
"""
from __future__ import annotations

from benchmark_ext.faults import FaultPlan, FaultSpec
from benchmark_ext.overlay import install_overlay

TASK = "07b42fd_1"  # spotify: follow classical artists with >=22 followers


def test_live_overlay_and_faults(live_root):
    from appworld.environment import AppWorld

    world = AppWorld(task_id=TASK, experiment_name="overlay_it", random_seed=1)

    # --- Patch 2 + S4: enrichment on a REAL response, plus a seeded fault + forbidden-attempt ---
    plan = FaultPlan([FaultSpec(app="spotify", endpoint_contains="artists", status=422, trigger_on_nth=1)])
    records = install_overlay(world, fault_plan=plan)

    # a real, un-faulted GET -> captured with the real status
    resp = world.requester._get("/supervisor/profile", data={})
    assert getattr(resp, "status_code", None) == 200
    assert records[-1]["response_status"] == 200
    assert records[-1]["forbidden_attempt"] is False

    # a seeded fault on a mutating call -> synthetic 422 that raises like a real error; the enriched
    # record still captures it (real endpoint never hit)
    try:
        world.requester._post("/spotify/artists", data={"access_token": "x"})
    except Exception:
        pass
    assert records[-1]["response_status"] == 422
    assert records[-1]["forbidden_attempt"] is False  # a seeded error is not a denial: no permission wording
