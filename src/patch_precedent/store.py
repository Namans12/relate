"""Evidence manifest to Relate store: build, read-only access, queries, snapshot."""
import os
import tempfile
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import relate

from . import pins

_REQUIRED = {
    "upstream": ("repo", "revision"),
    "decision": ("id", "title", "status", "rule", "reason", "source_path",
                 "context_lines", "consequence_lines"),
    "citation": ("file", "decision", "lines", "curated"),
    "commit": ("sha", "subject", "implements"),
    "check": ("decision", "name", "kind", "number_at_pin", "file", "lines", "evidence"),  # + harness
}
_KEY = {"File": "path", "Decision": "id", "Check": "name",
        "Commit": "sha", "Upstream": "revision", "Patch": "id", "Run": "id",
        "Observation": "id"}

_BATCH = 1000

# Read-only connections handed out by open_readonly, so build_store can refuse
# to replace a store that is still open.
_open_stores: list[tuple[Path, object]] = []


@dataclass
class Evidence:
    """Everything build_store writes: curated manifests plus the scanned index."""
    repo: str
    revision: str
    decisions: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    commits: list[dict] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)
    scanned_citations: list[dict] = field(default_factory=list)
    scanned_decisions: list[dict] = field(default_factory=list)


def _load_manifest(path: Path) -> dict:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    name = Path(path).name
    up = data.get("upstream")
    if up is None:
        raise ValueError(f"{name}: manifest is missing required table 'upstream'")
    for key in _REQUIRED["upstream"]:
        if key not in up:
            raise ValueError(f"{name}: manifest [upstream] is missing required key '{key}'")
    if up["revision"] != pins.UPSTREAM_SHA:
        raise ValueError(f"{name}: upstream revision {up['revision']} "
                         f"is not the pinned {pins.UPSTREAM_SHA}")
    for section in ("decision", "citation", "commit", "check"):
        items = data.get(section)
        if not items:
            raise ValueError(f"{name}: manifest is missing required section '[[{section}]]'")
        for i, item in enumerate(items):
            for key in _REQUIRED[section]:
                if key not in item:
                    raise ValueError(
                        f"{name}: manifest [[{section}]] #{i + 1} is missing required key '{key}'"
                    )
    ids = {d["id"] for d in data["decision"]}
    for section, fld in (("citation", "decision"), ("commit", "implements"),
                         ("check", "decision")):
        for item in data[section]:
            if item[fld] not in ids:
                raise ValueError(
                    f"{name}: manifest [[{section}]] references unknown decision '{item[fld]}'"
                )
    return data


def _load_scanned(path: Path, kind: str) -> list[dict]:
    from .scan import COLUMNS, read_tsv  # lazy: scan pulls in the upstream module

    name = Path(path).name
    if not Path(path).is_file():
        raise ValueError(f"{name}: scanned index file not found: {path}")
    meta, rows = read_tsv(path)
    if meta.get("revision") != pins.UPSTREAM_SHA:
        raise ValueError(f"{name}: scanned revision {meta.get('revision')} "
                         f"is not the pinned {pins.UPSTREAM_SHA}")
    cols = COLUMNS[kind]
    out = []
    for i, row in enumerate(rows):
        if len(row) != len(cols):
            raise ValueError(f"{name}: row {i + 1} has {len(row)} fields, expected {len(cols)}")
        out.append(dict(zip(cols, row)))
    return out


def load_evidence(evidence_dir: Path) -> Evidence:
    """Load and validate every curated manifest plus the scanned index."""
    evidence_dir = Path(evidence_dir)
    manifests = sorted(evidence_dir.glob("*.toml"), key=lambda p: p.name)
    if not manifests:
        raise ValueError(f"no *.toml evidence manifests in {evidence_dir}")
    ev: Evidence | None = None
    seen_checks: dict[str, str] = {}
    seen_decisions: dict[str, str] = {}
    for path in manifests:
        m = _load_manifest(path)
        if ev is None:
            ev = Evidence(repo=m["upstream"]["repo"], revision=m["upstream"]["revision"])
        elif m["upstream"]["repo"] != ev.repo:
            raise ValueError(f"{path.name}: upstream repo {m['upstream']['repo']} "
                             f"differs from {ev.repo}")
        for d in m["decision"]:
            if d["id"] in seen_decisions:
                raise ValueError(f"{path.name}: duplicate decision {d['id']} "
                                 f"(also in {seen_decisions[d['id']]})")
            seen_decisions[d["id"]] = path.name
        for k in m["check"]:
            if "harness" not in k:
                raise ValueError(f"{path.name}: check '{k['name']}' is missing "
                                 "required key 'harness'")
            if k["name"] in seen_checks:
                raise ValueError(f"{path.name}: duplicate check name '{k['name']}' "
                                 f"(also in {seen_checks[k['name']]})")
            seen_checks[k["name"]] = path.name
        ev.decisions += m["decision"]
        ev.citations += m["citation"]
        ev.commits += m["commit"]
        ev.checks += m["check"]
    scan_dir = evidence_dir / "scanned"
    ev.scanned_citations = _load_scanned(scan_dir / "citations.tsv", "citations")
    ev.scanned_decisions = _load_scanned(scan_dir / "decisions.tsv", "decisions")
    known = {d["adr"] for d in ev.scanned_decisions}
    for d in ev.decisions:
        if d["id"] not in known:
            raise ValueError(f"curated decision {d['id']} ({seen_decisions[d['id']]}) "
                             "is missing from scanned/decisions.tsv")
    for c in ev.scanned_citations:
        if c["adr"] not in known:
            raise ValueError(f"citations.tsv: {c['path']} cites {c['adr']}, "
                             "which is missing from decisions.tsv")
    return ev


def _blob(ev: Evidence, path: str, lines: Sequence[int]) -> str:
    a, b = lines
    return f"https://github.com/{ev.repo}/blob/{ev.revision}/{path}#L{a}-L{b}"


def _batches(rows: list[dict]):
    for i in range(0, len(rows), _BATCH):
        yield rows[i:i + _BATCH]


def _run(conn, query: str, rows: list[dict]) -> None:
    for chunk in _batches(rows):
        conn.execute(query, {"rows": chunk})


def _decision_rows(ev: Evidence) -> list[dict]:
    cur = {d["id"]: d for d in ev.decisions}
    rows = []
    for d in sorted(ev.scanned_decisions, key=lambda r: r["adr"]):
        c = cur.get(d["adr"])
        if c is not None:
            rows.append({"id": c["id"], "title": c["title"], "status": c["status"],
                         "url": _blob(ev, c["source_path"], c["context_lines"]),
                         "rule": c["rule"], "reason": c["reason"],
                         "curl": _blob(ev, c["source_path"], c["consequence_lines"]),
                         "curated": True})
        else:
            url = (f"https://github.com/{ev.repo}/blob/{ev.revision}/{d['record_path']}"
                   if d["record_path"] else "")
            rows.append({"id": d["adr"], "title": d["title"], "status": d["status"],
                         "url": url, "rule": "", "reason": "", "curl": "",
                         "curated": False})
    return rows


def _citation_rows(ev: Evidence) -> list[dict]:
    edges: dict[tuple[str, str], dict] = {}
    for c in ev.scanned_citations:
        first = int(c["first_line"])
        int(c["count"])  # validate
        edges[(c["path"], c["adr"])] = {
            "path": c["path"], "adr": c["adr"], "scanned": True, "curated": False,
            "line": first,
            "url": f"https://github.com/{ev.repo}/blob/{ev.revision}/{c['path']}#L{first}"}
    for c in ev.citations:
        key = (c["file"], c["decision"])
        prev = edges.get(key)
        edges[key] = {
            "path": c["file"], "adr": c["decision"],
            "scanned": bool(prev and prev["scanned"]), "curated": bool(c["curated"]),
            "line": int(c["lines"][0]), "url": _blob(ev, c["file"], c["lines"])}
    return [edges[k] for k in sorted(edges)]


def _populate(conn, ev: Evidence) -> None:
    conn.execute("CREATE (:Upstream {repo: $repo, revision: $rev})",
                 {"repo": ev.repo, "rev": ev.revision})
    _run(conn,
         "UNWIND $rows AS r CREATE (:Decision {id: r.id, title: r.title, status: r.status, "
         "url: r.url, curated: r.curated})", [
             {k: r[k] for k in ("id", "title", "status", "url", "curated")}
             for r in _decision_rows(ev)])
    _run(conn,
         "UNWIND $rows AS r MATCH (d:Decision {id: r.id}) "
         "SET d.rule = r.rule, d.reason = r.reason, d.consequences_url = r.curl",
         [r for r in _decision_rows(ev) if r["curated"]])
    cites = _citation_rows(ev)
    _run(conn, "UNWIND $rows AS r MERGE (:File {path: r.path})",
         [{"path": p} for p in sorted({c["path"] for c in cites})])
    _run(conn,
         "UNWIND $rows AS r MATCH (f:File {path: r.path}), (d:Decision {id: r.adr}) "
         "CREATE (f)-[:CITES {scanned: r.scanned, curated: r.curated, line: r.line, "
         "url: r.url}]->(d)", cites)
    _run(conn, "UNWIND $rows AS r CREATE (:Commit {sha: r.sha, subject: r.subject, url: r.url})",
         [{"sha": c["sha"], "subject": c["subject"],
           "url": f"https://github.com/{ev.repo}/commit/{c['sha']}"} for c in ev.commits])
    _run(conn,
         "UNWIND $rows AS r MATCH (c:Commit {sha: r.sha}), (d:Decision {id: r.d}) "
         "CREATE (c)-[:IMPLEMENTS]->(d)",
         [{"sha": c["sha"], "d": c["implements"]} for c in ev.commits])
    _run(conn,
         "UNWIND $rows AS r CREATE (:Check {name: r.name, kind: r.kind, "
         "number_at_pin: r.n, url: r.url, evidence: r.ev, harness: r.harness})",
         [{"name": k["name"], "kind": k["kind"], "n": int(k["number_at_pin"]),
           "url": _blob(ev, k["file"], k["lines"]), "ev": k["evidence"],
           "harness": k["harness"]} for k in ev.checks])
    _run(conn,
         "UNWIND $rows AS r MATCH (d:Decision {id: r.d}), (k:Check {name: r.name}) "
         "CREATE (d)-[:CHECKED_BY]->(k)",
         [{"d": k["decision"], "name": k["name"]} for k in ev.checks])


def build_store(evidence_dir: Path, out: Path) -> None:
    """Build the store from all evidence into a temp file, then replace `out`."""
    ev = load_evidence(evidence_dir)
    out = Path(out)
    target = out.resolve()
    _open_stores[:] = [(p, c) for p, c in _open_stores if not c.closed]
    for p, _c in _open_stores:
        if p == target:
            raise ValueError(f"refusing to build over {out}: it is open as a read-only store")
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=out.stem + ".", suffix=".tmp.rl")
    os.close(fd)
    os.unlink(tmp)  # let Relate create the file itself
    try:
        conn = relate.connect(tmp)
        try:
            _populate(conn, ev)
            conn.commit()
        finally:
            conn.close()
        os.chmod(tmp, 0o644)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def open_readonly(path: Path):
    conn = relate.connect(str(path), read_only=True)
    _open_stores.append((Path(path).resolve(), conn))
    return conn


_EVIDENCE_QUERY = (
    "MATCH (f:File {path: $path})-[c:CITES {curated: true}]->(d:Decision), "
    "(d)-[:CHECKED_BY]->(k:Check), (m:Commit)-[:IMPLEMENTS]->(d) "
    "RETURN f.path AS file, d.id AS decision, d.title AS title, d.status AS status, "
    "d.rule AS rule, d.reason AS reason, d.url AS decision_url, c.url AS citation_url, "
    "d.consequences_url AS consequences_url, m.sha AS implementation, "
    "m.subject AS commit_subject, m.url AS commit_url, k.name AS check, "
    "k.kind AS check_kind, k.number_at_pin AS check_number_at_pin, "
    "k.url AS check_url, k.evidence AS check_evidence"
)


def evidence_for_paths(conn, paths: Sequence[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for path in paths:
        rows = [r.data() for r in conn.execute(_EVIDENCE_QUERY, {"path": path})]
        rows.sort(key=lambda r: (r["check_number_at_pin"], r["check"]))
        result[path] = rows
    return result


_CITED_QUERY = (
    "MATCH (f:File {path: $path})-[c:CITES]->(d:Decision) "
    "OPTIONAL MATCH (d)-[:CHECKED_BY]->(k:Check) "
    "RETURN f.path AS file, d.id AS decision, d.title AS title, d.status AS status, "
    "d.url AS decision_url, c.url AS citation_url, c.curated AS curated, "
    "c.scanned AS scanned, count(k) AS n_checks"
)


def cited_decisions(conn, paths: Sequence[str]) -> dict[str, list[dict]]:
    """Every decision each path cites (curated or scanned), curated first."""
    result: dict[str, list[dict]] = {}
    for path in paths:
        rows = []
        for r in conn.execute(_CITED_QUERY, {"path": path}):
            d = r.data()
            d["has_checks"] = d.pop("n_checks") > 0
            rows.append(d)
        rows.sort(key=lambda r: (not r["curated"], r["decision"]))
        result[path] = rows
    return result


def _props(d: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in d.items()))


def snapshot(conn) -> list[tuple]:
    """All nodes and relationships as sorted, hashable tuples."""
    out: list[tuple] = []
    for r in conn.execute("MATCH (n) RETURN labels(n) AS l, properties(n) AS p"):
        d = r.data()
        out.append(("node", d["l"][0], _props(d["p"])))
    for r in conn.execute(
        "MATCH (a)-[r]->(b) RETURN labels(a) AS la, properties(a) AS pa, "
        "type(r) AS t, properties(r) AS pr, labels(b) AS lb, properties(b) AS pb"
    ):
        d = r.data()
        la, lb = d["la"][0], d["lb"][0]
        out.append(("rel", d["t"], la, d["pa"][_KEY[la]], lb, d["pb"][_KEY[lb]],
                    _props(d["pr"])))
    return sorted(out)
