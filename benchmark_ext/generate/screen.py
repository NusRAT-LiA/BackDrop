"""screen: rank AppWorld's scenarios by the substrate a compound needs, from files every stock task ships.
No judgment here; the dossier is the reading.

    python -m benchmark_ext.generate.screen            # the ranked worklist, built scenarios marked
    python -m benchmark_ext.generate.screen --next 10  # the next unbuilt ten

A scenario is eligible when its grader reads the change set, through changed records or an end-state comparison
(a mutating task), and it touches at least two apps. Ranking: apps descending (more surfaces a counterparty can write to), then AppWorld's own api-call
count descending (more steps, more room for a hazard), which is the order PLAN_10 used.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re

from benchmark_ext.generate.tasks.task_generators.base import STOCK_TASKS, Scenario

# A grader reads the change set through models.changed_records or by comparing the start and end state; both
# mean the task mutates the world. The end-state idiom (models.end, "end state", start_file_path_to_content) was
# missed until batch 22, which hid six mutating scenarios behind the read-only ones.
MUTATING = re.compile(r"changed_records|added_\w+|deleted_\w+|updated_\w+")
END_STATE = re.compile(r"models\.end|end[ _-]state|start_file_path_to_content")
ASSERTS_CHANGES = re.compile(r"model changes match")   # a read-only grader asserts no model changes; a mutating one names the models


def screen(min_apps: int = 2) -> list[dict]:
    rows = []
    for d in sorted(glob.glob(os.path.join(STOCK_TASKS, "*_1"))):
        anchor = os.path.basename(d)[:-2]
        gt = os.path.join(d, "ground_truth")
        ev = open(os.path.join(gt, "evaluation.py"), encoding="utf-8", errors="ignore").read()
        meta = json.load(open(os.path.join(gt, "metadata.json")))
        mutating = MUTATING.search(ev) or (END_STATE.search(ev) and ASSERTS_CHANGES.search(ev))
        if not (mutating and meta.get("num_apps", 0) >= min_apps):
            continue
        specs = json.load(open(os.path.join(d, "specs.json")))
        rows.append({"anchor": anchor, "apps": meta["num_apps"], "calls": meta.get("num_api_calls", 0),
                     "difficulty": meta.get("difficulty"), "instruction": specs["instruction"]})
    rows.sort(key=lambda r: (-r["apps"], -r["calls"], r["anchor"]))
    built = {s.anchor for s in Scenario.all()}
    for i, r in enumerate(rows, 1):
        r["rank"], r["built"] = i, r["anchor"] in built
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=0, help="print only the next N unbuilt scenarios")
    ap.add_argument("--min-apps", type=int, default=2, help="admit scenarios with at least this many apps (1 widens to the single-app pool)")
    args = ap.parse_args(argv)
    rows = screen(args.min_apps)
    if args.next:
        rows = [r for r in rows if not r["built"]][:args.next]
    for r in rows:
        print(f"{r['rank']:3d} {'built' if r['built'] else '     '} {r['anchor']}  apps {r['apps']}  calls {r['calls']:3d}  "
              f"d{r['difficulty']}  {r['instruction'][:110]}")


if __name__ == "__main__":
    main()
