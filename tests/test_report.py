from dataclasses import replace
from pathlib import Path

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import RunResult
from patch_precedent.report import (
    comparison_table,
    compute_verdicts,
    join_table,
    observed_map,
    render_cited_block,
    render_evidence_chain,
    shorten_status,
    verdict_records,
)
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


def test_baseline_changed_cell_says_unpatched():
    table = comparison_table(_runs(), _evidence())
    baseline_line = next(line for line in table.splitlines() if line.startswith("baseline"))
    assert "— (unpatched)" in baseline_line
    assert "upstream" not in table


def _chain_rows():
    return [dict(_row(D7, 7, "static", "e7"), title="T", status="Proposed", reason="r",
                 citation_url="cu", decision_url="du", consequences_url="su",
                 implementation="a" * 40, commit_subject="subj", commit_url="cm",
                 check_url="k7"),
            dict(_row(D193, 193, "runtime", "e193"), title="T", status="Proposed", reason="r",
                 citation_url="cu", decision_url="du", consequences_url="su",
                 implementation="a" * 40, commit_subject="subj", commit_url="cm",
                 check_url="k193")]


def test_shared_chain_prints_each_patch_under_each_check_once():
    runs = _runs()
    obs = [(r.label, observed_map(r)) for r in runs[1:]]
    out = render_evidence_chain("distribution/install.sh", _chain_rows(), patch_observed=obs)
    assert out.count("distribution/install.sh") == 1
    assert out.count("cites ADR-0585") == 1
    lines = out.splitlines()
    i7 = next(i for i, line in enumerate(lines) if "#7 " in line or line.strip().startswith("#7"))
    block7 = "\n".join(lines[i7:i7 + 4])
    assert "wording → ok 7" in block7
    assert "release-lookup → not ok 7" in out
    assert "release-lookup → not ok 193" in out
    assert "wording → ok 193" in out
    assert out.count("→") == 4


def test_chain_without_patch_observed_is_unchanged():
    out = render_evidence_chain("a.sh", _chain_rows())
    assert "→" not in out


def test_join_table_columns_match_query():
    rows = [{"patch": "patch:abc", "label": "wording", "file": "f.sh", "decision": "ADR-0585",
             "implementation": "5ac38808547d", "assertion": D7, "observed": "not ok",
             "tap_number": 7, "reason": "ignored"}]
    lines = join_table(rows).splitlines()
    assert lines[0].split() == ["patch", "label", "file", "decision", "implementation",
                                "assertion", "observed"]
    assert "patch:abc" in lines[2]
    assert "5ac38808 " in lines[2] and "5ac388085" not in lines[2]
    assert lines[2].rstrip().endswith("not ok 7")


def _cited(decision, title="Some title", status="Accepted", curated=False, has_checks=False):
    return {"file": "a.sh", "decision": decision, "title": title, "status": status,
            "decision_url": "du", "citation_url": f"http://c/{decision}",
            "curated": curated, "scanned": True, "has_checks": has_checks}


def test_verdict_scanned_only():
    cited = {WORDING.id: [_cited("ADR-0300"), _cited("ADR-0115"), _cited("ADR-0300")],
             RELEASE.id: []}
    lines, code = compute_verdicts(_runs(), {WORDING.id: [], RELEASE.id: ROWS}, [], cited)
    assert "wording: cites ADR-0115, ADR-0300 (scanned, unreviewed); no linked checks" in lines
    assert not any("consistent with" in ln and ln.startswith("wording") for ln in lines)
    assert code == 0


def test_verdict_control_no_linked_decision():
    lines, code = compute_verdicts(
        _runs(), {WORDING.id: [], RELEASE.id: ROWS}, [], {WORDING.id: [], RELEASE.id: []})
    assert "wording: no linked decision" in lines
    assert code == 0


def test_render_cited_block():
    out = render_cited_block("a.sh", [_cited("ADR-0115", status="Accepted"),
                                      _cited("ADR-0116", title="")])
    assert out.splitlines() == [
        "  also cites (scanned from source, not reviewed)",
        "    ADR-0115 · Some title [Accepted]  http://c/ADR-0115",
        "    ADR-0116 · (no record) [Accepted]  http://c/ADR-0116",
    ]
    assert render_cited_block("a.sh", []) == ""


def test_shorten_status():
    assert shorten_status("Accepted") == "Accepted"
    assert shorten_status("Accepted\nsecond line") == "Accepted"
    long = "x" * 50
    assert shorten_status(long) == "x" * 40 + "…"
    assert shorten_status("y" * 40) == "y" * 40


# --- verdict records -------------------------------------------------------

def _fakes():
    return _runs(), _evidence(), {WORDING.id: [], RELEASE.id: []}


def test_verdict_records_match_compute_verdicts_kinds():
    prefixes = {"violates": "violates", "consistent": "consistent with",
                "no_decision": "no linked decision", "scanned_only": "cites",
                "inconclusive": "inconclusive"}
    cases = [
        (_runs(), _evidence(), {}),
        (_runs(), {WORDING.id: [], RELEASE.id: ROWS}, {}),
        (_runs(), {WORDING.id: [], RELEASE.id: ROWS},
         {WORDING.id: [_cited("ADR-0300"), _cited("ADR-0115")], RELEASE.id: []}),
    ]
    inc = _runs()
    inc[2] = replace(inc[2], status="inconclusive", reason="timeout", tap=None)
    cases.append((inc, _evidence(), {}))
    for runs, ev, cited in cases:
        lines, _ = compute_verdicts(runs, ev, [], cited)
        recs = verdict_records(runs, ev, cited)
        heads = [ln for ln in lines if not ln.startswith("    ")]
        for rec in recs:
            head = next(h for h in heads if h.startswith(f"{rec.label}: "))
            assert head[len(rec.label) + 2:].startswith(prefixes[rec.kind]), (rec, head)
    recs = {r.label: r for r in verdict_records(_runs(), _evidence(), {})}
    assert recs["release-lookup"].kind == "violates"
    assert recs["release-lookup"].decisions == ("ADR-0585",)
    assert recs["release-lookup"].rule == "no GitHub API"
    assert [f[0] for f in recs["release-lookup"].failing] == [7, 193]
    assert recs["wording"].kind == "consistent"
    assert recs["wording"].covered == (7, 193)


def test_verdict_records_scanned_only_lists_decisions():
    cited = {WORDING.id: [_cited("ADR-0300"), _cited("ADR-0115"), _cited("ADR-0300")],
             RELEASE.id: []}
    recs = {r.label: r for r in
            verdict_records(_runs(), {WORDING.id: [], RELEASE.id: ROWS}, cited)}
    assert recs["wording"].kind == "scanned_only"
    assert recs["wording"].decisions == ("ADR-0115", "ADR-0300")


def test_verdict_records_baseline_red_all_inconclusive():
    runs = _runs()
    runs[0] = _run("baseline", None, "release-lookup", 1, "fail")
    recs = verdict_records(runs, _evidence(), {})
    assert [r.label for r in recs] == ["wording", "release-lookup"]
    assert all(r.kind == "inconclusive" for r in recs)


def test_verdict_record_as_dict_is_json_safe():
    import json
    out = json.loads(json.dumps([r.as_dict() for r in verdict_records(*_fakes())]))
    viol = next(r for r in out if r["kind"] == "violates")
    assert viol["failing"] == [[7, "static", D7], [193, "runtime", D193]]
    assert viol["decisions"] == ["ADR-0585"]
