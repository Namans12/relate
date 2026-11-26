"""Evidence manifest to Relate store: build, read-only access, queries, snapshot."""
import os
import tempfile
import tomllib
from collections.abc import Sequence
from pathlib import Path

import relate

_REQUIRED = {
    "upstream": ("repo", "revision"),
    "decision": ("id", "title", "status", "rule", "reason", "source_path",
                 "context_lines", "consequence_lines"),
    "citation": ("file", "decision", "lines", "curated"),
    "commit": ("sha", "subject", "implements"),
    "check": ("decision", "name", "kind", "number_at_pin", "file", "lines", "evidence"),
}
_KEY = {"File": "path", "Decision": "id", "Check": "name",
        "Commit": "sha", "Upstream": "revision", "Patch": "id", "Run": "id",
        "Observation": "id"}

# Read-only connections handed out by open_readonly, so build_store can refuse
# to replace a store that is still open.
_open_stores: list[tuple[Path, object]] = []


def load_manifest(path: Path) -> dict:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    up = data.get("upstream")
    if up is None:
        raise ValueError("manifest is missing required table 'upstream'")
    for key in _REQUIRED["upstream"]:
        if key not in up:
            raise ValueError(f"manifest [upstream] is missing required key '{key}'")
    for section in ("decision", "citation", "commit", "check"):
        items = data.get(section)
        if not items:
            raise ValueError(f"manifest is missing required section '[[{section}]]'")
        for i, item in enumerate(items):
            for key in _REQUIRED[section]:
                if key not in item:
                    raise ValueError(
                        f"manifest [[{section}]] #{i + 1} is missing required key '{key}'"
                    )
    ids = {d["id"] for d in data["decision"]}
    for section, field in (("citation", "decision"), ("commit", "implements"),
                           ("check", "decision")):
        for item in data[section]:
            if item[field] not in ids:
                raise ValueError(
                    f"manifest [[{section}]] references unknown decision '{item[field]}'"
                )
    return data


def _blob(manifest: dict, path: str, lines: Sequence[int]) -> str:
    a, b = lines
    return (f"https://github.com/{manifest['upstream']['repo']}/blob/"
            f"{manifest['upstream']['revision']}/{path}#L{a}-L{b}")


def _populate(conn, m: dict) -> None:
    up = m["upstream"]
    conn.execute("CREATE (:Upstream {repo: $repo, revision: $rev})",
                 {"repo": up["repo"], "rev": up["revision"]})
    for d in m["decision"]:
        conn.execute(
            "CREATE (:Decision {id: $id, title: $title, status: $status, rule: $rule, "
            "reason: $reason, url: $url, consequences_url: $curl})",
            {"id": d["id"], "title": d["title"], "status": d["status"],
             "rule": d["rule"], "reason": d["reason"],
             "url": _blob(m, d["source_path"], d["context_lines"]),
             "curl": _blob(m, d["source_path"], d["consequence_lines"])})
    for c in m["citation"]:
        conn.execute("MERGE (:File {path: $p})", {"p": c["file"]})
        conn.execute(
            "MATCH (f:File {path: $p}), (d:Decision {id: $d}) "
            "CREATE (f)-[:CITES {url: $url, curated: $cur}]->(d)",
            {"p": c["file"], "d": c["decision"], "cur": bool(c["curated"]),
             "url": _blob(m, c["file"], c["lines"])})
    for c in m["commit"]:
        conn.execute(
            "CREATE (:Commit {sha: $sha, subject: $subj, url: $url})",
            {"sha": c["sha"], "subj": c["subject"],
             "url": f"https://github.com/{up['repo']}/commit/{c['sha']}"})
        conn.execute(
            "MATCH (c:Commit {sha: $sha}), (d:Decision {id: $d}) "
            "CREATE (c)-[:IMPLEMENTS]->(d)",
            {"sha": c["sha"], "d": c["implements"]})
    for k in m["check"]:
        conn.execute(
            "CREATE (:Check {name: $name, kind: $kind, number_at_pin: $n, "
            "url: $url, evidence: $ev})",
            {"name": k["name"], "kind": k["kind"], "n": int(k["number_at_pin"]),
             "url": _blob(m, k["file"], k["lines"]), "ev": k["evidence"]})
        conn.execute(
            "MATCH (d:Decision {id: $d}), (k:Check {name: $name}) "
            "CREATE (d)-[:CHECKED_BY]->(k)",
            {"d": k["decision"], "name": k["name"]})


def build_store(manifest: Path, out: Path) -> None:
    """Build the store from the manifest into a temp file, then replace `out`."""
    m = load_manifest(manifest)
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
            _populate(conn, m)
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
    "MATCH (f:File {path: $path})-[c:CITES]->(d:Decision), "
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
