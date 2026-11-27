"""Styled (Rich) terminal output for `demo` and `explain`.

Used only when stdout is a terminal; plain output is produced elsewhere and stays unchanged.
Anything that comes from upstream or the graph is passed as `Text`, never as markup.
"""
from __future__ import annotations

import os
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console
from rich.segment import Segment
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from . import pins
from .report import cell_for, shorten_status
from .text import prose

if TYPE_CHECKING:
    from .diffparse import PatchInfo

STYLES: dict[str, str] = {
    "pp.accent": "#D9623B",
    "pp.pass": "#3FA672",
    "pp.fail": "#E0533D",
    "pp.strong": "bold",
    "pp.dim": "dim",
}

_LABEL_W = 16
_PASSED_W = 11
_FAILED_W = 9
_EXIT_W = 14


class _Console(Console):
    """Console that never emits trailing spaces (Rich pads table cells to column width)."""

    def _render_buffer(self, buffer):  # type: ignore[override]
        segs = list(buffer)
        ends_nl = bool(segs) and not segs[-1].control and segs[-1].text.endswith("\n")
        out: list[Segment] = []
        for line in Segment.split_lines(segs):
            line = list(line)
            while line and not line[-1].control:
                last = line[-1]
                text = last.text.rstrip(" ")
                if text == last.text:
                    break
                if text:
                    line[-1] = Segment(text, last.style)
                    break
                line.pop()
            out.extend(line)
            out.append(Segment.line())
        if out and not ends_nl:
            out.pop()
        return super()._render_buffer(out)


def should_style(stream: Any, plain: bool, env: Mapping[str, str] = os.environ) -> bool:
    """Styled only on a terminal, without --plain, and with NO_COLOR unset or empty."""
    if plain or env.get("NO_COLOR", ""):
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def make_console(file=None, *, width: int | None = None, force_terminal: bool | None = None,
                 color_system: str | None = "auto") -> Console:
    return _Console(file=file, width=width, force_terminal=force_terminal,
                   color_system=color_system, theme=Theme(STYLES),  # type: ignore[arg-type]
                   highlight=False, emoji=False, soft_wrap=False)


def _t(value: object, style: str = "") -> Text:
    return Text(str(value), style=style)


def _grid(*widths: int | None, padding: tuple[int, int] = (0, 1)) -> Table:
    grid = Table.grid(padding=padding)
    for w in widths:
        grid.add_column(width=w, no_wrap=w is not None, overflow="fold")
    return grid


def _indent(renderable, n: int = 2):
    return Padding(renderable, (0, 0, 0, n))


def _adr_text(ids, style: str = "pp.accent") -> Text:
    out = Text()
    for i, d in enumerate(ids):
        if i:
            out.append(", ")
        out.append(str(d), style=style)
    return out


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(pins.project_root().resolve()).as_posix()
    except ValueError:
        return str(path)


def _diff_text(raw: str) -> Text:
    out = Text()
    for line in raw.rstrip("\n").split("\n"):
        style = ""
        if line.startswith("+") and not line.startswith("+++"):
            style = "pp.pass"
        elif line.startswith("-") and not line.startswith("---"):
            style = "pp.fail"
        out.append(line + "\n", style=style)
    out.rstrip()
    return out


class StyledReporter:
    """Rich implementation of `DemoReporter`; details are buffered until a scenario ends."""

    def __init__(self, console: Console, links: bool = False) -> None:
        self.console = console
        self.links = links
        self._diffs: list[tuple[str, Any]] = []
        self._details: tuple | None = None
        self._scenario_open = False

    # -- header ---------------------------------------------------------
    def begin(self, command, upstream_url, upstream_sha, relate_version):
        repo = upstream_url.removeprefix("https://github.com/").removesuffix(".git")
        head = Text.assemble(("Patch Precedent", "pp.strong"), "  ", (command, "pp.dim"))
        sub = Text(f"{repo} @ {upstream_sha[:8]} · Relate {relate_version} · read-only store",
                   style="pp.dim")
        self.console.print(Panel(Text("\n").join([head, sub]), box=box.ROUNDED,
                                 border_style="pp.accent", padding=(0, 2),
                                 width=min(self.console.width, 70)))

    def scenario(self, name):
        self._flush_details()
        self.console.print()
        self.console.print(_t(name, "pp.strong"))

    def preamble(self, upstream_url, upstream_sha, relate_version, store):
        pass

    def run_start(self, label, patch):
        if patch is not None:
            self._diffs.append((label, patch))

    # -- per run --------------------------------------------------------
    def run_end(self, run, duration_s):
        ok = run.status == "pass"
        tap = run.tap
        passed = f"{tap.passed} passed" if tap is not None else "no TAP"
        failed = f"{tap.failed} failed" if tap is not None and tap.failed else ""
        code = "-" if run.exit_code is None else run.exit_code
        timing = Text.assemble((f"exit {code}".ljust(7), "pp.dim"),
                               (f"{duration_s:.1f}s".rjust(5), "pp.dim"))
        nums = [f"#{r.number}" for r in tap.results if not r.ok] if tap is not None else []
        if run.status == "inconclusive" and not nums:
            tail = _t(prose(run.reason or "inconclusive"), "pp.fail")
        else:
            tail = _t(" ".join(nums), "pp.fail")
        row = _grid(1, _LABEL_W, _PASSED_W, _FAILED_W, _EXIT_W, None)
        row.add_row(_t("✓" if ok else "✗", "pp.pass" if ok else "pp.fail"), _t(run.label),
                    _t(passed), _t(failed, "pp.fail"), timing, tail)
        self.console.print(_indent(row))

    # -- details (buffered) --------------------------------------------
    def details(self, runs, evidence_by_patch, file_blocks, join_query, joined):
        self._details = (runs, evidence_by_patch, file_blocks, join_query, joined)

    def _flush_details(self) -> None:
        details, diffs = self._details, self._diffs
        self._details, self._diffs = None, []
        if details is None and not diffs:
            return
        c = self.console
        c.print()
        c.rule(_t("Details"), style="pp.dim")
        for label, patch in diffs:
            c.print()
            c.print(Text.assemble((label, "pp.strong"), "  ",
                                  (f"patch {patch.sha256[:12]} changes "
                                   f"{', '.join(patch.changed_files)}", "pp.dim")))
            c.print(_diff_text(Path(patch.path).read_text(errors="replace")))
        if details is None:
            return
        runs, evidence_by_patch, file_blocks, join_query, joined = details
        c.print()
        c.print(_t("Comparison", "pp.strong"))
        c.print(self._comparison(runs, evidence_by_patch))
        c.print()
        c.print(_t("Graph evidence", "pp.strong"))
        for block in file_blocks:
            c.print(Text(block))
            c.print()
        c.print(_t("Graph join (replay.rl)", "pp.strong"))
        c.print(Text(join_query.rstrip()))
        c.print()
        c.print(self._join_table(joined))

    @staticmethod
    def _table(headers: list[str], rows: list[list[str]]) -> Table:
        table = Table(box=box.SIMPLE_HEAD, header_style="pp.dim", pad_edge=False,
                      show_edge=False, collapse_padding=False)
        for h in headers:
            table.add_column(Text(h), overflow="fold")
        for r in rows:
            table.add_row(*[Text(str(x)) for x in r])
        return table

    def _comparison(self, runs, evidence_by_patch) -> Table:
        linked: dict[str, tuple[int, str, str]] = {}
        for rows in evidence_by_patch.values():
            for r in rows:
                linked[r["check"]] = (r["check_number_at_pin"], r["check_kind"], r["check"])
        checks = sorted(linked.values())
        headers = ["Input", "Changed", "Exit", "Passed/failed"] + [f"#{n} {k}" for n, k, _ in checks]
        body = []
        for run in runs:
            changed = "- (unpatched)" if run.patch is None else ", ".join(run.patch.changed_files)
            exit_cell = "-" if run.exit_code is None else str(run.exit_code)
            pf = f"{run.tap.passed} / {run.tap.failed}" if run.tap else "-"
            body.append([run.label, changed, exit_cell, pf]
                        + [cell_for(run, c).replace("—", "-") for _, _, c in checks])
        return self._table(headers, body)

    def _join_table(self, joined) -> Table:
        # Every field of the plain join table is kept; related short fields share a cell
        # (one per line) so only the long assertion text has to wrap at 80 columns.
        table = Table(box=box.SIMPLE_HEAD, header_style="pp.dim", pad_edge=False, show_edge=False)
        table.add_column(Text("label / patch"), no_wrap=True)
        table.add_column(Text("file / decision / impl"), no_wrap=True)
        table.add_column(Text("observed"), no_wrap=True)
        table.add_column(Text("assertion"), overflow="fold")
        for r in joined:
            table.add_row(
                Text(f'{r["label"]}\n{r["patch"]}'),
                Text(f'{r["file"]}\n{r["decision"]} {r["implementation"][:8]}'),
                Text(f'{r["observed"]} {r["tap_number"]}'),
                Text(r["assertion"]))
        return table

    # -- verdicts -------------------------------------------------------
    def verdicts(self, lines, records, rcheck, warnings, mismatches):
        c = self.console
        c.print()
        c.print(_t("Verdicts", "pp.strong"))
        grid = _grid(1, _LABEL_W, None)
        for rec in records:
            dot = {"violates": "pp.fail", "consistent": "pp.pass"}.get(rec.kind, "pp.dim")
            if rec.kind == "violates":
                wording = Text("violates ").append_text(_adr_text(rec.decisions))
            elif rec.kind == "consistent":
                wording = Text("consistent with ").append_text(_adr_text(rec.decisions))
            elif rec.kind == "scanned_only":
                wording = Text("cites ").append_text(_adr_text(rec.decisions, "")).append(
                    " (scanned, not reviewed)")
            elif rec.kind == "no_decision":
                wording = Text("no linked decision")
            else:
                wording = Text("inconclusive")
            if rec.failing:
                refs = ", ".join(f"#{n} {kind}" for n, kind, _name in rec.failing)
                wording.append("  ").append(refs, style="pp.dim")
            grid.add_row(_t("●", dot), _t(rec.label), wording)
        c.print(_indent(grid))
        c.print()
        c.print(_t(prose(rcheck["line"]), "pp.dim"))
        for label in rcheck["reproduced"]:
            c.print(Text.assemble("  ", label, (" - expected regression reproduced; "
                                               "demo replay succeeded", "pp.dim")))
        for label in rcheck["inconclusive"]:
            c.print(Text.assemble("  ", label, (" - inconclusive, not counted", "pp.dim")))
        for title, items, style in (("Warnings", warnings, "pp.dim"),
                                    ("Mismatches", mismatches, "pp.fail")):
            if items:
                c.print()
                c.print(_t(title, "pp.strong"))
                for item in items:
                    c.print(_indent(_t(prose(item), style)))

    # -- artifacts / overall -------------------------------------------
    def artifacts(self, run_dir, runs, replay_store, summary_path):
        self._flush_details()
        self.console.print()
        self.console.print(Text.assemble(("artifacts  ", "pp.dim"), _rel(run_dir)))

    def overall(self, rows, overall, summary_path, elapsed_s):
        matched = total = 0
        for _name, _n, ratio, _code in rows:
            m, t = str(ratio).split("/")
            matched += int(m)
            total += int(t)
        good = overall == 0 and matched == total
        c = self.console
        c.print()
        c.print(Text.assemble(
            (f"{'✓' if good else '✗'} {matched}/{total} runs match expectations",
             "pp.pass" if good else "pp.fail"),
            "   ",
            (f"overall exit {overall} · {elapsed_s:.0f}s · {_rel(summary_path.parent)}", "pp.dim")))

    def finish(self):
        self._flush_details()


# -- explain -------------------------------------------------------------

def _chain(console: Console, path: str, rows: list[dict], cited: list[dict], links: bool,
           show_path: bool) -> None:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["decision"], []).append(row)
    extra = [c for c in cited if c["decision"] not in groups]
    if not groups and not extra:
        console.print(_t(f"{path}: no linked decision"))
        return
    if show_path:
        console.print(_t(path, "pp.strong"))
    for decision, group in groups.items():
        first = group[0]
        head = _grid(len(decision), None, padding=(0, 2))
        head.add_row(_t(decision, "pp.accent"), Text.assemble(
            (prose(first["title"]), "pp.strong"), "  ",
            (f"[{prose(shorten_status(first['status']))}]", "pp.dim")))
        console.print(head)
        fields = _grid(8, None)
        fields.add_row(_t("rule", "pp.dim"), _t(prose(first["rule"])))
        fields.add_row(_t("why", "pp.dim"), _t(prose(" ".join(first["reason"].split()))))
        sha = first["implementation"][:8]
        fields.add_row(_t("commit", "pp.dim"),
                       _t(f"{sha} {first['commit_url']}" if links else sha))
        if links:
            fields.add_row(_t("cite", "pp.dim"), _t(first["citation_url"]))
            fields.add_row(_t("decision", "pp.dim"), _t(first["decision_url"]))
            fields.add_row(_t("scope", "pp.dim"), _t(first["consequences_url"]))
        console.print(_indent(fields))
        console.print()
        console.print(_indent(_t("checks", "pp.dim")))
        checks = _grid(5, 8, None)
        for row in group:
            checks.add_row(_t(f"#{row['check_number_at_pin']}"), _t(row["check_kind"], "pp.dim"),
                           _t(row["check"]))
            if links:
                checks.add_row(Text(""), Text(""), _t(row["check_url"], "pp.dim"))
        console.print(_indent(checks, 4))
        console.print()
    if extra:
        ids = " ".join(c["decision"].removeprefix("ADR-") for c in extra)
        console.print(_t(f"also cites {len(extra)} ADR{'s' if len(extra) != 1 else ''} "
                         f"(scanned, not reviewed): {ids}", "pp.dim"))
        if links:
            for c in extra:
                console.print(_indent(_t(f"{c['decision']}  {c['citation_url']}", "pp.dim")))
        console.print()


def render_explain(console: Console, patch: "PatchInfo", evidence: dict, cited: dict,
                   links: bool) -> None:
    console.print(Text.assemble((patch.label, "pp.strong"), "  ",
                                (f"changes {', '.join(patch.changed_files)} · read-only, offline",
                                 "pp.dim")))
    console.print()
    if not patch.changed_files:
        console.print(_t("no changed files found in patch"))
        return
    for f in patch.changed_files:
        _chain(console, f, evidence.get(f, []), cited.get(f, []), links,
               show_path=len(patch.changed_files) > 1)
    if not links:
        console.print(_t("links: run with --links to print the GitHub permalinks", "pp.dim"))
