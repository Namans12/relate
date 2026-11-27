import json
import shutil
from pathlib import Path

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.eval.cases import load_cases
from patch_precedent.eval.score import (error_class, load_events, norm, parse_final, score_row,
                                        score_run, summarise)
from patch_precedent.evidence import precedent_for_patch
from patch_precedent.harness import RunResult
from patch_precedent.replay import record_runs
from patch_precedent.tap import parse_tap

ROOT = pins.project_root()
DATA = ROOT / "tests" / "data"
EV = DATA / "eval"
CASES = {c.id: c for c in load_cases()}
CHECKS = {
    "C1": list(CASES["C1"].check_outcomes),
    "C4": list(CASES["C4"].check_outcomes),
}


def _result(text, turns=3, cost=0.5):
    return {"type": "result", "subtype": "success", "result": text, "num_turns": turns,
            "total_cost_usd": cost}


def _asst(text=None, tool_input=None):
    blocks = []
    if text is not None:
        blocks.append({"type": "text", "text": text})
    if tool_input is not None:
        blocks.append({"type": "tool_use", "id": "t1", "name": "Grep", "input": tool_input})
    return {"type": "assistant", "message": {"content": blocks}}


def _tool_result(payload, as_list=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    content = [{"type": "text", "text": text}] if as_list else text
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": content}]}}


def _wrap(events, step=1000):
    return [{"t_ms": (i + 1) * step, "event": e} for i, e in enumerate(events)]


def _final_line(**kw):
    base = {"verdict": "violates", "decisions": ["ADR-0585"], "checks": [], "check_outcomes": {}}
    base.update(kw)
    return json.dumps(base)


def test_norm_collapses_whitespace():
    assert norm("  a \t b\n c ") == "a b c"


def test_parse_final_variants():
    assert parse_final('prose\n{"verdict": "violates"}') == {"verdict": "violates"}
    assert parse_final('{"a": 1}\nthanks!\nbye') == {"a": 1}  # prose after: last JSON object wins
    assert parse_final('x\n```json\n{"a": 2}\n```') == {"a": 2}
    assert parse_final('{"a": 1}\n{"b": 2}') == {"b": 2}
    assert parse_final('[1, 2]\nno json') is None
    assert parse_final("") is None and parse_final("just words") is None


def test_load_events_three_formats(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join([
        json.dumps({"t_ms": 5, "event": {"type": "system"}}),
        json.dumps({"t_ms": 6, "raw": "garbage"}),
        json.dumps({"type": "result", "result": "x"}),
        "not json at all",
        ""]))
    ev = load_events(p)
    assert [e["t_ms"] for e in ev] == [5, None]
    assert [e["event"]["type"] for e in ev] == ["system", "result"]
    assert load_events(tmp_path / "missing.jsonl") == []


def test_real_spike_c4_baseline():
    ev = load_events(EV / "spike-run.jsonl")
    final = parse_final(next(e["event"]["result"] for e in ev if e["event"]["type"] == "result"))
    s = score_run(CASES["C4"], ev, final)
    assert s["parse_error"] is False
    assert s["verdict_correct"] is True
    assert s["decisions_precision"] == 1.0 and s["decisions_recall"] == 1.0
    assert s["decisions_exact"] is True
    assert s["checks_recall"] == 0.5  # lists 1 of the 2 linked checks
    assert s["outcome_accuracy"] is None  # final has no check_outcomes
    assert s["unsupported_claims"] == 0
    assert s["time_to_first_correct_citation_ms"] is None  # bare format: no t_ms
    assert s["turns"] == 6 and abs(s["cost_usd"] - 0.0307462) < 1e-9


def test_real_spike_relate_c1():
    ev = load_events(EV / "spike-run-relate-c1.jsonl")
    final = parse_final(next(e["event"]["result"] for e in ev if e["event"]["type"] == "result"))
    s = score_run(CASES["C1"], ev, final)
    assert s["verdict_correct"] is True and s["decisions_exact"] is True
    assert abs(s["checks_recall"] - 2 / 3) < 1e-9
    assert s["unsupported_claims"] == 0 and s["turns"] == 7
    assert s["time_to_first_correct_citation_ms"] is None


def test_wrapped_citation_time():
    ev = _wrap([_asst(text="looking around"), _asst(tool_input={"pattern": "ADR-0585"}),
                _asst(text="ADR-0585 applies"), _result(_final_line())])
    s = score_run(CASES["C1"], ev, parse_final(_final_line()))
    assert s["time_to_first_correct_citation_ms"] == 3000  # tool_use input (2000) never counts
    ev = _wrap([_tool_result("ADR-0585 in a tool result"), _asst(text="no cite")])
    assert score_run(CASES["C1"], ev, parse_final(_final_line()))[
        "time_to_first_correct_citation_ms"] is None


def test_c4_graph_tool_input_with_patch_does_not_count():
    patch = CASES["C4"].diff_text()
    assert "ADR-0580" in patch
    ev = [{"t_ms": 900, "event": _asst(tool_input={"diff": patch})},
          {"t_ms": 20000, "event": _asst(text="This violates ADR-0580.")}]
    final = {"verdict": "violates", "decisions": ["ADR-0580"], "checks": [], "check_outcomes": {}}
    assert score_run(CASES["C4"], ev, final)["time_to_first_correct_citation_ms"] == 20000
    ev = [{"t_ms": 900, "event": _asst(tool_input={"diff": patch})}]
    assert score_run(CASES["C4"], ev, final)["time_to_first_correct_citation_ms"] is None


def test_error_class_mapping():
    assert error_class(None) is None and error_class("") is None
    for e in ("spawn failed: OSError()", "no init event: tool set not verified",
              "graph arm init lacks mcp__precedent__precedent_for_patch",
              "mcp server precedent status failed", "baseline arm has MCP tools ['mcp__x']",
              "exit code 1; no init event: tool set not verified"):
        assert error_class(e) == "infrastructure", e
    for e in ("exit code 1", "timed out after 900s; process group killed",
              "out-of-worktree file access", "worktree not clean after run: 'M x'",
              "something new and unknown"):
        assert error_class(e) == "agent", e


def test_agent_failure_scored_as_failed_but_infra_excluded(tmp_path):
    (tmp_path / "t").mkdir()
    ev = _wrap([_result(_final_line(), turns=9, cost=1.25)])
    (tmp_path / "t" / "a.jsonl").write_text("\n".join(json.dumps(e) for e in ev))
    base = {"case": "C1", "arm": "graph", "repeat": 1, "transcript": "t/a.jsonl",
            "num_turns": 9, "total_cost_usd": 1.25}
    agent = score_row(CASES["C1"], dict(base, error="exit code 1"), tmp_path)
    assert agent["error_class"] == "agent" and agent["verdict_correct"] is False
    assert agent["decisions_exact"] is None and agent["unsupported_claims"] is None
    assert agent["turns"] == 9 and agent["cost_usd"] == 1.25 and agent["outcome_linked"] == 3
    infra = score_row(CASES["C1"], dict(base, error="no init event: tool set not verified"), tmp_path)
    sm = summarise([agent, infra])
    assert sm["arms"]["graph"]["n"] == 1 and sm["arms"]["graph"]["verdict_k"] == 0
    assert sm["arms"]["graph"]["cost_total"] == 1.25
    assert [x["class"] for x in sm["excluded"]] == ["infrastructure"]


def test_c6_citation_null():
    ev = _wrap([_asst(text="ADR-0580 ADR-0585 mentioned anyway")])
    final = {"verdict": "no_decision", "decisions": [], "checks": [], "check_outcomes": {}}
    s = score_run(CASES["C6"], ev, final)
    assert s["time_to_first_correct_citation_ms"] is None
    assert s["verdict_correct"] is True and s["decisions_exact"] is True
    assert s["decisions_precision"] is None and s["decisions_recall"] is None
    assert s["checks_recall"] is None and s["outcome_accuracy"] is None


def test_baseline_claims_are_unsupported():
    c = CASES["C1"]
    names = CHECKS["C1"]
    final = {"verdict": "violates", "decisions": ["ADR-0585"], "checks": names[:2],
             "check_outcomes": {names[0]: "fails", names[1]: "fails", names[2]: "unknown"}}
    # a tool result that merely mentions the text is not support
    ev = _wrap([_tool_result(f"grep hit: {names[0]} \"observed\": \"not ok\""), _result("x")])
    s = score_run(c, ev, final)
    assert s["unsupported_claims"] == 2
    assert s["outcome_marked"] == 2 and s["outcome_correct"] == 2  # ground truth: both fail
    assert s["outcome_accuracy"] == 1.0


def test_unknown_not_counted_and_whitespace_normalised():
    names = CHECKS["C1"]
    final = {"verdict": "violates", "decisions": [], "checks": [],
             "check_outcomes": {names[0]: "unknown", "  " + names[1].replace(" ", "  ") + " ": "passes"}}
    s = score_run(CASES["C1"], _wrap([]), final)
    assert s["unsupported_claims"] == 1
    assert s["outcome_marked"] == 1 and s["outcome_correct"] == 0  # truth for names[1] is fails


def _build_replays(root):
    ts = "20260101T000000Z"
    for scn, cmd, tapdir, items in (
        ("installer", "sh scripts/tests/test_install_sh.sh", DATA,
         [("release-lookup", 1), ("token-header", 1), ("wording", 0)]),
        ("release", "sh scripts/tests/test_release_advance.sh", DATA / "release",
         [("always-rotate", 1), ("docs-only", 0), ("wording", 0)]),
    ):
        d = root / ts / scn
        d.mkdir(parents=True)
        shutil.copy2(pins.STORE_PATH, d / "replay.rl")
        runs = [RunResult(n, read_patch(ROOT / "fixtures" / scn / f"{n}.patch"), "base", cmd, c,
                          parse_tap((tapdir / f"{n}.tap").read_text()), Path("/tmp/x.log"),
                          "pass" if c == 0 else "fail", None) for n, c in items]
        record_runs(d / "replay.rl", runs)


def test_graph_transcript_with_real_tool_result(tmp_path):
    _build_replays(tmp_path)
    diff = CASES["C1"].diff_text()
    res = precedent_for_patch(diff, pins.STORE_PATH, tmp_path)
    names = CHECKS["C1"]
    final = {"verdict": "violates", "decisions": ["ADR-0585"], "checks": names,
             "check_outcomes": dict(CASES["C1"].check_outcomes)}
    for as_list in (False, True):
        ev = _wrap([_asst(tool_input={"diff": "x"}), _tool_result(res, as_list=as_list),
                    _asst(text="done")])
        s = score_run(CASES["C1"], ev, final)
        assert s["unsupported_claims"] == 0
        assert s["outcome_accuracy"] == 1.0 and s["checks_recall"] == 1.0
    # no replay: every check is "not observed", so claiming fails/passes is unsupported
    res0 = precedent_for_patch(diff, pins.STORE_PATH, tmp_path / "none")
    ev = _wrap([_tool_result(res0)])
    assert score_run(CASES["C1"], ev, final)["unsupported_claims"] == 3


def test_not_observed_claim_is_unsupported():
    names = CHECKS["C4"]
    payload = {"files": [{"decisions": [{"checks": [
        {"name": names[0], "observed": "not ok"},
        {"name": names[1], "observed": "not observed"}]}]}], "changed_files": ["x"]}
    final = {"verdict": "violates", "decisions": ["ADR-0580"], "checks": names,
             "check_outcomes": {names[0]: "fails", names[1]: "fails"}}
    s = score_run(CASES["C4"], _wrap([_tool_result(payload)]), final)
    assert s["unsupported_claims"] == 1


def test_parse_error():
    s = score_run(CASES["C1"], _wrap([_asst(text="no json")]), None)
    assert s["parse_error"] is True and s["verdict_correct"] is False
    for k in ("decisions_exact", "decisions_precision", "decisions_recall", "checks_recall",
              "outcome_accuracy", "unsupported_claims", "time_to_first_correct_citation_ms"):
        assert s[k] is None


def test_final_fallback_to_last_assistant_text(tmp_path):
    d = tmp_path
    (d / "transcripts").mkdir()
    ev = _wrap([_asst(text="thinking"), _asst(text="Verdict.\n" + _final_line())])
    (d / "transcripts" / "C1-baseline-r1.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ev))
    row = {"case": "C1", "arm": "baseline", "repeat": 1, "error": None, "num_turns": 4,
           "total_cost_usd": 0.1, "model": "m", "argv": ["claude"],
           "transcript": "transcripts/C1-baseline-r1.jsonl"}
    s = score_row(CASES["C1"], row, d)
    assert s["parse_error"] is False and s["verdict_correct"] is True
    assert s["turns"] == 4 and s["cost_usd"] == 0.1 and s["arm"] == "baseline"


def test_row_falls_back_to_result_event_and_missing_transcript(tmp_path):
    (tmp_path / "transcripts").mkdir()
    ev = _wrap([_result(_final_line(), turns=9, cost=1.25)])
    (tmp_path / "transcripts" / "a.jsonl").write_text("\n".join(json.dumps(e) for e in ev))
    row = {"case": "C1", "arm": "graph", "repeat": 2, "error": None, "transcript": "transcripts/a.jsonl"}
    s = score_row(CASES["C1"], row, tmp_path)
    assert s["turns"] == 9 and s["cost_usd"] == 1.25
    gone = dict(row, transcript="transcripts/nope.jsonl")
    assert score_row(CASES["C1"], gone, tmp_path)["parse_error"] is True


def _scored(case, arm, repeat, **kw):
    base = {"case": case, "arm": arm, "repeat": repeat, "error": None, "parse_error": False,
            "verdict": "violates", "verdict_correct": True, "decisions_exact": True,
            "checks_recall": 1.0, "outcome_marked": 2, "outcome_correct": 1,
            "unsupported_claims": 2, "time_to_first_correct_citation_ms": 4000,
            "turns": 6, "cost_usd": 0.5}
    base.update(kw)
    return base


def test_errored_run_excluded_and_parse_error_counted():
    runs = [_scored("C1", "baseline", 1),
            _scored("C1", "baseline", 2, time_to_first_correct_citation_ms=8000, turns=8),
            _scored("C1", "baseline", 3, error="spawn failed: boom", cost_usd=9.0),
            _scored("C2", "baseline", 1, parse_error=True, verdict=None, verdict_correct=False,
                    decisions_exact=None, checks_recall=None, outcome_marked=None,
                    outcome_correct=None, unsupported_claims=None,
                    time_to_first_correct_citation_ms=None),
            _scored("C1", "graph", 1, unsupported_claims=0)]
    sm = summarise(runs)
    b = sm["arms"]["baseline"]
    assert b["n"] == 3 and b["verdict_k"] == 2 and b["decisions_exact_k"] == 2
    assert b["unsupported_total"] == 4 and b["unsupported_n"] == 2 and b["unsupported_mean"] == 2.0
    assert b["checks_recall_n"] == 2 and b["checks_recall_mean"] == 1.0
    assert b["outcome_marked"] == 4 and b["outcome_correct"] == 2 and b["outcome_accuracy"] == 0.5
    assert b["citation_n"] == 2 and b["citation_median_s"] == 6.0
    assert abs(b["turns_mean"] - 20 / 3) < 1e-9 and b["turns_n"] == 3 and b["cost_total"] == 1.5
    assert sm["arms"]["graph"]["n"] == 1
    assert sm["excluded"] == [{"case": "C1", "arm": "baseline", "repeat": 3,
                               "error": "spawn failed: boom", "class": "infrastructure",
                               "cost_usd": 9.0}]
    assert sm["cases"]["C1"]["baseline"]["n"] == 2 and sm["cases"]["C2"]["baseline"]["n"] == 1


def _call(diff="x", name="mcp__precedent__precedent_for_patch", tid="t9"):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": {"diff": diff}}]}}


def _reply(payload, tid="t9"):
    ev = _tool_result(payload)
    ev["message"]["content"][0]["tool_use_id"] = tid
    return ev


def test_catching_checks_recall():
    c1, c2, c4 = CASES["C1"], CASES["C2"], CASES["C4"]
    fails = [k for k, v in c1.check_outcomes.items() if v == "fails"]
    assert len(fails) == 2
    only_pass = [k for k, v in c1.check_outcomes.items() if v == "passes"]
    ev = _wrap([_asst(text="x")])
    # all three linked checks listed: both recalls are 1.0
    s = score_run(c1, ev, json.loads(_final_line(checks=list(c1.check_outcomes))))
    assert s["checks_recall"] == 1.0 and s["catching_checks_recall"] == 1.0
    # only the passing check listed: checks recall 1/3, catching recall 0
    s = score_run(c1, ev, json.loads(_final_line(checks=only_pass)))
    assert s["checks_recall"] == 1 / 3 and s["catching_checks_recall"] == 0.0
    # one of two failing checks, whitespace-mangled name: catching 0.5
    s = score_run(c1, ev, json.loads(_final_line(checks=["  " + fails[0].replace(" ", "  ")])))
    assert s["catching_checks_recall"] == 0.5
    # a case with no check expected to fail is null even with every check listed
    assert score_run(c2, ev, json.loads(_final_line(checks=list(c2.check_outcomes))))[
        "catching_checks_recall"] is None
    assert score_run(CASES["C6"], ev, json.loads(_final_line()))["catching_checks_recall"] is None
    # C4 has one failing and one passing check
    s = score_run(c4, ev, json.loads(_final_line(checks=[k for k, v in c4.check_outcomes.items()
                                                         if v == "fails"])))
    assert s["catching_checks_recall"] == 1.0 and s["checks_recall"] == 0.5
    # parse error: null
    assert score_run(c1, ev, None)["catching_checks_recall"] is None


def test_tool_replay_found_true_false_null():
    from patch_precedent.eval.score import tool_replay_found
    found = {"files": [], "replay": {"scenario": "installer", "run": "r", "label": "l"}}
    missed = {"files": [], "replay": None}
    assert tool_replay_found(_wrap([_asst(text="x")])) is None  # no tool call
    assert tool_replay_found(_wrap([_asst(tool_input={"pattern": "a"})])) is None  # other tool
    assert tool_replay_found(_wrap([_call(), _reply(found)])) is True
    assert tool_replay_found(_wrap([_call(), _reply(missed)])) is False
    # list-shaped content works
    ev = _reply(found)
    ev["message"]["content"][0]["content"] = [{"type": "text", "text": json.dumps(found)}]
    assert tool_replay_found(_wrap([_call(), ev])) is True
    # the LAST call decides
    assert tool_replay_found(_wrap([_call(tid="a"), _reply(missed, "a"),
                                    _call(tid="b"), _reply(found, "b")])) is True
    assert tool_replay_found(_wrap([_call(tid="a"), _reply(found, "a"),
                                    _call(tid="b"), _reply(missed, "b")])) is False
    # a call with no usable result counts as not found
    assert tool_replay_found(_wrap([_call()])) is False
    assert tool_replay_found(_wrap([_call(), _reply("not json")])) is False
    # score_run records it, including on a parse error; baseline-style runs get null
    s = score_run(CASES["C1"], _wrap([_call(), _reply(missed)]), json.loads(_final_line()))
    assert s["tool_replay_found"] is False
    assert score_run(CASES["C1"], _wrap([_call(), _reply(found)]), None)["tool_replay_found"] is True
    assert score_run(CASES["C1"], _wrap([_asst(text="x")]),
                     json.loads(_final_line()))["tool_replay_found"] is None


def test_summarise_new_aggregates():
    rows = [
        _scored("C1", "graph", 1, catching_checks_recall=1.0, decisions_recall=1.0,
                tool_replay_found=True),
        _scored("C1", "graph", 2, catching_checks_recall=0.5, decisions_recall=1.0,
                tool_replay_found=False),
        _scored("C2", "graph", 1, catching_checks_recall=None, decisions_recall=0.0,
                tool_replay_found=None),
        _scored("C1", "baseline", 1, catching_checks_recall=1.0, decisions_recall=0.0,
                tool_replay_found=None),
    ]
    m = summarise(rows)["arms"]
    assert m["graph"]["catching_recall_mean"] == 0.75 and m["graph"]["catching_recall_n"] == 2
    assert m["graph"]["decisions_recall_n"] == 3
    assert m["graph"]["replay_found_k"] == 1 and m["graph"]["replay_found_n"] == 2
    assert m["baseline"]["replay_found_n"] == 0 and m["baseline"]["catching_recall_n"] == 1
