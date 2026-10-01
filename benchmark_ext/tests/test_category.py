"""CategoryTestTracker (S2) — category side-channel + per-category profile."""
from __future__ import annotations

from appworld.evaluator import TestTracker

from benchmark_ext.category import CategoryTestTracker
from benchmark_ext.oracles._base import emit_result


def test_records_and_profile():
    t = CategoryTestTracker()
    emit_result(t, 4, "req a", True)
    emit_result(t, 4, "req b", False)
    emit_result(t, 8, "req c", True)
    assert t.profile()[4] == {"passed": 1, "failed": 1}
    assert t.profile()[8] == {"passed": 1, "failed": 0}
    assert t.category_success() == {4: False, 8: True}
    # standard TestTracker channel still works
    assert t.pass_count == 2 and t.fail_count == 1


def test_plain_tracker_still_works_without_categories():
    t = TestTracker()
    emit_result(t, 4, "req", True)  # no record_category attr -> behaves as stock
    assert t.pass_count == 1 and t.fail_count == 0
