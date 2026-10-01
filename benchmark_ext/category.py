"""CategoryTestTracker — a TestTracker that also records the failure mode of each requirement, so a run
produces a per-mode profile beside its pass or fail.

Additive: it IS a TestTracker (passes/failures/success unchanged), plus a category side-channel.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from appworld.evaluator import TestTracker


class CategoryTestTracker(TestTracker):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.category_records: list[dict[str, Any]] = []

    def record_category(self, category: int, requirement: str, passed: bool) -> None:
        self.category_records.append(
            {"category": category, "requirement": requirement, "passed": bool(passed)}
        )

    def profile(self) -> dict[int, dict[str, int]]:
        agg: dict[int, dict[str, int]] = defaultdict(lambda: {"passed": 0, "failed": 0})
        for r in self.category_records:
            agg[r["category"]]["passed" if r["passed"] else "failed"] += 1
        return {k: dict(v) for k, v in agg.items()}

    def category_success(self) -> dict[int, bool]:
        """A category 'passes' only if none of its requirements failed."""
        return {k: v["failed"] == 0 for k, v in self.profile().items()}
