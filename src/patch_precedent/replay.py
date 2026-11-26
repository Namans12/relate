"""Record replay runs into a private store copy, join them to the graph, check expectations."""
import tomllib
from collections.abc import Sequence
from pathlib import Path

import relate

from . import pins
from .harness import RunResult

JOIN_QUERY = """\
MATCH (p:Patch)-[:CHANGES]->(f:File)-[:CITES]->(d:Decision)-[:CHECKED_BY]->(t:Check),
      (p)-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(t),
      (c:Commit)-[:IMPLEMENTS]->(d)
RETURN p.id AS patch, f.path AS file, d.id AS decision, d.reason AS reason,
       c.sha AS implementation, t.name AS assertion, o.tap AS observed,
       p.label AS label, o.number AS tap_number
ORDER BY patch, assertion
"""


def _run_props(run: RunResult) -> dict:
    tap = run.tap
    props = {
        "base": run.base_sha,
        "command": run.command,
        "exit_code": run.exit_code,
        "status": run.status,
        "reason": run.reason,
        "log": str(run.log_path),
    }
    if tap is not None:
        props["passed"] = tap.passed
        props["failed"] = tap.failed
        props["total"] = tap.planned if tap.planned is not None else len(tap.results)
    return {k: v for k, v in props.items() if v is not None}


def _record_patch_run(conn, run: RunResult, checks: set[str]) -> None:
    patch = run.patch
    # Replace any earlier recording of this patch; Patch and CHANGES are content-derived.
    conn.execute("MATCH (p:Patch {id: $id})-[:PRODUCED]->(o:Observation) DETACH DELETE o",
                 {"id": patch.id})
    conn.execute("MATCH (r:Run {id: $id}) DETACH DELETE r", {"id": patch.id})
    conn.execute("MERGE (p:Patch {id: $id}) SET p.label = $label, p.sha256 = $sha",
                 {"id": patch.id, "label": patch.label, "sha": patch.sha256})
    for path in patch.changed_files:
        conn.execute("MERGE (f:File {path: $path})", {"path": path})
        conn.execute(
            "MATCH (p:Patch {id: $id}), (f:File {path: $path}) MERGE (p)-[:CHANGES]->(f)",
            {"id": patch.id, "path": path})
    conn.execute("MERGE (r:Run {id: $id}) SET r += $props",
                 {"id": patch.id, "props": _run_props(run)})
    conn.execute(
        "MATCH (r:Run {id: $id}), (p:Patch {id: $id}) MERGE (r)-[:APPLIED]->(p)",
        {"id": patch.id})
    if run.tap is None:
        return
    for res in run.tap.results:
        if res.description not in checks:
            continue
        oid = f"{patch.id}|{res.description}"
        conn.execute(
            "MERGE (o:Observation {id: $oid}) SET o.tap = $tap, o.number = $n",
            {"oid": oid, "tap": "ok" if res.ok else "not ok", "n": res.number})
        conn.execute(
            "MATCH (p:Patch {id: $id}), (o:Observation {id: $oid}), "
            "(c:Check {name: $name}) "
            "MERGE (p)-[:PRODUCED]->(o) MERGE (o)-[:FOR_CHECK]->(c)",
            {"id": patch.id, "oid": oid, "name": res.description})


def record_runs(store_copy: Path, runs: Sequence[RunResult]) -> list[str]:
    """Write patch runs into a private copy of the store; return drift warnings."""
    if Path(store_copy).resolve() == Path(pins.STORE_PATH).resolve():
        raise ValueError(f"refusing to record runs into the committed store {store_copy}")
    warnings: list[str] = []
    conn = relate.connect(str(store_copy))
    try:
        checks = {r.data()["n"] for r in conn.execute("MATCH (c:Check) RETURN c.name AS n")}
        for run in runs:
            if run.tap is not None:
                seen = {r.description for r in run.tap.results}
                warnings += [f"{run.label}: check not found in TAP: {name}"
                             for name in sorted(checks - seen)]
            if run.patch is not None:
                _record_patch_run(conn, run, checks)
        conn.commit()
    finally:
        conn.close()
    return warnings


def join_rows(conn) -> list[dict]:
    return [r.data() for r in conn.execute(JOIN_QUERY)]


def load_expectations(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _compare(label: str, run: RunResult, exp: dict) -> list[str]:
    tap = run.tap
    failing = sorted(r.description for r in tap.results if not r.ok)
    pairs = [("exit", exp["exit"], run.exit_code),
             ("passed", exp["passed"], tap.passed),
             ("failed", exp["failed"], tap.failed),
             ("failing", sorted(exp["failing"]), failing)]
    return [f"{label}: {field} expected {e!r}, observed {o!r}"
            for field, e, o in pairs if e != o]


def check_expectations(runs: Sequence[RunResult], expectations: dict) -> list[str]:
    by_sha = {p["sha256"]: p for p in expectations.get("patch", [])}
    out: list[str] = []
    for run in runs:
        if run.tap is None:
            out.append(f"{run.label}: no TAP")
        elif run.patch is None:
            out += _compare("baseline", run, expectations["baseline"])
        elif run.patch.sha256 not in by_sha:
            out.append(f"{run.label} ({run.patch.sha256[:12]}): "
                       "no expectation for this content")
        else:
            out += _compare(run.label, run, by_sha[run.patch.sha256])
    return out


def join_tap_disagreements(
    runs: Sequence[RunResult],
    evidence_by_patch: dict[str, list[dict]],
    joined: Sequence[dict],
) -> list[str]:
    """Compare graph-join observations with what each run's TAP says.

    The join is the displayed source of truth, so it must agree with the TAP it was
    recorded from. Only conclusive patch runs with linked evidence are compared.
    """
    in_join = {(r["patch"], r["assertion"]): r["observed"] for r in joined}
    out: list[str] = []
    for run in runs:
        if run.patch is None or run.status == "inconclusive" or run.tap is None:
            continue
        linked = {r["check"] for r in evidence_by_patch.get(run.patch.id, [])}
        if not linked:
            continue
        pid = run.patch.id
        if not any(p == pid for p, _ in in_join):
            out.append(f"join/TAP disagree: {run.label}: "
                       "no join rows for a patch with linked evidence")
            continue
        tap = {(pid, r.description): "ok" if r.ok else "not ok"
               for r in run.tap.results if r.description in linked}
        for key in sorted(set(tap) | {k for k in in_join if k[0] == pid}):
            j, t = in_join.get(key, "absent"), tap.get(key, "absent")
            if j != t:
                out.append(f"join/TAP disagree: {run.label} {key[1]}: join={j} tap={t}")
    return out


def replay_check(
    runs: Sequence[RunResult],
    expectations: dict,
    expectations_name: str = "fixtures/installer/expectations.toml",
) -> dict:
    """Per-run comparison against expectations.toml, for the explicit replay-success line."""
    by_sha = {p["sha256"]: p for p in expectations.get("patch", [])}
    mismatches: list[str] = []
    matched = 0
    reproduced: list[str] = []
    inconclusive: list[str] = []
    baseline = next((r for r in runs if r.patch is None), None)
    baseline_green = baseline is not None and baseline.status == "pass"
    for run in runs:
        found = check_expectations([run], expectations)
        mismatches += found
        # Mirrors compute_verdicts: inconclusive runs, and every patch run when the
        # baseline is not green, are never "matched" regardless of the counts.
        if run.status == "inconclusive" or (run.patch is not None and not baseline_green):
            inconclusive.append(run.label)
            continue
        if found:
            continue
        matched += 1
        exp = expectations["baseline"] if run.patch is None else by_sha[run.patch.sha256]
        if run.patch is not None and exp["exit"] != 0:
            reproduced.append(run.label)
    total = len(runs)
    line = (f"replay check: {matched}/{total} runs match "
            f"{expectations_name} (by content sha256)")
    return {"line": line, "matched": matched, "total": total,
            "mismatches": mismatches, "reproduced": reproduced,
            "inconclusive": inconclusive}
