import hashlib
import shutil
from pathlib import Path

import pytest
import relate

from patch_precedent.pins import IMPLEMENTING_SHA, project_root
from patch_precedent.store import (
    build_store,
    evidence_for_paths,
    load_manifest,
    open_readonly,
    snapshot,
)

MANIFEST = project_root() / "evidence" / "installer.toml"


@pytest.fixture
def store(tmp_path):
    out = tmp_path / "s.rl"
    build_store(MANIFEST, out)
    return out


def test_build_and_query(store):
    conn = open_readonly(store)
    try:
        rows = evidence_for_paths(conn, ["distribution/install.sh"])["distribution/install.sh"]
    finally:
        conn.close()
    assert len(rows) == 2
    assert {r["decision"] for r in rows} == {"ADR-0585"}
    assert all(r["implementation"] == IMPLEMENTING_SHA for r in rows)
    assert [r["check_number_at_pin"] for r in rows] == [7, 193]
    assert rows[0]["status"] == "Proposed"
    assert rows[0]["check_kind"] == "static" and rows[1]["check_kind"] == "runtime"
    assert rows[0]["citation_url"].endswith("/distribution/install.sh#L120-L128")
    assert rows[0]["decision_url"].endswith(".md#L8-L38")
    assert rows[0]["consequences_url"].endswith(".md#L89-L97")
    assert rows[1]["check_url"].endswith("test_install_sh.sh#L610-L615")


def test_unlinked_path_empty(store):
    conn = open_readonly(store)
    try:
        assert evidence_for_paths(conn, ["README.md"]) == {"README.md": []}
    finally:
        conn.close()


def _snap(path):
    conn = open_readonly(path)
    try:
        return snapshot(conn)
    finally:
        conn.close()


def test_rebuild_snapshot_equal(tmp_path, store):
    other = tmp_path / "o.rl"
    build_store(MANIFEST, other)
    assert _snap(store) == _snap(other)
    assert len(_snap(store)) > 5


def test_readonly_leaves_bytes(store):
    before = hashlib.sha256(store.read_bytes()).hexdigest()
    conn = open_readonly(store)
    evidence_for_paths(conn, ["distribution/install.sh"])
    snapshot(conn)
    conn.close()
    assert hashlib.sha256(store.read_bytes()).hexdigest() == before
    conn = open_readonly(store)
    with pytest.raises(relate.OperationalError):
        conn.execute("CREATE (:File {path: $p})", {"p": "x"})
    conn.close()


def test_manifest_missing_key(tmp_path):
    bad = tmp_path / "bad.toml"
    text = MANIFEST.read_text().replace('rule = "install.sh consults no GitHub API endpoint"\n', "")
    bad.write_text(text)
    with pytest.raises(ValueError, match="rule"):
        load_manifest(bad)


def test_build_refuses_open_store(store):
    conn = open_readonly(store)
    try:
        with pytest.raises(ValueError, match="open"):
            build_store(MANIFEST, store)
    finally:
        conn.close()


def test_failed_build_keeps_existing(tmp_path, store):
    before = store.read_bytes()
    bad = tmp_path / "bad.toml"
    bad.write_text(MANIFEST.read_text().replace('implements = "ADR-0585"', 'implements = "ADR-9999"'))
    with pytest.raises(ValueError):
        build_store(bad, store)
    assert store.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".rl"] == ["s.rl"]


def test_cli_no_subcommand_exits_2(capsys):
    from patch_precedent.cli import main

    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


def test_cli_verify_detects_drift(tmp_path, capsys):
    from patch_precedent.cli import main

    s = tmp_path / "s.rl"
    assert main(["build-store", "--out", str(s)]) == 0
    assert main(["verify-store", "--store", str(s)]) == 0
    assert "store matches manifest" in capsys.readouterr().out
    other = tmp_path / "m.toml"
    other.write_text(MANIFEST.read_text().replace('number_at_pin = 7', 'number_at_pin = 8'))
    assert main(["verify-store", "--manifest", str(other), "--store", str(s)]) == 1
    assert "differing" in capsys.readouterr().out
