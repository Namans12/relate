from dataclasses import replace
from pathlib import Path

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import RunResult
from patch_precedent.report import compute_verdicts
from patch_precedent.tap import parse_tap

ROOT = pins.project_root()
DATA = ROOT / "tests" / "data"
FIX = ROOT / "fixtures" / "installer"
D7 = "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)"
D193 = "no case made a GitHub API request (ADR-0585)"
LOG = Path("/tmp/x.log")
WORDING = read_patch(FIX / "wording.patch")
RELEASE = read_patch(FIX / "release-lookup.patch")


def _run(label, patch, tapname, exit_code, status, reason=None):
    tap = parse_tap((DATA / f"{tapname}.tap").read_text())
    return RunResult(label, patch, "base", "cmd", exit_code, tap, LOG, status, reason)


def _row(name, number, kind, evidence):
    return {"decision": "ADR-0585", "rule": "no GitHub API", "check": name,
            "check_number_at_pin": number, "check_kind": kind, "check_evidence": evidence}


ROWS = [_row(D7, 7, "static", "install.sh must not name an API endpoint"),
        _row(D193, 193, "runtime", "curl log must hold no api.github.com request")]


def _runs():
    return [
        _run("baseline", None, "baseline", 0, "pass"),
        _run("wording", WORDING, "wording", 0, "pass"),
        _run("release-lookup", RELEASE, "release-lookup", 1, "fail"),
    ]


def _evidence(rows=ROWS):
    return {WORDING.id: list(rows), RELEASE.id: list(rows)}


def test_failing_baseline_marks_all_inconclusive():
    runs = _runs()
    runs[0] = _run("baseline", None, "release-lookup", 1, "fail")
    lines, code = compute_verdicts(runs, _evidence(), [])
    assert code == 2
    assert len(lines) == 2
    assert all("inconclusive (baseline not green" in line for line in lines)


def test_violates_lists_failing_checks():
    lines, code = compute_verdicts(_runs(), _evidence(), [])
    assert code == 0
    assert "release-lookup: violates ADR-0585 — no GitHub API" in lines
    assert "    #7 static: install.sh must not name an API endpoint" in lines
    assert "    #193 runtime: curl log must hold no api.github.com request" in lines
    assert "    harness exit 1, 192 passed / 2 failed" in lines


def test_consistent_when_linked_checks_pass():
    lines, _ = compute_verdicts(_runs(), _evidence(), [])
    assert "wording: consistent with ADR-0585 as far as checks #7, #193 cover" in lines


def test_no_linked_decision():
    lines, code = compute_verdicts(_runs(), {WORDING.id: [], RELEASE.id: ROWS}, [])
    assert "wording: no linked decision" in lines
    assert code == 0


def test_mismatch_gives_exit_3():
    _, code = compute_verdicts(_runs(), _evidence(), ["wording: exit expected 0, observed 1"])
    assert code == 3


def test_inconclusive_patch_gives_exit_2():
    runs = _runs()
    runs[1] = replace(runs[1], tap=None, exit_code=None, status="inconclusive",
                      reason="the patch did not apply cleanly to the pinned upstream")
    lines, code = compute_verdicts(runs, _evidence(), ["x"])
    assert code == 2
    assert "wording: inconclusive (the patch did not apply cleanly to the pinned upstream)" in lines
