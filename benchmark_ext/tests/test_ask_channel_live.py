"""S6 live — the injected ask_supervisor channel works inside a real AppWorld REPL.

World cleanup handled by the autouse `_cleanup_worlds` fixture.
"""
from __future__ import annotations

from benchmark_ext.ask_channel import install_ask_channel
from benchmark_ext.user_simulator import Persona, UserSimulator

TASK = "07b42fd_1"


def test_ask_supervisor_answers_in_live_repl(live_root):
    from appworld.environment import AppWorld

    world = AppWorld(task_id=TASK, experiment_name="ask_it", random_seed=1)
    sim = UserSimulator(Persona(knowledge={"disputed amount": "$75, still contested"},
                                load_bearing={"disputed amount"}))
    ask_log = install_ask_channel(world, sim)

    # the agent asks a clarifying question from within its normal execute() loop
    out = world.execute("print(ask_supervisor('What is the disputed amount?'))")

    assert "75" in out                       # the simulated answer reached the agent
    assert len(ask_log) == 1                 # the exchange was recorded for the oracle
    assert ask_log[0]["known"] is True
    assert "disputed amount" in ask_log[0]["question"].lower()
