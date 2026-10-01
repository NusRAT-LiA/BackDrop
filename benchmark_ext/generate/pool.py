"""pool — emit a seeded pool of task families (emit-time procedural generation).

    python -m benchmark_ext.generate.pool --root <data_root> --seeds 1-20 [--base <.../tasks/83a7951_1>]

Each seed -> family `83a7951s<seed:04d>` (no underscore, as AppWorld requires) -> its 8 variants, each
carrying its instance under private_data.json["extended"]["instance"]. The RL env samples a seed -> a task id.
"""
from __future__ import annotations

import argparse
import os

from benchmark_ext.generate.tasks.task_generators.reconcile_and_record import build_generator

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_BASE_TASK = os.path.join(PROJECT, "appworld", "data", "tasks", "83a7951_1")


def family_name(seed: int) -> str:
    return f"83a7951s{int(seed):04d}"


def emit_pool(out_data_root: str, seeds, base_task_dir: str = DEFAULT_BASE_TASK) -> dict[int, dict[str, str]]:
    """{seed: {variant: task_id}} for every seed; each family is invariant-checked at build time."""
    return {int(s): build_generator(base_task_dir, seed=int(s)).emit_family(out_data_root, family_name(s))
            for s in seeds}


def _parse_seeds(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            out.extend(range(int(lo), int(hi) + 1))
        elif part.strip():
            out.append(int(part))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="data root to emit into (<root>/tasks/<family>_<variant>)")
    ap.add_argument("--seeds", default="1-5", help="e.g. 1-20 or 3,7,11")
    ap.add_argument("--base", default=DEFAULT_BASE_TASK)
    a = ap.parse_args(argv)
    ids = emit_pool(a.root, _parse_seeds(a.seeds), a.base)
    for s, fam in ids.items():
        print(f"seed {s:4d}: {len(fam)} variants  e.g. {fam['compound']}")


if __name__ == "__main__":
    main()
