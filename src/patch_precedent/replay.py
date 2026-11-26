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
