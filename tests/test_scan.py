import pytest

from patch_precedent import pins
from patch_precedent.scan import (
    parse_adr_header, parse_grep_output, read_tsv, scan, write_tsv,
)

SHA = pins.UPSTREAM_SHA


def test_parse_grep_first_line_and_count():
    text = (
        f"{SHA}:a/b.sh:30:ADR-0002\n"
        f"{SHA}:a/b.sh:10:ADR-0002\n"
        f"{SHA}:a/b.sh:12:ADR-0001\n"
        f"{SHA}:odd:name/x.md:5:ADR-0003\n"
        f"{SHA}:a/b.sh:10:ADR-0002\n"
        "\n"
    )
    got = parse_grep_output(text)
    assert got[("a/b.sh", "ADR-0002")] == (10, 3)
    assert got[("a/b.sh", "ADR-0001")] == (12, 1)
    assert got[("odd:name/x.md", "ADR-0003")] == (5, 1)
    assert len(got) == 3


def test_parse_adr_header_variants():
    full = "# ADR-0580: Post-release workspace versioning\n\nStatus: Proposed\nx\n"
    assert parse_adr_header(full) == ("Post-release workspace versioning", "Proposed")
    assert parse_adr_header("# ADR-0001: T\n\nbody\n") == ("T", "unknown")
    assert parse_adr_header("no heading\nStatus: Accepted\n") == ("", "Accepted")
    assert parse_adr_header("") == ("", "unknown")
    assert parse_adr_header("# 0004. Memory first\n\n- **Status**: Superseded by ADR-0012\n") == (
        "Memory first", "Superseded by ADR-0012")
    assert parse_adr_header("# plain title\n\nStatus: accepted\n") == ("plain title", "accepted")
    assert parse_adr_header("# 0557 \u2014 List only the procedures\n\nStatus: Proposed\n") == (
        "List only the procedures", "Proposed")
    assert parse_adr_header("# ADR 0052: GraphStore withdrawn\n\n## Status\n\nAccepted\n\n## Context\n") == (
        "GraphStore withdrawn", "Accepted")
    assert parse_adr_header("# T\n\n## Status\n\n## Context\nx\n") == ("T", "unknown")


def test_tsv_roundtrip_byte_stable(tmp_path):
    p1, p2 = tmp_path / "a.tsv", tmp_path / "b.tsv"
    comments = [
        "# patch-precedent scanned decisions",
        f"# upstream {pins.UPSTREAM_URL}",
        f"# revision {SHA}",
    ]
    rows = [("ADR-0001", "Título", "Accepted", "docs/adr/0001-x.md"), ("ADR-0002", "", "unknown", "")]
    write_tsv(p1, comments, rows)
    meta, got = read_tsv(p1)
    assert meta["revision"] == SHA and meta["kind"] == "decisions"
    assert meta["upstream"] == pins.UPSTREAM_URL
    assert got == rows
    write_tsv(p2, comments, got)
    assert p1.read_bytes() == p2.read_bytes()
    assert p1.read_bytes().endswith(b"\n") and b"\r" not in p1.read_bytes()


@pytest.mark.parametrize("bad", ["a\tb", "a\nb"])
def test_write_tsv_rejects_tab_newline(tmp_path, bad):
    with pytest.raises(ValueError):
        write_tsv(tmp_path / "x.tsv", ["# patch-precedent scanned decisions"], [(bad, "", "", "")])


@pytest.mark.upstream
def test_scan_pinned_known_rows():
    cites, decs = scan()
    by_file: dict[str, set[str]] = {}
    for path, adr, first, count in cites:
        by_file.setdefault(path, set()).add(adr)
        assert not path.startswith("docs/adr/")
        assert isinstance(first, int) and isinstance(count, int) and count >= 1
    assert by_file["distribution/install.sh"] == {
        f"ADR-{n}" for n in ("0115", "0250", "0431", "0457", "0585", "0586")}
    assert by_file["scripts/release-bump.sh"] == {
        f"ADR-{n}" for n in ("0278", "0560", "0580", "0616")}
    assert "CONTRIBUTING.md" not in by_file
    row = next(d for d in decs if d[0] == "ADR-0580")
    assert row[1] == "Post-release workspace versioning" and row[2] == "Proposed"
    assert row[3] == "docs/adr/0580-post-release-workspace-versioning.md"
    assert [d[0] for d in decs] == sorted(d[0] for d in decs)


@pytest.mark.upstream
def test_scan_deterministic():
    assert scan() == scan()
