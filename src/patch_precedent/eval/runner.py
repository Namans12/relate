"""Evaluation runner: headless Claude Code reviews each patch with and without the graph tool.

Fairness: both arms get a byte-identical prompt and identical flags; only the --mcp-config
file (and the MCP tool name in --allowedTools) differs. Nothing here runs in tests against
a real `claude`: `spawn` is an injectable seam.
"""
import contextlib
import datetime
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Iterator, Sequence

from .. import pins
from ..evidence import precedent_for_patch
from ..upstream import clean_checkout
from .cases import Case, prompt_path, render_prompt

ARMS = ("baseline", "graph")
GRAPH_TOOL = "mcp__precedent__precedent_for_patch"
BASE_TOOLS = ("Read", "Grep", "Glob")
RUN_TIMEOUT_S = 900
MAX_TURNS = "25"

# spawn(argv, cwd, on_line, on_err=None) -> (exit_code, timed_out)
Spawn = Callable[..., "tuple[int, bool]"]


class EvalRefused(RuntimeError):
    """The evaluation cannot start; the message is one line for the user."""


def run_order(cases: Sequence, arms: Sequence[str], repeats: int) -> list[tuple[int, object, str]]:
    """(repeat, case, arm): repeat-major, then case order; arm order rotates by (case index + k)."""
    out = []
    for k in range(1, repeats + 1):
        for i, case in enumerate(cases):
            shift = (i + k) % len(arms)
            for arm in (*arms[shift:], *arms[:shift]):
                out.append((k, case, arm))
    return out


def build_command(prompt: str, arm: str, mcp_config: Path, claude_bin: str = "claude") -> list[str]:
    tools = [*BASE_TOOLS, GRAPH_TOOL] if arm == "graph" else list(BASE_TOOLS)
    return [claude_bin, "-p", prompt, "--restricted", "--strict-mcp-config",
            "--mcp-config", str(mcp_config), "--tools", *BASE_TOOLS,
            "--allowedTools", *tools, "--model", "sonnet", "--max-turns", MAX_TURNS,
            "--output-format", "stream-json", "--verbose", "--no-session-persistence"]


def default_spawn(argv: Sequence[str], cwd: Path, on_line: Callable[[str], None],
                  on_err: Callable[[str], None] | None = None) -> tuple[int, bool]:
    """Run argv with stdin from /dev/null in its own process group.

    stdout lines go to on_line; stderr is a separate pipe drained in a thread to on_err
    (discarded when None), so noise can never corrupt the stdout stream.
    """
    proc = subprocess.Popen(
        list(argv), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
        start_new_session=True)
    timed_out = threading.Event()

    def expire() -> None:
        timed_out.set()
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)

    def drain_err() -> None:
        for line in proc.stderr:
            if on_err is not None:
                on_err(line.rstrip("\n"))

    reader = threading.Thread(target=drain_err, daemon=True)
    reader.start()
    timer = threading.Timer(RUN_TIMEOUT_S, expire)
    timer.start()
    try:
        for line in proc.stdout:
            on_line(line.rstrip("\n"))
        proc.wait()
    finally:
        timer.cancel()
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)  # reap stragglers (MCP server children)
        reader.join(timeout=5)
        proc.stdout.close()
        proc.stderr.close()
    return proc.returncode, timed_out.is_set()


@contextlib.contextmanager
def agent_worktree(sha: str = pins.UPSTREAM_SHA) -> Iterator[Path]:
    """Detached clean worktree of the pin in a fresh temp dir OUTSIDE the project.

    Restricted file tools are confined to cwd, so agents cannot read our own evidence.
    """
    tmp = Path(tempfile.mkdtemp(prefix="patch-precedent-agent-")).resolve()
    try:
        with clean_checkout(sha, tmp / "relate") as wt:
            yield wt
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _git_status(wt: Path) -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=wt, check=True,
                          capture_output=True, text=True).stdout


def _restore(wt: Path) -> None:
    subprocess.run(["git", "reset", "--hard", "-q"], cwd=wt, capture_output=True)
    subprocess.run(["git", "clean", "-fdxq"], cwd=wt, capture_output=True)


def _claude_version(claude_bin: str) -> str:
    r = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=60)
    return (r.stdout or r.stderr).strip()


def _outside(wt: Path, value: str) -> bool:
    """True if a tool path argument resolves outside the worktree (relative/empty: inside)."""
    if not value:
        return False
    p = os.path.expanduser(value)
    joined = p if os.path.isabs(p) else os.path.join(wt, p)
    real, root = os.path.realpath(joined), os.path.realpath(wt)
    return os.path.commonpath([real, root]) != root


def _summarise(event: dict, info: dict, wt: Path) -> None:
    if event.get("type") == "system" and event.get("subtype") == "init":
        info["model"] = event.get("model")
        info["init_tools"] = event.get("tools")
        info["mcp_servers"] = [{"name": s.get("name"), "status": s.get("status")}
                               for s in event.get("mcp_servers") or []]
    elif event.get("type") == "result":
        info["num_turns"] = event.get("num_turns")
        info["total_cost_usd"] = event.get("total_cost_usd")
    elif event.get("type") == "assistant":
        content = (event.get("message") or {}).get("content")
        for block in content if isinstance(content, list) else []:
            if not (isinstance(block, dict) and block.get("type") == "tool_use"):
                continue
            args = block.get("input")
            # Grep's pattern is a regex, not a path; only Glob's pattern can carry one.
            keys = ("file_path", "path") + (("pattern",) if block.get("name") == "Glob" else ())
            for key in keys:
                v = args.get(key) if isinstance(args, dict) else None
                if isinstance(v, str) and _outside(wt, v) and v not in info["out_of_worktree"]:
                    info["out_of_worktree"].append(v)


def _tool_integrity_errors(arm: str, info: dict) -> list[str]:
    tools, servers = info["init_tools"], info["mcp_servers"]
    if tools is None:
        return ["no init event: tool set not verified"]
    mcp = [x for x in tools if str(x).startswith("mcp__")]
    if arm == "graph":
        errs = [] if GRAPH_TOOL in tools else [f"graph arm init lacks {GRAPH_TOOL}"]
        errs += [f"mcp server {s['name']} status {s['status']}" for s in servers
                 if s["status"] != "connected"]
        return errs
    return [f"baseline arm has MCP tools {mcp}"] if mcp else []


def _one_run(argv, wt, tpath: Path, errpath: Path, arm: str, spawn: Spawn) -> dict:
    info = {"model": None, "num_turns": None, "total_cost_usd": None, "init_tools": None,
            "mcp_servers": [], "out_of_worktree": []}
    errors: list[str] = []
    start = time.monotonic()
    exit_code, timed_out = None, False
    with open(tpath, "w", encoding="utf-8") as tf, open(errpath, "w", encoding="utf-8") as ef:
        def on_line(line: str) -> None:
            if not line.strip():
                return
            t_ms = int((time.monotonic() - start) * 1000)
            try:
                event = json.loads(line)
            except ValueError:
                event = None
            if isinstance(event, dict):
                _summarise(event, info, wt)
                rec = {"t_ms": t_ms, "event": event}
            else:
                rec = {"t_ms": t_ms, "raw": line}
            tf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            tf.flush()

        def on_err(line: str) -> None:
            ef.write(line + "\n")
            ef.flush()

        try:
            exit_code, timed_out = spawn(argv, wt, on_line, on_err=on_err)
        except Exception as exc:  # a failed run is recorded; the evaluation continues
            errors.append(f"spawn failed: {exc!r}")
    duration_ms = int((time.monotonic() - start) * 1000)
    if timed_out:
        errors.append(f"timed out after {RUN_TIMEOUT_S}s; process group killed")
    elif exit_code not in (0, None):
        errors.append(f"exit code {exit_code}")
    if not any(e.startswith("spawn failed") for e in errors):
        errors += _tool_integrity_errors(arm, info)
    if info["out_of_worktree"]:
        errors.append("out-of-worktree file access")
    dirty = _git_status(wt)
    if dirty.strip():
        errors.append(f"worktree not clean after run: {dirty.strip()[:200]!r}")
        _restore(wt)
    return {"exit_code": exit_code, "timed_out": timed_out, "duration_ms": duration_ms,
            **info, "error": "; ".join(errors) or None}


def run_eval(cases: Sequence[Case], arms: Sequence[str], repeats: int, out_dir: Path, *,
             runs_root: Path, worktree: Path | None = None, store: Path | None = None,
             claude_bin: str = "claude", spawn: Spawn | None = None,
             claude_version: str | None = None) -> Path:
    """Run every case x arm x repeat sequentially; returns out_dir (see runs.jsonl, meta.json)."""
    store = Path(store or pins.STORE_PATH).resolve()
    runs_root = Path(runs_root).resolve()
    out_dir = Path(out_dir).resolve()
    arms = list(arms)
    bad = [a for a in arms if a not in ARMS]
    if bad or not arms:
        raise EvalRefused(f"unknown arm(s) {bad or arms}; choose from {', '.join(ARMS)}")

    template = prompt_path().read_text(encoding="utf-8")
    prompts, replay_runs = {}, {}
    for case in cases:
        diff = case.diff_text()
        res = precedent_for_patch(diff, store, runs_root)
        if res["replay"] is None:
            raise EvalRefused(
                f"no replay evidence for {case.id} ({case.fixture}) under {runs_root}; "
                "run `uv run patch-precedent demo all` first")
        replay_runs[res["replay"]["scenario"]] = res["replay"]["run"]
        prompts[case.id] = render_prompt(template, diff)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transcripts").mkdir(exist_ok=True)
    cfgs = {"baseline": out_dir / "mcp-baseline.json", "graph": out_dir / "mcp-graph.json"}
    cfgs["baseline"].write_text(json.dumps({"mcpServers": {}}, indent=2) + "\n")
    cfgs["graph"].write_text(json.dumps({"mcpServers": {"precedent": {
        "command": "uv", "args": ["run", "--project", str(pins.project_root()), "--quiet",
                                  "patch-precedent", "mcp", "--store", str(store),
                                  "--runs-dir", str(runs_root)]}}}, indent=2) + "\n")
    version = claude_version if claude_version is not None else _claude_version(claude_bin)
    (out_dir / "meta.json").write_text(json.dumps({
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "claude_version": version, "upstream_sha": pins.UPSTREAM_SHA,
        "store_sha256": hashlib.sha256(store.read_bytes()).hexdigest(),
        "replay_runs": replay_runs, "repeats": repeats, "arms": arms,
        "cases": [c.id for c in cases], "claude_bin": claude_bin,
    }, indent=2) + "\n")

    spawn = spawn or default_spawn
    runs_path = out_dir / "runs.jsonl"
    runs_path.write_text("")
    with contextlib.ExitStack() as stack:
        wt = Path(worktree) if worktree else stack.enter_context(agent_worktree())
        if _git_status(wt).strip():
            raise EvalRefused(f"agent worktree {wt} is not clean before the first run")
        for k, case, arm in run_order(cases, arms, repeats):
            argv = build_command(prompts[case.id], arm, cfgs[arm], claude_bin)
            rel = f"transcripts/{case.id}-{arm}-r{k}.jsonl"
            rel_err = f"transcripts/{case.id}-{arm}-r{k}.err"
            row = {"case": case.id, "arm": arm, "repeat": k,
                   **_one_run(argv, wt, out_dir / rel, out_dir / rel_err, arm, spawn),
                   "claude_version": version, "argv": argv, "transcript": rel,
                   "stderr": rel_err}
            with open(runs_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{case.id} {arm} r{k}: exit={row['exit_code']} turns={row['num_turns']} "
                  f"cost={row['total_cost_usd']} error={row['error']}", file=sys.stderr)
    return out_dir
