"""Plain-text rendering of evidence chains (shared by explain and demo)."""
import textwrap

from .tap import TapResult

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


def render_evidence_chain(
    path: str, rows: list[dict], observed: dict[str, TapResult] | None = None
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
            lines.append(f"            {row['check_url']}")
    return "\n".join(lines)
