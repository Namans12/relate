import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.eval import runner
from patch_precedent.eval.cases import load_cases, render_prompt
from patch_precedent.eval.runner import EvalRefused, build_command, run_eval, run_order
from patch_precedent.store import open_readonly
from test_evidence import _make_replays

SPIKE = Path(__file__).parent / "data" / "eval" / "spike-run.jsonl"
GRAPH_TOOL = "mcp__precedent__precedent_for_patch"
CASES = load_cases()


def _case(cid):
    return next(c for c in CASES if c.id == cid)


@pytest.fixture
def worktree(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=wt, check=True)
    (wt / "a.txt").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=wt, check=True)
    return wt


@pytest.fixture
def runs_root(tmp_path):
    root = tmp_path / "runs"
    _make_replays(root)
    return root


class FakeSpawn:
    """Replays a recorded spike transcript; never runs claude."""

    def __init__(self, dirty=False, exit_code=0, timed_out=False, extra=("not json at all",)):
        self.calls = []
        self.dirty, self.exit_code, self.timed_out, self.extra = dirty, exit_code, timed_out, extra

    def __call__(self, argv, cwd, on_line):
        self.calls.append((argv, cwd))
        for line in self.extra:
            on_line(line)
        for line in SPIKE.read_text().splitlines():
            on_line(line)
        if self.dirty:
            (Path(cwd) / "a.txt").write_text("changed\n")
        return self.exit_code, self.timed_out


def _run(tmp_path, worktree, runs_root, spawn, cases=("C1",), arms=("baseline", "graph"),
         repeats=1):
    out = tmp_path / "out"
    run_eval([_case(c) for c in cases], list(arms), repeats, out, worktree=worktree,
             runs_root=runs_root, spawn=spawn, claude_version="2.1.292")
    return out, [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]


def _paths(tmp_path):
    return {"baseline": tmp_path / "mcp-baseline.json", "graph": tmp_path / "mcp-graph.json"}


def test_arms_differ_only_in_mcp(tmp_path):
    p = _paths(tmp_path)
    prompt = render_prompt("hello {patch}", "diff")
    base = build_command(prompt, "baseline", p["baseline"])
    graph = build_command(prompt, "graph", p["graph"])
    assert base[0] == "claude" and base[1:3] == ["-p", prompt]
    assert len(graph) == len(base) + 1
    # strip the two allowed differences, the rest must be identical
    def strip(argv, cfg, extra):
        out = [a for a in argv if a != extra]
        out[out.index("--mcp-config") + 1] = "<cfg>"
        return out
    assert strip(base, p["baseline"], GRAPH_TOOL) == strip(graph, p["graph"], GRAPH_TOOL)
    assert base[base.index("--mcp-config") + 1] == str(p["baseline"])
    assert graph[graph.index("--mcp-config") + 1] == str(p["graph"])
    assert GRAPH_TOOL in graph and GRAPH_TOOL not in base
    assert base == ["claude", "-p", prompt, "--restricted", "--strict-mcp-config",
                    "--mcp-config", str(p["baseline"]), "--tools", "Read", "Grep", "Glob",
                    "--allowedTools", "Read", "Grep", "Glob", "--model", "sonnet",
                    "--max-turns", "25", "--output-format", "stream-json", "--verbose",
                    "--no-session-persistence"]
    assert graph[graph.index("--allowedTools") + 1:graph.index("--model")] == [
        "Read", "Grep", "Glob", GRAPH_TOOL]
    assert build_command(prompt, "graph", p["graph"], claude_bin="/x/claude")[0] == "/x/claude"


def test_prompt_identical_across_arms(tmp_path, worktree, runs_root):
    spawn = FakeSpawn()
    _run(tmp_path, worktree, runs_root, spawn)
    assert len(spawn.calls) == 2
    (b, _), (g, _) = spawn.calls
    assert b[2] == g[2]
    diff = (pins.project_root() / _case("C1").fixture).read_text()
    assert b[2] == render_prompt((pins.project_root() / "eval" / "prompt.md").read_text(),
                                 diff)
    assert diff.rstrip("\n") in b[2] and "{patch}" not in b[2]


def test_render_prompt_survives_braces_and_whitespace():
    diff = "+\tx = {a} {0} {patch}\r\n+tail \n"
    assert render_prompt("A\n```diff\n{patch}\n```\n", diff) == (
        "A\n```diff\n+\tx = {a} {0} {patch}\r\n+tail \n```\n")  # one trailing newline dropped


def test_prompt_template_shape():
    t = (pins.project_root() / "eval" / "prompt.md").read_text()
    assert t.count("{patch}") == 1
    assert '"check_outcomes": {"<exact test assertion description>": "fails" | "passes" | "unknown", ...}' in t
    assert t.endswith('Say "unknown" for any check whose result you did not observe.\n')


def test_run_order_interleaved():
    cases = ["c1", "c2", "c3"]
    order = run_order(cases, ["baseline", "graph"], 2)
    assert len(order) == 12
    assert [r for r, _, _ in order] == [1] * 6 + [2] * 6  # repeat-major
    assert [c for r, c, _ in order[:6:2]] == cases  # then case order
    first = {(r, c): a for (r, c, a), _ in zip(order[::2], range(6))}
    # neither arm always goes first: alternates with (case index + k) parity
    assert first[(1, "c1")] != first[(1, "c2")] != first[(1, "c3")]
    assert first[(1, "c1")] != first[(2, "c1")]
    for k in (1, 2):
        for c in cases:
            assert sorted(a for r, cc, a in order if r == k and cc == c) == ["baseline", "graph"]
    assert order == run_order(cases, ["baseline", "graph"], 2)  # deterministic
    assert [a for _, _, a in run_order(["x"], ["graph"], 1)] == ["graph"]


def test_refuses_without_replay(tmp_path, worktree):
    spawn = FakeSpawn()
    out = tmp_path / "out"
    with pytest.raises(EvalRefused) as e:
        run_eval([_case("C1")], ["baseline"], 1, out, worktree=worktree,
                 runs_root=tmp_path / "empty", spawn=spawn, claude_version="x")
    assert "uv run patch-precedent demo all" in str(e.value) and "\n" not in str(e.value)
    assert spawn.calls == []
    assert not (out / "runs.jsonl").exists()


def test_transcript_format(tmp_path, worktree, runs_root):
    out, rows = _run(tmp_path, worktree, runs_root, FakeSpawn(), arms=("graph",))
    (row,) = rows
    tpath = out / "transcripts" / "C1-graph-r1.jsonl"
    assert row["transcript"] == "transcripts/C1-graph-r1.jsonl"
    lines = [json.loads(line) for line in tpath.read_text().splitlines()]
    assert lines[0]["raw"] == "not json at all" and set(lines[0]) == {"t_ms", "raw"}
    events = [x for x in lines if "event" in x]
    assert len(events) == len(SPIKE.read_text().splitlines())
    assert all(set(x) in ({"t_ms", "event"}, {"t_ms", "raw"}) and isinstance(x["t_ms"], int)
               for x in lines)
    assert [x["t_ms"] for x in lines] == sorted(x["t_ms"] for x in lines)
    assert events[0]["event"]["subtype"] == "init"
    assert set(row) == {"case", "arm", "repeat", "exit_code", "timed_out", "duration_ms",
                        "num_turns", "total_cost_usd", "model", "claude_version", "argv",
                        "transcript", "error"}
    assert (row["case"], row["arm"], row["repeat"], row["exit_code"], row["timed_out"]) == (
        "C1", "graph", 1, 0, False)
    assert (row["num_turns"], row["model"], row["claude_version"]) == (
        6, "claude-sonnet-5-5", "2.1.292")
    assert row["total_cost_usd"] == pytest.approx(0.0307462)
    assert row["error"] is None
    assert row["argv"][0] == "claude" and "--mcp-config" in row["argv"]


def test_meta_and_configs(tmp_path, worktree, runs_root):
    out, _ = _run(tmp_path, worktree, runs_root, FakeSpawn(), cases=("C1", "C4"))
    meta = json.loads((out / "meta.json").read_text())
    assert meta["claude_version"] == "2.1.292"
    assert meta["upstream_sha"] == pins.UPSTREAM_SHA
    import hashlib
    assert meta["store_sha256"] == hashlib.sha256(pins.STORE_PATH.read_bytes()).hexdigest()
    assert set(meta["replay_runs"]) == {"installer", "release"}
    assert meta["date"]
    assert json.loads((out / "mcp-baseline.json").read_text()) == {"mcpServers": {}}
    g = json.loads((out / "mcp-graph.json").read_text())["mcpServers"]["precedent"]
    assert g["command"] == "uv"
    root = str(pins.project_root())
    assert g["args"] == ["run", "--project", root, "--quiet", "patch-precedent", "mcp",
                         "--store", str(pins.STORE_PATH), "--runs-dir", str(runs_root.resolve())]


def test_worktree_clean_check_fails_run(tmp_path, worktree, runs_root):
    out, rows = _run(tmp_path, worktree, runs_root, FakeSpawn(dirty=True), arms=("baseline",),
                     repeats=2)
    assert len(rows) == 2
    assert rows[0]["error"] and "worktree" in rows[0]["error"]
    # the runner restores a clean worktree so later runs stay comparable
    assert subprocess.run(["git", "status", "--porcelain"], cwd=worktree, capture_output=True,
                          text=True).stdout == ""
    assert (worktree / "a.txt").read_text() == "x\n"


def test_failures_recorded_and_eval_continues(tmp_path, worktree, runs_root):
    out, rows = _run(tmp_path, worktree, runs_root,
                     FakeSpawn(exit_code=1, timed_out=True), arms=("baseline",), repeats=2)
    assert [r["timed_out"] for r in rows] == [True, True]
    assert all(r["error"] for r in rows) and rows[0]["exit_code"] == 1

    def boom(argv, cwd, on_line):
        raise OSError("no claude")

    out2 = tmp_path / "out2"
    run_eval([_case("C1")], ["baseline"], 1, out2, worktree=worktree, runs_root=runs_root,
             spawn=boom, claude_version="x")
    (row,) = [json.loads(line) for line in (out2 / "runs.jsonl").read_text().splitlines()]
    assert "no claude" in row["error"] and row["num_turns"] is None and row["model"] is None


def test_cases_match_store_checks():
    assert [c.id for c in CASES] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    conn = open_readonly(pins.STORE_PATH)
    try:
        names = {r.data()["n"] for r in conn.execute("MATCH (k:Check) RETURN k.name AS n")}
    finally:
        conn.close()
    raw = tomllib.loads((pins.project_root() / "eval" / "cases.toml").read_text())["cases"]
    assert len(raw) == 6
    for c in CASES:
        assert set(c.check_outcomes) <= names, c.id
        assert set(c.check_outcomes.values()) <= {"fails", "passes"}
        assert (pins.project_root() / c.fixture).is_file()
    c6 = _case("C6")
    assert c6.decisions == () and c6.check_outcomes == {} and c6.verdict == "no_decision"
    assert {c.verdict for c in CASES} == {"violates", "consistent", "no_decision"}
    assert len(_case("C1").check_outcomes) == 3 and len(_case("C4").check_outcomes) == 2


def test_cases_agree_with_fixture_expectations():
    """Failing checks in cases.toml match the harness acceptance criteria per fixture sha."""
    import hashlib
    for c in CASES:
        exp = tomllib.loads((pins.project_root() / "fixtures" / c.scenario /
                             "expectations.toml").read_text())
        sha = hashlib.sha256((pins.project_root() / c.fixture).read_bytes()).hexdigest()
        (patch,) = [p for p in exp["patch"] if p["sha256"] == sha]
        failing = {n for n, o in c.check_outcomes.items() if o == "fails"}
        assert failing == set(patch["failing"]), c.id


def test_run_eval_exports(tmp_path):
    assert runner.RUN_TIMEOUT_S == 900
