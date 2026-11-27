"""Inline SVG graphs for the website (no JS library; deterministic output)."""
from __future__ import annotations

from html import escape

from ..text import prose
from .data import PatchPage, StoreStats

__all__ = ["patch_graph_svg", "schema_svg"]

INK, INK2, INK3 = "#1B1F2A", "#4A4F5C", "#686D79"
SUNK, LINE, LINE2, SURFACE = "#F3EEE4", "#E7E0D3", "#D9D1C2", "#FFFFFF"
BRIGHT, PASS, FAIL = "#E36B47", "#2F7D57", "#B4472A"
SANS = "Inter, system-ui, sans-serif"
MONO = "'JetBrains Mono', ui-monospace, monospace"

W = 760
X_PATCH, X_FILE, X_DEC, X_CHECK = 76, 255, 485, 668


def _n(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _trunc(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _e(text: str) -> str:
    return escape(text, quote=True)


def _spread(count: int, center: float, gap: float) -> list[float]:
    return [center + (i - (count - 1) / 2) * gap for i in range(count)]


def _edge(x1, y1, x2, y2, f, t, cls="edge", stroke=LINE2, dash=False) -> str:
    mx = (x1 + x2) / 2
    d = f"M{_n(x1)} {_n(y1)}C{_n(mx)} {_n(y1)} {_n(mx)} {_n(y2)} {_n(x2)} {_n(y2)}"
    da = ' stroke-dasharray="5 4"' if dash else ""
    return (f'<path class="{cls}" data-from="{_e(f)}" data-to="{_e(t)}" d="{d}" fill="none" '
            f'stroke="{stroke}" stroke-width="1.5"{da}/>')


def _text(x, y, s, size=12, fill=INK, anchor="middle", mono=False, weight=None) -> str:
    w = f' font-weight="{weight}"' if weight else ""
    return (f'<text x="{_n(x)}" y="{_n(y)}" text-anchor="{anchor}" font-size="{size}" fill="{fill}" '
            f'font-family="{MONO if mono else SANS}"{w}>{_e(s)}</text>')


def _node(cls: str, nid: str, title: str, body: str, verbatim: bool = False) -> str:
    v = ' data-verbatim="1"' if verbatim else ""
    return (f'<g class="node {cls}" tabindex="0" data-id="{_e(nid)}"{v}><title>{_e(title)}</title>'
            f"{body}</g>")


def _decision_sources(d, files: list[str]):
    """File indexes whose path the decision's citation names; None means draw from the patch."""
    if len(files) == 1:
        return [0]
    hit = [i for i, f in enumerate(files) if f in d.citation_url]
    return hit or None


def patch_graph_svg(page: PatchPage) -> str:
    files = [f.path for f in page.diff]
    decisions = page.decisions
    scanned = page.also_cites
    commits: list[tuple[str, str]] = []
    for d in decisions:
        if d.commit_sha and d.commit_sha not in [c[0] for c in commits]:
            commits.append((d.commit_sha, d.commit_subject))
    checks = [(d, c) for d in decisions for c in d.checks]

    # decision-column slots (top to bottom): commits, decisions, scanned
    dec_y: dict[str, float] = {}
    commit_y: dict[str, float] = {}
    scan_y: list[float] = []
    y = 40.0
    for sha, _ in commits:
        commit_y[sha] = y
        y += 44
    if commits:
        y += 8
    for d in decisions:
        y += 20
        dec_y[d.id] = y
        y += 82
    if not decisions:
        y += 20
        none_y = y
        y += 40
    if scanned and decisions:
        y += 4
    for _ in scanned:
        scan_y.append(y)
        y += 30
    height = max(y + 20, 40 + 34 * len(checks) + 40, 40 + 36 * len(files) + 40, 150)
    mid = height / 2

    patch_y = mid
    file_ys = _spread(len(files), mid, 44)
    check_ys = _spread(len(checks), mid, 34)

    edges: list[str] = []
    nodes: list[str] = []

    # patch node + edges
    pid = "patch"
    for i, f in enumerate(files):
        edges.append(_edge(X_PATCH + 64, patch_y, X_FILE - 95, file_ys[i], pid, f"file:{f}"))
    nodes.append(_node(
        "n-patch", pid, page.label,
        f'<rect x="{X_PATCH - 64}" y="{_n(patch_y - 18)}" width="128" height="36" rx="8" fill="{INK}" stroke="{INK}"/>'
        + _text(X_PATCH, patch_y + 4, _trunc(prose(page.label), 14), 14, SURFACE, weight=600)))

    for i, f in enumerate(files):
        label = f if len(f) <= 23 else "…" + f[-22:]
        nodes.append(_node(
            "n-file", f"file:{f}", f,
            f'<rect x="{X_FILE - 95}" y="{_n(file_ys[i] - 15)}" width="190" height="30" rx="3" fill="{SUNK}" stroke="{LINE2}"/>'
            + _text(X_FILE, file_ys[i] + 5, label, 13, INK, mono=True)))

    # commits
    for sha, subj in commits:
        cy = commit_y[sha]
        nodes.append(_node(
            "n-commit", f"commit:{sha}", f"commit {sha[:8]} {prose(subj)}",
            f'<rect x="{X_DEC - 7}" y="{_n(cy - 7)}" width="14" height="14" fill="{INK3}" stroke="{INK3}"/>'
            + _text(X_DEC + 16, cy + 5, sha[:8], 13, INK3, "start", mono=True)))
    for d in decisions:
        if d.commit_sha in commit_y:
            edges.append(_edge(X_DEC, commit_y[d.commit_sha] + 7, X_DEC, dec_y[d.id] - 16,
                               f"commit:{d.commit_sha}", f"dec:{d.id}"))

    # decisions
    for d in decisions:
        dy = dec_y[d.id]
        title = prose(d.title)
        src = _decision_sources(d, files)
        if src is None:
            edges.append(_edge(X_PATCH + 64, patch_y, X_DEC - 16, dy, pid, f"dec:{d.id}"))
        else:
            for i in src:
                edges.append(_edge(X_FILE + 95, file_ys[i], X_DEC - 16, dy, f"file:{files[i]}", f"dec:{d.id}"))
        nodes.append(_node(
            "n-decision", f"dec:{d.id}", f"{d.id} {title} ({prose(d.status)})",
            f'<circle cx="{X_DEC}" cy="{_n(dy)}" r="16" fill="{INK}" stroke="{BRIGHT}" stroke-width="3"/>'
            + _text(X_DEC, dy + 35, d.id, 14, INK, mono=True, weight=600)
            + _text(X_DEC, dy + 52, _trunc(title, 28), 14, INK2)))
    if not decisions:
        for i, f in enumerate(files):
            edges.append(_edge(X_FILE + 95, file_ys[i], X_DEC - 72, none_y, f"file:{f}", "none",
                               dash=True))
        nodes.append(_node(
            "n-none", "none", "no linked decision",
            f'<rect x="{X_DEC - 72}" y="{_n(none_y - 16)}" width="144" height="34" rx="8" fill="{SURFACE}" '
            f'stroke="{LINE2}" stroke-dasharray="5 4"/>'
            + _text(X_DEC, none_y + 5, "no linked decision", 14, INK3)))

    # scanned
    for c, sy in zip(scanned, scan_y):
        if len(files) == 1:
            edges.append(_edge(X_FILE + 95, file_ys[0], X_DEC - 5, sy, f"file:{files[0]}", f"scan:{c.id}",
                               cls="edge edge-scanned", dash=True))
        else:
            edges.append(_edge(X_PATCH + 64, patch_y, X_DEC - 5, sy, pid, f"scan:{c.id}",
                               cls="edge edge-scanned", dash=True))
        nodes.append(_node(
            "n-scanned", f"scan:{c.id}", f"{c.id} {prose(c.title)} ({prose(c.status)}), scanned" + ("" if len(files) == 1 else " (scanned list is for the whole patch)"),
            f'<circle cx="{X_DEC}" cy="{_n(sy)}" r="5" fill="{SURFACE}" stroke="{INK3}" stroke-width="1.5"/>'
            + _text(X_DEC + 14, sy + 5, c.id, 13, INK3, "start", mono=True)))

    # checks
    for (d, c), cy in zip(checks, check_ys):
        cid = f"chk:{d.id}:{c.number}"
        kind = {"ok": "ok", "not ok": "fail"}.get(c.observed, "none")
        col = {"ok": PASS, "fail": FAIL, "none": LINE2}[kind]
        edges.append(_edge(X_DEC + 16, dec_y[d.id], X_CHECK - 13, cy, f"dec:{d.id}", cid,
                           cls="edge edge-fail" if kind == "fail" else "edge",
                           stroke=FAIL if kind == "fail" else LINE2))
        nodes.append(_node(
            f"n-check n-check-{kind}", cid, f"#{c.number} {c.name} ({c.observed})",
            f'<circle cx="{X_CHECK}" cy="{_n(cy)}" r="12" fill="{col}" stroke="{col}"/>'
            + _text(X_CHECK + 20, cy + 5, f"#{c.number}", 13, INK, "start", mono=True),
            verbatim=True))

    aria = (f"Graph for patch {prose(page.label)}: {len(files)} changed file(s), "
            f"{len(decisions)} linked decision(s), {len(checks)} check(s), {len(scanned)} scanned decision(s).")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {_n(height)}" width="100%" '
            f'role="img" aria-label="{_e(aria)}" class="patch-graph">'
            + "".join(edges) + "".join(nodes) + "</svg>")


_SCHEMA_NODES = {  # label -> (x, y)
    "Run": (60, 60), "Patch": (225, 60), "File": (395, 60), "Decision": (630, 60),
    "Observation": (225, 200), "Check": (480, 200), "Commit": (630, 200),
}
_REPLAY_ONLY = {"Run", "Patch", "Observation"}
_SCHEMA_EDGES = [
    ("Run", "Patch", "APPLIED"), ("Patch", "File", "CHANGES"), ("File", "Decision", "CITES"),
    ("Commit", "Decision", "IMPLEMENTS"), ("Decision", "Check", "CHECKED_BY"),
    ("Patch", "Observation", "PRODUCED"), ("Observation", "Check", "FOR_CHECK"),
]
_REPLAY_NOTE = "created in each demo run's replay copy, not in the committed store"


def schema_svg(stats: StoreStats) -> str:
    hw, hh = 54, 26
    out: list[str] = []
    for a, b, rel in _SCHEMA_EDGES:
        (x1, y1), (x2, y2) = _SCHEMA_NODES[a], _SCHEMA_NODES[b]
        replay = a in _REPLAY_ONLY or b in _REPLAY_ONLY
        anchor = "middle"
        if y1 == y2:
            sx, ex = (x1 + hw, x2 - hw) if x2 > x1 else (x1 - hw, x2 + hw)
            sy = ey = y1
            lx, ly = (sx + ex) / 2, sy - 8
        elif x1 == x2:
            sx = ex = x1
            sy, ey = (y1 + hh, y2 - hh) if y2 > y1 else (y1 - hh, y2 + hh)
            lx, ly, anchor = sx + 8, (sy + ey) / 2 + 5, "start"
        else:
            sx, sy, ex, ey = x1 - 20, y1 + hh, x2 + 30, y2 - hh
            lx, ly = (sx + ex) / 2 - 10, (sy + ey) / 2 - 12
            anchor = "end"
        count = stats.by_type.get(rel)
        lab = f"{rel} {count}" if count is not None else rel
        cls = "edge edge-replay" if replay else "edge"
        da = ' stroke-dasharray="5 4"' if replay else ""
        out.append(f'<path class="{cls}" data-from="{a}" data-to="{b}" d="M{_n(sx)} {_n(sy)}L{_n(ex)} {_n(ey)}" '
                   f'fill="none" stroke="{INK3}" stroke-width="1.5"{da} marker-end="url(#arr)"/>')
        out.append(_text(lx, ly, lab, 13, INK2, anchor, mono=True))
    for label, (x, y) in _SCHEMA_NODES.items():
        n = stats.by_label.get(label)
        replay = n is None and label in _REPLAY_ONLY
        if replay:
            title = f"{label}: {_REPLAY_NOTE}"
            shape = (f'<rect x="{x - hw}" y="{y - hh}" width="{hw * 2}" height="{hh * 2}" rx="8" '
                     f'fill="{SURFACE}" stroke="{INK3}" stroke-dasharray="5 4"/>')
            count = "per demo run"
        else:
            n = n or 0
            title = f"{label}: {n} nodes"
            shape = (f'<rect x="{x - hw}" y="{y - hh}" width="{hw * 2}" height="{hh * 2}" rx="8" '
                     f'fill="{SUNK}" stroke="{LINE2}"/>')
            count = str(n)
        out.append(_node(
            "n-schema n-replay" if replay else "n-schema", label, title,
            shape + _text(x, y - 3, label, 14, INK, weight=600) + _text(x, y + 16, count, 13, INK2, mono=True)))
    defs = (f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{INK3}"/></marker></defs>')
    legend = _text(20, 268, "Dashed: created in each demo run's replay copy, not in the committed store.", 13, INK3, "start")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 280" width="100%" role="img" '
            f'aria-label="Store schema: node labels and the relationships between them" class="schema-graph">'
            + defs + "".join(out) + legend + "</svg>")
