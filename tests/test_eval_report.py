import json
import shutil
from pathlib import Path

from patch_precedent import cli, pins
from patch_precedent.eval.report import render_results_md
from patch_precedent.eval.score import summarise

EV = pins.project_root() / "tests" / "data" / "eval"
GOLDEN = EV / "RESULTS.golden.md"
PROMPT = "You are reviewing a proposed patch ... DIFF CONTENT"
C1_CHECKS = [
    "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)",
    "no case made a GitHub API request (ADR-0585)",
    "token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)",
]
META = {"date": "2026-11-27T10:00:00+00:00", "claude_version": "2.1.0 (Claude Code)",
        "upstream_sha": "149adbb71aa163c5711d79edb6162140bf2671a7", "repeats": 1,
        "arms": ["baseline", "graph"], "cases": ["C1", "C4"]}


def _argv(arm):
    tools = ["Read", "Grep", "Glob"] + (["mcp__precedent__precedent_for_patch"] if arm == "graph" else [])
    return ["claude", "-p", PROMPT, "--restricted", "--mcp-config", f"/x/mcp-{arm}.json",
            "--allowedTools", *tools, "--model", "sonnet"]


def _wrapped(final, ev_extra=(), turns=5, cost=0.25):
    def a(text):
        return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
    events = [a("Checking ADR-0585 now"), *ev_extra,
              {"type": "result", "result": "done\n" + json.dumps(final), "num_turns": turns,
               "total_cost_usd": cost}]
    return "\n".join(json.dumps({"t_ms": 1500 * (i + 1), "event": e})
                     for i, e in enumerate(events)) + "\n"


def _tool_result():
    payload = {"files": [{"decisions": [{"checks": [
        {"name": C1_CHECKS[0], "observed": "not ok"}, {"name": C1_CHECKS[1], "observed": "not ok"},
        {"name": C1_CHECKS[2], "observed": "ok"}]}]}], "changed_files": ["distribution/install.sh"]}
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t", "content": json.dumps(payload)}]}}


def make_results(root: Path) -> Path:
    (root / "transcripts").mkdir(parents=True)
    (root / "meta.json").write_text(json.dumps(META))
    c1_final = {"verdict": "violates", "decisions": ["ADR-0585"], "checks": C1_CHECKS,
                "check_outcomes": {C1_CHECKS[0]: "fails", C1_CHECKS[1]: "fails",
                                   C1_CHECKS[2]: "passes"}}
    rows = []

    def add(case, arm, k, text, error=None, turns=5, cost=0.25):
        rel = f"transcripts/{case}-{arm}-r{k}.jsonl"
        (root / rel).write_text(text)
        rows.append({"case": case, "arm": arm, "repeat": k, "error": error, "model": "claude-sonnet-5-5",
                     "num_turns": turns, "total_cost_usd": cost, "argv": _argv(arm),
                     "transcript": rel, "claude_version": META["claude_version"]})

    add("C1", "graph", 1, _wrapped(c1_final, [_tool_result()]))
    add("C1", "baseline", 1, _wrapped(c1_final, turns=7, cost=0.4), turns=7, cost=0.4)
    shutil.copy2(EV / "spike-run.jsonl", root / "transcripts" / "C4-baseline-r1.jsonl")
    rows.append({"case": "C4", "arm": "baseline", "repeat": 1, "error": None,
                 "model": "claude-sonnet-5-5", "num_turns": 6, "total_cost_usd": 0.0307462,
                 "argv": _argv("baseline"), "transcript": "transcripts/C4-baseline-r1.jsonl"})
    (root / "transcripts" / "C4-graph-r1.jsonl").write_text(
        _wrapped({"verdict": "consistent", "decisions": [], "checks": [], "check_outcomes": {}}))
    rows.append({"case": "C4", "arm": "graph", "repeat": 1, "error": "exit code 1",
                 "model": "claude-sonnet-5-5", "num_turns": 3, "total_cost_usd": 0.1,
                 "argv": _argv("graph"), "transcript": "transcripts/C4-graph-r1.jsonl"})
    (root / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return root


def _render(tmp_path):
    root = make_results(tmp_path / "res")
    assert cli.main(["eval", "score", "--results", str(root)]) == 0
    assert cli.main(["eval", "report", "--results", str(root)]) == 0
    return root, (root / "RESULTS.md").read_bytes()


def test_cli_score_and_report(tmp_path):
    root, md = _render(tmp_path)
    scored = [json.loads(x) for x in (root / "scored.jsonl").read_text().splitlines()]
    assert len(scored) == 4
    results = json.loads((root / "results.json").read_text())
    assert results["arms"]["graph"]["n"] == 1 and len(results["excluded"]) == 1
    text = md.decode()
    # graph arm's claims are all supported; baseline's are not
    assert results["arms"]["graph"]["unsupported_total"] == 0
    assert results["arms"]["baseline"]["unsupported_total"] == 3
    assert "<prompt from eval/prompt.md>" in text and PROMPT not in text
    assert "exit code 1" in text


def test_report_is_deterministic_and_matches_golden(tmp_path):
    root, md = _render(tmp_path)
    assert cli.main(["eval", "report", "--results", str(root)]) == 0
    assert (root / "RESULTS.md").read_bytes() == md
    scored = [json.loads(x) for x in (root / "scored.jsonl").read_text().splitlines()]
    meta = json.loads((root / "meta.json").read_text())
    a = render_results_md(summarise(scored), scored, meta)
    b = render_results_md(summarise(list(reversed(scored))), list(reversed(scored)), meta)
    assert a == b == md.decode()
    if not GOLDEN.exists():  # first run only: review the file before committing it
        GOLDEN.write_bytes(md)
    assert md == GOLDEN.read_bytes()


def test_report_sections_and_no_verdict_language(tmp_path):
    _, md = _render(tmp_path)
    text = md.decode()
    for heading in ("# ", "## Headline", "## Per case", "## Every run", "## Excluded runs",
                    "## Method", "## Commands", "## Limitations"):
        assert heading in text
    assert "claude-sonnet-5-5" in text and "2.1.0" in text and "2026-11-27" in text
    assert META["upstream_sha"] in text
    for word in ("wins", "outperform", "better than", "superior"):
        assert word not in text.lower()


def test_report_no_excluded_says_none(tmp_path):
    root = make_results(tmp_path / "res")
    rows = [json.loads(x) for x in (root / "runs.jsonl").read_text().splitlines()]
    for r in rows:
        r["error"] = None
    (root / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    cli.main(["eval", "score", "--results", str(root)])
    cli.main(["eval", "report", "--results", str(root)])
    text = (root / "RESULTS.md").read_text()
    assert "## Excluded runs\n\nnone\n" in text


def test_default_results_dir_is_newest(tmp_path, monkeypatch):
    base = tmp_path / "eval" / "results"
    make_results(base / "20260101T000000Z")
    newest = make_results(base / "20260202T000000Z")
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    assert cli.main(["eval", "score"]) == 0
    assert (newest / "scored.jsonl").exists()
    assert not (base / "20260101T000000Z" / "scored.jsonl").exists()


def test_missing_results_dir_is_a_clean_error(tmp_path, capsys):
    assert cli.main(["eval", "score", "--results", str(tmp_path / "nope")]) == 2
    assert "runs.jsonl" in capsys.readouterr().err
    assert cli.main(["eval", "report", "--results", str(tmp_path)]) == 2
