import hashlib
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import RunResult, run_case
from patch_precedent.replay import check_expectations, load_expectations
from patch_precedent.scenarios import SCENARIOS, Scenario, get_scenario
from patch_precedent.tap import parse_tap

ROOT = pins.project_root()
FIX = ROOT / "fixtures" / "release"
DATA = ROOT / "tests" / "data" / "release"
D2 = ("advance: empty-[Unreleased] CHANGELOG.md byte-identical — "
      "no heading inserted, [Unreleased] ref unchanged")
HASHES = {
    "wording": "25a59c759f3f8876f6fe6495e01d016dbfc1ef83ce717a5b9293936edc291269",
    "always-rotate": "5b21144e810e0ac0b41f213f1f42c2846e7b79410b1dcec5509ff1b11fd5f1c5",
    "docs-only": "8ea2fb7d08c0eb7a34a9304f351477678848ee4f1cdbff9334c177b62ebfc27a",
}


def _tap(name):
    return parse_tap((DATA / f"{name}.tap").read_text())


def test_registry_names():
    assert list(SCENARIOS) == ["installer", "release"]
    inst, rel = get_scenario("installer"), get_scenario("release")
    assert isinstance(inst, Scenario)
    assert inst.harness_cmd == pins.HARNESS_CMD
    assert rel.harness_cmd == ("sh", "scripts/tests/test_release_advance.sh")
    assert inst.timeout_s == rel.timeout_s == 600
    assert rel.fixtures_dir == ROOT / "fixtures" / "release"
    assert rel.expectations_path == ROOT / "fixtures" / "release" / "expectations.toml"
    assert inst.fixtures_dir == ROOT / "fixtures" / "installer"
    assert inst.expectations_path.is_absolute() and inst.expectations_path.is_file()


def test_unknown_scenario_lists_known():
    with pytest.raises(KeyError) as exc:
        get_scenario("nope")
    assert "installer" in str(exc.value) and "release" in str(exc.value)


def test_release_fixture_hashes():
    for name, sha in HASHES.items():
        assert hashlib.sha256((FIX / f"{name}.patch").read_bytes()).hexdigest() == sha


def test_parse_release_taps():
    for name in ("baseline", "wording", "docs-only"):
        t = _tap(name)
        assert (t.passed, t.failed, t.skipped, t.complete) == (6, 0, 0, True)
    t = _tap("always-rotate")
    assert (t.passed, t.failed) == (5, 1)
    assert [(r.number, r.description) for r in t.results if not r.ok] == [(2, D2)]


def _runs(overrides=None):
    log = Path("x.log")
    runs = [RunResult("baseline", None, "base", "cmd", 0, _tap("baseline"), log, "pass", None)]
    for name in HASHES:
        patch = read_patch(FIX / f"{name}.patch")
        bad = name == "always-rotate"
        runs.append(RunResult(name, patch, "base", "cmd", 1 if bad else 0, _tap(name), log,
                              "fail" if bad else "pass", None))
    return runs


def test_expectations_release_ok():
    exp = load_expectations(get_scenario("release").expectations_path)
    assert check_expectations(_runs(), exp) == []


@pytest.mark.upstream
def test_run_release_baseline(tmp_path):
    rel = get_scenario("release")
    r = run_case("baseline", None, tmp_path, rel.harness_cmd, rel.timeout_s)
    assert r.status == "pass" and (r.tap.passed, r.tap.failed) == (6, 0)
