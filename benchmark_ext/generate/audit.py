"""audit: does the stock no-op floor hold on every twin when nothing else has run in the process?

    python -m benchmark_ext.generate.audit <anchor>,<anchor>,...      # the twins of these scenarios
    python -m benchmark_ext.generate.audit all                        # every standing twin

The emit re-checks the floor in-process right after writing a family; that check can mask a mismatch that
only shows when a task is loaded fresh (found on `bde252e`, shelved since). This runs `validate_noop` on each
twin in its own child process and writes one JSON line per twin to `.tmp/diag/floor_audit.jsonl`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from benchmark_ext import store

CHILD = """
import json, os, sys, tempfile
from appworld.common.path_store import path_store
from benchmark_ext.generate.tasks.task_generators.base import PROJECT, compose_root, validate_noop
scratch = tempfile.mkdtemp(prefix="audit_", dir=os.path.join(PROJECT, ".tmp", "diag"))
path_store.update_root(compose_root(scratch))
r = validate_noop(sys.argv[1])
print(json.dumps({"task": sys.argv[1], "ok": r["ok"], "mismatches": r["mismatches"]}))
"""


def audit(anchors: list[str], out_path: str = os.path.join(".tmp", "diag", "floor_audit.jsonl")) -> int:
    """Audit the twins of `anchors` (or all twins when `anchors` is ["all"]). Returns the number that failed."""
    twins = store.select_tasks("twins")
    if anchors != ["all"]:
        twins = [t for t in twins if any(t.startswith(a) for a in anchors)]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bad = 0
    with open(out_path, "w") as out:
        for i, task in enumerate(twins, 1):
            proc = subprocess.run([sys.executable, "-c", CHILD, task], capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": "."})
            line = next((l for l in reversed(proc.stdout.splitlines()) if l.startswith("{")), None)
            if line:
                row = json.loads(line)
            else:
                tail = (proc.stderr.strip().splitlines() or ["?"])[-1][:200]
                row = {"task": task, "ok": False, "mismatches": ["crashed: " + tail]}
            out.write(json.dumps(row) + "\n")
            out.flush()
            if not row["ok"]:
                bad += 1
                print(f"[{i}/{len(twins)}] BAD {task}: {row['mismatches'][:1]}", flush=True)
    print(f"done: {len(twins)} twins, {bad} bad", flush=True)
    return bad


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        raise SystemExit(__doc__)
    raise SystemExit(1 if audit([a.strip() for a in args[0].split(",") if a.strip()]) else 0)


if __name__ == "__main__":
    main()
