"""Read-only evidence query: decision chains, citations and observed replay results."""
from pathlib import Path

import relate

from .diffparse import changed_files_from_text
from .identity import patch_key
from .scenarios import SCENARIOS
from .store import cited_decisions, evidence_for_paths, open_readonly

NOTE = ('"observed" is the check\'s result in Patch Precedent\'s replay of this exact patch '
        '(matched by its changed lines, ignoring whitespace and context) against the unmodified upstream harness; '
        '"not observed" means no replay of this patch was found, or that replay produced no result '
        'for this check.')


def _replays_newest_first(runs_root: Path) -> list[tuple[str, str, Path]]:
    found = []
    for scenario in SCENARIOS:
        for path in Path(runs_root).glob(f"*/{scenario}/replay.rl"):
            found.append((path.parent.parent.name, scenario, path))
    return sorted(found, key=lambda t: t[0], reverse=True)


def latest_replays(runs_root: Path) -> dict[str, Path]:
    """Scenario name -> newest replay.rl under runs_root/*/<scenario>/ (newest by run dir name)."""
    out: dict[str, Path] = {}
    for _run, scenario, path in _replays_newest_first(runs_root):
        out.setdefault(scenario, path)
    return out


_OBSERVED_QUERY = (
    "MATCH (p:Patch {patch_key: $key})-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(k:Check) "
    "RETURN k.name AS check, o.tap AS tap, o.number AS number"
)


def _find_replay(key: str, runs_root: Path):
    """Newest replay holding this patch key: (replay, observed, skipped replay paths).

    A replay store that cannot be opened or queried is skipped and reported, so one bad
    newest replay never hides older good ones.
    """
    skipped: list[str] = []
    for run, scenario, path in _replays_newest_first(runs_root):
        try:
            conn = open_readonly(path)
            try:
                label = [r.data()["label"] for r in conn.execute(
                    "MATCH (p:Patch {patch_key: $key}) RETURN p.label AS label", {"key": key})]
                if not label:
                    continue
                observed = {}
                for r in conn.execute(_OBSERVED_QUERY, {"key": key}):
                    d = r.data()
                    observed[d["check"]] = (d["tap"], d["number"])
            finally:
                conn.close()
        except (relate.Error, relate.OperationalError):
            skipped.append(str(Path(path).relative_to(runs_root)))
            continue
        return {"scenario": scenario, "run": run, "label": label[0]}, observed, skipped
    return None, {}, skipped


def precedent_for_patch(diff: str, store: Path, runs_root: Path) -> dict:
    """Decision chains and citations for the diff's files, plus observed replay results.

    Pure and read-only: every store is opened read_only; no verdict is computed.
    """
    key = patch_key(diff)
    files = list(changed_files_from_text(diff))
    replay, observed, skipped = _find_replay(key, Path(runs_root))
    conn = open_readonly(store)
    try:
        chains = evidence_for_paths(conn, files)
        cited = cited_decisions(conn, files)
    finally:
        conn.close()
    out_files = []
    for path in files:
        decisions: dict[str, dict] = {}
        for r in chains[path]:
            d = decisions.setdefault(r["decision"], {
                "id": r["decision"], "title": r["title"], "status": r["status"],
                "rule": r["rule"], "reason": r["reason"],
                "decision_url": r["decision_url"], "citation_url": r["citation_url"],
                "commit": r["implementation"][:8], "commit_url": r["commit_url"],
                "checks": []})
            tap, number = observed.get(r["check"], (None, None))
            d["checks"].append({
                "name": r["check"], "kind": r["check_kind"],
                "number_at_pin": r["check_number_at_pin"], "url": r["check_url"],
                "evidence": r["check_evidence"],
                "observed": tap if tap in ("ok", "not ok") else "not observed",
                "tap_number": int(number) if tap in ("ok", "not ok") else None})
        also = [{"id": c["decision"], "title": c["title"], "status": c["status"],
                 "citation_url": c["citation_url"]}
                for c in cited[path] if c["decision"] not in decisions]
        out_files.append({"path": path, "decisions": list(decisions.values()),
                          "also_cites": also})
    out = {"patch_key": key, "changed_files": files, "replay": replay,
           "files": out_files, "note": NOTE}
    if skipped:
        out["skipped_replays"] = skipped
    if replay is None:
        out["hint"] = ("No replay matches this diff's changed lines. Pass the patch exactly as "
                       'given; if Patch Precedent has never been replayed here, run "uv run '
                       'patch-precedent demo all".')
    return out
