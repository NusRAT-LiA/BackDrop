"""Per-task modes report for one agent: which modes fired on each run, per mode, per scenario and per task.

    python -m benchmark_ext.modes_report [agent_id] [json_out] [--attempt N]

Writes results/<agent_id>/modes_by_task.md for attempt 1, or modes_by_task_a<N>.md for another attempt (and,
with a json_out argument, the same data as JSON)."""
import collections
import glob
import json
import os
import sys

from benchmark_ext.generate.tasks.task_generators.base import Scenario
ARGS = list(sys.argv[1:])
ATTEMPT = int(ARGS.pop(ARGS.index("--attempt") + 1)) if "--attempt" in ARGS else 1
if "--attempt" in ARGS:
    ARGS.remove("--attempt")
sys.argv = [sys.argv[0]] + ARGS
AGENT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].endswith(".json") else "react_gemini_flash_latest_t0_s40"
R = f"results/{AGENT}"
NAMES = {2: "collateral", 4: "injection followed", 5: "out-of-scope write", 7: "false claim", 9: "guardrail broken", 10: "fault mishandled", 12: "abandonment"}
rows = []
for vp in sorted(glob.glob(f"{R}/*/a{ATTEMPT}/verdict.json")):
    d = os.path.dirname(vp); v = json.load(open(vp)); m = json.load(open(f"{d}/manifest.json")); e = v["extended"]
    a, inst, var = m["scenario"]["anchor"], int(m["scenario"]["instance"]), m["scenario"]["variant"]
    name = Scenario.by_anchor(a).__class__.__module__.rsplit(".", 1)[-1]
    tested = sorted(int(k) for k in e["category_success"]); fired = sorted(int(x) for x in e["modes_fired"])
    rows.append({"task": m["task_id"], "scenario": name, "anchor": a, "instance": inst, "variant": var, "stock": bool(v["stock"]["success"]),
                 "tested": tested, "fired": fired, "fired_share": round(100 * len(fired) / len(tested)) if tested else 0,
                 "steps": m["steps"], "tokens": m["tokens"]["total"], "capped": m["steps"] >= 40})
rows.sort(key=lambda r: (r["scenario"], r["instance"], r["variant"]))
def pct(f, t): return f"{100 * f / t:.0f}%" if t else "n/a"
def mode_table(sel):
    T = collections.Counter(); F = collections.Counter()
    for r in sel:
        for x in r["tested"]: T[x] += 1
        for x in r["fired"]: F[x] += 1
    return [(x, NAMES[x], F[x], T[x], pct(F[x], T[x])) for x in sorted(T)]
cpd = [r for r in rows if r["variant"] == "compound"]; tw = [r for r in rows if r["variant"] == "twin"]
out = [f"# Modes fired per task, agent `{AGENT}`, pass 1", "",
       "Generated from the stored verdicts (`verdict.json`, grader commit as recorded there). A mode counts as fired when its",
       "requirement failed; the denominator for a percentage is the number of runs where that mode was tested at all.", "",
       "## Per mode", "", "| mode | compounds fired / tested | twins fired / tested |", "|---|---|---|"]
mc = {x: (f, t, p) for x, _, f, t, p in mode_table(cpd)}; mt = {x: (f, t, p) for x, _, f, t, p in mode_table(tw)}
for x in sorted(set(mc) | set(mt)):
    c = mc.get(x, (0, 0, "n/a")); t = mt.get(x, (0, 0, "n/a"))
    out.append(f"| {x} {NAMES[x]} | {c[0]} / {c[1]} ({c[2]}) | {t[0]} / {t[1]} ({t[2]}) |")
out += ["", f"Runs: {len(cpd)} compounds, {len(tw)} twins. Compounds with at least one mode fired: {sum(1 for r in cpd if r['fired'])} "
        f"({pct(sum(1 for r in cpd if r['fired']), len(cpd))}); twins: {sum(1 for r in tw if r['fired'])} ({pct(sum(1 for r in tw if r['fired']), len(tw))}).", "",
        "## Per scenario", "", "Each cell is one instance: S or F for the stock grader, then the modes that fired. The last columns give, over the",
        "scenario's three compounds, the share of tested modes that fired and the per-mode firing counts.", "",
        "| scenario | anchor | compound 1 | compound 2 | compound 3 | twin 1 | twin 2 | twin 3 | modes fired / tested | per mode |", "|---|---|---|---|---|---|---|---|---|---|"]
by = collections.defaultdict(dict)
for r in rows: by[(r["scenario"], r["anchor"])][(r["variant"], r["instance"])] = r
def cell(r):
    if not r: return "--"
    return ("S" if r["stock"] else "F") + (" " + ",".join(str(x) for x in r["fired"]) if r["fired"] else " none")
for (name, a), d in sorted(by.items()):
    cs = [d.get(("compound", i)) for i in (1, 2, 3)]; ts = [d.get(("twin", i)) for i in (1, 2, 3)]
    tested = sum(len(r["tested"]) for r in cs if r); fired = sum(len(r["fired"]) for r in cs if r)
    per = collections.Counter(x for r in cs if r for x in r["fired"])
    out.append(f"| `{name}` | `{a}` | " + " | ".join(cell(r) for r in cs) + " | " + " | ".join(cell(r) for r in ts) +
               f" | {fired} / {tested} ({pct(fired, tested)}) | " + (", ".join(f"{x}:{n}/3" for x, n in sorted(per.items())) or "none") + " |")
out += ["", "## Per task", "", "| task | scenario | variant | stock | modes fired | fired / tested | steps | tokens |", "|---|---|---|---|---|---|---|---|"]
for r in rows:
    out.append(f"| `{r['task']}` | `{r['scenario']}` | {r['variant']} | {'pass' if r['stock'] else 'fail'} | "
               f"{', '.join(f'{x} {NAMES[x]}' for x in r['fired']) or 'none'} | {len(r['fired'])} / {len(r['tested'])} ({r['fired_share']}%) | {r['steps']}{' (cap)' if r['capped'] else ''} | {r['tokens']:,} |")
open(f"{R}/" + ("modes_by_task.md" if ATTEMPT == 1 else f"modes_by_task_a{ATTEMPT}.md"), "w").write("\n".join(out) + "\n")
if len(sys.argv) > 1 and sys.argv[-1].endswith(".json"):
    json.dump({"agent": AGENT, "names": {str(k): v for k, v in NAMES.items()}, "rows": rows,
               "per_mode": {"compound": [list(x) for x in mode_table(cpd)], "twin": [list(x) for x in mode_table(tw)]}},
              open(sys.argv[-1], "w"))
print("markdown lines:", len(out), "| rows:", len(rows))
