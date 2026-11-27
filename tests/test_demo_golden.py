"""Plain-mode `demo all` output is pinned byte-for-byte (paths and run ids normalised)."""
import json
import re
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.demo import run_all

pytestmark = pytest.mark.upstream

GOLDEN_DIR = Path(__file__).parent / "data" / "golden"


def normalise(text: str, root: Path, runs_root: Path) -> str:
    text = text.replace(str(runs_root), "<RUNS>")
    text = text.replace(str(root), "<ROOT>")
    text = re.sub(r"<RUNS>/\d{8}T\d{6}Z(-\d+)?", "<RUNS>/<RUN>", text)
    return text.replace(str(Path.home()), "<HOME>")


def test_plain_demo_all_matches_golden(tmp_path, capsys):
    assert run_all(runs_root=tmp_path) == 0
    out = normalise(capsys.readouterr().out, pins.project_root(), tmp_path)
    assert out == (GOLDEN_DIR / "demo-all.txt").read_text()


def test_summary_has_durations_and_records(tmp_path):
    assert run_all(runs_root=tmp_path) == 0
    top = json.loads(next(tmp_path.iterdir()).joinpath("summary.json").read_text())
    assert top["elapsed_s"] > 0
    inst = top["scenarios"]["installer"]
    assert all(r["duration_s"] > 0 for r in inst["runs"])
    recs = {r["label"]: r for r in inst["verdict_records"]}
    assert recs["token-header"]["kind"] == "violates"
    assert recs["token-header"]["decisions"] == ["ADR-0585"]
    assert [f[0] for f in recs["token-header"]["failing"]] == [64]
    assert recs["wording"]["kind"] == "consistent"
    rel = {r["label"]: r for r in top["scenarios"]["release"]["verdict_records"]}
    assert rel["docs-only"]["kind"] == "no_decision"
    assert rel["always-rotate"]["failing"][0][0] == 2
