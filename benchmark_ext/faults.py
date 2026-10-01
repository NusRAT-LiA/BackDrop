"""Fault-injection core (S4) — the deterministic decide-and-synthesize logic (mode 10).

Kept pure/testable here; wiring into `EnrichedRequester._get/_post/_put` is the live step. Faults
are chosen by seeded call-COUNTS (not RNG), so identical specs -> identical fault pattern (V-det).
`post_commit_error` is the idempotency probe: the caller commits the write, THEN sees the error.
`pre_commit_error` is its mirror: the error is raised and the write never lands. Both synthesize the SAME
response, so an agent cannot tell them apart without reading the state back — which is the point (mode 10):
under a mix of the two, the only policy correct on both is "check, then act".
"""
from __future__ import annotations

from dataclasses import dataclass

from appworld.requester import CustomResponse

SERVER_ERROR = "server_error"
RATE_LIMIT = "rate_limit"
POST_COMMIT_ERROR = "post_commit_error"
PRE_COMMIT_ERROR = "pre_commit_error"   # the error is raised and the write NEVER lands (server_error semantics)
FAULT_KINDS = (POST_COMMIT_ERROR, PRE_COMMIT_ERROR)


MUTATING_METHODS = ("post", "put", "patch", "delete")


@dataclass
class FaultSpec:
    app: str
    endpoint_contains: str = ""
    kind: str = SERVER_ERROR
    status: int = 500
    trigger_on_nth: int = 1  # fault the nth matching call (1-indexed)
    # Only WRITES are faulted. Without this a GET sharing the path (GET /venmo/transactions is the read-back
    # for POST /venmo/transactions) could absorb the fault meant for the write: the read 500s, the write sails
    # through, and the trap silently never fires. The fault MONITOR (monitors/atoms._hits_endpoint) already
    # counts only mutating calls, so this aligns the overlay with the thing that grades it.
    methods: tuple = MUTATING_METHODS

    def matches(self, url: str, app: str | None, method: str | None = None) -> bool:
        if method is not None and method.lower() not in self.methods:
            return False
        return app == self.app and (not self.endpoint_contains or self.endpoint_contains in url)


class FaultPlan:
    """Deterministic per-run plan: same specs + same call sequence -> same faults."""

    def __init__(self, specs: list[FaultSpec]) -> None:
        self.specs = specs
        self._counts: dict[int, int] = {}

    def decide(self, url: str, app: str | None, method: str | None = None) -> FaultSpec | None:
        for i, spec in enumerate(self.specs):
            if spec.matches(url, app, method):
                self._counts[i] = self._counts.get(i, 0) + 1
                if self._counts[i] == spec.trigger_on_nth:
                    return spec
        return None

    @staticmethod
    def synthesize(spec: FaultSpec) -> CustomResponse:
        if spec.kind == RATE_LIMIT:
            return CustomResponse(status_code=429, text="synthetic rate limit")
        return CustomResponse(status_code=spec.status, text="synthetic fault")

    @staticmethod
    def is_post_commit(spec: FaultSpec) -> bool:
        return spec.kind == POST_COMMIT_ERROR
