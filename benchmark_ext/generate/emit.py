"""emit: emit every scenario's families into benchmark_ext/data/tasks/ and check the stock floor on each.
Mirrors appworld/generate/tasks/generate_and_validate_tasks.py.

    python -m benchmark_ext.generate.emit                    # every scenario: emit, then validate
    python -m benchmark_ext.generate.emit 988af8e,82d2e01    # by anchor
    python -m benchmark_ext.generate.emit --only_emit
    python -m benchmark_ext.generate.emit --only_validate    # the standing tasks as they are
"""
from __future__ import annotations

import argparse
import glob
import os
import tempfile

from benchmark_ext.generate.tasks.task_generators.base import STANDING, Scenario, compose_root, validate_noop


def validate(scenarios: list[Scenario]) -> list[dict]:
    from appworld.common.path_store import path_store

    root = compose_root(tempfile.mkdtemp(prefix="emit_validate_"))
    prev = path_store.root
    path_store.update_root(root)
    bad = []
    try:
        for s in scenarios:
            for family in s.instances().values():
                for d in sorted(glob.glob(os.path.join(STANDING, "tasks", f"{family}_*"))):
                    r = validate_noop(os.path.basename(d.rstrip("/")))
                    flag = "ok " if r["ok"] else "BAD"
                    print(f"  {flag} {r['task_id']:<24} {r['num_tests']} requirements, {r['no_op_fail']} no_op_fail"
                          + (f", mismatches: {r['mismatches']}" if r["mismatches"] else ""))
                    if not r["ok"]:
                        bad.append(r)
    finally:
        path_store.update_root(prev)
    return bad


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("anchors", nargs="?", default="all", help="comma-separated scenario anchors, or 'all'")
    ap.add_argument("--only_emit", action="store_true")
    ap.add_argument("--only_validate", action="store_true")
    args = ap.parse_args(argv)
    scenarios = Scenario.all() if args.anchors == "all" else [Scenario.by_anchor(a) for a in args.anchors.split(",")]

    if not args.only_validate:
        for s in scenarios:
            print(f"=== {type(s).__name__} ({s.anchor})")
            s.emit_all(STANDING)
    if not args.only_emit:
        print("validating the stock no-op floor on every emitted variant:")
        bad = validate(scenarios)
        if bad:
            raise SystemExit(f"{len(bad)} variant(s) do not hold the stock floor: {[b['task_id'] for b in bad]}")
        print("every variant holds the stock floor")


if __name__ == "__main__":
    main()
