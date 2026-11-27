import io
from pathlib import Path

from patch_precedent.cli import main
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import RunResult
from patch_precedent.pins import STORE_PATH, project_root
from patch_precedent.report import VerdictRecord
from patch_precedent.store import cited_decisions, evidence_for_paths, open_readonly
from patch_precedent.tap import TapReport, TapResult
from patch_precedent.tui import StyledReporter, make_console, render_explain, should_style
from patch_precedent.text import prose

FIX = project_root() / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "data" / "golden"


def _explain(patch_path: Path, links: bool, width: int = 80) -> tuple[str, list[str]]:
    patch = read_patch(patch_path)
    conn = open_readonly(STORE_PATH)
    try:
        evidence = evidence_for_paths(conn, patch.changed_files)
        cited = cited_decisions(conn, patch.changed_files)
    finally:
        conn.close()
    buf = io.StringIO()
    render_explain(make_console(file=buf, width=width, force_terminal=False),
                   patch, evidence, cited, links)
    names = [r["check"] for rows in evidence.values() for r in rows]
    return buf.getvalue(), names


def test_should_style():
    class T(io.StringIO):
        def isatty(self):
            return True

    assert should_style(T(), plain=False, env={}) is True
    assert should_style(T(), plain=True, env={}) is False
    assert should_style(T(), plain=False, env={"NO_COLOR": "1"}) is False
    assert should_style(T(), plain=False, env={"NO_COLOR": ""}) is True
    assert should_style(io.StringIO(), plain=False, env={}) is False


def test_explain_styled_snapshot():
    out, _ = _explain(FIX / "installer/token-header.patch", links=False)
    assert out == (GOLDEN_DIR / "explain-token-header.styled.txt").read_text()


def test_explain_styled_links_flag_adds_permalinks():
    base = "https://github.com/relatedb/relate/"
    without, _ = _explain(FIX / "installer/token-header.patch", links=False)
    with_links, _ = _explain(FIX / "installer/token-header.patch", links=True)
    assert base not in without and "--links" in without
    assert base in with_links and "--links" not in with_links


def test_styled_text_has_no_forbidden_dashes_outside_check_names():
    out, names = _explain(FIX / "release/always-rotate.patch", links=False, width=400)
    for n in sorted(names, key=len, reverse=True):
        out = out.replace(n, "")
    assert "–" not in out and "—" not in out
    assert prose("a — b–c") == "a - b-c"


def _run(label, passed, failed, code, nums=()):
    results = [TapResult(i + 1, True, f"t{i}") for i in range(passed)]
    results += [TapResult(n, False, f"f{n}") for n in nums]
    tap = TapReport(tuple(results), passed + failed, passed, failed, 0, True)
    return RunResult(label, None, "sha", "cmd", code, tap, Path("log"),
                     "pass" if code == 0 else "fail", None)


def test_styled_reporter_row_alignment():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=80, force_terminal=False))
    rep.run_end(_run("baseline", 194, 0, 0), 6.8)
    rep.run_end(_run("release-lookup", 192, 2, 1, (7, 193)), 7.1)
    first, second = buf.getvalue().splitlines()
    assert first.index("passed") == second.index("passed")
    assert "#7 #193" in second and "exit 1" in second and "7.1s" in second
    assert first.lstrip().startswith("✓") and second.lstrip().startswith("✗")


def test_markup_in_names_is_not_interpreted():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=80, force_terminal=False))
    rep.verdicts([], [VerdictRecord("x[red]", "violates", ("ADR-1",), "r",
                                    ((2, "runtime", "empty-[Unreleased] CHANGELOG"),))],
                 {"line": "replay check: 1/1 [Unreleased]", "reproduced": ["x[red]"],
                  "inconclusive": []},
                 ["w [Unreleased] — z"], [])
    out = buf.getvalue()
    assert "x[red]" in out and "[Unreleased]" in out
    assert "—" not in out and "expected regression reproduced" in out


def test_finish_is_idempotent_and_flushes_buffered_details():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=80, force_terminal=False))
    rep.details([], {}, ["BLOCK"], "MATCH q", [])
    rep.finish()
    rep.finish()
    assert buf.getvalue().count("BLOCK") == 1


def test_cli_plain_flag_keeps_plain_explain(capsys):
    assert main(["explain", "--plain", str(FIX / "installer/token-header.patch")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("patch    token-header (sha256 5146b525a26d)\n")
    assert "mode     read-only" in out and "\x1b" not in out


def _no_trailing(text: str):
    bad = [ln for ln in text.splitlines() if ln != ln.rstrip()]
    assert not bad, bad[:3]


def test_no_trailing_whitespace_in_styled_output():
    for links in (False, True):
        out, _ = _explain(FIX / "installer/token-header.patch", links=links)
        _no_trailing(out)
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=80, force_terminal=False))
    rep.run_end(_run("baseline", 194, 0, 0), 6.8)
    rep.run_end(_run("release-lookup", 192, 2, 1, (7, 193)), 7.1)
    rep.details([_run("baseline", 6, 0, 0)], {}, ["blk"], "Q",
                [{"patch": "patch:abc", "label": "l", "file": "f.sh", "decision": "ADR-1",
                  "implementation": "0123456789ab", "assertion": "a long assertion " * 6,
                  "observed": "ok", "tap_number": 2}])
    rep.verdicts([], [VerdictRecord("x", "consistent", ("ADR-1",))],
                 {"line": "l", "reproduced": [], "inconclusive": []}, [], [])
    rep.finish()
    out = buf.getvalue()
    _no_trailing(out)
    assert "patch:abc" in out and "f.sh" in out and "0123456789"[:8] in out


def test_run_row_gap_before_failing_numbers():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=80, force_terminal=False))
    rep.run_end(_run("release-lookup", 192, 2, 1, (7, 193)), 7.1)
    assert "7.1s   #7 #193" in buf.getvalue()
