"""Plain-text rendering of evidence chains (shared by explain and demo)."""
from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .tap import TapResult

if TYPE_CHECKING:  # keep `explain` free of harness/upstream imports
    from .harness import RunResult

_LABEL = 10  # width of the label column inside a chain
_INDENT = "    "


def _field(label: str, value: str) -> str:
    return f"{_INDENT}{label:<{_LABEL}}{value}"


def _why(reason: str) -> str:
    pad = " " * (len(_INDENT) + _LABEL)
    wrapped = textwrap.wrap(
        reason, width=88, initial_indent=pad, subsequent_indent=pad, break_long_words=False
    )
    return f"{_INDENT}{'why':<{_LABEL}}" + "\n".join(wrapped)[len(pad):]


def _observed_suffix(check: str, observed: dict[str, TapResult] | None) -> str:
    if observed is None:
        return ""
    res = observed.get(check)
    if res is None:
        return "  → not observed"
    return f"  → {'ok' if res.ok else 'not ok'} {res.number}"


def _patch_observed_lines(
    check: str, patch_observed: Sequence[tuple[str, Mapping[str, TapResult]]]
) -> list[str]:
    lines = []
    for label, observed in patch_observed:
        res = observed.get(check)
        verdict = "not observed" if res is None else f"{'ok' if res.ok else 'not ok'} {res.number}"
        lines.append(f"            {label} → {verdict}")
    return lines


def render_evidence_chain(
    path: str,
    rows: list[dict],
    observed: dict[str, TapResult] | None = None,
    patch_observed: Sequence[tuple[str, Mapping[str, TapResult]]] | None = None,
) -> str:
    if not rows:
        return f"{path}: no linked decision"
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["decision"], []).append(row)
    lines = [path]
    for decision, group in groups.items():
        first = group[0]
        lines.append(f"  cites {decision} · {first['title']} [{first['status']}]")
        lines.append(_field("rule", first["rule"]))
        lines.append(_why(first["reason"]))
        lines.append(_field("citation", first["citation_url"]))
        lines.append(_field("decision", first["decision_url"]))
        lines.append(_field("scope", first["consequences_url"]))
        lines.append(
            _field(
                "commit",
                f"{first['implementation'][:8]} {first['commit_subject']} ({first['commit_url']})",
            )
        )
        lines.append(f"{_INDENT}checks")
        for row in group:
            num = f"#{row['check_number_at_pin']}"
            lines.append(
                f"      {num:<6}{row['check_kind']:<9}{row['check']}"
                f"{_observed_suffix(row['check'], observed)}"
            )
            if patch_observed:
                lines += _patch_observed_lines(row["check"], patch_observed)
            lines.append(f"            {row['check_url']}")
    return "\n".join(lines)


# --- demo rendering -------------------------------------------------------

def format_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    cells = [list(map(str, headers))] + [list(map(str, r)) for r in rows]
    widths = [max(len(r[i]) for r in cells) for i in range(len(headers))]

    def fmt(r):
        return "  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip()

    rule = "  ".join("-" * w for w in widths)
    return "\n".join([fmt(cells[0]), rule, *map(fmt, cells[1:])])


def observed_map(run: RunResult) -> dict[str, TapResult]:
    return {r.description: r for r in run.tap.results} if run.tap else {}


def cell_for(run: RunResult, check: str) -> str:
    res = observed_map(run).get(check)
    if res is None:
        return "—"
    if res.skipped:
        return f"skip {res.number}"
    return f"{'ok' if res.ok else 'not ok'} {res.number}"


def comparison_table(runs: Sequence[RunResult], evidence_by_patch: Mapping[str, list[dict]]) -> str:
    linked: dict[str, tuple[int, str, str]] = {}
    for rows in evidence_by_patch.values():
        for r in rows:
            linked[r["check"]] = (r["check_number_at_pin"], r["check_kind"], r["check"])
    checks = sorted(linked.values())
    headers = ["Input", "Changed", "Exit", "Passed/failed"] + [f"#{n} {k}" for n, k, _ in checks]
    body = []
    for run in runs:
        changed = "— (unpatched)" if run.patch is None else ", ".join(run.patch.changed_files)
        exit_cell = "—" if run.exit_code is None else str(run.exit_code)
        pf = f"{run.tap.passed} / {run.tap.failed}" if run.tap else "—"
        body.append([run.label, changed, exit_cell, pf] + [cell_for(run, c) for _, _, c in checks])
    return format_table(headers, body)


def join_table(rows: Sequence[Mapping]) -> str:
    """The graph-join result as a table whose columns mirror the printed JOIN_QUERY."""
    return format_table(
        ["patch", "label", "file", "decision", "implementation", "assertion", "observed"],
        [[r["patch"], r["label"], r["file"], r["decision"], r["implementation"][:8],
          r["assertion"], f'{r["observed"]} {r["tap_number"]}'] for r in rows])


def compute_verdicts(
    runs: Sequence[RunResult],
    evidence_by_patch: Mapping[str, list[dict]],
    mismatches: Sequence[str],
) -> tuple[list[str], int]:
    """Derive one verdict per patch purely from observed runs and graph evidence."""
    baseline = next((r for r in runs if r.patch is None), None)
    patches = [r for r in runs if r.patch is not None]
    lines: list[str] = []
    inconclusive = False
    if baseline is None or baseline.status != "pass":
        why = "no baseline run" if baseline is None else (baseline.reason or baseline.status)
        return [f"{r.label}: inconclusive (baseline not green: {why})" for r in patches], 2
    for run in patches:
        if run.status == "inconclusive" or run.tap is None:
            inconclusive = True
            lines.append(f"{run.label}: inconclusive ({run.reason or 'no TAP observed'})")
            continue
        rows = evidence_by_patch.get(run.patch.id, [])
        if not rows:
            lines.append(f"{run.label}: no linked decision")
            lines += _unlinked_failures(run, set())
            continue
        obs = observed_map(run)
        seen = [r for r in rows if r["check"] in obs]
        if not seen:
            inconclusive = True
            lines.append(f"{run.label}: inconclusive (linked checks not found in TAP output)")
            continue
        failing = [r for r in seen if not obs[r["check"]].ok]
        if failing:
            by_decision: dict[str, list[dict]] = {}
            for r in failing:
                by_decision.setdefault(r["decision"], []).append(r)
            for decision, group in by_decision.items():
                lines.append(f"{run.label}: violates {decision} — {group[0]['rule']}")
                for r in group:
                    n = obs[r["check"]].number
                    lines.append(f"    #{n} {r['check_kind']}: {r['check_evidence']}")
            lines.append(
                f"    harness exit {run.exit_code}, {run.tap.passed} passed / "
                f"{run.tap.failed} failed"
            )
        else:
            decisions = ", ".join(dict.fromkeys(r["decision"] for r in seen))
            nums = ", ".join(f"#{n}" for n in sorted({obs[r["check"]].number for r in seen}))
            lines.append(f"{run.label}: consistent with {decisions} as far as checks {nums} cover")
        lines += _unlinked_failures(run, {r["check"] for r in rows})
    code = 2 if inconclusive else 3 if mismatches else 0
    return lines, code


def _unlinked_failures(run: RunResult, linked: set[str]) -> list[str]:
    return [
        f"    also failed (no linked decision): #{r.number} {r.description}"
        for r in run.tap.results
        if not r.ok and r.description not in linked
    ]
