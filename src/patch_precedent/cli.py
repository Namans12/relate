"""Command-line entry point."""
import argparse
import sys
import tempfile
from pathlib import Path

from . import pins
from .pins import STORE_PATH, project_root
from .scenarios import SCENARIOS

DEFAULT_EVIDENCE = project_root() / "evidence"
DEFAULT_SCAN_DIR = project_root() / "evidence" / "scanned"


def build_parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(
        prog="patch-precedent",
        description="Replay patches against upstream test harnesses (installer, release) "
        "and explain the results via a Relate graph.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    build = subparsers.add_parser("build-store", help="build the Relate store from the evidence directory")
    build.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    build.add_argument("--out", type=Path, default=STORE_PATH)

    verify = subparsers.add_parser(
        "verify-store", help="check the committed store matches a fresh build of the evidence"
    )
    verify.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    verify.add_argument("--store", type=Path, default=STORE_PATH)

    explain = subparsers.add_parser(
        "explain", help="show the decision, commit and checks behind a patch's files (read-only)"
    )
    explain.add_argument("patch_file", type=Path, metavar="PATCH_FILE")
    explain.add_argument("--store", type=Path, default=STORE_PATH)
    explain.add_argument("--plain", action="store_true", help="force plain text (no styling)")
    explain.add_argument("--links", action="store_true",
                         help="print the GitHub permalinks (styled output only)")

    demo = subparsers.add_parser(
        "demo", help="replay baseline and patches against the upstream harness and explain"
    )
    demo.add_argument("scenario", metavar="SCENARIO", choices=[*SCENARIOS, "all"],
                      help=f"scenario to run ({', '.join(SCENARIOS)}, or all)")
    demo.add_argument("--fixtures", type=Path, default=None, help="directory of *.patch files")
    demo.add_argument("--runs-dir", type=Path, default=None, help="where run directories go")
    demo.add_argument("--plain", action="store_true", help="force plain text (no styling)")

    mcp = subparsers.add_parser(
        "mcp", help="serve the read-only precedent_for_patch tool over stdio (MCP)"
    )
    mcp.add_argument("--store", type=Path, default=STORE_PATH)
    mcp.add_argument("--runs-dir", type=Path, default=project_root() / "runs",
                     help="where demo run directories (replay evidence) live")

    subparsers.add_parser(
        "fetch-relate-cli", help="download and verify the pinned relate CLI; print its path"
    )

    ev = subparsers.add_parser("eval", help="agent evaluation (runs headless Claude Code)")
    ev_sub = ev.add_subparsers(dest="eval_command", metavar="<eval-command>", required=True)
    run = ev_sub.add_parser(
        "run", help="run each case with and without the precedent tool (needs `demo all` first)"
    )
    run.add_argument("--repeats", type=int, default=3)
    run.add_argument("--cases", default=None, help="comma-separated case ids, e.g. C1,C2")
    run.add_argument("--arms", default="baseline,graph", help="comma-separated: baseline,graph")
    run.add_argument("--out", type=Path, default=None,
                     help="output directory (default eval/results/<UTC timestamp>)")
    run.add_argument("--claude-bin", default="claude")
    run.add_argument("--runs-dir", type=Path, default=project_root() / "runs",
                     help="where demo run directories (replay evidence) live")

    for name, text in (("score", "score a results directory (writes scored.jsonl, results.json)"),
                       ("report", "render RESULTS.md from a scored results directory")):
        sub = ev_sub.add_parser(name, help=text)
        sub.add_argument("--results", type=Path, default=None,
                         help="results directory (default: newest eval/results/*)")

    scan = subparsers.add_parser(
        "scan-citations", help="scan upstream for ADR-NNNN mentions into evidence/scanned/"
    )
    scan.add_argument("--out-dir", type=Path, default=DEFAULT_SCAN_DIR)
    return parser, subparsers


def _snapshot_of(path: Path) -> list[tuple]:
    from .store import open_readonly, snapshot

    conn = open_readonly(path)
    try:
        return snapshot(conn)
    finally:
        conn.close()


def _cmd_build(args: argparse.Namespace) -> int:
    from .store import build_store

    build_store(args.evidence_dir, args.out)
    print(f"built {args.out}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from .store import build_store

    if not args.store.is_file():
        print(f"store not found: {args.store}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "fresh.rl"
        build_store(args.evidence_dir, fresh)
        expected = _snapshot_of(fresh)
    actual = _snapshot_of(args.store)
    if expected == actual:
        nodes = sum(1 for t in actual if t[0] == "node")
        rels = len(actual) - nodes
        print(f"store matches manifest: {nodes} nodes, {rels} relationships")
        return 0
    exp, act = set(expected), set(actual)
    diffs = [("missing from store", t) for t in sorted(exp - act)]
    diffs += [("unexpected in store", t) for t in sorted(act - exp)]
    print(f"store does not match manifest: {len(diffs)} differing entries")
    for label, t in diffs[:10]:
        print(f"  {label}: {t}")
    return 1


def _cmd_explain(args: argparse.Namespace) -> int:
    from .diffparse import read_patch
    from .report import render_file_evidence
    from .store import cited_decisions, evidence_for_paths, open_readonly
    from .tui import make_console, render_explain, should_style

    if not args.patch_file.is_file():
        print(f"patch file not found: {args.patch_file}", file=sys.stderr)
        return 2
    if not args.store.is_file():
        print(f"store not found: {args.store}", file=sys.stderr)
        return 2
    patch = read_patch(args.patch_file)
    styled = should_style(sys.stdout, args.plain)
    if not styled:
        print(f"patch    {patch.label} (sha256 {patch.sha256[:12]})")
        print(f"changes  {', '.join(patch.changed_files)}")
        print("mode     read-only: no upstream fetch, no patch executed")
        print()
        if not patch.changed_files:
            print("no changed files found in patch")
            return 0
    evidence: dict = {}
    cited: dict = {}
    if patch.changed_files:
        conn = open_readonly(args.store)
        try:
            evidence = evidence_for_paths(conn, patch.changed_files)
            cited = cited_decisions(conn, patch.changed_files)
        finally:
            conn.close()
    if styled:
        render_explain(make_console(), patch, evidence, cited, args.links)
        return 0
    print("\n\n".join(render_file_evidence(f, evidence[f], cited[f]) for f in patch.changed_files))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_all, run_demo
    from .tui import StyledReporter, make_console, should_style

    reporter = StyledReporter(make_console()) if should_style(sys.stdout, args.plain) else None
    try:
        if args.scenario == "all":
            if args.fixtures is not None:
                print("--fixtures cannot be used with 'demo all'", file=sys.stderr)
                return 2
            return run_all(args.runs_dir, reporter=reporter)
        return run_demo(args.scenario, args.fixtures, args.runs_dir, reporter=reporter)
    finally:
        if reporter is not None:
            reporter.finish()  # idempotent; run_all returns early when upstream is lost


def _cmd_mcp(args: argparse.Namespace) -> int:
    if not args.store.is_file():
        print(f"store not found: {args.store}", file=sys.stderr)
        return 2
    from .mcp_server import serve  # lazy: demo and explain never import the SDK

    serve(args.store, args.runs_dir)
    return 0


def _cmd_fetch_relate_cli(args: argparse.Namespace) -> int:
    from .relate_cli import RelateCliError, ensure_relate_cli

    try:
        print(ensure_relate_cli())
    except (RelateCliError, OSError) as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 4
    return 0


def _cmd_eval_run(args: argparse.Namespace) -> int:
    import datetime

    from .eval.cases import load_cases
    from .eval.runner import EvalRefused, run_eval
    from .upstream import UpstreamUnavailable

    cases = load_cases()
    if args.cases:
        want = [c.strip() for c in args.cases.split(",") if c.strip()]
        unknown = [c for c in want if c not in {x.id for x in cases}]
        if unknown:
            print(f"unknown case(s): {', '.join(unknown)}", file=sys.stderr)
            return 2
        cases = [c for c in cases if c.id in want]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    if args.repeats < 1:
        print("--repeats must be at least 1", file=sys.stderr)
        return 2
    out = args.out or project_root() / "eval" / "results" / datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        run_eval(cases, arms, args.repeats, out, runs_root=args.runs_dir,
                 claude_bin=args.claude_bin)
    except EvalRefused as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 2
    except UpstreamUnavailable as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 4
    print(f"wrote {out}")
    return 0


def _results_dir(args: argparse.Namespace, need: str) -> Path | None:
    d = args.results
    if d is None:
        root = project_root() / "eval" / "results"
        found = sorted(p for p in root.glob("*") if p.is_dir()) if root.is_dir() else []
        if not found:
            print(f"no results directory under {root}", file=sys.stderr)
            return None
        d = found[-1]
    if not (Path(d) / need).is_file():
        print(f"{Path(d) / need} not found (is {d} an eval results directory?)", file=sys.stderr)
        return None
    return Path(d)


def _cmd_eval_score(args: argparse.Namespace) -> int:
    import json

    from .eval.cases import load_cases
    from .eval.score import score_row, summarise

    d = _results_dir(args, "runs.jsonl")
    if d is None:
        return 2
    cases = {c.id: c for c in load_cases()}
    rows = [json.loads(x) for x in (d / "runs.jsonl").read_text(encoding="utf-8").splitlines()
            if x.strip()]
    unknown = sorted({r["case"] for r in rows} - set(cases))
    if unknown:
        print(f"runs.jsonl names unknown case(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    scored = [score_row(cases[r["case"]], r, d) for r in rows]
    (d / "scored.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False, sort_keys=True) + "\n" for s in scored),
        encoding="utf-8")
    (d / "results.json").write_text(
        json.dumps(summarise(scored), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"scored {len(scored)} runs in {d}")
    return 0


def _cmd_eval_report(args: argparse.Namespace) -> int:
    import json

    from .eval.report import render_results_md
    from .eval.score import summarise

    d = _results_dir(args, "scored.jsonl")
    if d is None:
        return 2
    if not (d / "meta.json").is_file():
        print(f"{d / 'meta.json'} not found", file=sys.stderr)
        return 2
    scored = [json.loads(x) for x in (d / "scored.jsonl").read_text(encoding="utf-8").splitlines()
              if x.strip()]
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    (d / "RESULTS.md").write_text(render_results_md(summarise(scored), scored, meta, str(d.resolve())),
                                  encoding="utf-8")
    print(f"wrote {d / 'RESULTS.md'}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    from .scan import write_index
    from .upstream import UpstreamUnavailable

    try:
        citations, decisions = write_index(args.out_dir)
    except UpstreamUnavailable as exc:
        print(str(exc).replace("\n", " "), file=sys.stderr)
        return 4
    files = len({c[0] for c in citations})
    adrs = len({c[1] for c in citations})
    recs = sum(1 for d in decisions if d[3])
    print(f"scanned {len(citations)} citations across {files} files and {adrs} ADRs; "
          f"{len(decisions)} decisions ({recs} with records) at {pins.UPSTREAM_SHA[:12]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser, _subparsers = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build-store":
        return _cmd_build(args)
    if args.command == "verify-store":
        return _cmd_verify(args)
    if args.command == "explain":
        return _cmd_explain(args)
    if args.command == "scan-citations":
        return _cmd_scan(args)
    if args.command == "demo":
        return _cmd_demo(args)
    if args.command == "mcp":
        return _cmd_mcp(args)
    if args.command == "fetch-relate-cli":
        return _cmd_fetch_relate_cli(args)
    if args.command == "eval":
        return {"run": _cmd_eval_run, "score": _cmd_eval_score,
                "report": _cmd_eval_report}[args.eval_command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
