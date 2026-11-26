# Patch Precedent · Milestone 2 (Second Decision, Control, Scanned Citations) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the method generalises. A second decision in a different subsystem (release tooling, ADR-0580) gets the same replay proof. A patch touching a file that cites no decision is correctly reported as "no linked decision". Every explicit `ADR-NNNN` citation in Relate's repo is scanned automatically, while the semantic links (reasons, rules, checks) stay hand-reviewed.

**Architecture:**
- **Scenarios.** A scenario registry replaces the single installer harness. Each scenario has its own harness command, fixtures and expectations.
- **Citation index.** A `scan-citations` command reads the pinned upstream once. It writes a committed, diffable citation index (`evidence/scanned/*.tsv`).
- **Store build.** `build-store` merges the curated manifests (`evidence/*.toml`) with the scanned index into the same single-file Relate store. This stays offline.
- **Display.** `explain` and the demo show curated decision chains in full, and scanned-only citations as a compact "also cites" list.

**Tech Stack:** unchanged from Milestone 1. Python 3.12, uv, `relate-db==1.1.0`, pytest, Git, POSIX `sh`/`bash`.

**Spec:** `/Users/naman/Documents/ChatGPT/Buildathon/HACKATHON_PLAN.md`, row "22–26 Nov": "Validate a second decision in a different subsystem and an unknown-file control. Automate explicit citations while retaining source-backed review for semantic links." Milestone 1's plan (`docs/superpowers/plans/2026-11-26-milestone-1-installer-demo.md`) and its constraints still apply.

## Global Constraints

- Every Milestone 1 constraint still holds:
  - the committed store is opened only read-only, and replays write to a copy;
  - patch identity is its content;
  - all Cypher uses `$param` binding;
  - no network after the first fetch, no API keys;
  - verdicts and results come only from fresh runs and graph queries.
- Upstream stays pinned at `5f7a510713c3feac146133e77d8c5bb72bae1b11`. Scanned data must record this SHA, and `build-store` refuses scanned files from any other SHA.
- `build-store` and `verify-store` stay offline: they read only `evidence/`. Only `scan-citations` needs the upstream cache.
- Scan output is deterministic: two scans give byte-identical TSV files.
- Store size budget: `data/precedent.rl` ≤ 5 MB. The spike gave 2.08 MB for the citation graph.
- Release fixtures are byte-exact. Copy them from the spike, never retype them:

| File | sha256 |
|---|---|
| `fixtures/release/wording.patch` | `25a59c759f3f8876f6fe6495e01d016dbfc1ef83ce717a5b9293936edc291269` |
| `fixtures/release/always-rotate.patch` | `5b21144e810e0ac0b41f213f1f42c2846e7b79410b1dcec5509ff1b11fd5f1c5` |
| `fixtures/release/docs-only.patch` | `8ea2fb7d08c0eb7a34a9304f351477678848ee4f1cdbff9334c177b62ebfc27a` |

  Spike copies are in `/private/tmp/claude-501/-Users-naman--claude-spares-spare-zlhnQL/93e0637a-f31b-4e1e-a996-0118460b3a22/scratchpad/m2/fx/`.
- The installer scenario's fixtures, expectations and acceptance results are unchanged.

## Spike-verified facts (26 Nov, macOS)

Release harness: `sh scripts/tests/test_release_advance.sh`, 6 checks, about 3 s.

| Run | Exit | Pass / fail | Failing |
|---|---:|---:|---|
| baseline | 0 | 6 / 0 | none |
| wording (rewords the skip message) | 0 | 6 / 0 | none |
| always-rotate (drops the `--skip-changelog` guard: "rotation is idempotent") | 1 | 5 / 1 | #2 only |
| docs-only (CONTRIBUTING.md, cites no ADR) | 0 | 6 / 0 | none |

Check descriptions, verbatim:
- #2 `advance: empty-[Unreleased] CHANGELOG.md byte-identical — no heading inserted, [Unreleased] ref unchanged`
- #3 `advance: the version surfaces still advanced`

The spike TAP captures are in the same scratchpad: `m2/baseline.tap` (drop its last line, `exit=0`, which the spike appended), plus `m2/a.tap`, `m2/b.tap` and `m2/c.tap`.

ADR-0580 at the pin:
- File: `docs/adr/0580-post-release-workspace-versioning.md`. Title "Post-release workspace versioning", status "Proposed". Context is at lines 6–25, Decision at 26–45, Consequences from line 66.
- Implementing commit: `d79d8b150561f56b4940876a067d6b7e4781d2bc`, "fix(release): close the cargo package drift window with a post-release version advance (LABS-1443, ADR-0580) (#233)".
- `scripts/release-bump.sh` cites ADR-0580 in its header (lines 13–16) and in the rotation block (lines 224–238, `if (( ! skip_changelog ))`). The checks are in `scripts/tests/test_release_advance.sh`, around lines 45–49.
- Verify every line range with `git show` before writing it into the manifest.

Citation scan at the pin, run as `git grep -I -n -o -E 'ADR-[0-9]{4}' <sha> -- . ':!docs/adr'`:
- 14,182 mentions, giving 6,837 distinct (file, ADR) pairs across 1,982 files and 514 ADRs. There are 567 ADR record files.
- `distribution/install.sh` cites ADR-0115, 0250, 0431, 0457, 0585 and 0586.
- `scripts/release-bump.sh` cites ADR-0278, 0560, 0580 and 0616.
- `CONTRIBUTING.md` cites none.
- Relate 1.1.0 builds this with `UNWIND $rows … MERGE` in 0.16 s, into a 2.08 MB file. A path lookup takes 2 ms.

## Review Focus

1. **Scan provenance and determinism.** Two scans give byte-identical TSVs. Each TSV header names the SHA. `build-store` refuses a TSV whose SHA differs from `pins.UPSTREAM_SHA`. Owned by Task 2 and Task 3.
2. **A file citing many ADRs.** `install.sh` cites 6. `explain` must stay readable: the curated ADR-0585 chain in full, the other 5 as one line each, marked scanned and unreviewed. Verdicts use only decisions with linked checks. Owned by Task 4.
3. **Control patch.** docs-only.patch gives `CONTRIBUTING.md: no linked decision` in `explain` and the demo. The harness passes, and the demo exits 0. Owned by Task 4 and Task 5.
4. **Scanned but unchecked.** A patch whose file cites decisions, none of which has linked checks, is reported as "cites ADR-… (scanned, unreviewed); no linked checks". It is never "consistent with". Owned by Task 4.
5. **`demo all` with a failing scenario.** If one scenario is inconclusive or mismatched, the other scenario's results still print. The overall exit uses Milestone 1's precedence: 4 for an unreachable upstream, then 2, then 3, then 0. Owned by Task 5.

---

## Execution model

Same as Milestone 1. The Opus session orchestrates and reviews; fresh Sonnet implementers handle one task each, sequentially, and commit their own work; Opus reviewers run per task, plus a final whole-branch review; there is one fix wave. Work on branch `m2-second-decision` from `main`.

## File Structure (new or changed)

```
src/patch_precedent/
  scenarios.py      # NEW  Scenario registry (installer, release)
  scan.py           # NEW  citation scan: git grep + ADR header parse → TSV
  harness.py        # run_case takes the harness command from the scenario
  store.py          # merges curated manifests + scanned TSVs; cited_decisions()
  report.py         # "also cites" block; scanned-only verdict
  demo.py           # demo <scenario>|all
  cli.py            # scan-citations; demo choices from registry
  pins.py           # HARNESS_CMD moves into scenarios
evidence/installer.toml          # unchanged content
evidence/release.toml            # NEW curated ADR-0580
evidence/scanned/citations.tsv   # NEW generated, committed
evidence/scanned/decisions.tsv   # NEW generated, committed
fixtures/release/{wording,always-rotate,docs-only}.patch, expectations.toml   # NEW
tests/data/release/{baseline,wording,always-rotate,docs-only}.tap             # NEW
```

---

### Task 1: Scenario registry and release fixtures

**Files:**
- Create: `src/patch_precedent/scenarios.py`, `fixtures/release/*.patch`, `fixtures/release/expectations.toml`, `tests/data/release/*.tap`, `tests/test_scenarios.py`
- Modify: `src/patch_precedent/harness.py`, `src/patch_precedent/pins.py`, `src/patch_precedent/demo.py`, `src/patch_precedent/cli.py`, plus the tests that use `HARNESS_CMD`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Scenario(name: str, harness_cmd: tuple[str, ...], fixtures_dir: Path, expectations_path: Path, timeout_s: int)`
  - `SCENARIOS: dict[str, Scenario]`, with `installer` and `release` in that order
  - `get_scenario(name) -> Scenario`, which raises `KeyError` with the known names
  - Release uses `("sh", "scripts/tests/test_release_advance.sh")`; installer keeps its current command; timeout is 600 for both.
- Changes `run_case(label, patch, run_dir, harness_cmd: tuple[str, ...] = INSTALLER_CMD, timeout_s: int = 600) -> RunResult`, so existing callers keep working.
- `run_demo(scenario)` resolves fixtures and expectations through `get_scenario`. The `--fixtures` override still works, and expectations always come from the scenario's file. An unknown scenario prints the known names and exits 2.
- The CLI `demo` takes its choices from `SCENARIOS`.

- [ ] **Step 1:** Copy the three release fixtures and the four TAP captures from the spike. Assert the sha256 values. Write `fixtures/release/expectations.toml` from the spike table above, using the same schema as the installer file.
- [ ] **Step 2:** Write the tests:
  - `test_registry_names`
  - `test_release_fixture_hashes`
  - `test_parse_release_taps`: counts match the spike table, and always-rotate fails exactly #2 with the exact description
  - `test_expectations_release_ok`: synthetic RunResults from the captures pass `check_expectations`
  - `test_run_release_baseline` (marked upstream): `run_case` with the release command gives pass 6/0
- [ ] **Step 3:** Implement. Running `uv run patch-precedent demo release` must give exit 0. It shows 6/0, 6/0, 5/1 and 6/0, and every verdict reads "no linked decision" for now, because ADR-0580 is not curated until Task 3. `demo installer` output must be byte-identical to before, apart from the timestamped artifact paths.
- [ ] **Step 4:** `uv run pytest` and `uv run pytest -m upstream` pass.

### Task 2: Citation scanner and committed index

**Files:**
- Create: `src/patch_precedent/scan.py`, `evidence/scanned/citations.tsv`, `evidence/scanned/decisions.tsv`, `tests/test_scan.py`
- Modify: `cli.py` (add the `scan-citations` command)

**Interfaces:**
- `parse_grep_output(text: str) -> dict[tuple[str, str], tuple[int, int]]` maps `(path, adr)` to `(first_line, mention_count)`. The input lines are `<sha>:<path>:<line>:<ADR-NNNN>`. Split on the first three `:` only, because paths may not contain `:` but the format starts with the SHA.
- `parse_adr_header(text: str) -> tuple[str, str]` returns `(title, status)`:
  - the title comes from the first line `# ADR-NNNN: <title>`;
  - the status comes from the first `^Status: (.+)$` line;
  - a missing title gives `""`, and a missing status gives `"unknown"`.
- `scan(sha: str = pins.UPSTREAM_SHA) -> tuple[list[tuple], list[tuple]]`:
  - It uses `ensure_upstream()`, then runs `git --git-dir <cache> grep -I -n -o -E 'ADR-[0-9]{4}' <sha> -- . ':!docs/adr'`.
  - It lists `docs/adr/*.md` with `git ls-tree` and reads each header with `git cat-file --batch` or `git show`, keeping it fast.
  - It returns citation rows `(path, adr, first_line, count)` sorted by path then ADR.
  - It returns decision rows `(adr, title, status, record_path)` sorted by ADR. Every ADR that is cited or has a record file appears; `record_path` is `""` when an ADR is cited but has no record.
- `write_tsv(path, header_comment_lines, rows)`. Its format:
  - first, `# patch-precedent scanned citations`, then `# upstream https://github.com/relatedb/relate.git`, then `# revision <sha>`;
  - then a tab-separated column-header line, then the rows;
  - LF line endings and a trailing newline.
- `read_tsv(path) -> tuple[dict[str, str], list[tuple]]` returns the metadata (`revision` and so on) and the rows.
- CLI `scan-citations [--out-dir evidence/scanned]`. It prints the counts and exits 0, or 4 on `UpstreamUnavailable`.

- [ ] **Step 1: Write unit tests** with synthetic grep text and ADR headers:
  - `test_parse_grep_first_line_and_count`
  - `test_parse_adr_header_variants`, covering a missing status and a missing title
  - `test_tsv_roundtrip_byte_stable`: write, read, write again gives identical bytes
- [ ] **Step 2: Write upstream tests**:
  - `test_scan_pinned_known_rows`:
    - `distribution/install.sh` cites exactly the 6 ADRs above;
    - `scripts/release-bump.sh` cites exactly the 4;
    - `CONTRIBUTING.md` is absent;
    - nothing under `docs/adr/` appears in the citations;
    - ADR-0580's decision row has title "Post-release workspace versioning" and status "Proposed".
  - `test_scan_deterministic`: two scans give identical rows.
- [ ] **Step 3:** Implement. Run `uv run patch-precedent scan-citations` and commit both TSVs. Expect about 6,837 citation rows. Record the exact counts and the file sizes in the report.

### Task 3: Store merges curated and scanned evidence; ADR-0580 curated

**Files:**
- Create: `evidence/release.toml`
- Modify: `src/patch_precedent/store.py`, `cli.py` (build-store and verify-store read all evidence), `data/precedent.rl` (rebuilt), `tests/test_store.py`

**Interfaces:**
- `load_evidence(evidence_dir: Path) -> Evidence`. It loads every `evidence/*.toml` manifest in sorted order, plus `evidence/scanned/{citations,decisions}.tsv`. It validates as follows:
  - each manifest's `[upstream] revision` and each TSV `revision` must equal `pins.UPSTREAM_SHA`, otherwise `ValueError` naming the file;
  - Check names are unique across manifests;
  - every curated citation's decision exists.
- `build_store(evidence_dir: Path, out: Path) -> None` replaces the `manifest` argument. It writes everything with `UNWIND $rows` batches. The graph:
  - `(:Decision {id, title, status, url})` for every decision row. `url` is the record permalink, or empty when there is no record. Curated decisions add `rule, reason, consequences_url, curated: true`.
  - `(:File {path})` for every cited path.
  - `(:File)-[:CITES {scanned: bool, curated: bool, line, url}]->(:Decision)`, one edge per (file, decision). A curated citation sets `curated=true` and its curated line url. A scanned one sets `scanned=true` and its first-line url. When both exist they share one edge.
  - `(:Check {name, kind, number_at_pin, url, evidence, harness})`, where `harness` is the harness script path.
  - `CHECKED_BY`, `(:Commit)-[:IMPLEMENTS]->`, and `(:Upstream)` as in Milestone 1.
- `evidence_for_paths(conn, paths)` keeps its exact row contract: curated decisions that have checks and a commit. It must not return scanned-only decisions.
- NEW `cited_decisions(conn, paths) -> dict[str, list[dict]]`. Each row has `file, decision, title, status, decision_url, citation_url, curated, scanned, has_checks`. Rows are sorted with curated first, then by decision id. An uncited path maps to `[]`.
- `verify-store` and `snapshot` work unchanged on the bigger graph. `_KEY` is unchanged: File.path, Decision.id, Check.name, Commit.sha, Upstream.revision, plus the replay labels.
- `evidence/release.toml` (ADR-0580) holds:
  - `rule`: "An advance never rotates CHANGELOG.md; the changelog rotates only at a release cut";
  - `reason`: two or three faithful sentences from the ADR's Decision, namely that rotating at an advance would mint a release section for a version that never shipped, and that main must never carry a released version;
  - the citation `scripts/release-bump.sh` with the rotation-block lines (verify them);
  - the commit `d79d8b15…`;
  - checks #2 (`kind="runtime"`, evidence "an advance rewrote CHANGELOG.md, minting a release section for a version that never shipped") and #3 (`kind="runtime"`, evidence "the advance did not sweep the version surfaces"), with verified line ranges;
  - `harness="scripts/tests/test_release_advance.sh"`.

  `evidence/installer.toml` gains `harness="scripts/tests/test_install_sh.sh"` on its checks.

- [ ] **Step 1: Write tests:**
  - `test_build_merged_counts`: decisions ≥ 567; `install.sh` has 6 cited decisions, of which exactly 1 is curated and has checks.
  - `test_release_chain`: `evidence_for_paths(["scripts/release-bump.sh"])` gives the 2 ADR-0580 rows with checks #2 and #3.
  - `test_cited_decisions_control`: `CONTRIBUTING.md` maps to `[]`.
  - `test_revision_mismatch_refused`
  - `test_duplicate_check_name_refused`
  - `test_store_size_budget`: ≤ 5 MB.
  - The existing store tests are updated to the new `build_store` signature.
- [ ] **Step 2:** Implement, then run `uv run patch-precedent build-store` and `verify-store` (exit 0). Commit the rebuilt store. `git status` must be clean after a second `verify-store`.

### Task 4: Explain and verdicts with scanned citations and the control

**Files:**
- Modify: `src/patch_precedent/report.py`, `cli.py` (explain), `src/patch_precedent/demo.py` (passes the cited decisions to verdicts), `tests/test_explain.py`, `tests/test_report.py`

**Interfaces:**
- `render_cited_block(path: str, cited: list[dict]) -> str`. It renders the scanned-only decisions, those not already shown as curated chains:
```
  also cites (scanned from source, not reviewed)
    ADR-0115 · <title> [<status>]  <citation_url>
    …
```
  Nothing is printed when there are none.
- `explain` prints, per changed file:
  - the curated chains (the existing `render_evidence_chain`), then the `render_cited_block`;
  - if the file cites nothing at all, exactly `<path>: no linked decision`.
- `compute_verdicts(runs, evidence_by_patch, mismatches, cited_by_patch: Mapping[str, list[dict]] | None = None)`. A patch with no curated evidence but with cited decisions gets `<label>: cites ADR-a, ADR-b (scanned, unreviewed); no linked checks`, using sorted unique ids. With nothing cited at all, it keeps `no linked decision`. The exit codes are unchanged.

- [ ] **Step 1: Write tests:**
  - `test_explain_install_shows_scanned_block`: the ADR-0585 chain plus 5 one-line entries, and ADR-0585 is not repeated in the block.
  - `test_explain_release_bump`: the ADR-0580 chain plus 3 scanned entries.
  - `test_explain_control`: docs-only gives exactly `CONTRIBUTING.md: no linked decision`.
  - `test_verdict_scanned_only`
  - `test_verdict_control_no_linked_decision`
- [ ] **Step 2:** Implement, then re-run `uv run patch-precedent demo release`. The expected verdicts are:
  - always-rotate: violates ADR-0580, #2 failing;
  - wording: consistent with ADR-0580 as far as checks #2, #3 cover;
  - docs-only: no linked decision.

  Exit 0.

### Task 5: `demo all` and per-scenario run directories

**Files:**
- Modify: `src/patch_precedent/demo.py`, `cli.py`, `tests/test_demo.py`, `tests/test_demo_preflight.py`

**Interfaces:**
- `run_demo(scenario: str, fixtures_dir=None, runs_root=None) -> int` keeps its behaviour for one scenario. Its run directory becomes `runs/<ts>/<scenario>/`, so `summary.json`, the logs and `replay.rl` live there.
- `run_all(runs_root=None) -> int` runs every scenario in registry order under one `runs/<ts>/`. It prints each scenario's full output under a `### scenario: <name>` banner, then an overall table with the columns scenario | runs | matched | verdict exit, and writes `runs/<ts>/summary.json`, which lists the scenario summaries and the overall exit. It runs `ensure_upstream()` once, up front. Overall exit: 4 if the upstream is unavailable; otherwise the worst of the scenario exits, in the order 2, then 3, then 0.
- CLI: `demo {installer,release,all}`.

- [ ] **Step 1: Write tests:**
  - `test_overall_exit_precedence` (unit; factor out a pure `overall_exit(codes)`)
  - `test_demo_release_acceptance` (upstream): 6/0/0, 6/0/0, 5/1/1 failing exactly #2, and 6/0/0; join rows exist for wording and always-rotate only; exit 0
  - `test_demo_all` (upstream): both scenario summaries, overall exit 0, and the committed store's hash unchanged
- [ ] **Step 2:** Implement. Run `uv run patch-precedent demo all` for real and save the output to the SDD workspace as `m2-demo-all.txt`.

### Task 6: README, NOTICE and the regenerated excerpts

**Files:** `README.md`, `NOTICE`

- [ ] **Step 1:** README updates:
  - "Run it" leads with `uv run patch-precedent demo all`, and still lists `demo installer` and `demo release`.
  - A new "Scenarios" section: one table with the scenario, decision, harness, patches and expected outcome. Include the release story in two sentences: rotation looks idempotent, but an advance must not rotate.
  - "Evidence and provenance" splits the curated part (TOML, hand-reviewed rules, reasons and checks) from the scanned part (TSV, every explicit `ADR-NNNN` mention at the pin, regenerated by `scan-citations`, never interpreted). State the counts from Task 2.
  - `explain` now works on any patch against Relate's repo. Show the control's output.
  - Regenerate the "What you'll see" excerpt verbatim from `m2-demo-all.txt`. Keep it to the overall table, the release comparison and verdicts, and the installer verdicts, with `…` for omissions.
  - Update the exit-code and artifact paths to `runs/<ts>/<scenario>/`.
- [ ] **Step 2:** NOTICE adds three items:
  - ADR titles and statuses for all decisions, quoted in `evidence/scanned/decisions.tsv`;
  - file paths and line numbers of ADR citations in `citations.tsv`;
  - ADR-0580 paraphrased in `evidence/release.toml`, plus the release fixtures' context from `scripts/release-bump.sh` and `CONTRIBUTING.md`.
- [ ] **Step 3:** Check every documented command by running it.

### Task 7: Judge-path verification (controller)

- [ ] Fresh clone of the branch:
  - run `demo all` twice: identical join rows per scenario, store hash unchanged, `git status` clean;
  - run with renamed release fixtures (`--fixtures` on `demo release`): verdicts follow the content;
  - run `explain` for the control and for `release-bump.sh` offline from `/tmp`;
  - run `verify-store` offline;
  - run `scan-citations` twice: byte-identical TSVs, with no diff against the committed files.
- [ ] Final Opus whole-branch review, one fix wave, merge to `main`, push.
