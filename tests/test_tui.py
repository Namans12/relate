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


# -- demo details and verdicts with fake runs -------------------------------

_URL = "https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/"


def _row(check, number, decision="ADR-0431"):
    return {
        "decision": decision, "title": "Extension distribution — the first-party channel",
        "status": "Accepted", "rule": "install.sh — never calls the API",
        "reason": "Because – of limits " * 8, "implementation": "0123456789abcdef",
        "commit_subject": "fix: scripts — install", "commit_url": _URL.replace("blob", "commit") + "x" * 20,
        "citation_url": _URL + "distribution/install.sh#L10-L12",
        "decision_url": _URL + "docs/adr/0431-extension-distribution-the-first-party-channel.md",
        "consequences_url": _URL + "docs/adr/0431-extension-distribution-the-first-party-channel.md#consequences",
        "check": check, "check_number_at_pin": number, "check_kind": "runtime",
        "check_url": _URL + "scripts/tests/test_distribution_installer_release_lookup_failures.sh#L100-L140",
        "check_evidence": "e",
    }


def _patch(label="release-lookup"):
    from patch_precedent.diffparse import PatchInfo
    return PatchInfo(Path("/nonexistent.patch"), label, "a" * 64, "patch:" + "a" * 12,
                     ("distribution/install.sh",), "k")


def _patched_run(label, nums=(), unlinked=()):
    r = _run(label, 3, len(nums) + len(unlinked), 1, tuple(nums) + tuple(n for n, _ in unlinked))
    results = tuple(TapResult(x.number, x.ok, "extension channel check" if x.number in nums
                              else dict(unlinked).get(x.number, x.description)) for x in r.tap.results)
    tap = TapReport(results, len(results), r.tap.passed, r.tap.failed, 0, True)
    return RunResult(label, _patch(label), "sha", "cmd", 1, tap, Path("log"), "fail", None)


def test_styled_details_transcript_is_clean():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=100, force_terminal=False))
    run = _patched_run("release-lookup", nums=(7,))
    rows = [_row("extension channel check", 7)]
    rep.details([_run("baseline", 6, 0, 0), run], {run.patch.id: rows}, ["RAW BLOCK"], "Q", [],
                [("distribution/install.sh", rows, [], [("release-lookup", {"extension channel check":
                  run.tap.results[-1]})])])
    rep.finish()
    out = buf.getvalue()
    assert "RAW BLOCK" not in out
    assert "–" not in out and "—" not in out
    assert "ADR-0431" in out and "Extension distribution - the first-party channel" in out
    assert "release-lookup → not ok 7" in out
    for ln in out.splitlines():
        tok = ln.strip()
        if " " not in tok and ("/blob/" in tok or "/commit/" in tok or "relatedb" in tok):
            assert tok.startswith("https://"), ln  # a URL is never a wrapped fragment
        if ln and not ln[0].isspace():  # nothing wrapped back to column 0
            assert ln.startswith(("\u2500", "-", "Input", "Comparison", "Graph", "Q",
                                  "distribution/install.sh", "ADR-0431", "baseline",
                                  "release-lookup", "label")), ln
    # every permalink survives intact on one line
    for url in (rows[0]["citation_url"], rows[0]["check_url"], rows[0]["commit_url"]):
        assert any(ln.strip() == url or ln.strip().endswith(url) for ln in out.splitlines())


def test_comparison_changed_column_does_not_fold():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=100, force_terminal=False))
    run = _patched_run("release-lookup", nums=(7,))
    rows = [_row("extension channel check", 7)]
    rep.details([run], {run.patch.id: rows}, [], "Q", [])
    rep.finish()
    assert "install.sh" in buf.getvalue()
    assert not any(ln.strip() in ("l.sh", "sh") for ln in buf.getvalue().splitlines())


def test_verdicts_show_unlinked_failures_reasons_and_covered_checks():
    buf = io.StringIO()
    rep = StyledReporter(make_console(file=buf, width=100, force_terminal=False))
    recs = [
        VerdictRecord("p1", "consistent", ("ADR-0585",), covered=(7, 64),
                      unlinked=((12, "other [Unreleased] check"),)),
        VerdictRecord("p2", "inconclusive", reason="linked checks not found in TAP output"),
        VerdictRecord("p3", "no_decision", unlinked=((3, "stray"),)),
    ]
    rep.verdicts([], recs, {"line": "l", "reproduced": [], "inconclusive": []}, [], [])
    out = buf.getvalue()
    assert "consistent with ADR-0585 (checks #7, #64)" in out
    assert "also failed (no linked decision): #12 other [Unreleased] check" in out
    assert "also failed (no linked decision): #3 stray" in out
    assert "linked checks not found in TAP output" in out


def test_verdict_records_carry_unlinked_and_reason():
    from patch_precedent.report import verdict_records
    base = _run("baseline", 6, 0, 0)
    run = _patched_run("p", nums=(7,), unlinked=((9, "stray"),))
    rows = [_row("extension channel check", 7)]
    (rec,) = verdict_records([base, run], {run.patch.id: rows})
    assert rec.kind == "violates" and rec.unlinked == ((9, "stray"),)
    assert rec.as_dict()["unlinked"] == [[9, "stray"]]
    bad = RunResult("p", _patch(), "sha", "cmd", None, None, Path("log"), "inconclusive", "timed out")
    (rec,) = verdict_records([base, bad], {})
    assert rec.kind == "inconclusive" and rec.reason == "timed out"
    (rec,) = verdict_records([_run("baseline", 1, 1, 1, (1,)), run], {})
    assert rec.reason.startswith("baseline not green")
    import json
    json.dumps(rec.as_dict())
