import hashlib
import shutil
from pathlib import Path

import pytest
import relate

from patch_precedent.pins import IMPLEMENTING_SHA, project_root
from patch_precedent.store import (
    build_store,
    cited_decisions,
    evidence_for_paths,
    load_evidence,
    open_readonly,
    snapshot,
)

EVIDENCE = project_root() / "evidence"
MANIFEST = EVIDENCE / "installer.toml"


@pytest.fixture
def ev(tmp_path):
    """A private, mutable copy of the evidence directory."""
    dst = tmp_path / "evidence"
    shutil.copytree(EVIDENCE, dst)
    return dst


@pytest.fixture
def store(tmp_path):
    out = tmp_path / "s.rl"
    build_store(EVIDENCE, out)
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
    build_store(EVIDENCE, other)
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


def test_manifest_missing_key(ev):
    bad = ev / "installer.toml"
    bad.write_text(bad.read_text().replace(
        'rule = "install.sh consults no GitHub API endpoint"\n', ""))
    with pytest.raises(ValueError, match="rule"):
        load_evidence(ev)


def test_check_without_harness_refused(ev):
    bad = ev / "release.toml"
    bad.write_text(bad.read_text().replace(
        'harness = "scripts/tests/test_release_advance.sh"\n', "", 1))
    with pytest.raises(ValueError, match="harness"):
        load_evidence(ev)


def test_build_refuses_open_store(store):
    conn = open_readonly(store)
    try:
        with pytest.raises(ValueError, match="open"):
            build_store(EVIDENCE, store)
    finally:
        conn.close()


def test_failed_build_keeps_existing(tmp_path, store, ev):
    before = store.read_bytes()
    bad = ev / "installer.toml"
    bad.write_text(bad.read_text().replace('implements = "ADR-0585"', 'implements = "ADR-9999"'))
    with pytest.raises(ValueError):
        build_store(ev, store)
    assert store.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".rl"] == ["s.rl"]


def test_cli_no_subcommand_exits_2(capsys):
    from patch_precedent.cli import main

    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2


def test_cli_verify_detects_drift(tmp_path, ev, capsys):
    from patch_precedent.cli import main

    s = tmp_path / "s.rl"
    assert main(["build-store", "--out", str(s)]) == 0
    assert main(["verify-store", "--store", str(s)]) == 0
    assert "store matches manifest" in capsys.readouterr().out
    other = ev / "installer.toml"
    other.write_text(other.read_text().replace('number_at_pin = 7', 'number_at_pin = 8'))
    assert main(["verify-store", "--evidence-dir", str(ev), "--store", str(s)]) == 1
    assert "differing" in capsys.readouterr().out


def _with(path, fn):
    conn = open_readonly(path)
    try:
        return fn(conn)
    finally:
        conn.close()


def test_build_merged_counts(store):
    n = _with(store, lambda c: c.execute(
        "MATCH (d:Decision) RETURN count(d) AS n").fetchone().data()["n"])
    assert n >= 567
    rows = _with(store, lambda c: cited_decisions(c, ["distribution/install.sh"]))[
        "distribution/install.sh"]
    assert len(rows) == 6
    assert [r["curated"] for r in rows].count(True) == 1
    curated = [r for r in rows if r["curated"]]
    assert curated[0]["decision"] == "ADR-0585" and curated[0]["has_checks"] is True
    assert all(r["has_checks"] is False for r in rows if not r["curated"])
    assert all(r["scanned"] for r in rows)
    assert rows[0]["curated"] and rows[1:] == sorted(rows[1:], key=lambda r: r["decision"])


def test_release_chain(store):
    rows = _with(store, lambda c: evidence_for_paths(c, ["scripts/release-bump.sh"]))[
        "scripts/release-bump.sh"]
    assert len(rows) == 2
    assert {r["decision"] for r in rows} == {"ADR-0580"}
    assert [r["check_number_at_pin"] for r in rows] == [2, 3]
    assert rows[0]["citation_url"].endswith("/scripts/release-bump.sh#L224-L238")
    assert rows[0]["implementation"] == "d79d8b150561f56b4940876a067d6b7e4781d2bc"


def test_scanned_edge_and_decision_shape(store):
    def q(c):
        return [r.data() for r in c.execute(
            "MATCH (f:File {path: $p})-[c:CITES]->(d:Decision {id: $d}) "
            "RETURN c.scanned AS s, c.curated AS cu, c.line AS line, c.url AS url, "
            "d.url AS durl, d.curated AS dcur", {"p": "distribution/install.sh", "d": "ADR-0457"})]
    (row,) = _with(store, q)
    assert row["s"] is True and row["cu"] is False
    assert row["url"].endswith(f"/distribution/install.sh#L{row['line']}")
    assert row["dcur"] is False and "/blob/" in row["durl"]


def test_cited_decisions_control(store):
    assert _with(store, lambda c: cited_decisions(c, ["CONTRIBUTING.md"])) == {
        "CONTRIBUTING.md": []}


def test_revision_mismatch_refused(tmp_path, ev):
    bad = ev / "release.toml"
    bad.write_text(bad.read_text().replace("5f7a5107", "0000000a", 1))
    with pytest.raises(ValueError, match="release.toml"):
        load_evidence(ev)
    ev2 = tmp_path / "ev2"
    shutil.copytree(EVIDENCE, ev2)
    tsv = ev2 / "scanned" / "citations.tsv"
    tsv.write_text(tsv.read_text().replace("# revision 5f7a5107", "# revision 0000000a", 1))
    with pytest.raises(ValueError, match="citations.tsv"):
        load_evidence(ev2)


def test_duplicate_check_name_refused(ev):
    rel = ev / "release.toml"
    inst = ev / "installer.toml"
    name = "advance: the version surfaces still advanced"
    inst.write_text(inst.read_text().replace(
        "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)", name))
    rel_text = rel.read_text()
    assert name in rel_text
    with pytest.raises(ValueError, match="duplicate"):
        load_evidence(ev)


def test_curated_decision_missing_from_scan_refused(ev):
    tsv = ev / "scanned" / "decisions.tsv"
    lines = [ln for ln in tsv.read_text().split("\n") if not ln.startswith("ADR-0580\t")]
    tsv.write_text("\n".join(lines))
    with pytest.raises(ValueError, match="ADR-0580"):
        load_evidence(ev)


def test_store_size_budget():
    from patch_precedent.pins import STORE_PATH
    assert STORE_PATH.stat().st_size <= 5 * 1024 * 1024
