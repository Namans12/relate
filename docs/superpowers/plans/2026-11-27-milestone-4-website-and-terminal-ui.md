# Milestone 4: Website and Terminal UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static website generated from the project's real data, plus styled terminal output for `demo` and `explain`. The site is published on GitHub Pages and is the hackathon's "working demo" link.

**Architecture:**
- A `site` subcommand renders Jinja2 templates and vanilla JS/CSS into `_site/`. Its inputs are the committed Relate store, a committed recording of a styled `demo all` run, the published eval results and one content file.
- `demo` gets a reporter seam. `PlainReporter` prints today's output byte for byte; `StyledReporter` prints with Rich.
- The graph on each patch page is SVG generated in Python.

**Tech Stack:** Python 3.12, uv, relate-db 1.1.0, Jinja2, Rich, vanilla JS, CSS, GitHub Actions Pages.

**Spec:** `docs/superpowers/specs/2026-11-27-website-and-terminal-ui-design.md`. Mockups (layout and style reference only) are in `docs/superpowers/specs/2026-11-27-site-mockups/`.

## Global Constraints

- **Dependencies.** Add `jinja2` and `rich` to `[project].dependencies`, pinned `==` to the current stable release at build time. Add no other runtime dependency. No Node and no npm.
- **Plain output is frozen.** Plain-mode stdout of `demo`, `demo all` and `explain` must stay byte for byte as at commit `c8a5a7a`. Plain mode applies when stdout is not a TTY, when `NO_COLOR` is set to a non-empty value, or when `--plain` is passed.
- **Text rule.**
  - No U+2013 or U+2014 in headings, titles, labels or prose on the site or in styled terminal output. Upstream ADR and scanned titles go through `prose()`, which turns them into a hyphen.
  - Verbatim source text keeps its characters: diff lines, check names in code font, Cypher, and recorded transcript lines that echo upstream text. On the site that text lives in elements carrying the `data-verbatim` attribute.
  - Our own CLI separators print as `-` in styled mode.
- **Untrusted text in Rich.** Never pass check names, titles, diffs or paths to Rich as markup. Build `rich.text.Text` objects, or call `print(..., markup=False)`. Check names contain `[Unreleased]`.
- **Palette (site):**
  - bg `#FAF7F2`, surface `#FFFFFF`, sunk `#F3EEE4`, line `#E7E0D3`, line-2 `#D9D1C2`;
  - ink `#1B1F2A`, ink-2 `#4A4F5C`, ink-3 `#686D79`;
  - accent `#B4472A`, bright `#E36B47`, accent-soft `#FBE7DF`;
  - pass `#2F7D57`/`#E2F1E8`, fail `#B4472A`/`#FBE3DA`, none `#ECE7DC`.
- **Site terminal panel colours (dark):** bg `#16191F`, bar `#1F232C`, text `#E8E2D6`, accent `#F2A07B`, dim `#8C8577`, pass `#8FD0A8`, fail `#F29A86`, strong `#FAF7F2` bold.
- **Real-terminal colours (Ruling).** These must read on both dark and light terminal themes, so they are mid-tones: accent `#D9623B`, pass `#3FA672`, fail `#E0533D`. Strong is `bold` with no colour, dim is the `dim` attribute, and body text uses the terminal's default colour. The spec's dark mapping is used only for the site's terminal panel.
- **Fonts.** Playfair Display (title and all headings), Inter (body), JetBrains Mono (code), loaded from Google Fonts. No Fraunces anywhere.
- **Links.** All internal links are relative. The only absolute URLs allowed are:
  - `https://github.com/Namans12/relate` and paths under it;
  - `https://github.com/relatedb/relate/` with paths at the pinned SHA, or commit URLs;
  - `https://fonts.googleapis.com` and `https://fonts.gstatic.com`;
  - `https://relate.devpost.com`;
  - `https://namans12.github.io/relate/lockup.png` (the `og:image` only).
- **Licence.** Nothing GPL ships: no `neo4j-viz`, no NVL. The Uiverse credit comment is kept verbatim. Pixelcraft is vendored without `pixelcraft.jpg` and without any "Hack4Hack" string.
- **Relate naming.** "Built with Relate" appears exactly once on the site (the home hero eyebrow). Relate is named only to identify the product. No Relate or Neo4j logo.
- **Copy.** No filler copy. Every hand-written sentence lives in `site/content.toml`. A `{placeholder}` without a computed value fails the build.
- **Responsive and accessible.**
  - Layout holds at 320, 375, 768, 1024, 1440 and 1920 px with no horizontal page scroll.
  - Every animation is off under `prefers-reduced-motion`.
  - Every control works by keyboard with a visible focus ring.
- **Commits.** End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **The site opened offline or without JavaScript.** Expected:
   - `index.html` shows `lockup.png` and a working Enter link;
   - the demo panel shows the full transcript as static text;
   - the graph's `<title>` elements still label nodes;
   - nothing is invisible because a reveal animation never ran (reveal hiding is applied only after JS adds `js` to `<html>`).
2. **Pages served under `/relate/` or from `file://`.** Every link, script and image resolves, because all of them are relative. Pinned by the link test (Task 6) and the Task 10 browser pass.
3. **A 320px-wide phone.** No horizontal page scroll; long commands and diffs scroll inside their own box; the intro uses the stacked lockup. Pinned by the Task 10 browser pass, plus CSS min-width rules named in Tasks 6 and 7.
4. **Output piped, `NO_COLOR` set, or run in CI.** Identical to today. Pinned by the golden test (Task 1) and `should_style` tests (Task 2).
5. **The recording leaks local data.** No `/Users/`, home directory or absolute project path in `recorded/demo-all.json` or anywhere in `_site/`. Pinned by Task 3 and Task 6 tests.

---

### Task 1: Demo reporter seam, verdict records and run durations

**Files:**
- Modify: `src/patch_precedent/report.py` (add `VerdictRecord`, `verdict_records`)
- Modify: `src/patch_precedent/demo.py` (route every print through a reporter; time each run)
- Create: `tests/data/golden/demo-all.txt`
- Test: `tests/test_report.py`, `tests/test_demo_golden.py`

**Interfaces:**
- Produces:
  - `report.VerdictRecord`, a frozen dataclass with these fields:
    - `label: str`
    - `kind: Literal["violates","consistent","no_decision","scanned_only","inconclusive"]`
    - `decisions: tuple[str, ...]`
    - `rule: str | None`
    - `failing: tuple[tuple[int, str, str], ...]`: (tap number, check kind, check name) per linked failing check
    - `covered: tuple[int, ...]`: tap numbers of the linked checks seen
    - `as_dict()`, which returns JSON-safe lists.
  - `report.verdict_records(runs, evidence_by_patch, cited_by_patch) -> list[VerdictRecord]`. It follows the same branch logic as `compute_verdicts`, for patches only. When the baseline is not green, every record is `inconclusive`.
  - `demo.DemoReporter`, a Protocol with these methods (all return `None`):
    - `begin(command: str, upstream_url: str, upstream_sha: str, relate_version: str)`
    - `scenario(name: str)`
    - `preamble(upstream_url: str, upstream_sha: str, relate_version: str, store: Path)`
    - `run_start(label: str, patch: PatchInfo | None)`
    - `run_end(run: RunResult, duration_s: float)`
    - `details(runs, evidence_by_patch, file_blocks: list[str], join_query: str, joined: list[dict])`
    - `verdicts(lines: list[str], records: list[VerdictRecord], rcheck: dict, warnings: list[str], mismatches: list[str])`
    - `artifacts(run_dir: Path, runs, replay_store: Path, summary_path: Path)`
    - `overall(rows: list[tuple], overall: int, summary_path: Path, elapsed_s: float)`
    - `finish()`
  - `demo.PlainReporter()`, whose method bodies are the existing `print` calls moved verbatim. `begin` and `finish` are no-ops.
  - `run_demo(scenario, fixtures_dir=None, runs_root=None, reporter: DemoReporter | None = None) -> int` and `run_all(runs_root=None, reporter: DemoReporter | None = None) -> int`. `None` means `PlainReporter()`.
  - `summary.json` gains, per run, `"duration_s": float` (wall time of `run_case`, rounded to 0.1). Per scenario it gains `"verdict_records": [record.as_dict(), ...]`. Each top-level `run_all` summary gains `"elapsed_s"`. No existing key changes.

- [ ] **Step 1: Capture the golden output before touching `demo.py`.**

  Run `uv run patch-precedent demo all > /tmp/pp-golden.txt` on the unmodified code. Its runs root is `<root>/runs`. Then normalise it with a helper `normalise(text: str, root: Path, runs_root: Path) -> str` (defined in `tests/test_demo_golden.py`), which applies these steps in order:
  1. replace `str(runs_root)` with `<RUNS>`;
  2. replace `str(root)` with `<ROOT>`;
  3. replace `<RUNS>/<YYYYMMDDTHHMMSSZ>(-N)?` with `<RUNS>/<RUN>`;
  4. replace `str(Path.home())` with `<HOME>`.

  Write the result to `tests/data/golden/demo-all.txt`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_demo_golden.py
pytestmark = pytest.mark.upstream

def test_plain_demo_all_matches_golden(tmp_path, capsys):
    assert run_all(runs_root=tmp_path) == 0
    out = normalise(capsys.readouterr().out, pins.project_root(), tmp_path)
    assert out == (GOLDEN_DIR / "demo-all.txt").read_text()

def test_summary_has_durations_and_records(tmp_path):
    assert run_all(runs_root=tmp_path) == 0
    top = json.loads(next(tmp_path.iterdir()).joinpath("summary.json").read_text())
    assert top["elapsed_s"] > 0
    inst = top["scenarios"]["installer"]
    assert all(r["duration_s"] > 0 for r in inst["runs"])
    recs = {r["label"]: r for r in inst["verdict_records"]}
    assert recs["token-header"]["kind"] == "violates"
    assert recs["token-header"]["decisions"] == ["ADR-0585"]
    assert [f[0] for f in recs["token-header"]["failing"]] == [64]
    assert recs["wording"]["kind"] == "consistent"
    rel = {r["label"]: r for r in top["scenarios"]["release"]["verdict_records"]}
    assert rel["docs-only"]["kind"] == "no_decision"
    assert rel["always-rotate"]["failing"][0][0] == 2
```

```python
# tests/test_report.py (reuse its _runs/_evidence/_cited fakes)
def test_verdict_records_match_compute_verdicts_kinds():
    # for each existing compute_verdicts scenario in this file, the record's kind
    # agrees with the line prefix: "violates" / "consistent with" / "no linked decision" /
    # "cites ... (scanned" / "inconclusive"
def test_verdict_records_baseline_red_all_inconclusive(): ...
def test_verdict_record_as_dict_is_json_safe():
    json.dumps([r.as_dict() for r in verdict_records(*_fakes())])
```

The golden test needs the upstream cache, so it is marked `upstream`. The new `test_report.py` tests run offline.

- [ ] **Step 3: Run them and see them fail.**

  Run `uv run pytest tests/test_report.py -q` and `uv run pytest -m upstream tests/test_demo_golden.py -q`. Expected: FAIL. `verdict_records` doesn't exist yet, and neither do the `duration_s` and `verdict_records` keys.

- [ ] **Step 4: Implement.**
  - `verdict_records` in `report.py`.
  - In `demo.py`:
    - add the reporter Protocol and `PlainReporter`;
    - move every `print` in `_run_scenario`, `run_demo` and `run_all` into reporter calls;
    - time `run_case` with `time.monotonic()`;
    - add the new summary keys.
  - `file_blocks` are the exact `render_file_evidence(...)` strings `demo.py` prints today.

- [ ] **Step 5: Run the tests and make sure they pass.**

  Run `uv run pytest -q` and `uv run pytest -m upstream -q`. Expected: all pass, including `test_demo.py` unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/patch_precedent/report.py src/patch_precedent/demo.py tests/test_report.py tests/test_demo_golden.py tests/data/golden/demo-all.txt
git commit -m "refactor: demo reporter seam, verdict records and run durations"
```

---

### Task 2: Styled terminal output (`rich`) for demo and explain

**Files:**
- Modify: `pyproject.toml` (add pinned `rich`), `uv.lock`
- Create: `src/patch_precedent/tui.py`
- Modify: `src/patch_precedent/cli.py` (`--plain` on `demo` and `explain`; `--links` on `explain`; choose the reporter)
- Test: `tests/test_tui.py`, `tests/data/golden/explain-token-header.styled.txt`

**Interfaces:**
- Consumes: `DemoReporter`, `VerdictRecord`, and the new summary keys (Task 1); `evidence_for_paths`, `cited_decisions` and `render_file_evidence` (existing).
- Produces:
  - `tui.STYLES: dict[str, str]`:
    - `pp.accent` = `"#D9623B"`
    - `pp.pass` = `"#3FA672"`
    - `pp.fail` = `"#E0533D"`
    - `pp.strong` = `"bold"`
    - `pp.dim` = `"dim"`
  - `tui.should_style(stream, plain: bool, env: Mapping[str, str] = os.environ) -> bool`
  - `tui.make_console(file=None, *, width: int | None = None, force_terminal: bool | None = None, color_system: str | None = "auto") -> rich.console.Console`. It sets `theme`, `highlight=False`, `emoji=False` and `soft_wrap=False`.
  - `tui.StyledReporter(console, links: bool = False)`, which implements `DemoReporter`.
  - `tui.render_explain(console, patch: PatchInfo, evidence: dict, cited: dict, links: bool) -> None`

**What styled output contains.** Layout per `docs/superpowers/specs/2026-11-27-site-mockups/terminal.html`.

- **`StyledReporter`:**
  - `begin` prints a rounded panel. Line 1 is "Patch Precedent" (strong) plus the command (dim). Line 2 is `relatedb/relate @ <sha[:8]> · Relate <version> · read-only store` (dim).
  - `scenario` prints the bold scenario name. `preamble` prints nothing; the panel already covered it.
  - `run_end` prints one aligned row as soon as the run ends:
    - mark: `✓` in pass colour or `✗` in fail colour;
    - label, padded to 16;
    - `N passed`;
    - `N failed` in fail colour, or blank;
    - `exit N` and duration `6.8s`, both dim;
    - failing numbers `#7 #193` in fail colour.
  - `verdicts` prints a "Verdicts" heading, then one row per `VerdictRecord`:
    - a `●` coloured by kind (violates = fail, consistent = pass, otherwise dim);
    - the label;
    - wording: `violates ADR-0585`, `consistent with ADR-0585`, `no linked decision`, `cites ADR-x (scanned, not reviewed)` or `inconclusive`;
    - dim failing refs such as `#7 static, #193 runtime`.

    After the rows comes the replay-check line, rewritten without the em dash, then any warnings and mismatches.
  - `details` is buffered and printed at the end of the scenario under a dim rule titled "Details":
    - each patch's diff, verbatim, with `+` lines in pass colour and `-` lines in fail colour;
    - a comparison table, built as a Rich `Table` from `runs`, with `-` for empty cells;
    - each `file_blocks` string, verbatim;
    - the join query, verbatim, then the join table.
  - `artifacts` prints the run dir relative to the project root when it is inside it. `overall` prints `✓ N/N runs match expectations` (or `✗`) plus dim `overall exit X · Ns · runs/<id>`.
- **`render_explain`:**
  - a header with the patch label (strong) and `changes <files> · read-only, offline` (dim);
  - per curated decision:
    - the ADR id (accent) with `prose(title)` (strong) and `[status]` (dim);
    - `rule`, wrapped `why`, `commit <sha8>`;
    - a checks block: `#N  kind  check name` (verbatim name);
  - then `also cites N ADRs (scanned, not reviewed): <ids>` (dim);
  - permalinks print only when `links=True`; otherwise a dim hint `links: run with --links to print the GitHub permalinks`.
  - A file with no decision prints `<path>: no linked decision`.
- **Width.** Fits 80 columns. Long values wrap with an indent, never breaking column alignment.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tui.py
def test_should_style():
    class T(io.StringIO):
        def isatty(self): return True
    assert should_style(T(), plain=False, env={}) is True
    assert should_style(T(), plain=True, env={}) is False
    assert should_style(T(), plain=False, env={"NO_COLOR": "1"}) is False
    assert should_style(T(), plain=False, env={"NO_COLOR": ""}) is True
    assert should_style(io.StringIO(), plain=False, env={}) is False

def test_explain_styled_snapshot():
    buf = io.StringIO()
    c = make_console(file=buf, width=80, force_terminal=False)   # no ANSI, layout only
    render_explain(c, read_patch(FIX / "installer/token-header.patch"), *_evidence_for(...), links=False)
    assert buf.getvalue() == (GOLDEN_DIR / "explain-token-header.styled.txt").read_text()

def test_explain_styled_links_flag_adds_permalinks(): ...   # "https://github.com/relatedb/relate/" absent without, present with
def test_styled_text_has_no_forbidden_dashes_outside_check_names():
    # render explain for fixtures/release/always-rotate.patch; remove every occurrence of
    # each verbatim check name, then assert "–" and "—" are absent
def test_styled_reporter_row_alignment():
    # feed StyledReporter a fake RunResult (pass and fail) into a width-80 console;
    # the "passed" column starts at the same index in both rows
def test_markup_in_names_is_not_interpreted():
    # a check name containing "[Unreleased]" prints literally
def test_cli_plain_flag_keeps_plain_explain(capsys):
    # main(["explain", "--plain", FIX/"installer/token-header.patch"]) output == today's plain output
```

  Generate the snapshot golden once from the implementation. Then review it by eye against `terminal.html` before committing.

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_tui.py -q`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement.**
  - `tui.py` as specified above.
  - In `cli.py`, `_cmd_demo` and `_cmd_explain` do two things:
    - choose `StyledReporter(make_console(), links=False)`, or the styled explain path, when `should_style(sys.stdout, args.plain)` is true;
    - otherwise run the existing code path unchanged.

- [ ] **Step 4: Run the tests and make sure they pass.**
  - Run `uv run pytest -q` and `uv run pytest -m upstream -q`. All pass; the Task 1 golden test still matches.
  - Then run `uv run patch-precedent demo all` in a real terminal and `uv run patch-precedent demo all | cat`. The first is styled; the second matches the golden text.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/patch_precedent/tui.py src/patch_precedent/cli.py tests/test_tui.py tests/data/golden/explain-token-header.styled.txt
git commit -m "feat: styled terminal output for demo and explain"
```

---

### Task 3: `site record`: the committed recorded run

**Files:**
- Create: `src/patch_precedent/site/__init__.py` (empty), `src/patch_precedent/site/record.py`
- Modify: `src/patch_precedent/cli.py` (add a `site` subcommand with an optional positional `action` in `{build, record}`, default `build`, and `--out`; `build` is wired in Task 6 and prints "not yet implemented" until then)
- Create: `recorded/demo-all.json` (produced by running the command)
- Test: `tests/test_site_record.py`

**Interfaces:**
- Consumes: `run_all(runs_root, reporter)`, `StyledReporter`, `make_console`, `tui.STYLES`, and the summary keys from Task 1.
- Produces:
  - `record.record_demo(out: Path, runs_root: Path) -> int`. It runs `run_all` with a `StyledReporter` whose console has `width=100`, `force_terminal=True` and `color_system="truecolor"`, writing to a `TimingSink`. It writes `out` only when the exit code is 0, and returns the exit code.
  - `record.TimingSink`: a text file-like object. `write()` splits on `\n` and stamps each completed line with seconds since creation (`time.monotonic`). `lines` is a `list[tuple[float, str]]`.
  - `record.ansi_to_spans(line: str) -> list[tuple[str, str]]`. It parses SGR sequences into (text, style) pairs, with style in `{"plain","accent","pass","fail","strong","dim"}`:
    - `38;2;r;g;b` maps by matching the RGB of `tui.STYLES`;
    - `1` maps to `strong`, and `2` to `dim`;
    - `0` or `39` resets.

    Adjacent spans with the same style are merged.
  - `record.scrub(text: str) -> str`. It replaces `str(project_root())` with `.`, `str(Path.home())` with `~`, and any remaining `/Users/<name>` with `~`.
  - **`recorded/demo-all.json`** (`format` 1, UTF-8, `ensure_ascii=False`, indent 2):

```json
{"format": 1, "run_id": "<runs dir name>", "recorded_at": "<UTC ISO8601 Z>",
 "upstream": {"url": "...", "sha": "..."}, "relate_version": "1.1.0",
 "overall_exit": 0, "elapsed_s": 44.1,
 "scenarios": {"installer": {"runs": [{"label": "...", "patch_id": "...|null", "sha256": "...|null",
     "changed_files": [], "status": "pass|fail|inconclusive", "exit_code": 0, "passed": 194,
     "failed": 0, "total": 194, "failing_numbers": [], "failing": [], "duration_s": 6.8,
     "observed": {"<check name>": {"ok": true, "number": 7}}}],
   "verdict_records": [ ... ], "replay_check": {...}}, "release": {...}},
 "transcript": [{"t": 0.0, "spans": [["text", "style"]]}]}
```

  `observed` covers linked checks only. It is read from that scenario's `replay.rl` with `MATCH (p:Patch {label: $label})-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(k:Check) RETURN k.name, o.tap, o.number` (opened with `open_readonly`). Baseline runs get `{}`. Every string in the file passes through `scrub`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site_record.py
def test_ansi_to_spans_maps_palette():
    c = make_console(file=(buf := io.StringIO()), width=100, force_terminal=True, color_system="truecolor")
    c.print(Text("✗ ", style="pp.fail") + Text("label", style="pp.strong") + Text(" exit 1", style="pp.dim"))
    assert ansi_to_spans(buf.getvalue().rstrip("\n")) == [("✗ ", "fail"), ("label", "strong"), (" exit 1", "dim")]

def test_scrub_removes_local_paths():
    assert "/Users/" not in scrub(f"{pins.project_root()}/runs/x and {Path.home()}/.cache")

def test_timing_sink_stamps_complete_lines(): ...   # two writes forming one line -> one entry; t is non-decreasing

def test_committed_recording_shape():          # offline, reads recorded/demo-all.json
    rec = json.loads((pins.project_root() / "recorded/demo-all.json").read_text())
    assert rec["format"] == 1 and rec["overall_exit"] == 0
    labels = {(s, r["label"]) for s, sc in rec["scenarios"].items() for r in sc["runs"] if r["patch_id"]}
    assert labels == {("installer","release-lookup"),("installer","token-header"),("installer","wording"),
                      ("release","always-rotate"),("release","wording"),("release","docs-only")}
    assert "/Users/" not in json.dumps(rec) and str(Path.home()) not in json.dumps(rec)
    th = next(r for r in rec["scenarios"]["installer"]["runs"] if r["label"] == "token-header")
    assert (th["passed"], th["failed"], th["exit_code"], th["failing_numbers"]) == (193, 1, 1, [64])
    assert rec["transcript"] and all(set(s[1] for s in l["spans"]) <= STYLE_NAMES for l in rec["transcript"])
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_record.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `record.py` and the `site record` CLI wiring.**
- [ ] **Step 4: Produce the recording.** Run `uv run patch-precedent site record` (about 45 s; needs the warm upstream cache). Expected: prints `wrote recorded/demo-all.json` and exits 0.
- [ ] **Step 5: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 6: Commit**

```bash
git add src/patch_precedent/site src/patch_precedent/cli.py recorded/demo-all.json tests/test_site_record.py
git commit -m "feat: site record writes the committed demo recording"
```

---

### Task 4: Site data layer and content file

**Files:**
- Modify: `pyproject.toml` (add pinned `jinja2`), `uv.lock`
- Create: `src/patch_precedent/site/data.py`, `site/content.toml`
- Test: `tests/test_site_data.py`

**Interfaces:**
- Consumes:
  - `recorded/demo-all.json` (Task 3);
  - `store.open_readonly`, `evidence_for_paths`, `cited_decisions`, `store._EVIDENCE_QUERY`, `store._CITED_QUERY`, `replay.JOIN_QUERY`;
  - `eval/results/20261127T040059Z/{results.json,scored.jsonl}` and `eval/cases.toml`;
  - `diffparse.read_patch`.
- Produces, in `site/data.py` (all frozen dataclasses):
  - `class SiteDataError(Exception)`
  - `prose(text: str) -> str`: `" — "` and `" – "` become `" - "`, then any remaining U+2014 or U+2013 becomes `"-"`.
  - `fill(template: str, values: Mapping[str, object]) -> str`: `str.format_map` with a mapping that raises `SiteDataError(f"no value for {{{key}}}")` on a missing key.
  - `literal_query(query: str, params: Mapping[str, str]) -> str`: replaces each `$name` with a single-quoted Cypher string literal, escaping `\` and `'`. Raises `SiteDataError` if a `$name` has no param.
  - `CheckRow(number: int, kind: str, name: str, short: str, url: str, observed: Literal["ok","not ok","not observed"])`
  - `DecisionCard(id, title, status, rule, reason, decision_url, consequences_url, citation_url, commit_sha, commit_subject, commit_url, checks: tuple[CheckRow, ...])`. `title` and `status` have already gone through `prose`.
  - `Cited(id, title, status, url)`, with `prose` applied.
  - `DiffLine(kind: Literal["hunk","add","del","ctx"], old: int | None, new: int | None, text: str)`
  - `DiffFile(path: str, added: int, removed: int, lines: tuple[DiffLine, ...])`
  - `PatchPage`, with these fields:
    - identity: `slug` (`f"{scenario}-{label}"`), `scenario`, `label`, `scenario_title` ("Installer" / "Release"), `fixture` (repo-relative path);
    - diff and run: `sha256`, `diff: tuple[DiffFile, ...]`, `status`, `exit_code`, `passed`, `failed`, `total`, `failing_numbers`, `duration_s`;
    - verdict and evidence: `verdict: dict` (the record), `decisions: tuple[DecisionCard, ...]`, `also_cites: tuple[Cited, ...]`;
    - copy: `summary`, `heading`, `body` (`body` is filled), `explain_cmd`;
    - `queries: tuple[tuple[str, str], ...]`: (title, literal Cypher), always including `("Decision chain", literal _EVIDENCE_QUERY for each changed file)` and `("Every cited decision", literal _CITED_QUERY ...)`;
    - links: `prev_slug`, `next_slug`.
  - `EvalView`, with these fields:
    - `arms: dict` (from results.json);
    - `cases: tuple[dict, ...]` (per case: `id`, `label`, `scenario`, `expected` verdict from cases.toml, the per-arm metrics);
    - `per_run: tuple[dict, ...]` (from scored.jsonl, trimmed to `case`, `arm`, `repeat`, `verdict`, `verdict_correct`, `turns`, `cost_usd`, `tool_replay_found`);
    - `intro: str`, `caveats: tuple[str, ...]` (both filled);
    - `metrics: tuple[dict, ...]`: one entry per headline metric (key, label, baseline display, graph display, baseline 0..1, graph 0..1), in the order verdict correct, decisions exact, decision recall, checks recall, catching-checks recall, unsupported claims, median citation time, mean turns, cost.
  - `StoreStats(nodes: int, rels: int, by_label: dict[str, int], by_type: dict[str, int])`
  - `SiteData(patches: tuple[PatchPage, ...], eval: EvalView, store: StoreStats, recording: dict, content: dict, home_chain: PatchPage)`. `home_chain` is the token-header page.
  - `load_site_data(root: Path) -> SiteData`. It raises `SiteDataError` with a precise message when any input file is missing, any patch lacks a content entry, or any placeholder is unfilled.
- **Computed placeholder values** available to `results` copy:
  - `{repeats}` (3), `{cases}` (6), `{model}` ("Claude Sonnet");
  - `{graph_runs}` (`replay_found_n`), `{replay_found}` (`replay_found_k`), `{replay_missed}` (n - k);
  - `{baseline_verdict_k}`, `{graph_verdict_k}`, `{n}` (18);
  - `{baseline_verdict_misses}` (n - verdict_k for baseline);
  - `{catching_recall_baseline}` / `{catching_recall_graph}` as percentages.
- **The boundary assertion.** `load_site_data` checks one claim the "both baseline verdict misses" caveat relies on. Every baseline run with `verdict_correct == false` must have an expected verdict and an answered verdict that both lie in `{consistent, no_decision}`. If not, it raises `SiteDataError("caveat 'boundary' no longer true")`.

**`site/content.toml`** keys:
- `[home]`: `eyebrow`, `title`, `lede`, `steps` (array of `{name, text}`), `scenarios_title`, `results_title`, `use_title`, `chain_caption`.
- `[patches."<scenario>/<label>"]`, × 6, each with:
  - `summary`: the one line on the carousel card and patch header;
  - `heading`: the callout heading;
  - `body`: the callout body. It may use `{decision}`, `{rule}`, `{failing}` (for example "#64") and `{passed}`/`{total}`.
- `[checks."<exact check name>"]` `short`: the short label for every linked check.
- `[results]`: `intro`, `caveats` (array).
- `[use]`: `steps` (array of `{title, text, tag}`).
- `[relate]`: `intro`, `capabilities` (array of `{name, text}`).

Copy comes verbatim from the mockups where they have it. The rest:

| key | text |
|---|---|
| home.lede | Check every patch against the architecture decisions behind the code, and the tests that prove it. |
| home.steps | Cite / Replay / Explain: the three texts in `welcome.html` |
| patches summaries | the carousel lines in `welcome.html`; token-header uses `scenario.html`'s "Sends GITHUB_TOKEN as an Authorization header, for the authenticated rate limit." |
| installer/release-lookup heading | Breaks the installer's no-API rule |
| installer/token-header heading | Breaks the installer's no-token rule |
| installer/wording heading | Keeps the installer's direct-route rule |
| release/always-rotate heading | Breaks the no-rotation rule for version advances |
| release/wording heading | Keeps the no-rotation rule |
| release/docs-only heading | Touches no recorded decision |
| violates body | `{decision}: {rule}. Check {failing} caught it.`, plus one patch-specific clause per patch in the style of `scenario.html` |
| consistent body | `{decision}: {rule}. All {checks} linked checks passed in the replay.` |
| docs-only body | `No decision cites {file}. The release harness still ran: {passed} of {total} checks passed.` |
| checks short | from `scenario.html` for installer; release #2 "Advance leaves CHANGELOG.md untouched", #3 from `evidence/release.toml` evidence text, trimmed to under 60 chars |
| results.intro | `{model} reviewed each patch {repeats} times per arm. Same prompt, same tools, same budget. The graph arm adds one MCP tool.` |
| results.caveats | the four sentences in `results.html`, with each number replaced by its placeholder (`{replay_missed} of {graph_runs} graph runs`, `all {baseline_verdict_misses} baseline verdict misses sit on that line`) |
| use.steps | the six steps in `use.html` |
| relate.intro | Patch Precedent keeps its evidence in one embedded Relate store, `data/precedent.rl`, and asks every question of it in Cypher. |
| relate.capabilities | Embedded store (single-file, no server); Cypher reads and writes; parameter binding (`$path`, `$key`); read-only opens for every query path; the relate CLI's `serve --mcp stdio --read-only` for raw Cypher over MCP |

Placeholders like `{checks}` and `{file}` above are allowed in `body`. Add them to the per-patch value map: `{checks}` (the linked check count) and `{file}` (the first changed file).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site_data.py
def test_prose_replaces_dashes():
    assert prose("Extension distribution — the first-party channel") == "Extension distribution - the first-party channel"
    assert prose("2019–2020") == "2019-2020"

def test_fill_raises_on_missing():
    with pytest.raises(SiteDataError, match=r"\{gone\}"): fill("x {gone}", {})

def test_literal_query_quotes():
    assert literal_query("MATCH (f {path: $path})", {"path": "a'b"}) == "MATCH (f {path: 'a\\'b'})"

def test_six_patch_pages_match_recording():
    d = load_site_data(pins.project_root())
    assert [p.slug for p in d.patches] == ["installer-release-lookup","installer-token-header","installer-wording",
                                          "release-always-rotate","release-wording","release-docs-only"]
    th = next(p for p in d.patches if p.label == "token-header")
    assert (th.passed, th.failed, th.exit_code, th.failing_numbers) == (193, 1, 1, [64])
    assert [c.number for c in th.decisions[0].checks] == [7, 64, 193]
    assert {c.number: c.observed for c in th.decisions[0].checks} == {7: "ok", 64: "not ok", 193: "ok"}
    docs = next(p for p in d.patches if p.label == "docs-only")
    assert docs.decisions == () and docs.verdict["kind"] == "no_decision"

def test_titles_have_no_dashes():
    d = load_site_data(pins.project_root())
    for p in d.patches:
        for t in [c.title for c in p.also_cites] + [x.title for x in p.decisions]:
            assert "—" not in t and "–" not in t

def test_query_literal_runs_against_store():
    d = load_site_data(pins.project_root()); conn = open_readonly(STORE_PATH)
    for _title, q in d.home_chain.queries:
        assert list(conn.execute(q))     # runs as-is and returns rows

def test_eval_numbers_equal_results_json(): ...   # metrics baseline/graph displays: "16/18", "18/18", turns "6.2"/"2.1", cost "$0.73"/"$0.38"
def test_caveats_filled(): ...                    # "3 of 18" appears; no "{" left in any caveat
def test_missing_content_entry_raises(tmp_path): ...  # copy the repo inputs, drop one [patches] table -> SiteDataError
def test_store_stats():
    s = load_site_data(pins.project_root()).store
    assert (s.nodes, s.rels) == (2557, 6844)
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_data.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `data.py` and write `site/content.toml`.** Diff parsing follows `gen_scenario.py` in the mockups folder: hunk headers set the old and new line counters.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/patch_precedent/site/data.py site/content.toml tests/test_site_data.py
git commit -m "feat: site data layer and content file"
```

---

### Task 5: Graph SVG

**Files:**
- Create: `src/patch_precedent/site/graph.py`
- Test: `tests/test_site_graph.py`

**Interfaces:**
- Consumes: `PatchPage`, `DecisionCard`, `Cited`, `StoreStats` (Task 4).
- Produces:
  - `patch_graph_svg(page: PatchPage) -> str`
  - `schema_svg(stats: StoreStats) -> str`

**Layout (decided):**
- **Columns.** Four columns at fixed x: patch, file, decision, check. Nodes in a column are spaced evenly and centred vertically. The commit node sits in the decision column above the curated decisions. Scanned decisions follow below them, smaller, with an outline only.
- **Shapes and colours.**

  | Node | Shape | Colour |
  |---|---|---|
  | patch | ink rounded rect | |
  | file | sunk rect | |
  | decision | ink circle | bright stroke |
  | check (observed ok) | circle | pass |
  | check (not ok) | circle | fail |
  | check (not observed) | circle | line-2 |
  | commit | small square | ink-3 |

- **Edges.** Cubic paths, 1.5px, in line-2. A scanned edge is dashed. A check edge whose check failed is drawn in fail colour.
- **Node markup.** Every node is `<g class="node n-<kind>" tabindex="0" data-id="...">` with a `<title>` such as `#64 runtime: token set: no Authorization header anywhere ... (not ok)`, plus a visible short label (for checks, `#64`).
- **SVG element.** `viewBox` is set from content; `width="100%"`, `role="img"` and `aria-label`; no inline script.
- **No decision.** For a patch with no decision, the file node gets a dashed connector to a `n-none` node labelled "no linked decision".
- **Fixed rendering.** Output is deterministic, with numbers rounded to 1 decimal.
- **Schema graph.** `schema_svg` draws the label graph: File -CITES-> Decision -CHECKED_BY-> Check, Commit -IMPLEMENTS-> Decision, Patch -CHANGES-> File, Patch -PRODUCED-> Observation -FOR_CHECK-> Check, Run -APPLIED-> Patch. Each label shows its node count from `stats.by_label` (0 when absent).

- [ ] **Step 1: Write the failing tests**

```python
def test_token_header_graph_nodes_and_classes():
    svg = patch_graph_svg(_page("token-header"))
    assert svg.count('class="node n-check') == 3
    assert svg.count("n-check-fail") == 1 and "#64" in svg
    assert 'class="node n-decision' in svg and "ADR-0585" in svg
    assert svg.count("n-scanned") == len(_page("token-header").also_cites)
def test_docs_only_graph_has_none_marker():
    svg = patch_graph_svg(_page("docs-only")); assert "n-none" in svg and "n-decision" not in svg
def test_graph_is_deterministic(): assert patch_graph_svg(_page("wording")) == patch_graph_svg(_page("wording"))
def test_graph_is_wellformed_xml(): ET.fromstring(patch_graph_svg(_page("always-rotate")))
def test_schema_svg_counts(): ...   # contains "File", "Decision", "Check", each with its count from stats
def test_no_forbidden_dashes_in_titles(): ...  # <title> text of decision nodes has no U+2013/U+2014
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_graph.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `graph.py`.** Escape every text with `html.escape`.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5: Commit**

```bash
git add src/patch_precedent/site/graph.py tests/test_site_graph.py
git commit -m "feat: patch and schema graphs as SVG"
```

---

### Task 6: Build skeleton, shared layout, intro page and assets

**Files:**
- Create:
  - `src/patch_precedent/site/build.py`
  - `src/patch_precedent/site/templates/{base,macros,intro}.html.j2`
  - `src/patch_precedent/site/static/site.css` (from mockup `site.css`, with ink-3 `#686D79` and a `.js .reveal` gate)
  - `src/patch_precedent/site/static/site.js` (reveal, copy buttons, menu)
  - `src/patch_precedent/site/static/intro.js` (from `intro-v2.html`'s module script)
  - `src/patch_precedent/site/static/c-art.js` (from mockup; add `drawCStacked(type)`)
  - `src/patch_precedent/site/static/pixelcraft/{pixelcraft-banner.js,scatter.js,banner.css}` (from the mockup copy; strip the default artwork constant and Hack4Hack alt; with no `src`, the element renders nothing)
  - `src/patch_precedent/site/static/lockup.png`
  - `site/tools/render-lockup.html`
- Modify: `src/patch_precedent/cli.py` (`site` / `site build` calls `build_site`), `.gitignore` (add `_site/`)
- Test: `tests/test_site_build.py`

**Interfaces:**
- Consumes: `load_site_data`, `SiteData` (Task 4); `patch_graph_svg`, `schema_svg` (Task 5).
- Produces:
  - `build.build_site(root: Path, out: Path) -> list[Path]`. It:
    - deletes and recreates `out`;
    - renders every page;
    - copies `static/` to `out/assets/`;
    - returns the written HTML paths.
  - The Jinja environment uses `autoescape=True` and `StrictUndefined`, with filters `prose` and `rel` (relative path from the current page to a site path).
  - `base.html.j2` provides blocks `title`, `body_class`, `main`, plus `nav_active`.
  - `macros.html.j2` provides:
    - `copy_block(cmd, label="terminal")`, which renders `<pre data-verbatim>`;
    - `badge(kind, text)`;
    - `stat(label, value)`;
    - `check_dot(observed)`;
    - `gh_icon()`;
    - `play_icon()`.
  - Site map, as paths relative to the out root:
    - `index.html`, `home.html`, `results.html`, `use.html`, `relate.html`, `scenarios/<slug>.html`;
    - `assets/...`, `lockup.png` at the root (for `og:image`), `.nojekyll`.
  - CLI: `uv run patch-precedent site [build|record] [--out PATH]`. `build` defaults `--out` to `<root>/_site`, prints `wrote N pages to <out>`, and exits 0. On `SiteDataError` it prints the message to stderr and exits 2.

**Intro page.** `index.html` is built from `intro-v2.html` as-is: dots, corner GitHub icon, Uiverse `pp-enter` with its credit comment verbatim, Enter/Escape/click going to `home.html`. Changes from the mockup:
- `<noscript>` shows `<img src="lockup.png" alt="Patch Precedent">` and a plain `<a href="home.html">Enter</a>` styled as the button.
- Under `prefers-reduced-motion`, `intro.js` uses the PNG and does not create the pixelcraft element.
- Below 600px, `intro.js` draws with `drawCStacked` and sets the slot's aspect ratio to match.
- `<head>` carries `og:title`, `og:description` (the home lede), and `og:image`=`https://namans12.github.io/relate/lockup.png`.

**`lockup.png`.** `site/tools/render-lockup.html` imports `c-art.js` and draws `drawC(FONTS.playfair)` on the page. Render it at 2160x760 with headless Chrome:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars --window-size=2160,760 --screenshot=src/patch_precedent/site/static/lockup.png "http://127.0.0.1:8765/site/tools/render-lockup.html"
```

Serve the repo root first with `python3 -m http.server 8765 --bind 127.0.0.1`; an ES module needs http, not `file://`. If Chrome is unavailable, report `BLOCKED: lockup.png` and continue; the controller renders it with the browser pane.

**Shared layout.**
- **Nav (`base.html.j2`):**
  - brand: the C mark as inline SVG (ink tile, page node, ring with bright stroke, check nodes, as in `c-art.js`) plus "Patch Precedent";
  - links: Overview → `home.html`, Scenarios → `home.html#scenarios`, Results, Use it, Relate;
  - GitHub icon;
  - "Run the demo" with the play icon → `home.html#demo`;
  - a menu button below 720px that toggles a panel.
- **Footer:** "Patch Precedent · MIT", a GitHub link, and "Relate is a product of Neo4j. Not affiliated." No Relate logo.
- **No-JS reveal gate.** `<html class="no-js">` is swapped to `js` by an inline head script. `.reveal` hides content only under `.js`.
- **Copy announcements.** `base.html.j2` holds one visually hidden `<div aria-live="polite" id="sr-status">`. `site.js` copy buttons write "Copied" into it, and the button label shows "Copied" for 1.5 s.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_site_build.py
@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site"); build_site(pins.project_root(), out); return out

PAGES = ["index.html","home.html","results.html","use.html","relate.html"] + [f"scenarios/{s}.html" for s in SLUGS]
ALLOWED = ("https://github.com/Namans12/relate", "https://github.com/relatedb/relate/", "https://fonts.googleapis.com",
           "https://fonts.gstatic.com", "https://relate.devpost.com", "https://namans12.github.io/relate/lockup.png")

def test_all_pages_exist(site): assert all((site / p).is_file() for p in PAGES)   # pages from later tasks: xfail until built
def test_relative_links_resolve(site): ...   # every href/src without a scheme or "#" resolves from its page's directory; "#id" targets exist
def test_external_links_allowlisted(site): ...
def test_no_forbidden_dashes_outside_verbatim(site):
    # parse each .html with html.parser, drop text inside any element with data-verbatim
    # (and inside <script>/<style>), assert no U+2013/U+2014; also check .css/.js under assets
def test_no_gpl_or_hack4hack(site):
    blob = "".join(p.read_text(errors="ignore") for p in site.rglob("*") if p.suffix in {".html",".js",".css"})
    for bad in ("neo4j-viz", "nvl", "Hack4Hack", "pixelcraft.jpg"): assert bad not in blob
    assert not (site / "assets/pixelcraft/pixelcraft.jpg").exists()
def test_uiverse_credit_kept(site): assert "From Uiverse.io by adamgiebl - https://uiverse.io/adamgiebl/new-bird-34" in (site/"index.html").read_text()
def test_built_with_relate_once(site): assert sum(p.read_text().count("Built with Relate") for p in site.rglob("*.html")) == 1
def test_no_local_paths(site): assert all("/Users/" not in p.read_text(errors="ignore") for p in site.rglob("*") if p.is_file() and p.suffix != ".png")
def test_noscript_fallback(site): t = (site/"index.html").read_text(); assert "<noscript>" in t and 'src="lockup.png"' in t
def test_reveal_hidden_only_with_js(site):
    css = (site/"assets/site.css").read_text(); assert ".js .reveal" in css
    assert not re.search(r"(^|[}\s])\.reveal\s*\{[^}]*opacity:\s*0", css)   # no ungated hiding rule
def test_copy_announces(site): assert 'aria-live="polite"' in (site/"home.html").read_text()  # xfail until Task 7
def test_cli_site_build(tmp_path): assert main(["site", "--out", str(tmp_path / "s")]) == 0
def test_cli_site_missing_recording_exit_2(tmp_path, monkeypatch): ...   # point root at a copy without recorded/ -> exit 2
```

  Mark the page-existence and per-page checks for `home`, `scenarios/*`, `results`, `use` and `relate` as `xfail(strict=False)` until Tasks 7-9 build them. Task 9 removes the xfails.

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_build.py -q`. Expected: FAIL (`build_site` missing).
- [ ] **Step 3: Implement.** `build.py`, the base, macros and intro templates, the static assets, the CLI wiring and `.gitignore`. Render `lockup.png`.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: pass, with xfails only for pages not yet built.
- [ ] **Step 5: Commit**

```bash
git add .gitignore src/patch_precedent/site src/patch_precedent/cli.py site/tools tests/test_site_build.py
git commit -m "feat: site build, shared layout and intro page"
```

---

### Task 7: Home page and recorded-run demo panel

**Files:**
- Create: `src/patch_precedent/site/templates/home.html.j2`
- Modify: `src/patch_precedent/site/static/site.js` (carousel, tabs, results bars, demo replay), `site.css`
- Modify: `src/patch_precedent/site/build.py` (render `home.html`)
- Test: `tests/test_site_home.py`

**Interfaces:**
- Consumes: `SiteData.home_chain`, `patches`, `eval.metrics`, `recording`, `content["home"]`, `content["use"]`.
- Produces:
  - `home.html` with section ids `top`, `how`, `scenarios`, `demo`, `results`, `use`;
  - JS hooks `data-carousel`, `data-tabs`, `data-copy`, `data-replay`.

**Sections**, laid out per `welcome.html` (Playfair headings):
1. **Hero**, with:
   - eyebrow `content.home.eyebrow` (the only "Built with Relate");
   - h1, lede;
   - "Run the demo" → `#demo`;
   - "Explore the scenarios" → `#scenarios`;
   - `copy_block("uv run patch-precedent demo all")`;
   - the chain card from `home_chain`: patch, then file, then decision (`prose(title)`), then its checks with observed badges.
2. **How it works**: the three steps.
3. **Scenarios**: a scroll-snap carousel of 6 cards, one per `PatchPage`. Each card has:
   - the scenario tag;
   - a verdict badge from `verdict.kind`;
   - the label as h3;
   - `summary`;
   - check chips `#N ok|not ok` (docs-only shows `{passed} of {total} tests ok`);
   - a link to `scenarios/<slug>.html`.

   Controls: arrow buttons (prev/next, disabled at the ends), dots, and Left/Right keys when focused. Native touch swipe.
4. **Demo**, `id="demo"`, a dark terminal panel:
   - Its bar shows the command and the label `Recorded run · <recorded_at as YYYY-MM-DD HH:MM UTC> · run <run_id>`.
   - The body is a `<pre data-verbatim data-replay>` containing **every** transcript line pre-rendered as `<span class="t-<style>">`. That is the no-JS state.
   - With JS, a Play button hides the lines, then reveals them using `t` scaled so the last line lands at 12 s. A Skip button shows everything. Replay is allowed after it finishes.
   - Opening `home.html#demo` scrolls there and auto-plays once, unless reduced motion is set, in which case it shows all lines at once.
   - Below the panel, `copy_block("uv run patch-precedent demo all")` and the line "Runs locally in about 45 seconds." (`content.home`).
5. **Results**: the dark results panel with bars for verdict correct, catching-checks recall, mean turns and unsupported claims, from `eval.metrics`. Bars animate their width on reveal. Includes `results.intro` and a link to `results.html`.
6. **Use it**: tabs "Run the demo" / "Explain a patch" / "Add to Claude Code", each a copy block from `content.use`, using the ARIA tabs pattern.

**Footer.** As in Task 6.

**CSS requirements.**
- `pre` and code blocks get `overflow-x:auto` and `max-width:100%`.
- Grid children get `min-width:0`.
- Carousel cards are `flex:0 0 min(340px, 85vw)`.
- No element may make `document.documentElement.scrollWidth` exceed the viewport at 320px.

- [ ] **Step 1: Write the failing tests**

```python
def test_home_sections(site): t = _read(site, "home.html"); assert all(f'id="{i}"' in t for i in ("top","how","scenarios","demo","results","use"))
def test_home_carousel_has_six_cards(site): assert _read(site,"home.html").count("data-card") == 6
def test_demo_panel_has_full_transcript(site):
    rec = json.loads((pins.project_root()/"recorded/demo-all.json").read_text())
    assert _read(site,"home.html").count('class="t-line"') == len(rec["transcript"])
def test_demo_label_names_run(site): assert "Recorded run" in _read(site,"home.html") and rec_run_id in _read(site,"home.html")
def test_home_results_numbers(site): t = _read(site,"home.html"); assert "16/18" in t and "18/18" in t
def test_tabs_aria(site): t = _read(site,"home.html"); assert 'role="tablist"' in t and t.count('role="tab"') == 3
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_home.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the template, the JS and the CSS.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: pass.
- [ ] **Step 5: Commit**

```bash
git add src/patch_precedent/site tests/test_site_home.py
git commit -m "feat: site home page with recorded demo panel"
```

---

### Task 8: Patch pages

**Files:**
- Create: `src/patch_precedent/site/templates/patch.html.j2`
- Modify: `src/patch_precedent/site/build.py`, `static/site.js` (graph hover tooltip), `static/site.css`
- Test: `tests/test_site_patch.py`

**Interfaces:**
- Consumes: `PatchPage`, `patch_graph_svg`.
- Produces: `scenarios/<slug>.html` × 6.

**Layout**, per `scenario.html`:
- **Sidebar.** Grouped by scenario, with the decision id as the group meta (none for a group without a curated decision). Six items, each with a status dot: fail if `verdict.kind == "violates"`, pass if `consistent`, none otherwise. The current item is marked `aria-current="page"`.
- **Header.**
  - Eyebrow `Installer · ADR-0585` (or `Release · no linked decision`).
  - h1: the label.
  - Badge from `verdict.kind`, then `summary`.
  - Four stat tiles: Harness `passed / failed`; Exit code; Linked checks (count, or `0`); Failing (`#64`, or `none`).
- **Verdict callout.**
  - Fail styling for `violates`, pass styling for `consistent` (pass-soft background, pass icon `✓`), neutral for `no_decision`/`scanned_only`.
  - `heading` and `body` from content.
- **Diff.** One card per changed file. The header shows the path and `+added -removed`. Then line-numbered rows, `<pre data-verbatim>`, with `ln` grid rows as in the mockup CSS.
- **Decision card(s).**
  - Status pill, `id · prose(title)`, `rule`, `reason`.
  - A links row: Decision (`decision_url`), Scope (`consequences_url`), Citation in `<file>` (`citation_url`), Commit `<sha8>` (`commit_url`).
  - For `docs-only`, instead a card: "`CONTRIBUTING.md` cites no decision", plus the harness line from `body`.
- **Checks table.** Columns: Check (`#N`, mono), Kind, What it asserts (`short`, with the full verbatim name in a `<code data-verbatim>` under it, dimmed), and Result (badge ok / not ok / not observed).
- **Graph card.** Inline `patch_graph_svg(page)`, a legend (patch, decision, check ok, check not ok, scanned), and the caption "Drawn from the Relate store; observed results from the recorded run."
- **`<details>` "Also cited by `<file>`".** A list of `Cited` entries. The count is in the summary, with "scanned from source, not reviewed".
- **`<details>` "Query it yourself".** Each `(title, query)` as `<pre data-verbatim>` with a copy button, plus one line: "Runs as-is against `data/precedent.rl`, with `relate` or the MCP `read_cypher` tool."
- **"Inspect it yourself".** `copy_block(explain_cmd)`.
- **Pager.** Previous / Next.

**Graph JS.** Hovering or focusing a `.node` highlights its edges and shows a tooltip built from its `<title>`. Escape hides it.

- [ ] **Step 1: Write the failing tests**

```python
def test_six_patch_pages(site): assert sorted(p.name for p in (site/"scenarios").glob("*.html")) == sorted(f"{s}.html" for s in SLUGS)
def test_token_header_page_numbers(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert "193 / 1" in t and ">#64<" in t and "ADR-0585" in t and "Breaks the installer&#39;s no-token rule" in t
def test_docs_only_empty_state(site):
    t = _read(site, "scenarios/release-docs-only.html")
    assert "cites no decision" in t and "6 of 6" in t and "n-none" in t and "Decision</a>" not in t
def test_wording_pass_callout(site): assert "callout-pass" in _read(site, "scenarios/installer-wording.html")
def test_check_name_verbatim_keeps_dash(site):
    t = _read(site, "scenarios/release-always-rotate.html")
    assert "byte-identical — no heading inserted" in t      # inside data-verbatim only (dash test enforces)
def test_query_blocks_present(site): assert _read(site,"scenarios/installer-token-header.html").count("MATCH (f:File {path: 'distribution/install.sh'})") >= 1
def test_sidebar_current(site): assert 'aria-current="page"' in _read(site, "scenarios/release-wording.html")
def test_pager_links(site): ...   # first page has no Previous; last has no Next; others link correctly
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_patch.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the template, the build loop, and the graph hover JS and CSS.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: pass, including the Task 6 dash and link tests over the new pages.
- [ ] **Step 5: Commit**

```bash
git add src/patch_precedent/site tests/test_site_patch.py
git commit -m "feat: site patch pages with graph, checks and queries"
```

---

### Task 9: Results, Use it and Relate pages

**Files:**
- Create: `src/patch_precedent/site/templates/{results,use,relate}.html.j2`
- Modify: `src/patch_precedent/site/build.py`; `tests/test_site_build.py` (remove the Task 6 xfails)
- Test: `tests/test_site_pages.py`

**Interfaces:**
- Consumes: `EvalView`, `StoreStats`, `schema_svg`, `content["use"]`, `content["relate"]`, `store._EVIDENCE_QUERY`, `store._CITED_QUERY`, `replay.JOIN_QUERY`, `evidence._OBSERVED_QUERY`.
- Produces: `results.html`, `use.html`, `relate.html`.

**`results.html`** (per mockup):
- h1, `intro`.
- Metric cards, one per `eval.metrics` entry, each with two bars (baseline ink-3, graph accent) and display values.
- The "Read these first" box with the four filled caveats.
- The headline table: metric × baseline × graph, with n per figure.
- The per-case table, full width: case, patch label, expected verdict, and verdict correct per arm as `k/3`, then the remaining per-arm metrics. It is a horizontally scrollable wrapper on small screens.
- Links to `eval/results/20261127T040059Z/RESULTS.md` on GitHub (the `Namans12/relate` blob on `main`) and to `use.html#rescore`.

**`use.html`** (per mockup):
- The prerequisites chips row (macOS, git, uv, no API key).
- Six numbered steps from `content.use.steps`, each with a copy block. Step 4's `.mcp.json` block is a `<pre data-verbatim>`. Step 6 has `id="rescore"`.
- The commands and exit-codes table from the mockup.

**`relate.html`:**
- h1 "How it uses Relate"; `relate.intro`.
- `schema_svg(store)`, with a caption giving the node and relationship totals from `StoreStats`.
- A capability list from `relate.capabilities`.
- Four query cards: "Decision chain for a file" (`_EVIDENCE_QUERY`), "Every decision a file cites" (`_CITED_QUERY`), "Patch to observed result join" (`JOIN_QUERY`), and "Observed results for a patch key" (`_OBSERVED_QUERY`). Each is verbatim with a copy button and a one-line description, and names the CLI command that uses it (`explain`, `demo`, `mcp`).
- A block on the MCP tool `precedent_for_patch` and `relate serve --mcp stdio --read-only`, linking to `use.html`.

- [ ] **Step 1: Write the failing tests**

```python
def test_results_numbers(site):
    t = _read(site, "results.html")
    for s in ("16/18","18/18","13/18","6.2","2.1","$0.73","$0.38","3 of 18"): assert s in t
def test_results_caveats_count(site): assert _read(site,"results.html").count('class="caveat"') == 4
def test_use_steps(site): t = _read(site,"use.html"); assert t.count('class="step"') == 6 and 'id="rescore"' in t
def test_relate_counts_and_queries(site):
    t = _read(site, "relate.html"); assert "2,557" in t and "6,844" in t
    assert t.count("<pre data-verbatim") >= 4 and "precedent_for_patch" in t
```

- [ ] **Step 2: Run them and see them fail.** Run `uv run pytest tests/test_site_pages.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the templates, then remove the xfails in `test_site_build.py`.
- [ ] **Step 4: Run the tests and make sure they pass.** Run `uv run pytest -q`. Expected: everything passes, with no xfails left.
- [ ] **Step 5: Commit**

```bash
git add src/patch_precedent/site tests/test_site_pages.py tests/test_site_build.py
git commit -m "feat: site results, use and relate pages"
```

---

### Task 10: Pages workflow, docs and browser pass

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `README.md` (a "Website" section and a "Terminal output" note), `NOTICE` (Pixelcraft, Uiverse, Jinja2, Rich)
- Test: the existing suite, plus a manual browser pass (controller)

**`.github/workflows/pages.yml`:**

```yaml
name: pages
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run patch-precedent site --out _site
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

**README.**
- A "Website" section, placed after "Run it":
  - the Pages URL `https://namans12.github.io/relate/`;
  - `uv run patch-precedent site` to build it locally, then `python3 -m http.server -d _site` to view it;
  - `uv run patch-precedent site record` to refresh the recording.
- A "Terminal output" note: styled in a terminal; plain when piped, with `NO_COLOR`, or with `--plain`; and `explain --links`.

**NOTICE.** Add:
- "Pixelcraft (the intro effect) by the repository author, MIT."
- "Enter button adapted from Uiverse.io by adamgiebl (MIT)."
- Jinja2 (BSD-3-Clause) and Rich (MIT).

- [ ] **Step 1: Write the workflow, README and NOTICE changes.**
- [ ] **Step 2: Run the full test suites.** Run `uv run pytest -q` and `uv run pytest -m upstream -q`. Expected: all pass.
- [ ] **Step 3: Check the README excerpt against real output.**

  Run `uv run patch-precedent demo all | diff - <(normalised golden)`; the README's quoted plain output must still match the real piped output. Expected: no diff in the lines the README quotes.

- [ ] **Step 4: Browser pass (controller, with the built-in browser).**
  - Build with `uv run patch-precedent site --out _site` and serve it at `/relate/`: `mkdir -p /tmp/pp-pages && ln -sfn $PWD/_site /tmp/pp-pages/relate && python3 -m http.server 8766 -d /tmp/pp-pages`.
  - Visit every page at 320, 375, 768, 1024, 1440 and 1920 wide, and check that `document.documentElement.scrollWidth <= innerWidth`.
  - Check:
    - the intro's stacked lockup below 600;
    - Enter, Escape and click;
    - carousel keys;
    - tabs;
    - copy buttons;
    - demo play, skip and auto-play from `#demo`;
    - graph hover and focus;
    - the menu below 720.
  - Repeat with JS disabled (CSP or devtools) and with reduced motion emulated.
  - Fix and re-test anything that fails. Each fix goes in its own commit with a test where one can pin it.
- [ ] **Step 5: Commit**

```bash
git add .github/workflows/pages.yml README.md NOTICE
git commit -m "docs: pages workflow, website and terminal sections, notices"
```

**After merge (owner action, not in this plan).** `Namans12` sets Settings → Pages → Source to "GitHub Actions". Pushing `.github/workflows/` needs a token with the `workflow` scope; if the push is refused, the owner adds the file.
