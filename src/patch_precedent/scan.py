"""Scan every explicit ADR-NNNN mention in the pinned upstream into a TSV index."""
import re
import subprocess
from pathlib import Path

from . import pins
from .upstream import UpstreamUnavailable, ensure_upstream

COLUMNS = {
    "citations": ("path", "adr", "first_line", "count"),
    "decisions": ("adr", "title", "status", "record_path"),
}
# Upstream ADR headers vary: "# ADR-0580: T", "# 0004. T", "# T"; "Status: X" or "- **Status**: X".
_TITLE_RE = re.compile(r"^# (?:ADR[- ]\d{4}[:.]?\s+|\d{4}[:.]?\s+)?(.*\S)\s*$")
_STATUS_RE = re.compile(r"^(?:[-*]\s+)?(?:\*\*)?Status(?::\*\*|\*\*:|:)\s*(.+?)\s*$", re.M)
_RECORD_RE = re.compile(r"^(\d{4})[^/]*\.md$")


def parse_grep_output(text: str) -> dict[tuple[str, str], tuple[int, int]]:
    """`<sha>:<path>:<line>:<ADR-NNNN>` lines -> {(path, adr): (first_line, count)}."""
    out: dict[tuple[str, str], tuple[int, int]] = {}
    for line in text.splitlines():
        if not line:
            continue
        _sha, rest = line.split(":", 1)
        path, line_no, adr = rest.rsplit(":", 2)
        n = int(line_no)
        first, count = out.get((path, adr), (n, 0))
        out[(path, adr)] = (min(first, n), count + 1)
    return out


def parse_adr_header(text: str) -> tuple[str, str]:
    first = text.split("\n", 1)[0].rstrip("\r")
    m = _TITLE_RE.match(first)
    s = _STATUS_RE.search(text)
    return (m.group(1) if m else "", s.group(1) if s else "unknown")


def _git(repo: Path, *args: str, input: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "--git-dir", str(repo), *args], input=input, capture_output=True
    )


def _read_blobs(repo: Path, sha: str, paths: list[str]) -> dict[str, str]:
    """Read many blobs through one `git cat-file --batch`."""
    if not paths:
        return {}
    r = _git(repo, "cat-file", "--batch",
             input="".join(f"{sha}:{p}\n" for p in paths).encode())
    if r.returncode != 0:
        raise UpstreamUnavailable(f"git cat-file failed in {repo}: {r.stderr.decode().strip()}")
    buf, pos, out = r.stdout, 0, {}
    for p in paths:
        nl = buf.index(b"\n", pos)
        header = buf[pos:nl].split()
        if len(header) != 3 or header[1] != b"blob":
            raise UpstreamUnavailable(f"cannot read {p} at {sha[:12]}: {buf[pos:nl].decode()}")
        size = int(header[2])
        out[p] = buf[nl + 1:nl + 1 + size].decode("utf-8", "replace")
        pos = nl + 1 + size + 1
    return out


def scan(sha: str = pins.UPSTREAM_SHA) -> tuple[list[tuple], list[tuple]]:
    repo = ensure_upstream(sha)
    g = _git(repo, "grep", "-I", "-n", "-o", "-E", "ADR-[0-9]{4}", sha, "--", ".", ":!docs/adr")
    if g.returncode > 1:
        raise UpstreamUnavailable(f"git grep failed in {repo}: {g.stderr.decode().strip()}")
    pairs = parse_grep_output(g.stdout.decode("utf-8", "replace"))
    citations = [(p, a, f, c) for (p, a), (f, c) in sorted(pairs.items())]

    ls = _git(repo, "ls-tree", "--name-only", sha, "docs/adr/")
    if ls.returncode != 0:
        raise UpstreamUnavailable(f"git ls-tree failed in {repo}: {ls.stderr.decode().strip()}")
    records: dict[str, str] = {}
    for p in ls.stdout.decode("utf-8").splitlines():
        m = _RECORD_RE.match(p.rsplit("/", 1)[-1])
        if m:
            records[f"ADR-{m.group(1)}"] = p
    blobs = _read_blobs(repo, sha, sorted(records.values()))
    decisions = []
    for adr in sorted(set(records) | {a for _, a in pairs}):
        path = records.get(adr, "")
        title, status = parse_adr_header(blobs[path]) if path else ("", "unknown")
        decisions.append((adr, title, status, path))
    return citations, decisions


def write_tsv(path: Path, header_comment_lines: list[str], rows: list[tuple]) -> None:
    """Columns come from the kind named in the first comment line."""
    kind = header_comment_lines[0].rsplit(" ", 1)[-1]
    lines = [*header_comment_lines, "\t".join(COLUMNS[kind])]
    for row in rows:
        fields = [str(f) for f in row]
        if any("\t" in f or "\n" in f or "\r" in f for f in fields):
            raise ValueError(f"field contains a tab or newline: {row!r}")
        lines.append("\t".join(fields))
    Path(path).write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def read_tsv(path: Path) -> tuple[dict[str, str], list[tuple]]:
    lines = Path(path).read_bytes().decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    meta: dict[str, str] = {}
    body = []
    for line in lines:
        if line.startswith("# "):
            if line.startswith("# patch-precedent scanned "):
                meta["kind"] = line.rsplit(" ", 1)[-1]
            elif line.startswith("# upstream "):
                meta["upstream"] = line[len("# upstream "):]
            elif line.startswith("# revision "):
                meta["revision"] = line[len("# revision "):]
        else:
            body.append(line)
    return meta, [tuple(r.split("\t")) for r in body[1:]]  # body[0] is the column header


def write_index(out_dir: Path, sha: str = pins.UPSTREAM_SHA) -> tuple[list[tuple], list[tuple]]:
    citations, decisions = scan(sha)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("citations", citations), ("decisions", decisions)):
        write_tsv(out_dir / f"{kind}.tsv", [
            f"# patch-precedent scanned {kind}",
            f"# upstream {pins.UPSTREAM_URL}",
            f"# revision {sha}",
        ], rows)
    return citations, decisions
