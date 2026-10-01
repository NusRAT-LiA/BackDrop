"""dossier: the facts of a stock scenario, printed in seconds, so designing its plants starts from a page
instead of a directory (inventory the structure first).

    python -m benchmark_ext.generate.dossier 80acbaf          # every instance
    python -m benchmark_ext.generate.dossier 80acbaf_1        # one

Per instance: the instruction and clock, the apps, the grader's requirements with AppWorld's own no-op labels
(no_op_fail = a must-do, the fault targets; no_op_pass = a must-not-touch), the public and private data, and
what the agent reads: every task-level seed table with its row count, and for each row of a text-bearing table
the string columns an agent could be shown (the carriers). No judgment is made here; that is the reading.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

from benchmark_ext.generate.tasks.task_generators.base import STOCK_TASKS

TEXT_MIN = 12          # a string column this long or longer is something an agent reads, not a code or a hash
SKIP_COLS = {"record_hash", "created_at", "updated_at", "joined_at", "file_compressed_data", "password", "email_ids",
             "recipient_ids", "sender_email_addresses", "recipient_email_addresses", "sender_names", "recipient_names",
             "debtor_ids", "participant_ids", "saved_search_text", "invitation_code", "access_token"}
MAX_ROWS = 6


def _cols(stmt: str) -> list[str]:
    return [c.strip() for c in re.search(r"\(([^)]*)\)\s*VALUES", stmt).group(1).split(",")]


def _rows(task_dir: str, db: str) -> list:
    p = os.path.join(task_dir, "dbs", f"{db}.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.isfile(p) else []


def _requirements(task_dir: str) -> list[tuple[str, str]]:
    td = json.load(open(os.path.join(task_dir, "ground_truth", "test_data.json"))) or []
    return [(" ".join(t["requirement"].split()), t["label"]) for t in td]


def dossier(task_id: str) -> str:
    d = os.path.join(STOCK_TASKS, task_id)
    specs = json.load(open(os.path.join(d, "specs.json")))
    gt = os.path.join(d, "ground_truth")
    meta = json.load(open(os.path.join(gt, "metadata.json")))
    public = json.load(open(os.path.join(gt, "public_data.json")))
    private = json.load(open(os.path.join(gt, "private_data.json")))
    out = [f"===== {task_id}  ({specs['datetime']}, difficulty {meta.get('difficulty')}, {meta.get('num_apps')} apps, "
           f"{meta.get('num_api_calls')} api calls in AppWorld's solution)",
           f"supervisor: {specs['supervisor']['first_name']} {specs['supervisor']['last_name']} <{specs['supervisor']['email']}>",
           "", "INSTRUCTION", "  " + specs["instruction"], "",
           "GRADER (AppWorld's own no-op labels: fail = a must-do, pass = a must-not-touch)"]
    for req, label in _requirements(d):
        out.append(f"  [{'MUST' if label == 'no_op_fail' else 'keep'}] {req}")
    out += ["", f"public_data : {json.dumps(public)}", f"private_data: {json.dumps(private)[:600]}", "",
            "WHAT THE AGENT READS (task-level seed rows; base-DB records are not listed)"]
    apps_with_rows = []
    for p in sorted(glob.glob(os.path.join(d, "dbs", "*.jsonl"))):
        db = os.path.basename(p)[:-6]
        rows = _rows(d, db)
        inserts = [r for r in rows if isinstance(r, list) and isinstance(r[0], str) and r[0].startswith("INSERT INTO ")]
        updates = [r for r in rows if isinstance(r, list) and isinstance(r[0], str) and r[0].startswith("UPDATE ")]
        if not inserts and not updates:
            continue
        apps_with_rows.append(db)
        tables: dict[str, list] = {}
        for r in inserts:
            tables.setdefault(r[0].split("INSERT INTO ")[1].split(" (")[0], []).append(r)
        upd = {}
        for r in updates:
            t = r[0].split("UPDATE ")[1].split(" SET")[0]
            upd[t] = upd.get(t, 0) + 1
        out.append(f"  {db}: " + ", ".join(f"{t} x{len(rs)}" for t, rs in tables.items())
                   + (("  | updates: " + ", ".join(f"{t} x{n}" for t, n in upd.items())) if upd else ""))
        for t, rs in tables.items():
            cols = _cols(rs[0][0])
            texty = [i for i, c in enumerate(cols) if c not in SKIP_COLS and any(
                isinstance(r[1][i], str) and len(r[1][i]) >= TEXT_MIN for r in rs)]
            if not texty or t.endswith("_fts"):
                continue
            ids = [i for i, c in enumerate(cols) if c.endswith("_id") and c not in SKIP_COLS]
            for r in rs[:MAX_ROWS]:
                head = " ".join(f"{cols[i]}={r[1][i]}" for i in ids)
                out.append(f"      {t} {head}")
                for i in texty:
                    v = r[1][i]
                    if isinstance(v, str) and v.strip():
                        v = " ".join(v.split())
                        out.append(f"         {cols[i]}: {v[:220]}{'...' if len(v) > 220 else ''}")
            if len(rs) > MAX_ROWS:
                out.append(f"      ... {len(rs) - MAX_ROWS} more {t} rows")
    out.append(f"  apps with task-level rows: {apps_with_rows}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    for a in args:
        ids = [a] if "_" in a else [os.path.basename(p) for p in sorted(glob.glob(os.path.join(STOCK_TASKS, f"{a}_*")))]
        for tid in ids:
            print(dossier(tid))
            print()


if __name__ == "__main__":
    main()
