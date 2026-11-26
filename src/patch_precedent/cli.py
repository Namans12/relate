"""Command-line entry point. Later tasks add explain and demo."""
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
        description="Replay patches against an upstream installer test harness "
        "and explain the results via a graph.",
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

    demo = subparsers.add_parser(
        "demo", help="replay baseline and patches against the upstream harness and explain"
    )
    demo.add_argument("scenario", metavar="SCENARIO", choices=list(SCENARIOS),
                      help=f"scenario to run ({', '.join(SCENARIOS)})")
    demo.add_argument("--fixtures", type=Path, default=None, help="directory of *.patch files")
    demo.add_argument("--runs-dir", type=Path, default=None, help="where run directories go")

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

    if not args.patch_file.is_file():
        print(f"patch file not found: {args.patch_file}", file=sys.stderr)
        return 2
    if not args.store.is_file():
        print(f"store not found: {args.store}", file=sys.stderr)
        return 2
    patch = read_patch(args.patch_file)
    print(f"patch    {patch.label} (sha256 {patch.sha256[:12]})")
    print(f"changes  {', '.join(patch.changed_files)}")
    print("mode     read-only: no upstream fetch, no patch executed")
    print()
    if not patch.changed_files:
        print("no changed files found in patch")
        return 0
    conn = open_readonly(args.store)
    try:
        evidence = evidence_for_paths(conn, patch.changed_files)
        cited = cited_decisions(conn, patch.changed_files)
    finally:
        conn.close()
    print("\n\n".join(render_file_evidence(f, evidence[f], cited[f]) for f in patch.changed_files))
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_demo

    return run_demo(args.scenario, args.fixtures, args.runs_dir)


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
    return 0
