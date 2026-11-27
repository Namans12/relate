"""`demo <scenario>`: replay baseline and patches, then explain the results via the graph."""
import json
import shutil
import sys
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from . import pins
from .scenarios import SCENARIOS, Scenario, get_scenario
from .report import (
    comparison_table,
    compute_verdicts,
    format_table,
    join_table,
    observed_map,
    overall_exit,
    render_file_evidence,
    verdict_records,
)

if TYPE_CHECKING:
    from .diffparse import PatchInfo
    from .harness import RunResult
    from .report import VerdictRecord


class DemoReporter(Protocol):
    """Everything `demo` shows on stdout goes through these calls, in this order."""

    def begin(self, command: str, upstream_url: str, upstream_sha: str,
              relate_version: str) -> None: ...

    def scenario(self, name: str) -> None: ...

    def preamble(self, upstream_url: str, upstream_sha: str, relate_version: str,
                 store: Path) -> None: ...

    def run_start(self, label: str, patch: "PatchInfo | None") -> None: ...

    def run_end(self, run: "RunResult", duration_s: float) -> None: ...

    def details(self, runs, evidence_by_patch, file_blocks: list[str], join_query: str,
                joined: list[dict], file_evidence: "list[tuple] | tuple" = ()) -> None:
        """`file_evidence` holds (path, chain rows, cited rows, [(run label, observed)]) per
        file, for reporters that render the chains themselves instead of `file_blocks`."""

    def verdicts(self, lines: list[str], records: "list[VerdictRecord]", rcheck: dict,
                 warnings: list[str], mismatches: list[str]) -> None: ...

    def artifacts(self, run_dir: Path, runs, replay_store: Path, summary_path: Path) -> None: ...

    def overall(self, rows: list[tuple], overall: int, summary_path: Path,
                elapsed_s: float) -> None: ...

    def finish(self) -> None: ...


class PlainReporter:
    """The original line-oriented output, unchanged byte for byte."""

    def __init__(self) -> None:
        self._scenarios_seen = 0

    def begin(self, command, upstream_url, upstream_sha, relate_version):
        pass

    def scenario(self, name):
        if self._scenarios_seen:
            print()
        self._scenarios_seen += 1
        print(f"### scenario: {name}")

    def preamble(self, upstream_url, upstream_sha, relate_version, store):
        print(f"upstream  {upstream_url}@{upstream_sha[:12]}")
        print(f"relate    {relate_version}")
        print(f"evidence  {store} (opened read-only)")
        print("Results below are observed from fresh runs and live graph queries.")
        print()

    def run_start(self, label, patch):
        print(f"== {label} ==")
        if patch is not None:
            print(f"patch {patch.sha256[:12]}  changes {', '.join(patch.changed_files)}")
            print(Path(patch.path).read_text(errors="replace").rstrip("\n"))
        print("running harness…", flush=True)

    def run_end(self, run, duration_s):
        if run.tap is not None:
            counts = f"{run.tap.passed} passed / {run.tap.failed} failed"
        else:
            counts = "no TAP"
        code = "none" if run.exit_code is None else run.exit_code
        tail = f" ({run.reason})" if run.status == "inconclusive" and run.reason else ""
        print(f"exit {code}  {counts}  → {run.status}{tail}")
        print()

    def details(self, runs, evidence_by_patch, file_blocks, join_query, joined, file_evidence=()):
        print("== comparison ==")
        print(comparison_table(runs, evidence_by_patch))
        print()

        print("== graph evidence ==")
        for block in file_blocks:
            print(block)
            print()

        print("== graph join (replay.rl) ==")
        print(join_query.rstrip())
        print()
        print(join_table(joined))
        print()

    def verdicts(self, lines, records, rcheck, warnings, mismatches):
        print("== verdicts ==")
        print("\n".join(lines))
        print()
        print(rcheck["line"])
        for label in rcheck["reproduced"]:
            print(f"  {label} — expected regression reproduced; demo replay succeeded")
        for label in rcheck["inconclusive"]:
            print(f"  {label} — inconclusive, not counted")
        if warnings:
            print("\nwarnings")
            print("\n".join(f"  {w}" for w in warnings))
        if mismatches:
            print("\nmismatches")
            print("\n".join(f"  {m}" for m in mismatches))
        print()

    def artifacts(self, run_dir, runs, replay_store, summary_path):
        print("== artifacts ==")
        print(f"run dir   {run_dir}")
        for run in runs:
            print(f"log       {run.log_path}")
        print(f"store     {replay_store}")
        print(f"summary   {summary_path}")

    def overall(self, rows, overall, summary_path, elapsed_s):
        if self._scenarios_seen:
            print()
        print("== overall ==")
        print(format_table(["scenario", "runs", "matched", "exit"], rows, rule=False))
        print(f"overall exit {overall}")
        print(f"summary   {summary_path}")

    def finish(self):
        pass


def _make_run_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n = 1
    while True:
        path = root / (base if n == 1 else f"{base}-{n}")
        try:
            path.mkdir()
            return path
        except FileExistsError:
            n += 1


def _relate_version() -> str:
    try:
        import relate

        return getattr(relate, "__version__", None) or pins.RELATE_VERSION
    except ImportError:  # pragma: no cover
        return pins.RELATE_VERSION


def _preflight(fixtures_dirs: Sequence[Path]) -> int | None:
    """Check fixtures, store and upstream before any output; return an exit code on failure."""
    from .upstream import UpstreamUnavailable, ensure_upstream

    for fixtures_dir in fixtures_dirs:
        if not fixtures_dir.is_dir():
            print(f"fixtures directory not found: {fixtures_dir}", file=sys.stderr)
            return 2
    if not pins.STORE_PATH.is_file():
        print(f"evidence store not found: {pins.STORE_PATH} "
              "(restore it with `git checkout data/precedent.rl`)", file=sys.stderr)
        return 2
    try:
        ensure_upstream()
    except UpstreamUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 4
    return None


def _run_scenario(
    sc: Scenario, fixtures_dir: Path, run_dir: Path, reporter: DemoReporter
) -> tuple[int, dict]:
    """Run one scenario into run_dir (already preflighted); return (exit code, summary)."""
    import relate

    from .diffparse import read_patch
    from .harness import run_case
    from .replay import (
        JOIN_QUERY,
        check_expectations,
        join_rows,
        join_tap_disagreements,
        load_expectations,
        record_runs,
        replay_check,
    )
    from .store import cited_decisions, evidence_for_paths, open_readonly
    from .upstream import UpstreamUnavailable

    root = pins.project_root()

    reporter.preamble(pins.UPSTREAM_URL, pins.UPSTREAM_SHA, _relate_version(), pins.STORE_PATH)
    patches = [read_patch(p) for p in sorted(fixtures_dir.glob("*.patch"))]
    expectations = load_expectations(sc.expectations_path)

    runs = []
    durations: list[float] = []
    try:
        for label, patch in [("baseline", None)] + [(p.label, p) for p in patches]:
            reporter.run_start(label, patch)
            started = time.monotonic()
            run = run_case(label, patch, run_dir, sc.harness_cmd, sc.timeout_s)
            duration = time.monotonic() - started
            runs.append(run)
            durations.append(duration)
            reporter.run_end(run, duration)
    except UpstreamUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 4, {}

    conn = open_readonly(pins.STORE_PATH)
    try:
        evidence_by_patch = {
            r.patch.id: [
                row for rows in evidence_for_paths(conn, r.patch.changed_files).values()
                for row in rows
            ]
            for r in runs if r.patch is not None
        }
        per_file = {
            r.patch.id: evidence_for_paths(conn, r.patch.changed_files)
            for r in runs if r.patch is not None
        }
        cited_per_file = {
            r.patch.id: cited_decisions(conn, r.patch.changed_files)
            for r in runs if r.patch is not None
        }
        cited_by_patch = {
            pid: [row for rows in files.values() for row in rows]
            for pid, files in cited_per_file.items()
        }
    finally:
        conn.close()

    replay_store = run_dir / "replay.rl"
    shutil.copy2(pins.STORE_PATH, replay_store)
    warnings = record_runs(replay_store, runs)
    jconn = relate.connect(str(replay_store))
    try:
        joined = join_rows(jconn)
    finally:
        jconn.close()
    rcheck = replay_check(
        runs, expectations, sc.expectations_path.relative_to(root).as_posix())
    mismatches = check_expectations(runs, expectations)
    mismatches += join_tap_disagreements(runs, evidence_by_patch, joined)

    by_file: dict[str, list] = {}
    for run in runs:
        if run.patch is not None:
            for f in run.patch.changed_files:
                by_file.setdefault(f, []).append(run)
    file_blocks = [
        render_file_evidence(
            f, per_file[file_runs[0].patch.id][f], cited_per_file[file_runs[0].patch.id][f],
            patch_observed=[(r.label, observed_map(r)) for r in file_runs])
        for f, file_runs in by_file.items()
    ]
    file_evidence = [
        (f, per_file[file_runs[0].patch.id][f], cited_per_file[file_runs[0].patch.id][f],
         [(r.label, observed_map(r)) for r in file_runs])
        for f, file_runs in by_file.items()
    ]
    reporter.details(runs, evidence_by_patch, file_blocks, JOIN_QUERY, joined, file_evidence)

    verdicts, exit_code = compute_verdicts(runs, evidence_by_patch, mismatches, cited_by_patch)
    records = verdict_records(runs, evidence_by_patch, cited_by_patch)
    reporter.verdicts(verdicts, records, rcheck, warnings, mismatches)

    summary_path = run_dir / "summary.json"
    reporter.artifacts(run_dir, runs, replay_store, summary_path)

    summary = {
        "upstream": {"url": pins.UPSTREAM_URL, "sha": pins.UPSTREAM_SHA},
        "run_dir": str(run_dir),
        "replay_store": str(replay_store),
        "runs": [
            {
                "label": r.label,
                "patch_id": r.patch.id if r.patch else None,
                "sha256": r.patch.sha256 if r.patch else None,
                "changed_files": list(r.patch.changed_files) if r.patch else [],
                "status": r.status,
                "reason": r.reason,
                "exit_code": r.exit_code,
                "passed": r.tap.passed if r.tap else None,
                "failed": r.tap.failed if r.tap else None,
                "skipped": r.tap.skipped if r.tap else None,
                "total": (r.tap.planned if r.tap.planned is not None else len(r.tap.results))
                if r.tap else None,
                "failing": [x.description for x in r.tap.results if not x.ok] if r.tap else [],
                "failing_numbers": [x.number for x in r.tap.results if not x.ok]
                if r.tap else [],
                "log": str(r.log_path),
                "duration_s": round(d, 1),
            }
            for r, d in zip(runs, durations)
        ],
        "join_rows": joined,
        "warnings": warnings,
        "mismatches": mismatches,
        "verdicts": verdicts,
        "replay_check": {k: rcheck[k] for k in ("matched", "total", "mismatches", "reproduced")},
        "exit_code": exit_code,
        "verdict_records": [rec.as_dict() for rec in records],
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return exit_code, summary


def run_demo(
    scenario: str = "installer",
    fixtures_dir: Path | None = None,
    runs_root: Path | None = None,
    reporter: DemoReporter | None = None,
) -> int:
    reporter = reporter or PlainReporter()
    try:
        sc = get_scenario(scenario)
    except KeyError:
        print(f"unknown scenario: {scenario!r} (available: {', '.join(SCENARIOS)})",
              file=sys.stderr)
        return 2
    fixtures_dir = Path(fixtures_dir) if fixtures_dir else sc.fixtures_dir
    runs_root = Path(runs_root) if runs_root else pins.project_root() / "runs"
    failed = _preflight([fixtures_dir])
    if failed is not None:
        return failed
    run_dir = _make_run_dir(runs_root) / sc.name
    run_dir.mkdir()
    reporter.begin(f"demo {sc.name}", pins.UPSTREAM_URL, pins.UPSTREAM_SHA, _relate_version())
    code, _summary = _run_scenario(sc, fixtures_dir, run_dir, reporter)
    reporter.finish()
    return code


def run_all(runs_root: Path | None = None, reporter: DemoReporter | None = None) -> int:
    """Run every scenario in registry order under one runs/<ts>/ directory."""
    reporter = reporter or PlainReporter()
    started = time.monotonic()
    runs_root = Path(runs_root) if runs_root else pins.project_root() / "runs"
    failed = _preflight([sc.fixtures_dir for sc in SCENARIOS.values()])
    if failed is not None:
        return failed
    ts_dir = _make_run_dir(runs_root)
    reporter.begin("demo all", pins.UPSTREAM_URL, pins.UPSTREAM_SHA, _relate_version())
    codes: list[int] = []
    summaries: dict[str, dict] = {}
    for sc in SCENARIOS.values():
        reporter.scenario(sc.name)
        run_dir = ts_dir / sc.name
        run_dir.mkdir()
        code, summary = _run_scenario(sc, sc.fixtures_dir, run_dir, reporter)
        if code == 4:  # upstream lost mid-run: nothing further can run
            return 4
        codes.append(code)
        summaries[sc.name] = summary
    overall = overall_exit(codes)
    rows = []
    for name, summary in summaries.items():
        rc = summary["replay_check"]
        rows.append((name, len(summary["runs"]), f"{rc['matched']}/{rc['total']}",
                     summary["exit_code"]))
    elapsed_s = round(time.monotonic() - started, 1)
    summary_path = ts_dir / "summary.json"
    summary_path.write_text(json.dumps(
        {"scenarios": summaries, "overall_exit": overall, "elapsed_s": elapsed_s},
        indent=2) + "\n")
    reporter.overall(rows, overall, summary_path, elapsed_s)
    reporter.finish()
    return overall
