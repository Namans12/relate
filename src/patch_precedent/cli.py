"""Command-line entry point. Later tasks add build-store, verify-store, explain, demo."""
import argparse


def build_parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(
        prog="patch-precedent",
        description="Replay patches against an upstream installer test harness "
        "and explain the results via a graph.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")
    return parser, subparsers


def main(argv: list[str] | None = None) -> int:
    parser, _subparsers = build_parser()
    parser.parse_args(argv)
    return 0
