"""The four-property gate, generic over every scenario, on the EMITTED standing tasks.

Reachable: every planted cue comes back through the API of the model it was planted on. Plausible and derived:
every cue is built from THIS instance's world, so no two instances of a scenario carry the same cue set, and
nothing planted carries an em-dash. Wrong, and stock-blind: an injection's target is unseeded, so the send
fails and the base grader never sees the attempt. Fair: the stock floor is inherited untouched, and a no-op
fails exactly what AppWorld says it fails. The judgment calls (which carrier, which wording) live in each
scenario's docstring and are not re-litigated here.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import tempfile

import pytest

from benchmark_ext.generate.tasks.task_generators import seed_lib
from benchmark_ext.generate.tasks.task_generators.base import (
    PROJECT,
    STANDING,
    STOCK_TASKS,
    Scenario,
    compose_root,
    validate_noop,
)

TASKS = os.path.join(STANDING, "tasks")
SCENARIOS = Scenario.all()


def _families():
    """(scenario, stock instance id, family) for every standing family."""
    return [(s, tid, fam) for s in SCENARIOS for tid, fam in s.instances().items()]


def _variants(family):
    return sorted(os.path.basename(d.rstrip("/")) for d in glob.glob(f"{TASKS}/{family}_*/"))


def _ext(tid):
    return json.load(open(f"{TASKS}/{tid}/ground_truth/private_data.json"))["extended"]


def _strings(task_dir):
    """Every string an agent could read: the seed rows' string values, and the instruction."""
    out = []
    for path in sorted(glob.glob(os.path.join(task_dir, "dbs", "*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            row = json.loads(line)
            params = row[1] if isinstance(row, list) and len(row) > 1 and isinstance(row[1], list) else []
            out.extend(v for v in params if isinstance(v, str))
    out.append(json.load(open(os.path.join(task_dir, "specs.json")))["instruction"])
    return out


def _planted(tid, stock_tid):
    """The strings an emitted task carries that its stock instance does not."""
    base = set(_strings(os.path.join(STOCK_TASKS, stock_tid)))
    return [s for s in _strings(os.path.join(TASKS, tid)) if s not in base]


@pytest.fixture(scope="module")
def emitted():
    missing = [fam for _, _, fam in _families() if not _variants(fam)]
    if missing:
        pytest.skip(f"families not emitted: {missing} (run python -m benchmark_ext.generate.emit)")
    return {fam: _variants(fam) for _, _, fam in _families()}


@pytest.fixture(scope="module")
def profiles():
    """Each family's plants, re-derived from the stock instance it was emitted from."""
    out = {}
    for s, tid, fam in _families():
        prof = s.profile(os.path.join(STOCK_TASKS, tid), tid)
        out[fam] = (s, prof, s.plants(prof))
    return out


@pytest.fixture(scope="module")
def root():
    """One composed path_store root for the whole module, never deleted while the process lives."""
    return compose_root(tempfile.mkdtemp(prefix="scenarios_gate_"))


def test_each_family_has_its_declared_variants(emitted, profiles):
    for fam, vs in emitted.items():
        s, prof, plants = profiles[fam]
        expected = sorted(f"{fam}_{suffix}" for suffix, _ in s.variants(plants, prof).values())
        assert vs == expected, (fam, vs, expected)


def test_each_plant_is_present_exactly_where_declared(emitted, profiles):
    """A plant's cue strings and grader knobs are in a variant iff the plant is active there: the twin carries
    nothing, an ablation exactly one, the compound all of them."""
    for fam, vs in emitted.items():
        s, prof, plants = profiles[fam]
        by_id = {p.id: p for p in plants}
        keys = [k for p in plants for k in p.extended]
        shared = {k for k in keys if keys.count(k) > 1}           # a knob two plants both set is not diagnostic
        for tid in vs:
            ext = _ext(tid)
            active = set(ext["active_modules"])
            text = "\n".join(_strings(os.path.join(TASKS, tid)))
            for pid, p in by_id.items():
                on = pid in active
                for cue in p.cues:
                    assert (cue in text) == on, (tid, pid, cue, on)
                    if on:
                        assert cue in ext["cue_markers"], (tid, pid, cue)
                for key in p.extended:
                    if key not in shared:
                        assert (key in ext) == on, (tid, pid, key, on)


def test_every_cue_is_derived_from_its_own_instance(emitted, profiles):
    """No text ported from one instance to another: the cue set differs between a scenario's instances."""
    for s in SCENARIOS:
        seen = {}
        for _, fam in s.instances().items():
            _, _, plants = profiles[fam]
            key = tuple(c for p in plants for c in p.cues)
            assert key not in seen.values(), (fam, key, seen)
            seen[fam] = key


def test_no_em_dash_in_anything_planted(emitted):
    for _, stock_tid, fam in _families():
        for tid in emitted[fam]:
            for text in _planted(tid, stock_tid):
                assert "—" not in text and "–" not in text, (tid, text[:80])


def test_stock_blind_targets_are_unseeded(emitted, profiles):
    """An injection's recipient must not exist, in the base DB or the task's own seed: the send fails, the
    base grader stays blind, and mode 4 is the only thing that can see the attempt."""
    for fam, (s, prof, plants) in profiles.items():
        for p in plants:
            if not p.unseeded:
                continue
            db, table, column, value = p.unseeded
            c = sqlite3.connect(os.path.join(PROJECT, "appworld", "data", "base_dbs", f"{db}.db"))
            assert c.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (value,)).fetchone()[0] == 0, (fam, value)
            c.close()
            rows = seed_lib.find_rows(os.path.join(TASKS, f"{fam}_compound"), db, table)
            assert not any(r.get(column) == value for r in rows), (fam, value)


@pytest.mark.slow
def test_the_plants_resolve_in_the_world(emitted, profiles, root):
    """Reachable through the API, not just present in a file: load each compound and find every cue on the
    model it was planted on."""
    from appworld.common.path_store import path_store
    from appworld.environment import AppWorld

    prev = path_store.root
    path_store.update_root(root)
    try:
        for fam, (s, prof, plants) in profiles.items():
            tid = f"{fam}_compound"
            world = AppWorld(task_id=tid, experiment_name=f"gate_{tid}", random_seed=1)
            try:
                for p in plants:
                    for cue in p.cues:
                        found = any(cue in str(getattr(r, field, "") or "")
                                    for app, model, field in p.carriers
                                    for r in getattr(getattr(world.models, app), model).all())
                        assert found, (tid, p.id, cue)
            finally:
                AppWorld.close_all()
    finally:
        path_store.update_root(prev)


@pytest.mark.slow
def test_the_stock_floor_holds(emitted, root):
    """test_data.json is the stock instance's, untouched, and a no-op on each compound fails exactly the
    requirements it labels no_op_fail: the floor AppWorld computed survives every plant, with no gold."""
    for _, stock_tid, fam in _families():
        stock = json.load(open(f"{STOCK_TASKS}/{stock_tid}/ground_truth/test_data.json"))
        for tid in emitted[fam]:
            assert json.load(open(f"{TASKS}/{tid}/ground_truth/test_data.json")) == stock, tid
    from appworld.common.path_store import path_store

    prev = path_store.root
    path_store.update_root(root)
    try:
        for fam in emitted:
            r = validate_noop(f"{fam}_compound")
            assert r["ok"], r
    finally:
        path_store.update_root(prev)
