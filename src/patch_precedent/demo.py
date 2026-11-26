"""`demo installer`: replay baseline and patches, then explain the results via the graph."""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import pins
from .report import (
    comparison_table,
    compute_verdicts,
    format_table,
    observed_map,
    render_evidence_chain,
)

SCENARIOS = ("installer",)


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


def run_demo(
    scenario: str = "installer",
    fixtures_dir: Path | None = None,
    runs_root: Path | None = None,
) -> int:
    if scenario not in SCENARIOS:
        print(f"unknown scenario: {scenario!r} (available: {', '.join(SCENARIOS)})",
              file=sys.stderr)
        return 2
    import relate

    from .diffparse import read_patch
    from .harness import run_case
    from .replay import (
        JOIN_QUERY,
        check_expectations,
        join_rows,
        load_expectations,
        record_runs,
    )
    from .store import evidence_for_paths, open_readonly
    from .upstream import UpstreamUnavailable, ensure_upstream

    root = pins.project_root()
    fixtures_dir = Path(fixtures_dir) if fixtures_dir else root / "fixtures" / "installer"
    runs_root = Path(runs_root) if runs_root else root / "runs"

    print(f"upstream  {pins.UPSTREAM_URL}@{pins.UPSTREAM_SHA[:12]}")
    print(f"relate    {_relate_version()}")
    print(f"evidence  {pins.STORE_PATH} (opened read-only)")
    print("Results below are observed from fresh runs and live graph queries.")
    print()
    try:
        ensure_upstream()
    except UpstreamUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 4
    if not fixtures_dir.is_dir():
        print(f"fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        return 2
    patches = [read_patch(p) for p in sorted(fixtures_dir.glob("*.patch"))]
    expectations = load_expectations(root / "fixtures" / "installer" / "expectations.toml")
    run_dir = _make_run_dir(runs_root)

    runs = []
    for label, patch in [("baseline", None)] + [(p.label, p) for p in patches]:
        print(f"== {label} ==")
        if patch is not None:
            print(f"patch {patch.sha256[:12]}  changes {', '.join(patch.changed_files)}")
            print(Path(patch.path).read_text(errors="replace").rstrip("\n"))
        print("running harness…", flush=True)
        run = run_case(label, patch, run_dir)
        runs.append(run)
        if run.tap is not None:
            counts = f"{run.tap.passed} passed / {run.tap.failed} failed"
        else:
            counts = "no TAP"
        code = "none" if run.exit_code is None else run.exit_code
        tail = f" ({run.reason})" if run.status == "inconclusive" and run.reason else ""
        print(f"exit {code}  {counts}  → {run.status}{tail}")
        print()

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
    mismatches = check_expectations(runs, expectations)

    print("== comparison ==")
    print(comparison_table(runs, evidence_by_patch))
    print()

    print("== graph evidence ==")
    for run in runs:
        if run.patch is None:
            continue
        print(f"-- {run.label} --")
        obs = observed_map(run)
        for f in run.patch.changed_files:
            print(render_evidence_chain(f, per_file[run.patch.id][f], obs))
        print()

    print("== graph join (replay.rl) ==")
    print(JOIN_QUERY.rstrip())
    print()
    print(format_table(
        ["patch", "file", "decision", "implementation", "assertion", "observed"],
        [[r["label"], r["file"], r["decision"], r["implementation"][:8], r["assertion"],
          r["observed"]] for r in joined]))
    print()

    verdicts, exit_code = compute_verdicts(runs, evidence_by_patch, mismatches)
    print("== verdicts ==")
    print("\n".join(verdicts))
    if warnings:
        print("\nwarnings")
        print("\n".join(f"  {w}" for w in warnings))
    if mismatches:
        print("\nmismatches")
        print("\n".join(f"  {m}" for m in mismatches))
    print()

    summary_path = run_dir / "summary.json"
    print("== artifacts ==")
    print(f"run dir   {run_dir}")
    for run in runs:
        print(f"log       {run.log_path}")
    print(f"store     {replay_store}")
    print(f"summary   {summary_path}")

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
            }
            for r in runs
        ],
        "join_rows": joined,
        "warnings": warnings,
        "mismatches": mismatches,
        "verdicts": verdicts,
        "exit_code": exit_code,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return exit_code
