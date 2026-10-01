"""Live wiring — install enrichment + fault injection on a running AppWorld's requester.

Additive & non-invasive: we monkeypatch the *instance* methods of `world.requester` (not the class,
not any core file). The stock `RequestTracker` / `api_calls.jsonl` are untouched (V0-safe); we append
enriched records ({response_status, actor, forbidden_attempt}) on the side, and optionally inject
seeded faults (mode 10). Verified dispatch: `_request` calls `_get(path, data=..., client=..., ...)`.
"""
from __future__ import annotations

from typing import Any, Callable

from benchmark_ext.faults import FaultPlan
from benchmark_ext.requester_enriched import enrich_record, repl_value_index
from benchmark_ext.trajectory import app_of

_VERBS = ("_get", "_post", "_put", "_patch", "_delete")


def install_overlay(
    world: Any,
    fault_plan: FaultPlan | None = None,
    actor_resolver: Callable[[str], str | None] | None = None,
    cue_markers: list[str] | None = None,
) -> list[dict[str, Any]]:
    req = world.requester
    records: list[dict[str, Any]] = []
    req.enriched_records = records

    def make(method_name: str, orig: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(url: Any, *args: Any, **kwargs: Any) -> Any:
            data = args[0] if args else kwargs.get("data")
            token = data.get("access_token") if isinstance(data, dict) else None
            app = app_of(url) if isinstance(url, str) else None

            if fault_plan is not None and isinstance(url, str):
                spec = fault_plan.decide(url, app, method_name)   # method-gated: reads are never faulted
                if spec is not None:
                    if FaultPlan.is_post_commit(spec):
                        try:  # commit the write, THEN return the error (idempotency hazard)
                            orig(url, *args, **{**kwargs, "raise_on_failure": False})
                        except Exception:
                            pass
                    else:  # pre-commit: nothing reaches the app, so register the ATTEMPT in the stock tracker —
                        # every attempted call must appear in the trajectory (mode 10 locates the fault by count)
                        try:
                            req.request_tracker.add_request(method=method_name, url=url, data=data if isinstance(data, dict) else None)
                        except Exception:
                            pass
                    resp = FaultPlan.synthesize(spec)
                    records.append(enrich_record(method_name, url, data, resp, token=token, resolve_actor=actor_resolver,
                                                 repl_index=repl_value_index(world), cue_markers=cue_markers))
                    req.raise_if_failure(resp, kwargs.get("raise_on_failure"))  # a fault raises like a real error
                    return resp

            # Force no-raise so we capture the status even on a failed/blocked call (e.g. 401/422 —
            # the mode-5 signal), record it, then re-apply the caller's raise behavior unchanged.
            orig_raise = kwargs.get("raise_on_failure", None)
            resp = orig(url, *args, **{**kwargs, "raise_on_failure": False})
            # index the agent's live REPL bindings BEFORE recording, so 'was it already holding this?' is
            # answered against the namespace as it stood when the call was made
            records.append(enrich_record(method_name, url, data, resp, token=token, resolve_actor=actor_resolver,
                                         repl_index=repl_value_index(world), cue_markers=cue_markers))
            req.raise_if_failure(resp, orig_raise)
            return resp

        return wrapper

    for verb in _VERBS:
        if hasattr(req, verb):
            setattr(req, verb, make(verb[1:], getattr(req, verb)))
    return records
