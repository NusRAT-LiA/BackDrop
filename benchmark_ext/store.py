"""store: the results tree. One directory per (agent, task, attempt), separate from the code, holding
everything a run produced, so a run never has to be paid for twice and can be regraded offline.

    results/
      index.jsonl                     one row per run, rebuilt from the run directories (derived, never edited)
      <agent_id>/
        agent.json                    the agent's configuration; written once, checked on every later run
        runs.log                      the scheduler's progress lines
        <task_id>/
          a<attempt>/
            manifest.json             what ran: agent, task, seed, timing, tokens, commits, versions, status,
                                      plus `diagnosis` (truncation, largest prompt, error kinds, step limit)
                                      and `failure_suspect`, one label for why the run did not pass
            verdict.json              the stock grader's verdict and the extended profile, both per requirement
            llm_calls.jsonl           one line per model call: latency, tokens, finish reason, prompt hash
            llm_io.jsonl              one line per model call, the prompt messages and the reply verbatim, so a
                                      finished pass can be re-analysed without paying to generate it again
            appworld/                 AppWorld's own output directory for the run, moved here verbatim:
              dbs/ logs/ version/ ... end-state databases, api_calls.jsonl, environment_io.md, our
                                      api_calls_enriched.jsonl, ask_log.json, messages.jsonl
          a<attempt>.failed.<stamp>/  an attempt that errored out, kept for provenance; not "done"

A run is done when its verdict.json exists. Regrading mounts `appworld/` back into a composed root as the
experiment's task output directory and runs both graders again on the stored state.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from benchmark_ext.generate.tasks.task_generators.base import PROJECT, STANDING

RESULTS = os.path.join(PROJECT, "results")
STANDING_TASKS = os.path.join(STANDING, "tasks")
_VARIANT = re.compile(r"^([0-9a-f]{7})([bc]?)_(.+)$")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scenario_of(task_id: str) -> dict[str, Any]:
    """`<anchor>[b|c]_<variant>` -> anchor, instance (1..3), variant."""
    m = _VARIANT.match(task_id)
    if not m:
        return {"anchor": task_id, "instance": None, "variant": None}
    return {"anchor": m.group(1), "instance": {"": 1, "b": 2, "c": 3}[m.group(2)], "variant": m.group(3)}


def standing_tasks() -> list[str]:
    return sorted(os.path.basename(d.rstrip("/")) for d in glob.glob(os.path.join(STANDING_TASKS, "*/")))


def select_tasks(selector: str) -> list[str]:
    """`compounds`, `twins`, `ablations`, `hard`, `all`, a comma list of those or of task ids, or a glob."""
    tasks = standing_tasks()
    out: list[str] = []
    for part in [p.strip() for p in selector.split(",") if p.strip()]:
        if part == "all":
            out += tasks
        elif part == "compounds":
            out += [t for t in tasks if t.endswith("_compound")]
        elif part == "twins":
            out += [t for t in tasks if t.endswith("_twin")]
        elif part == "ablations":
            out += [t for t in tasks if re.search(r"_abl[a-z]+$", t)]
        elif part == "hard":
            out += [t for t in tasks if t.endswith("_hard")]
        elif any(ch in part for ch in "*?["):
            out += [t for t in tasks if glob.fnmatch.fnmatch(t, part)]
        elif part in tasks:
            out.append(part)
        else:
            raise SystemExit(f"unknown task selector {part!r}")
    seen: set[str] = set()
    return [t for t in out if not (t in seen or seen.add(t))]


def run_dir(agent_id: str, task_id: str, attempt: int) -> str:
    return os.path.join(RESULTS, agent_id, task_id, f"a{attempt}")


def is_done(agent_id: str, task_id: str, attempt: int) -> bool:
    return os.path.isfile(os.path.join(run_dir(agent_id, task_id, attempt), "verdict.json"))


def commits() -> dict[str, str]:
    def rev(cwd: str) -> str:
        try:
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
            dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "benchmark_ext"], cwd=cwd,
                                   capture_output=True, text=True, check=True).stdout.strip()
            return f"{sha}-dirty" if dirty else sha
        except Exception:
            return "unknown"
    return {"appworld_extend": rev(PROJECT), "appworld": rev(os.path.join(PROJECT, "appworld"))}


TRANSPORT_KEYS = ("llm_timeout_s", "llm_retries", "api_base", "aws_region")   # how long a call may wait, how often it is
                                                     # retried, and which endpoint served it: recorded in every manifest,
                                                     # but not part of the agent's identity. aws_region is here because the
                                                     # same model id served from another region is the same model, and
                                                     # spreading a throttled model across regions is how it gets throughput.


def register_agent(agent_id: str, config: dict[str, Any]) -> str:
    """Write results/<agent_id>/agent.json once; a later run under the same id must carry the same config, the
    transport settings aside."""
    path = os.path.join(RESULTS, agent_id, "agent.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.isfile(path):
        try:
            stored = json.load(open(path))
        except Exception:
            stored = None          # truncated by a racing writer: rewrite rather than crash the run
        if stored is not None:
            if {k: v for k, v in stored.items() if k not in TRANSPORT_KEYS} != {k: v for k, v in config.items() if k not in TRANSPORT_KEYS}:
                raise SystemExit(f"agent id {agent_id!r} already registered with a different configuration:\n"
                                 f"stored: {json.dumps(stored, sort_keys=True)}\nnow:    {json.dumps(config, sort_keys=True)}")
            return path
    write_json(path, config)       # atomic: several nodes may register the same agent at the same moment
    return path


def write_json(path: str, data: Any) -> None:
    """Atomic, and safe when several machines write the same path: the temp name carries this process's pid, so
    two writers never share it. Without that, concurrent writers collide on one temp file and the rename can
    publish a mixture of both. Per-run files are already partitioned by task, but agent.json is shared."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=str)
    os.replace(tmp, path)


def read_json(path: str) -> Any:
    with open(path) as f:
        return json.load(f)


def tracker_dict(tracker: Any) -> dict[str, Any]:
    """A TestTracker (stock or category) as plain data: verdict, per-requirement outcomes, and for the
    extended tracker the per-mode profile and the signals the oracles derived."""
    d: dict[str, Any] = {"success": bool(tracker.success), "num_tests": int(tracker.num_tests),
                         "passes": list(getattr(tracker, "passes", [])), "failures": list(getattr(tracker, "failures", []))}
    if hasattr(tracker, "category_success"):
        d["category_success"] = {str(k): bool(v) for k, v in tracker.category_success().items()}
        d["profile"] = {str(k): v for k, v in tracker.profile().items()}
        d["records"] = list(getattr(tracker, "category_records", []))
        # the trajectory-sized signals live in appworld/logs already; keep the verdict small
        d["signals"] = {k: v for k, v in (getattr(tracker, "signals", {}) or {}).items() if k not in ("enriched_actions", "reasoning_text")}
        d["modes_fired"] = sorted(int(k) for k, v in tracker.category_success().items() if not v)
    return d


def log_line(agent_id: str, text: str) -> None:
    path = os.path.join(RESULTS, agent_id, "runs.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"{now()} {text}\n")


def index_rows() -> list[dict[str, Any]]:
    rows = []
    for verdict_path in sorted(glob.glob(os.path.join(RESULTS, "*", "*", "a*", "verdict.json"))):
        d = os.path.dirname(verdict_path)
        if not re.fullmatch(r"a\d+", os.path.basename(d)):
            continue
        m = read_json(os.path.join(d, "manifest.json")) if os.path.isfile(os.path.join(d, "manifest.json")) else {}
        v = read_json(verdict_path)
        ext, stock = v.get("extended", {}), v.get("stock", {})
        sig = ext.get("signals", {})
        rows.append({
            "agent_id": m.get("agent_id", os.path.basename(os.path.dirname(os.path.dirname(d)))),
            "task_id": m.get("task_id", os.path.basename(os.path.dirname(d))),
            **{k: (m.get("scenario") or {}).get(k) for k in ("anchor", "instance", "variant")},
            "attempt": m.get("attempt"), "status": m.get("status"),
            "stock_success": stock.get("success"), "stock_passed": len(stock.get("passes", [])), "stock_failed": len(stock.get("failures", [])),
            "modes_fired": ext.get("modes_fired", []), "n_modes": len(ext.get("modes_fired", [])),
            "task_accuracy": sig.get("reachable_success"), "claimed_success": sig.get("claimed_success"),
            "steps": m.get("steps"), "llm_calls": m.get("llm_calls"), "tokens_total": (m.get("tokens") or {}).get("total"),
            "duration_s": m.get("duration_s"), "model": m.get("model"), "graded_at": v.get("graded_at"),
            "commit": (m.get("commits") or {}).get("appworld_extend"),
        })
    return rows


def rebuild_index() -> str:
    rows = index_rows()
    path = os.path.join(RESULTS, "index.jsonl")
    os.makedirs(RESULTS, exist_ok=True)
    # Derived, and rebuilt by every scheduler that finishes. With several machines a plain open("w") lets one
    # truncate the file while another reads it. Write to a per-process temp and rename: a reader always sees a
    # whole index, and last-writer-wins is fine for something `--index` can regenerate.
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
    os.replace(tmp, path)
    return path


def summary(rows: list[dict[str, Any]] | None = None) -> str:
    """A short table per agent and variant kind: runs, stock pass rate, mean modes fired, task accuracy."""
    rows = index_rows() if rows is None else rows
    by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        kind = "ablation" if str(r.get("variant") or "").startswith("abl") else str(r.get("variant") or "?")
        by.setdefault((str(r["agent_id"]), kind), []).append(r)
    lines = ["| agent | variant | runs | stock pass | task accuracy | mean modes fired | mean tokens |", "|---|---|---|---|---|---|---|"]
    for (agent, kind), rs in sorted(by.items()):
        ok = [r for r in rs if r.get("status") in ("ok", "error_graded")]   # error_graded is a finished, graded run
        n = len(ok) or 1
        sp = sum(1 for r in ok if r.get("stock_success")) / n
        ta = sum(1 for r in ok if r.get("task_accuracy")) / n
        mm = sum(r.get("n_modes") or 0 for r in ok) / n
        tk = sum(r.get("tokens_total") or 0 for r in ok) / n
        lines.append(f"| {agent} | {kind} | {len(ok)} | {sp:.0%} | {ta:.0%} | {mm:.2f} | {tk:,.0f} |")
    return "\n".join(lines)
