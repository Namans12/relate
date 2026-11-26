"""Command-line entry point. Later tasks add explain and demo."""
import argparse
import tempfile
from pathlib import Path

from .pins import STORE_PATH, project_root

DEFAULT_MANIFEST = project_root() / "evidence" / "installer.toml"


def build_parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(
        prog="patch-precedent",
        description="Replay patches against an upstream installer test harness "
        "and explain the results via a graph.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    build = subparsers.add_parser("build-store", help="build the Relate store from the manifest")
    build.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    build.add_argument("--out", type=Path, default=STORE_PATH)

    verify = subparsers.add_parser(
        "verify-store", help="check the committed store matches a fresh build of the manifest"
    )
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    verify.add_argument("--store", type=Path, default=STORE_PATH)
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

    build_store(args.manifest, args.out)
    print(f"built {args.out}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    from .store import build_store

    if not args.store.is_file():
        print(f"store not found: {args.store}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "fresh.rl"
        build_store(args.manifest, fresh)
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


def main(argv: list[str] | None = None) -> int:
    parser, _subparsers = build_parser()
    args = parser.parse_args(argv)
    if args.command == "build-store":
        return _cmd_build(args)
    if args.command == "verify-store":
        return _cmd_verify(args)
    return 0
