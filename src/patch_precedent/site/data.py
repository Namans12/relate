"""The single data source for every website page, computed from committed inputs."""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from .. import store as _store
from ..diffparse import header_path
from ..text import prose

__all__ = [
    "SiteDataError", "prose", "fill", "literal_query", "CheckRow", "DecisionCard", "Cited",
    "DiffLine", "DiffFile", "PatchPage", "EvalView", "StoreStats", "SiteData", "load_site_data",
]

RESULTS_DIR = "eval/results/20261127T040059Z"
SCENARIO_TITLES = {"installer": "Installer", "release": "Release"}
MODEL_NAME = "Claude Sonnet"
_BOUNDARY = {"consistent", "no_decision"}


class SiteDataError(Exception):
    pass


class _Strict(dict):
    def __missing__(self, key):
        raise SiteDataError(f"no value for {{{key}}}")


def fill(template: str, values: Mapping[str, object]) -> str:
    try:
        return template.format_map(_Strict(values))
    except (ValueError, IndexError, KeyError, AttributeError) as e:
        if isinstance(e, SiteDataError):
            raise
        raise SiteDataError(f"bad placeholder in {template!r}: {e}") from e


_PARAM = re.compile(r"\$([A-Za-z_]\w*)")


def literal_query(query: str, params: Mapping[str, str]) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        if name not in params:
            raise SiteDataError(f"query parameter ${name} has no value")
        v = str(params[name]).replace("\\", "\\\\").replace("'", "\\'")
        return f"'{v}'"
    return _PARAM.sub(sub, query)


@dataclass(frozen=True)
class CheckRow:
    number: int
    kind: str
    name: str
    short: str
    url: str
    observed: Literal["ok", "not ok", "not observed"]


@dataclass(frozen=True)
class DecisionCard:
    id: str
    title: str
    status: str
    rule: str
    reason: str
    decision_url: str
    consequences_url: str
    citation_url: str
    commit_sha: str
    commit_subject: str
    commit_url: str
    checks: tuple[CheckRow, ...]


@dataclass(frozen=True)
class Cited:
    id: str
    title: str
    status: str
    url: str


@dataclass(frozen=True)
class DiffLine:
    kind: Literal["hunk", "add", "del", "ctx"]
    old: int | None
    new: int | None
    text: str


@dataclass(frozen=True)
class DiffFile:
    path: str
    added: int
    removed: int
    lines: tuple[DiffLine, ...]


@dataclass(frozen=True)
class PatchPage:
    slug: str
    scenario: str
    label: str
    scenario_title: str
    fixture: str
    sha256: str
    diff: tuple[DiffFile, ...]
    status: str
    exit_code: int
    passed: int
    failed: int
    total: int
    failing_numbers: list
    duration_s: float
    verdict: dict
    decisions: tuple[DecisionCard, ...]
    also_cites: tuple[Cited, ...]
    summary: str
    heading: str
    body: str
    explain_cmd: str
    queries: tuple[tuple[str, str], ...]
    prev_slug: str | None
    next_slug: str | None


@dataclass(frozen=True)
class EvalView:
    arms: dict
    cases: tuple[dict, ...]
    per_run: tuple[dict, ...]
    intro: str
    caveats: tuple[str, ...]
    metrics: tuple[dict, ...]


@dataclass(frozen=True)
class StoreStats:
    nodes: int
    rels: int
    by_label: dict
    by_type: dict


@dataclass(frozen=True)
class SiteData:
    patches: tuple[PatchPage, ...]
    eval: EvalView
    store: StoreStats
    recording: dict
    content: dict
    home_chain: PatchPage


# ---- inputs -------------------------------------------------------------------------

def _need(path: Path) -> Path:
    if not path.is_file():
        raise SiteDataError(f"missing input file: {path}")
    return path


def _toml(path: Path) -> dict:
    with open(_need(path), "rb") as fh:
        return tomllib.load(fh)


def _json(path: Path):
    return json.loads(_need(path).read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in _need(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ---- diff ---------------------------------------------------------------------------

_HUNK = re.compile(r"@@ -(\d+)(?:,\d+)? \+(\d+)")


def parse_diff(text: str) -> tuple[DiffFile, ...]:
    files: list[tuple[str, list[DiffLine]]] = []
    old = new = 0
    in_hunk = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            files.append((header_path(line) or "", []))
            in_hunk = False
            continue
        if not files:
            continue
        lines = files[-1][1]
        m = _HUNK.match(line)
        if m:
            old, new, in_hunk = int(m.group(1)), int(m.group(2)), True
            lines.append(DiffLine("hunk", None, None, line))
        elif not in_hunk or line.startswith("\\"):
            continue
        elif line.startswith("+"):
            lines.append(DiffLine("add", None, new, line[1:]))
            new += 1
        elif line.startswith("-"):
            lines.append(DiffLine("del", old, None, line[1:]))
            old += 1
        else:
            lines.append(DiffLine("ctx", old, new, line[1:]))
            old += 1
            new += 1
    return tuple(
        DiffFile(path, sum(1 for ln in ls if ln.kind == "add"),
                 sum(1 for ln in ls if ln.kind == "del"), tuple(ls))
        for path, ls in files)


# ---- patches ------------------------------------------------------------------------

def _failing_text(nums: list[int]) -> str:
    tags = [f"#{n}" for n in sorted(nums)]
    return tags[0] if len(tags) == 1 else ", ".join(tags[:-1]) + " and " + tags[-1] if tags else ""


def failing_label(nums: list[int]) -> str:
    """"Check #64" or "Checks #7 and #193"."""
    return ("Check " if len(nums) == 1 else "Checks ") + _failing_text(nums)


def checks_phrase(n: int) -> str:
    """Subject phrase for "passed": "The linked check", "Both linked checks", "All 3 linked checks"."""
    if n == 0:
        return "No linked checks"
    if n == 1:
        return "The linked check"
    if n == 2:
        return "Both linked checks"
    return f"All {n} linked checks"


def misses_sit(n: int) -> str:
    """Clause subject and verb for baseline verdict misses."""
    if n == 0:
        return "no baseline verdict misses sit"
    if n == 1:
        return "the one baseline verdict miss sits"
    if n == 2:
        return "both baseline verdict misses sit"
    return f"all {n} baseline verdict misses sit"


def _checks(rows: list[dict], observed: dict, content: dict) -> tuple[CheckRow, ...]:
    out: dict[str, CheckRow] = {}
    for r in rows:
        name = r["check"]
        if name in out:
            continue
        short = content.get("checks", {}).get(name, {}).get("short")
        if short is None:
            raise SiteDataError(f"no [checks] short label for {name!r}")
        o = observed.get(name)
        state = "not observed" if o is None else ("ok" if o["ok"] else "not ok")
        number = o["number"] if o is not None and o.get("number") is not None \
            else r["check_number_at_pin"]
        out[name] = CheckRow(number, r["check_kind"], name, short, r["check_url"], state)
    return tuple(sorted(out.values(), key=lambda c: (c.number, c.name)))


def _cards(rows: list[dict], observed: dict, content: dict) -> tuple[DecisionCard, ...]:
    by_decision: dict[str, list[dict]] = {}
    for r in rows:
        by_decision.setdefault(r["decision"], []).append(r)
    cards = []
    for did, rs in sorted(by_decision.items()):
        r = rs[0]
        cards.append(DecisionCard(
            did, prose(r["title"]), prose(r["status"]), prose(r["rule"]), prose(r["reason"]),
            r["decision_url"], r["consequences_url"], r["citation_url"],
            r["implementation"], prose(r["commit_subject"]), r["commit_url"],
            _checks(rs, observed, content)))
    return tuple(cards)


def _build_patch(run: dict, rec: dict, scenario: str, fixture: str, root: Path, conn,
                 content: dict, pc: dict, shared: Mapping[str, object]) -> PatchPage:
    label = run["label"]
    files = tuple(run["changed_files"])
    ev = _store.evidence_for_paths(conn, files)
    cited = _store.cited_decisions(conn, files)
    ev_rows = [r for f in files for r in ev[f]]
    observed = run["observed"]
    decisions = _cards(ev_rows, observed, content)
    seen: set[str] = set()
    also: list[Cited] = []
    for f in files:
        for r in cited[f]:
            if r["curated"] or r["decision"] in seen:
                continue
            seen.add(r["decision"])
            also.append(Cited(r["decision"], prose(r["title"]), prose(r["status"]),
                              r["decision_url"]))
    verdict = next(v for v in rec["verdict_records"] if v["label"] == label)
    nums = sorted(run["failing_numbers"])
    n_checks = sum(len(d.checks) for d in decisions)
    values = {
        **shared,
        "decision": ", ".join(verdict["decisions"]),
        "rule": prose(verdict.get("rule") or "") or (decisions[0].rule if decisions else ""),
        "failing": _failing_text(nums),
        "failing_label": failing_label(nums),
        "passed": run["passed"], "total": run["total"],
        "checks": n_checks, "checks_phrase": checks_phrase(n_checks),
        "file": files[0] if files else "",
    }
    body = prose(fill(pc["body"], values))
    diff = parse_diff(_need(root / fixture).read_text(encoding="utf-8"))
    queries = (
        ("Decision chain", "\n\n".join(
            literal_query(_store._EVIDENCE_QUERY, {"path": f}) for f in files)),
        ("Every cited decision", "\n\n".join(
            literal_query(_store._CITED_QUERY, {"path": f}) for f in files)),
    )
    return PatchPage(
        slug=f"{scenario}-{label}", scenario=scenario, label=label,
        scenario_title=SCENARIO_TITLES.get(scenario, scenario.title()), fixture=fixture,
        sha256=run["sha256"], diff=diff, status=run["status"], exit_code=run["exit_code"],
        passed=run["passed"], failed=run["failed"], total=run["total"],
        failing_numbers=list(run["failing_numbers"]), duration_s=run["duration_s"],
        verdict=verdict, decisions=decisions, also_cites=tuple(also),
        summary=pc["summary"], heading=pc["heading"], body=body,
        explain_cmd=f"uv run patch-precedent explain {fixture}", queries=queries,
        prev_slug=None, next_slug=None)


# ---- evaluation ---------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{int(x * 100 + 0.5)}%"


def _metrics(arms: dict) -> tuple[dict, ...]:
    b, g = arms["baseline"], arms["graph"]

    def ratio(label, key, kk):
        return {"key": key, "label": label,
                "baseline": f"{b[kk]}/{b['n']}", "graph": f"{g[kk]}/{g['n']}",
                "baseline_frac": b[kk] / b["n"], "graph_frac": g[kk] / g["n"]}

    def mean(label, key, kk):
        return {"key": key, "label": label, "baseline": _pct(b[kk]), "graph": _pct(g[kk]),
                "baseline_frac": b[kk], "graph_frac": g[kk]}

    def lower(label, key, bv, gv, fmt):
        top = max(bv, gv) or 1
        return {"key": key, "label": label, "baseline": fmt(bv), "graph": fmt(gv),
                "baseline_frac": bv / top, "graph_frac": gv / top}

    return (
        ratio("Verdict correct", "verdict", "verdict_k"),
        ratio("Decisions exact", "decisions_exact", "decisions_exact_k"),
        mean("Decision recall", "decision_recall", "decisions_recall_mean"),
        mean("Checks recall", "checks_recall", "checks_recall_mean"),
        mean("Catching-checks recall", "catching_recall", "catching_recall_mean"),
        lower("Unsupported claims", "unsupported", b["unsupported_total"],
              g["unsupported_total"], lambda v: f"{v}"),
        lower("Median time to first correct citation", "citation_time",
              b["citation_median_s"], g["citation_median_s"], lambda v: f"{v:.1f} s"),
        lower("Mean turns", "turns", b["turns_mean"], g["turns_mean"], lambda v: f"{v:.1f}"),
        lower("Cost", "cost", b["cost_total"], g["cost_total"], lambda v: f"${v:.2f}"),
    )


def _eval_inputs(root: Path):
    rdir = root / RESULTS_DIR
    results = _json(rdir / "results.json")
    scored = _jsonl(rdir / "scored.jsonl")
    cases_toml = _toml(root / "eval" / "cases.toml")["cases"]
    expected = {c["id"]: c["verdict"] for c in cases_toml}
    arms = results["arms"]
    b, g = arms["baseline"], arms["graph"]
    return results, scored, cases_toml, expected, arms, b, g


def _shared_values(root: Path, rec: dict) -> dict:
    results, scored, cases_toml, expected, arms, b, g = _eval_inputs(root)
    return {
        "model": MODEL_NAME,
        "repeats": max(r["repeat"] for r in scored),
        "cases": len(cases_toml),
        "n": b["n"],
        "graph_runs": g["replay_found_n"],
        "replay_found": g["replay_found_k"],
        "replay_missed": g["replay_found_n"] - g["replay_found_k"],
        "baseline_verdict_k": b["verdict_k"],
        "graph_verdict_k": g["verdict_k"],
        "baseline_verdict_misses": b["n"] - b["verdict_k"],
        "baseline_misses_sit": misses_sit(b["n"] - b["verdict_k"]),
        "catching_recall_baseline": _pct(b["catching_recall_mean"]),
        "catching_recall_graph": _pct(g["catching_recall_mean"]),
        "demo_seconds": round(rec["elapsed_s"]),
    }


def _eval_view(root: Path, content: dict, values: Mapping[str, object]) -> EvalView:
    results, scored, cases_toml, expected, arms, b, g = _eval_inputs(root)

    for r in scored:
        if r["arm"] == "baseline" and r["verdict_correct"] is False:
            exp = expected.get(r["case"])
            if exp not in _BOUNDARY or r["verdict"] not in _BOUNDARY:
                raise SiteDataError("caveat 'boundary' no longer true")

    cases = tuple(
        {"id": c["id"], "label": Path(c["fixture"]).stem, "scenario": c["scenario"],
         "expected": c["verdict"], **results["cases"][c["id"]]}
        for c in cases_toml)
    per_run = tuple(
        {k: r.get(k) for k in ("case", "arm", "repeat", "verdict", "verdict_correct", "turns",
                               "cost_usd", "tool_replay_found")}
        for r in scored)
    res = content.get("results")
    if not res:
        raise SiteDataError("content.toml has no [results] table")
    return EvalView(
        arms=arms, cases=cases, per_run=per_run, intro=prose(fill(res["intro"], values)),
        caveats=tuple(prose(fill(c, values)) for c in res["caveats"]), metrics=_metrics(arms))


# ---- store --------------------------------------------------------------------------

def _store_stats(path: Path) -> StoreStats:
    conn = _store.open_readonly(_need(path))
    try:
        one = lambda q: next(iter(conn.execute(q))).data()["c"]  # noqa: E731
        by_label: dict[str, int] = {}
        for r in conn.execute("MATCH (n) RETURN labels(n) AS l, count(n) AS c"):
            d = r.data()
            by_label[d["l"][0]] = d["c"]
        by_type = {d["t"]: d["c"] for d in
                   (r.data() for r in conn.execute(
                       "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c"))}
        return StoreStats(one("MATCH (n) RETURN count(n) AS c"),
                          one("MATCH ()-[r]->() RETURN count(r) AS c"), by_label, by_type)
    finally:
        conn.close()


def _fill_all(value, values: Mapping[str, object]):
    if isinstance(value, str):
        return prose(fill(value, values))
    if isinstance(value, list):
        return [_fill_all(v, values) for v in value]
    if isinstance(value, dict):
        return {k: _fill_all(v, values) for k, v in value.items()}
    return value


# ---- entry point --------------------------------------------------------------------

def load_site_data(root: Path) -> SiteData:
    root = Path(root)
    rec = _json(root / "recorded" / "demo-all.json")
    content = _toml(root / "site" / "content.toml")
    shared = _shared_values(root, rec)
    for section in ("home", "use", "relate"):
        if section not in content:
            raise SiteDataError(f"content.toml has no [{section}] table")
        content[section] = _fill_all(content[section], shared)
    store_path = root / "data" / "precedent.rl"
    _need(store_path)

    order = list(content.get("patches", {}))
    found: list[tuple[str, dict, dict]] = []
    for scenario, sc in rec["scenarios"].items():
        for run in sc["runs"]:
            if run.get("patch_id") is None:
                continue
            found.append((scenario, run, sc))
    pages_by_key: dict[str, PatchPage] = {}
    conn = _store.open_readonly(store_path)
    try:
        for scenario, run, sc in found:
            key = f"{scenario}/{run['label']}"
            pc = content.get("patches", {}).get(key)
            if pc is None:
                raise SiteDataError(f"no content entry for [patches.\"{key}\"]")
            fixture = f"fixtures/{scenario}/{run['label']}.patch"
            pages_by_key[key] = _build_patch(run, sc, scenario, fixture, root, conn, content, pc,
                                             shared)
    finally:
        conn.close()
    missing = [k for k in order if k not in pages_by_key]
    if missing:
        raise SiteDataError(f"content entry has no recorded patch: {missing[0]}")

    keys = list(pages_by_key)
    keys.sort(key=order.index)
    patches = []
    for i, k in enumerate(keys):
        p = pages_by_key[k]
        patches.append(_replace_links(
            p, keys[i - 1].replace("/", "-") if i > 0 else None,
            keys[i + 1].replace("/", "-") if i + 1 < len(keys) else None))
    home = next((p for p in patches if p.slug == "installer-token-header"), None)
    if home is None:
        raise SiteDataError("recording has no installer/token-header patch")
    return SiteData(tuple(patches), _eval_view(root, content, shared), _store_stats(store_path),
                    rec, content, home)


def _replace_links(p: PatchPage, prev: str | None, nxt: str | None) -> PatchPage:
    import dataclasses
    return dataclasses.replace(p, prev_slug=prev, next_slug=nxt)
