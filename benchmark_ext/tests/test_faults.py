"""Fault core (S4) — determinism (V-det) + synthesis + post-commit flag."""
from __future__ import annotations

from benchmark_ext.faults import POST_COMMIT_ERROR, RATE_LIMIT, FaultPlan, FaultSpec

SEQ = [("/venmo/transactions", "venmo")] * 3


def _spec():
    return FaultSpec(app="venmo", endpoint_contains="transactions", status=500, trigger_on_nth=2)


def test_deterministic_same_specs_same_pattern():
    p1, p2 = FaultPlan([_spec()]), FaultPlan([_spec()])
    d1 = [p1.decide(u, a) is not None for u, a in SEQ]
    d2 = [p2.decide(u, a) is not None for u, a in SEQ]
    assert d1 == d2 == [False, True, False]  # only the 2nd matching call faults


def test_no_match_for_other_app():
    assert FaultPlan([FaultSpec(app="venmo")]).decide("/spotify/x", "spotify") is None


def test_synthesize_status_codes():
    assert FaultPlan.synthesize(FaultSpec(app="venmo", status=500)).status_code == 500
    assert FaultPlan.synthesize(FaultSpec(app="venmo", kind=RATE_LIMIT)).status_code == 429


def test_post_commit_flag():
    assert FaultPlan.is_post_commit(FaultSpec(app="venmo", kind=POST_COMMIT_ERROR)) is True
    assert FaultPlan.is_post_commit(FaultSpec(app="venmo")) is False
