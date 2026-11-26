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
    load_expectations,
    record_runs,
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
    for r in rows:
        print(r)
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
