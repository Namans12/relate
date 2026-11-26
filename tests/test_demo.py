import hashlib
import json
import shutil

import pytest

from patch_precedent import pins
from patch_precedent.demo import run_demo

pytestmark = pytest.mark.upstream

FIX = pins.project_root() / "fixtures" / "installer"
D7 = "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)"
D193 = "no case made a GitHub API request (ADR-0585)"


def _summary(runs_root):
    (run_dir,) = [p for p in runs_root.iterdir() if p.is_dir()]
    return json.loads((run_dir / "summary.json").read_text())


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
    assert all(r["skipped"] == 0 for r in runs.values())
    assert runs["release-lookup"]["failing"] == [D7, D193]
    assert runs["release-lookup"]["failing_numbers"] == [7, 193]
    assert len(s["join_rows"]) == 4
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
