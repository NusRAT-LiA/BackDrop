"""Ask/clarify channel (S6) — inject an `ask_supervisor(...)` callable into a running world.

Base AppWorld has no ask channel (supervisor exposes only read/complete APIs; `input()` raises).
This installs one as an OVERLAY: a callable pushed into the REPL namespace (and best-effort bound
under `apis.supervisor.ask_supervisor`) so the agent can ask, and every exchange is recorded to
`world.ask_log` for the mode-6 oracle. No appworld core file is edited.
"""
from __future__ import annotations

from typing import Any

from benchmark_ext.user_simulator import UserSimulator


def install_ask_channel(world: Any, simulator: UserSimulator) -> list[dict[str, Any]]:
    ask_log: list[dict[str, Any]] = []

    def ask_supervisor(question: str) -> dict[str, str]:
        """Returns {"answer": ...} — every AppWorld API returns a JSON object, and the api_docs entry says so."""
        result = simulator.answer(question)
        try:  # position in the API-call timeline: the ask happened after this many logged actions
            after_action = len(world.requester.requests)
        except Exception:
            after_action = None
        ask_log.append({
            "question": question, "answer": result["answer"], "known": result["known"],
            "key": result.get("key"),
            # the simulator's GRADED score (1.0 load-bearing / 0.3 answerable-but-minor / 0.0 off-target);
            # it existed but was never wired — the grader used a binary stand-in
            "info_gain": simulator.information_gain(question),
            # lets the mode-6 monitor order asks against commits ("ask BEFORE acting on the unknowable item")
            "after_action": after_action,
        })
        return {"answer": result["answer"]}

    # 1) top-level in the REPL, so `ask_supervisor("...")` works in agent code
    try:
        world.shell.push({"ask_supervisor": ask_supervisor})
    except Exception:
        world.shell.user_ns["ask_supervisor"] = ask_supervisor
    # 2) best-effort: also expose as apis.supervisor.ask_supervisor
    try:
        setattr(world.apis.supervisor, "ask_supervisor", ask_supervisor)
    except Exception:
        pass

    # 3) make the channel DISCOVERABLE the way every other API is: an api_docs row for supervisor.ask_supervisor.
    #    (A real agent that wanted to ask tried complete_task(answer=...) because nothing listed the channel.)
    #    Runtime-only: the runner deletes the row before persisting state — it is an affordance, not task state,
    #    and must not read as a 'changed model' to the collateral oracle.
    world.ask_supervisor_doc = _add_ask_doc(world)
    world.ask_log = ask_log
    return ask_log


def _add_ask_doc(world: Any) -> Any:
    try:
        ApiDoc = world.models.api_docs.ApiDoc
        if any(d.app_name_ == "supervisor" and d.api_name == "ask_supervisor" for d in ApiDoc.all()):
            return None
        row = ApiDoc.create(  # create() only constructs; save() persists to the run's in-memory DB
            app_name_="supervisor", api_name="ask_supervisor", path="/supervisor/ask_supervisor", method="POST",
            description=("Ask your supervisor a clarifying question when the task is ambiguous and the answer is not "
                         "discoverable in any app; returns {'answer': <their answer>}. Call it as "
                         "apis.supervisor.ask_supervisor(question=...) or simply ask_supervisor(question=...)."),
            parameters=[{"name": "question", "type": "string", "required": True,
                         "description": "The clarifying question for your supervisor.", "default": None, "constraints": []}],
            response_schemas={"success": {"answer": "string"}, "failure": {"message": "string"}},
        )
        row.save()
        return row
    except Exception:
        return None
