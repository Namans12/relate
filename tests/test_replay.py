import shutil
from dataclasses import replace
from pathlib import Path

import pytest
import relate

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import RunResult
from patch_precedent.replay import (
    JOIN_QUERY,
    check_expectations,
    join_rows,
    join_tap_disagreements,
    load_expectations,
    record_runs,
    replay_check,
)
from patch_precedent.store import open_readonly, snapshot
from patch_precedent.tap import parse_tap

ROOT = pins.project_root()
DATA = ROOT / "tests" / "data"
FIX = ROOT / "fixtures" / "installer"
EXPECT = FIX / "expectations.toml"
D7 = "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)"
D193 = "no case made a GitHub API request (ADR-0585)"


def _tap(name):
    return parse_tap((DATA / f"{name}.tap").read_text())


def _runs():
    wording = read_patch(FIX / "wording.patch")
    release = read_patch(FIX / "release-lookup.patch")
    log = Path("/tmp/x.log")
    return [
        RunResult("baseline", None, "base", "cmd", 0, _tap("baseline"), log, "pass", None),
        RunResult("wording", wording, "base", "cmd", 0, _tap("wording"), log, "pass", None),
        RunResult("release-lookup", release, "base", "cmd", 1, _tap("release-lookup"),
                  log, "fail", None),
    ]


@pytest.fixture
def copy(tmp_path):
    dst = tmp_path / "replay.rl"
    shutil.copy(pins.STORE_PATH, dst)
    return dst


def _rows(path):
    conn = relate.connect(str(path))
    try:
        return join_rows(conn)
    finally:
        conn.close()


def test_join_four_rows(copy):
    record_runs(copy, _runs())
    rows = _rows(copy)
    a, b = _runs()[1].patch.id, _runs()[2].patch.id
    got = [(r["patch"], r["tap_number"], r["observed"]) for r in rows]
    assert sorted(got) == sorted([(a, 7, "ok"), (a, 193, "ok"),
                                  (b, 7, "not ok"), (b, 193, "not ok")])
    assert len(rows) == 4
    for r in rows:
        assert r["file"] == "distribution/install.sh"
        assert r["decision"] == "ADR-0585"
        assert r["implementation"] == pins.IMPLEMENTING_SHA
    assert {r["label"] for r in rows} == {"wording", "release-lookup"}


def test_record_twice_no_duplicates(copy):
    record_runs(copy, _runs())
    record_runs(copy, _runs())
    assert len(_rows(copy)) == 4
    conn = relate.connect(str(copy))
    try:
        for p in (_runs()[1].patch.id, _runs()[2].patch.id):
            n = [r.data()["n"] for r in conn.execute(
                "MATCH (:Patch {id: $i})-[:PRODUCED]->(o:Observation) RETURN count(o) AS n",
                {"i": p})]
            assert n == [2]
        assert [r.data()["n"] for r in conn.execute(
            "MATCH (r:Run) RETURN count(r) AS n")] == [2]
    finally:
        conn.close()


def test_baseline_not_written(copy):
    record_runs(copy, _runs())
    conn = relate.connect(str(copy))
    try:
        assert [r.data()["n"] for r in conn.execute(
            "MATCH (p:Patch) RETURN count(p) AS n")] == [2]
    finally:
        conn.close()


def test_expectations_ok():
    assert check_expectations(_runs(), load_expectations(EXPECT)) == []


def test_expectations_mismatch_detected():
    runs = _runs()
    swapped = [runs[0],
               replace(runs[1], exit_code=1, tap=runs[2].tap),
               replace(runs[2], exit_code=0, tap=runs[1].tap)]
    msgs = check_expectations(swapped, load_expectations(EXPECT))
    assert any(m.startswith("wording") for m in msgs)
    assert any(m.startswith("release-lookup") for m in msgs)
    assert not any(m.startswith("baseline") for m in msgs)
    assert len({m.split(":")[0] for m in msgs}) == 2


def test_expectation_unknown_content_and_no_tap():
    runs = _runs()
    other = replace(runs[1].patch, sha256="0" * 64)
    msgs = check_expectations([replace(runs[1], patch=other),
                               replace(runs[2], tap=None)], load_expectations(EXPECT))
    assert "wording (000000000000): no expectation for this content" in msgs
    assert "release-lookup: no TAP" in msgs


def test_drift_warning(copy):
    runs = _runs()
    tap = runs[1].tap
    cut = replace(tap, results=tuple(r for r in tap.results if r.description != D193))
    warnings = record_runs(copy, [runs[1], replace(runs[2], tap=cut)])
    assert warnings == [f"release-lookup: check not found in TAP: {D193}"]


def test_baseline_feeds_drift(copy):
    runs = _runs()
    tap = runs[0].tap
    cut = replace(tap, results=tuple(r for r in tap.results if r.description != D7))
    warnings = record_runs(copy, [replace(runs[0], tap=cut)])
    assert warnings == [f"baseline: check not found in TAP: {D7}"]


def test_no_tap_writes_run_without_observations(copy):
    runs = _runs()
    record_runs(copy, [replace(runs[2], tap=None, exit_code=None, status="inconclusive",
                               reason="no TAP")])
    conn = relate.connect(str(copy))
    try:
        assert [r.data()["n"] for r in conn.execute(
            "MATCH (o:Observation) RETURN count(o) AS n")] == [0]
        assert [r.data()["n"] for r in conn.execute(
            "MATCH (r:Run)-[:APPLIED]->(:Patch) RETURN count(r) AS n")] == [1]
    finally:
        conn.close()


def test_record_refuses_committed_store():
    with pytest.raises(ValueError):
        record_runs(pins.STORE_PATH, _runs())


def test_snapshot_replay_copy(copy):
    record_runs(copy, _runs())
    conn = open_readonly(copy)
    try:
        assert snapshot(conn)
    finally:
        conn.close()


def test_rerecord_replaces_stale_state(copy):
    runs = _runs()
    record_runs(copy, runs)
    pid = runs[2].patch.id
    record_runs(copy, [replace(runs[2], tap=None, exit_code=None,
                               status="inconclusive", reason="no TAP")])
    conn = relate.connect(str(copy))
    try:
        assert [r.data()["n"] for r in conn.execute(
            "MATCH (:Patch {id: $i})-[:PRODUCED]->(o:Observation) RETURN count(o) AS n",
            {"i": pid})] == [0]
        assert [r for r in join_rows(conn) if r["patch"] == pid] == []
        run = [r.data()["p"] for r in conn.execute(
            "MATCH (r:Run {id: $i}) RETURN properties(r) AS p", {"i": pid})]
        assert len(run) == 1
        assert "passed" not in run[0] and run[0]["status"] == "inconclusive"
    finally:
        conn.close()


# --- join/TAP cross-check and replay check (pure) --------------------------

def _linked(rows_for=(D7, D193)):
    return [{"check": c} for c in rows_for]


def _join(runs, flip=None, drop=False):
    out = []
    for run in runs:
        if run.patch is None or drop:
            continue
        for res in run.tap.results:
            if res.description in (D7, D193):
                tap = "ok" if res.ok else "not ok"
                if flip == (run.label, res.description):
                    tap = "ok" if tap == "not ok" else "not ok"
                out.append({"patch": run.patch.id, "label": run.label,
                            "assertion": res.description, "observed": tap})
    return out


def _evidence(runs):
    return {r.patch.id: _linked() for r in runs if r.patch is not None}


def test_join_tap_agree():
    runs = _runs()
    assert join_tap_disagreements(runs, _evidence(runs), _join(runs)) == []


def test_join_tap_disagree_is_reported():
    runs = _runs()
    out = join_tap_disagreements(runs, _evidence(runs), _join(runs, flip=("wording", D7)))
    assert out == [f"join/TAP disagree: wording {D7}: join=not ok tap=ok"]


def test_join_tap_zero_rows_is_mismatch():
    runs = _runs()
    out = join_tap_disagreements(runs, _evidence(runs), _join(runs, drop=True))
    assert len(out) == 2
    assert all("no join rows" in m for m in out)


def test_join_tap_ignores_inconclusive_and_unlinked():
    runs = _runs()
    runs[2] = replace(runs[2], tap=None, exit_code=None, status="inconclusive", reason="x")
    ev = _evidence(runs)
    ev[runs[1].patch.id] = []
    assert join_tap_disagreements(runs, ev, []) == []


def test_replay_check_all_match():
    ok = replay_check(_runs(), load_expectations(EXPECT))
    assert (ok["matched"], ok["total"], ok["mismatches"]) == (3, 3, [])
    assert ok["reproduced"] == ["release-lookup"]
    assert ok["line"].startswith("replay check: 3/3 runs match fixtures/installer/expectations.toml")
    assert "(by content sha256)" in ok["line"]


def test_replay_check_lists_mismatches():
    runs = _runs()
    runs[1] = replace(runs[1], exit_code=1)
    rc = replay_check(runs, load_expectations(EXPECT))
    assert (rc["matched"], rc["total"]) == (2, 3)
    assert rc["mismatches"] == ["wording: exit expected 0, observed 1"]
    assert rc["reproduced"] == ["release-lookup"]
    assert "2/3" in rc["line"]
