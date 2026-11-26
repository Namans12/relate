import hashlib
import json
import shutil

import pytest

from patch_precedent import pins
from patch_precedent.demo import run_all, run_demo

pytestmark = pytest.mark.upstream

FIX = pins.project_root() / "fixtures" / "installer"
D7 = "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)"
D64 = "token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)"
D193 = "no case made a GitHub API request (ADR-0585)"


def _summary(runs_root, scenario="installer"):
    (run_dir,) = [p for p in runs_root.iterdir() if p.is_dir()]
    return json.loads((run_dir / scenario / "summary.json").read_text())


def _by_label(summary):
    return {r["label"]: r for r in summary["runs"]}


def test_demo_matches_acceptance(tmp_path, capsys):
    assert run_demo("installer", runs_root=tmp_path) == 0
    s = _summary(tmp_path)
    runs = _by_label(s)
    triple = lambda r: (r["passed"], r["failed"], r["exit_code"])  # noqa: E731
    assert triple(runs["baseline"]) == (194, 0, 0)
    assert triple(runs["wording"]) == (194, 0, 0)
    assert triple(runs["release-lookup"]) == (192, 2, 1)
    assert triple(runs["token-header"]) == (193, 1, 1)
    assert len(runs) == 4
    assert all(r["skipped"] == 0 for r in runs.values())
    assert runs["release-lookup"]["failing"] == [D7, D193]
    assert runs["release-lookup"]["failing_numbers"] == [7, 193]
    assert runs["token-header"]["failing"] == [D64]
    assert runs["token-header"]["failing_numbers"] == [64]
    assert runs["wording"]["failing_numbers"] == []
    assert len(s["join_rows"]) == 9
    observed = {(r["label"], r["tap_number"]): r["observed"] for r in s["join_rows"]}
    assert {k: v for k, v in observed.items() if v == "not ok"} == {
        ("release-lookup", 7): "not ok", ("release-lookup", 193): "not ok",
        ("token-header", 64): "not ok"}
    assert observed[("release-lookup", 64)] == "ok"
    assert observed[("wording", 64)] == "ok"
    assert s["exit_code"] == 0
    assert "violates ADR-0585" in capsys.readouterr().out


def test_demo_twice_identical_and_store_untouched(tmp_path):
    store = pins.STORE_PATH
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    rows = []
    for i in (1, 2):
        root = tmp_path / str(i)
        assert run_demo("installer", runs_root=root) == 0
        rows.append(sorted(json.dumps(r, sort_keys=True) for r in _summary(root)["join_rows"]))
    assert rows[0] == rows[1]
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before


def test_demo_renamed_fixtures(tmp_path):
    fixtures = tmp_path / "fx"
    fixtures.mkdir()
    shutil.copy(FIX / "wording.patch", fixtures / "release-lookup.patch")
    shutil.copy(FIX / "release-lookup.patch", fixtures / "wording.patch")
    assert run_demo("installer", fixtures_dir=fixtures, runs_root=tmp_path / "runs") == 0
    runs = _by_label(_summary(tmp_path / "runs"))
    assert runs["wording"]["failing_numbers"] == [7, 193]
    assert runs["release-lookup"]["failing"] == []


RELEASE_2 = ("advance: empty-[Unreleased] CHANGELOG.md byte-identical — "
             "no heading inserted, [Unreleased] ref unchanged")


def test_demo_release_acceptance(tmp_path):
    assert run_demo("release", runs_root=tmp_path) == 0
    s = _summary(tmp_path, "release")
    runs = _by_label(s)
    triple = lambda r: (r["passed"], r["failed"], r["exit_code"])  # noqa: E731
    assert triple(runs["baseline"]) == (6, 0, 0)
    assert triple(runs["wording"]) == (6, 0, 0)
    assert triple(runs["always-rotate"]) == (5, 1, 1)
    assert triple(runs["docs-only"]) == (6, 0, 0)
    assert runs["always-rotate"]["failing"] == [RELEASE_2]
    assert runs["always-rotate"]["failing_numbers"] == [2]
    ids = {runs["wording"]["patch_id"], runs["always-rotate"]["patch_id"]}
    assert {row["patch"] for row in s["join_rows"]} == ids
    assert s["exit_code"] == 0


def test_demo_all(tmp_path, capsys):
    before = hashlib.sha256(pins.STORE_PATH.read_bytes()).hexdigest()
    assert run_all(runs_root=tmp_path) == 0
    (run_dir,) = [p for p in tmp_path.iterdir() if p.is_dir()]
    top = json.loads((run_dir / "summary.json").read_text())
    assert list(top["scenarios"]) == ["installer", "release"]
    assert top["overall_exit"] == 0
    for name, sc in top["scenarios"].items():
        assert sc["exit_code"] == 0
        assert json.loads((run_dir / name / "summary.json").read_text()) == sc
    out = capsys.readouterr().out
    assert out.index("### scenario: installer") < out.index("### scenario: release")
    assert "== overall ==" in out and "overall exit 0" in out
    assert hashlib.sha256(pins.STORE_PATH.read_bytes()).hexdigest() == before
