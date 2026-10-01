"""Shared oracle helper: emit a pass/fail requirement AND record its taxonomy category.

Every oracle computes a boolean `passed`, then calls `emit_result`. On a plain TestTracker
this behaves exactly like a normal `with test(...): test.case(...)`. On a CategoryTestTracker
it additionally records the category, so the run yields a per-category profile.
"""
from __future__ import annotations

from typing import Any


def emit_result(test: Any, category: int, requirement: str, passed: bool) -> None:
    with test(requirement):
        test.case(bool(passed), "==", True)
    if hasattr(test, "record_category"):
        test.record_category(category, requirement, bool(passed))
