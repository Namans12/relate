import hashlib
import json
import shutil
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.evidence import latest_replays, precedent_for_patch
from patch_precedent.harness import RunResult
from patch_precedent.replay import record_runs
from patch_precedent.tap import parse_tap

ROOT = pins.project_root()
DATA = ROOT / "tests" / "data"
FIX = ROOT / "fixtures"
REL_CMD = "sh scripts/tests/test_release_advance.sh"
INS_CMD = "sh scripts/tests/test_install_sh.sh"
NOTE = ('"observed" is the check\'s result in Patch Precedent\'s replay of this exact patch '
        '(matched by its changed lines, ignoring whitespace and context) against the unmodified upstream harness; '
        '"not observed" means no replay of this patch was found, or that replay produced no result '
        'for this check.')


def _text(scn, name):
    return (FIX / scn / f"{name}.patch").read_bytes().decode()


def _run(scn, name, tap_path, cmd, code):
    return RunResult(name, read_patch(FIX / scn / f"{name}.patch"), "base", cmd, code,
                     parse_tap(tap_path.read_text()), Path("/tmp/x.log"),
                     "pass" if code == 0 else "fail", None)


def _make_replays(root, ts="20260101T000000Z"):
    for scn, cmd, tapdir, items in (
        ("installer", INS_CMD, DATA, [("release-lookup", 1), ("token-header", 1), ("wording", 0)]),
        ("release", REL_CMD, DATA / "release",
         [("always-rotate", 1), ("docs-only", 0), ("wording", 0)]),
    ):
        d = root / ts / scn
        d.mkdir(parents=True)
        shutil.copy2(pins.STORE_PATH, d / "replay.rl")
        record_runs(d / "replay.rl",
                    [_run(scn, n, tapdir / f"{n}.tap", cmd, c) for n, c in items])


def _checks(res):
    return {c["tap_number"] if c["observed"] != "not observed" else c["number_at_pin"]:
            c["observed"] for f in res["files"] for d in f["decisions"] for c in d["checks"]}


def test_precedent_without_replay(tmp_path):
    res = precedent_for_patch(_text("installer", "release-lookup"), pins.STORE_PATH, tmp_path)
    assert res["replay"] is None
    assert res["changed_files"] == ["distribution/install.sh"]
    assert res["note"] == NOTE
    assert res["hint"] == (
        "No replay matches this diff's changed lines. Pass the patch exactly as given; if Patch "
        'Precedent has never been replayed here, run "uv run patch-precedent demo all".')
    assert str(tmp_path) not in json.dumps(res)
    (f,) = res["files"]
    (d,) = f["decisions"]
    assert d["id"] == "ADR-0585" and len(d["commit"]) == 8
    assert d["rule"] == "install.sh consults no GitHub API endpoint and does not read GITHUB_TOKEN"
    assert {c["observed"] for c in d["checks"]} == {"not observed"}
    assert {c["tap_number"] for c in d["checks"]} == {None}
    assert {c["number_at_pin"] for c in d["checks"]} == {7, 64, 193}
    assert "verdict" not in res and all("verdict" not in x for x in (f, d))
    assert "ADR-0585" not in {a["id"] for a in f["also_cites"]}


def test_no_changed_files(tmp_path):
    res = precedent_for_patch("not a diff\n", pins.STORE_PATH, tmp_path / "missing")
    assert res["files"] == [] and res["changed_files"] == [] and res["replay"] is None


def test_latest_replays_newest_first(tmp_path):
    _make_replays(tmp_path, "20260101T000000Z")
    (tmp_path / "20260202T000000Z" / "installer").mkdir(parents=True)
    (tmp_path / "20260202T000000Z" / "installer" / "replay.rl").write_bytes(b"x")
    (tmp_path / "junk").mkdir()
    got = latest_replays(tmp_path)
    assert got["installer"].parent.parent.name == "20260202T000000Z"
    assert got["release"].parent.parent.name == "20260101T000000Z"
    assert latest_replays(tmp_path / "nope") == {}


def test_precedent_with_replay(tmp_path):
    _make_replays(tmp_path)
    c1 = precedent_for_patch(_text("installer", "release-lookup"), pins.STORE_PATH, tmp_path)
    assert c1["replay"] == {"scenario": "installer", "run": "20260101T000000Z",
                            "label": "release-lookup"}
    assert _checks(c1) == {7: "not ok", 193: "not ok", 64: "ok"}
    assert "hint" not in c1 and "skipped_replays" not in c1
    c3 = precedent_for_patch(_text("installer", "token-header"), pins.STORE_PATH, tmp_path)
    assert _checks(c3) == {64: "not ok", 7: "ok", 193: "ok"}
    c4 = precedent_for_patch(_text("release", "always-rotate"), pins.STORE_PATH, tmp_path)
    assert c4["replay"]["scenario"] == "release"
    assert _checks(c4) == {2: "not ok", 3: "ok"}
    c6 = precedent_for_patch(_text("release", "docs-only"), pins.STORE_PATH, tmp_path)
    assert c6["replay"]["label"] == "docs-only"
    assert all(f["decisions"] == [] and f["also_cites"] == [] for f in c6["files"])
    # whitespace-mangled copy still matches
    mangled = _text("installer", "token-header").replace("\t", "    ").replace("\n", "\r\n")
    assert precedent_for_patch(mangled, pins.STORE_PATH, tmp_path)["replay"]["label"] == "token-header"
    # an unrelated patch finds no replay
    other = _text("installer", "release-lookup").replace("api.github.com", "api.example.com")
    assert precedent_for_patch(other, pins.STORE_PATH, tmp_path)["replay"] is None


def test_context_trimmed_diff_still_finds_replay(tmp_path):
    _make_replays(tmp_path)
    lines = _text("installer", "release-lookup").splitlines()
    trimmed = "\n".join(lines[:-2]) + "\n"
    res = precedent_for_patch(trimmed, pins.STORE_PATH, tmp_path)
    assert res["replay"]["label"] == "release-lookup"
    assert _checks(res) == {7: "not ok", 193: "not ok", 64: "ok"}


def test_older_replay_without_patch_key_does_not_match(tmp_path):
    _make_replays(tmp_path, "20260101T000000Z")
    import relate
    d = tmp_path / "20260202T000000Z" / "installer"
    d.mkdir(parents=True)
    shutil.copy2(tmp_path / "20260101T000000Z" / "installer" / "replay.rl", d / "replay.rl")
    conn = relate.connect(str(d / "replay.rl"))
    conn.execute("MATCH (p:Patch) REMOVE p.patch_key")
    conn.commit()
    conn.close()
    res = precedent_for_patch(_text("installer", "release-lookup"), pins.STORE_PATH, tmp_path)
    assert res["replay"]["run"] == "20260101T000000Z"


def test_garbage_newest_replay_is_skipped(tmp_path):
    _make_replays(tmp_path, "20260101T000000Z")
    bad = tmp_path / "20260202T000000Z" / "installer" / "replay.rl"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"this is not a relate database" * 50)
    res = precedent_for_patch(_text("installer", "release-lookup"), pins.STORE_PATH, tmp_path)
    assert res["replay"]["run"] == "20260101T000000Z"
    assert _checks(res) == {7: "not ok", 193: "not ok", 64: "ok"}
    assert res["skipped_replays"] == [str(bad.relative_to(tmp_path))]
    # when nothing matches, skipped replays are still reported alongside the hint
    other = _text("installer", "release-lookup").replace("api.github.com", "api.example.com")
    res = precedent_for_patch(other, pins.STORE_PATH, tmp_path)
    assert res["replay"] is None and "hint" in res
    assert res["skipped_replays"] == [str(bad.relative_to(tmp_path))]
    assert str(tmp_path) not in json.dumps(res)


def test_hint_only_when_replay_is_null(tmp_path):
    _make_replays(tmp_path)
    found = precedent_for_patch(_text("installer", "wording"), pins.STORE_PATH, tmp_path)
    assert found["replay"] is not None and "hint" not in found
    missing = precedent_for_patch(_text("installer", "wording"), pins.STORE_PATH,
                                  tmp_path / "none")
    assert missing["replay"] is None and "demo all" in missing["hint"]
    assert str(tmp_path) not in missing["hint"]


def test_precedent_readonly(tmp_path):
    _make_replays(tmp_path)
    paths = [pins.STORE_PATH, *tmp_path.rglob("replay.rl")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    precedent_for_patch(_text("installer", "release-lookup"), pins.STORE_PATH, tmp_path)
    precedent_for_patch(_text("release", "docs-only"), pins.STORE_PATH, tmp_path)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before


@pytest.mark.upstream
def test_precedent_with_real_demo(tmp_path):
    from patch_precedent.demo import run_demo
    run_demo("installer", runs_root=tmp_path)
    res = precedent_for_patch(_text("installer", "token-header"), pins.STORE_PATH, tmp_path)
    assert _checks(res) == {64: "not ok", 7: "ok", 193: "ok"}
