# Patch Precedent · Milestone 1 (Installer Demo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A judge runs `uv run patch-precedent demo installer` from a fresh checkout and sees both installer patches run against the unmodified upstream harness. A persistent Relate graph shows why only the release-lookup patch fails.

**Architecture:** A small Python CLI. A reviewed TOML evidence manifest builds the committed `data/precedent.rl` store (File → Decision → Check, plus Commit → Decision). The demo replays baseline, A and B in separate clean worktrees of the pinned upstream. It parses each run's TAP output and records the patches and observations into a private copy of the store. It then answers the plan's join query from that copy. `explain` opens the committed store read-only and never touches upstream.

**Tech Stack:** Python 3.12, uv, `relate-db==1.1.0` (import `relate`), stdlib `tomllib`/`subprocess`/`argparse`, pytest, Git, POSIX `sh`.

**Spec:** `/Users/naman/Documents/ChatGPT/Buildathon/HACKATHON_PLAN.md` (Milestone 1, Upstream inputs, Exact fixtures, Implementation order, Relate traversal, Handoff flags). Every implementer reads it alongside their task.

## Global Constraints

- Project root: `/Users/naman/Documents/ChatGPT/Buildathon/patch-precedent/` (its own git repo).
- Upstream: `https://github.com/relatedb/relate.git` at `5f7a510713c3feac146133e77d8c5bb72bae1b11`; implementing commit `5ac38808547d11f55b02333624cc3e88b46566eb`.
- `relate-db==1.1.0` exactly; `requires-python = ">=3.12,<3.13"`; `.python-version` = `3.12`; commit `uv.lock`.
- Fixtures are byte-exact. `sha256(fixtures/installer/wording.patch) = 96278d65b413302fa666500df1941180248cf2e0eab8b3d5e67ace9bcc8cff29`, `sha256(fixtures/installer/release-lookup.patch) = 635b00b21f4b918ab73a400abdda636e8923d76b2ada61ccc2bc5d17dc0217e5`. The release-lookup diff has 8 tab characters on 7 lines.
- Harness command, run from each checkout root: `sh scripts/tests/test_install_sh.sh`. Never modify upstream files except via `git apply` of a fixture.
- The committed store is only ever opened with `relate.connect(path, read_only=True)`. **Spike finding:** a read-write open rewrites the file even for a read-only query. Replays write to a copy.
- **Spike finding:** rebuilding the store does not reproduce identical bytes. Reproducibility is proven by comparing sorted query snapshots, never file hashes.
- Patch identity is its content: `id = "patch:" + sha256[:12]`. Filenames are display labels only. No verdict may be derived from a filename or hard-coded in display code.
- All Cypher uses `$param` binding; no string-built queries.
- No network after the first upstream fetch; no API keys; no LLM calls.
- Attribution: Relate is Apache-2.0. Fixtures are authored demonstration inputs against Relate's code.

## Spike-verified facts (26 Nov, macOS)

| Run | Exit | Pass / fail | #7 | #193 |
|---|---:|---:|---|---|
| baseline | 0 | 194 / 0 | ok | ok |
| wording.patch (extracted from the plan) | 0 | 194 / 0 | ok | ok |
| release-lookup.patch | 1 | 192 / 2 | not ok | not ok |

TAP shape: `ok N - <description>` / `not ok N - <description>`, then `1..194` and `# pass X, fail Y (of Z)`. Each run takes about 7 s. Check descriptions, verbatim:
- #7 `drift guard: install.sh consults no GitHub API endpoint (ADR-0585)`
- #193 `no case made a GitHub API request (ADR-0585)`

The Relate 1.1.0 API is `relate.connect(path, read_only=False)`. `conn.execute(cypher, params)` iterates `Record`s with `.data()`. A single `.rl` file is written, with no sidecars. Comma-separated `MATCH` patterns work.

## Review Focus

1. **Second invocation:** running the demo twice gives identical graph rows, no duplicated observations, and leaves `data/precedent.rl` byte-unchanged, so `git status` stays clean. Owned by Task 6 and Task 7.
2. **Renamed fixtures:** after copying the fixtures under swapped names, each verdict follows the content. Owned by Task 7.
3. **Unlinked file:** a patch touching a file with no citation prints `<path>: no linked decision` in `explain` and the demo, and does not crash. Owned by Task 5.
4. **Untrustworthy run:** a patch that fails `git apply --check`, a harness timeout, truncated TAP, or a failing baseline is reported as `inconclusive` with the reason, never as pass or fail. Owned by Task 2 and Task 3.
5. **Missing cache:** an absent cache with an unreachable upstream raises a one-line error that names the cache path and says the first run needs internet. It is not a git traceback. Owned by Task 3.

---

## Execution model (orchestrator instructions)

- **Orchestrator and reviewer: Opus (this session).** It dispatches each task to a fresh implementer with `Agent(subagent_type="general-purpose", model="sonnet")`. The prompt contains this plan's Global Constraints, the one task's text, and the spec path. Implementers do **not** commit. The orchestrator reviews the diff for spec compliance first and code quality second. It sends fixes back to the same implementer via SendMessage until approved, then commits.
- **Parallelism:** Task 1 runs first. Tasks 2, 3 and 4 touch disjoint files and may be dispatched concurrently. After that, 5 → 6 → 7 → 8 run in order. Task 9 is run by the orchestrator itself.
- **Final gate:** after Task 9, dispatch one fresh Opus reviewer (`model="opus"`) on the whole repo with only the spec and this plan. It looks for correctness bugs and spec drift.
- Integration tests marked `upstream` need the cache, plus internet on the first run. The default `uv run pytest` runs unit tests only.

## File Structure

```
patch-precedent/
  pyproject.toml  .python-version  uv.lock  .gitignore  README.md  NOTICE
  src/patch_precedent/
    __init__.py
    pins.py        # constants: URLs, SHAs, harness command, project_root()
    diffparse.py   # PatchInfo, read_patch()
    tap.py         # TapResult, TapReport, parse_tap()
    upstream.py    # cache, ensure_upstream(), clean_checkout()
    harness.py     # RunResult, classify(), run_case()
    store.py       # build_store(), open_readonly(), evidence_for_paths(), snapshot()
    replay.py      # record_runs(), JOIN_QUERY, join_rows(), check_expectations()
    report.py      # text rendering only (tables, chains, diffs)
    cli.py         # argparse: build-store, verify-store, explain, demo
  evidence/installer.toml              # reviewed manifest (curated links)
  fixtures/installer/wording.patch
  fixtures/installer/release-lookup.patch
  fixtures/installer/expectations.toml # acceptance criteria keyed by sha256
  data/precedent.rl                    # committed store (built by Task 4)
  runs/                                # gitignored; one dir per demo invocation
  tests/data/{baseline,wording,release-lookup}.tap, truncated.tap
  tests/test_*.py
```

---

### Task 1: Scaffold, pins and byte-exact fixtures

**Files:**
- Create: `pyproject.toml`, `.python-version`, `.gitignore` (`runs/`, `.venv/`, `__pycache__/`, `.pytest_cache/`), `src/patch_precedent/__init__.py`, `src/patch_precedent/pins.py`, `src/patch_precedent/cli.py` (stub), `fixtures/installer/*.patch`
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Produces, in `pins.py`: `UPSTREAM_URL: str` (overridable by env `PATCH_PRECEDENT_UPSTREAM_URL`), `UPSTREAM_SHA`, `IMPLEMENTING_SHA`, `RELATE_VERSION = "1.1.0"`, `HARNESS_CMD = ("sh", "scripts/tests/test_install_sh.sh")`, `HARNESS_TIMEOUT_S = 600`, and `project_root() -> Path`. `project_root()` walks up from `__file__` to the first directory containing both `pyproject.toml` and `evidence/`. Also `STORE_PATH = project_root()/"data"/"precedent.rl"`.
- Produces: console script `patch-precedent = "patch_precedent.cli:main"`; `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1:** `git init` in the project root. Create `pyproject.toml` with hatchling, a `src/` layout, dependency `relate-db==1.1.0`, the dev group `pytest`, and pytest config `addopts = "-m 'not upstream'"` with marker `upstream`. Run `uv lock`.
- [ ] **Step 2:** Extract both ```` ```diff ```` blocks from the spec verbatim into the two fixture files. Do not retype them, because the tabs must survive. One way: `awk '/^```diff/{n++;f=(n==1?"wording.patch":"release-lookup.patch");on=1;next} /^```/{on=0} on{print > f}' HACKATHON_PLAN.md`.
- [ ] **Step 3: Write tests**: `test_fixture_hashes` asserts both sha256 values from Global Constraints; `test_cli_help` runs `main(["--help"])` and expects `SystemExit` with code 0; `test_project_root` asserts `(project_root()/"evidence").is_dir()`. Create an empty `evidence/.gitkeep`.
- [ ] **Step 4:** `uv run pytest` passes; `uv run patch-precedent --help` exits 0.

### Task 2: Diff and TAP parsing; run classification

**Files:**
- Create: `src/patch_precedent/diffparse.py`, `src/patch_precedent/tap.py`, `tests/data/*.tap`
- Test: `tests/test_diffparse.py`, `tests/test_tap.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) PatchInfo(path: Path, label: str, sha256: str, id: str, changed_files: tuple[str, ...])`. Here `label` is the file stem and `id = "patch:" + sha256[:12]`. Also `read_patch(path: Path) -> PatchInfo`. Changed files come from `diff --git a/X b/Y` headers: take the b-side, or the a-side when the b-side is `/dev/null`, deduped in order.
- Produces: `@dataclass(frozen=True) TapResult(number: int, ok: bool, description: str)`, `@dataclass(frozen=True) TapReport(results: tuple[TapResult, ...], planned: int | None, passed: int, failed: int, complete: bool)`, and `parse_tap(text: str) -> TapReport`. `complete` holds iff a plan line `1..N` exists and the results are exactly numbers 1..N. Strip a trailing ` # SKIP ...` or ` # TODO ...` directive from descriptions. Check `scripts/tests/lib/tap.sh` upstream for its exact skip format. Count a skip as passed.

- [ ] **Step 1:** Copy the spike TAP captures into `tests/data/`. They are at `/private/tmp/claude-501/-Users-naman--claude-spares-spare-zlhnQL/93e0637a-f31b-4e1e-a996-0118460b3a22/scratchpad/{wording,release-lookup}.tap`. If they are gone, regenerate them via Task 3's runner, or by hand with a worktree. Copy `wording.tap` as `baseline.tap` too, since the TAP is identical. Create `truncated.tap` as the first 100 lines of `release-lookup.tap`.
- [ ] **Step 2: Write failing tests:**
  - `test_read_patch_changed_files`: both fixtures give `("distribution/install.sh",)`.
  - `test_patch_id_follows_content`: a renamed copy has the same `id` and a different `label`.
  - `test_parse_release_lookup`: `passed == 192`, `failed == 2`, `complete`, and the failing results are numbers `[7, 193]` with the exact descriptions from "Spike-verified facts".
  - `test_parse_wording`: 194/0, complete.
  - `test_truncated_incomplete`: `complete is False`.
  - `test_skip_directive_stripped`, on a synthetic line.
- [ ] **Step 3:** Implement. Run `uv run pytest tests/test_diffparse.py tests/test_tap.py`. Expect PASS.

### Task 3: Upstream cache, clean checkouts and harness runner

**Files:**
- Create: `src/patch_precedent/upstream.py`, `src/patch_precedent/harness.py`
- Test: `tests/test_harness_classify.py` (unit), `tests/test_upstream.py` (`@pytest.mark.upstream`)

**Interfaces:**
- Consumes: `pins.*`; `PatchInfo`, `TapReport` and `parse_tap` (Task 2). If Task 2 runs in parallel, code against these signatures.
- Produces:
  - `cache_dir() -> Path`: env `PATCH_PRECEDENT_CACHE`, else `~/.cache/patch-precedent`.
  - `class UpstreamUnavailable(RuntimeError)`.
  - `ensure_upstream(sha: str = UPSTREAM_SHA) -> Path`: returns the bare repo path `cache_dir()/"relate.git"`. A missing repo gets `git clone --bare --filter=blob:none`. A missing commit gets `git fetch origin <sha>`. Any git failure raises `UpstreamUnavailable` with a message naming the cache path and "first run needs internet".
  - `clean_checkout(sha: str, dest: Path) -> ContextManager[Path]`: `git worktree add --detach`. It asserts `rev-parse HEAD == sha` and an empty `status --porcelain`, and always runs `worktree remove --force` plus `prune` on exit.
  - `@dataclass(frozen=True) RunResult(label: str, patch: PatchInfo | None, base_sha: str, command: str, exit_code: int | None, tap: TapReport | None, log_path: Path, status: Literal["pass","fail","inconclusive"], reason: str | None)`.
  - `classify(apply_ok: bool, timed_out: bool, exit_code: int | None, tap: TapReport | None) -> tuple[status, reason]`. It returns `inconclusive` for a failed apply, a timeout, a missing or incomplete TAP, or exit/TAP disagreement (exit 0 with failures, or nonzero with 0 failures). Otherwise it returns `pass` when `exit == 0 and failed == 0`, and `fail` when `exit != 0 and failed > 0`.
  - `run_case(label: str, patch: PatchInfo | None, run_dir: Path) -> RunResult`. It uses checkout `run_dir/"checkouts"/label` and runs `git apply --check` then `git apply`. It runs `HARNESS_CMD` with `cwd=checkout` and `timeout=HARNESS_TIMEOUT_S`. Combined stdout+stderr goes to `run_dir/f"{label}.log"`, and the exit code is written to `run_dir/f"{label}.exit"`. On an apply failure, it writes the git stderr to the log and returns inconclusive.

- [ ] **Step 1: Write unit tests for `classify`**, one per branch, including `test_failing_baseline_shape_is_fail_not_pass` and `test_exit_tap_disagreement_inconclusive`.
- [ ] **Step 2: Write upstream tests:**
  - `test_missing_cache_offline_message`: set `PATCH_PRECEDENT_CACHE` to a tmp dir and `PATCH_PRECEDENT_UPSTREAM_URL=file:///nonexistent`. `ensure_upstream()` raises `UpstreamUnavailable` whose message contains the cache path. This is not marked `upstream`; it is a unit test.
  - `test_run_baseline` (upstream): status `pass`, 194/0, exit 0.
  - `test_unappliable_patch_inconclusive` (upstream): a patch with a wrong context line is inconclusive and its reason mentions apply.
- [ ] **Step 3:** Implement. Run `uv run pytest` (unit) and `uv run pytest -m upstream tests/test_upstream.py`. Expect PASS. Confirm no worktrees are left: `git --git-dir ~/.cache/patch-precedent/relate.git worktree list` shows only the bare repo.

### Task 4: Evidence manifest, store builder and the committed store

**Files:**
- Create: `evidence/installer.toml`, `src/patch_precedent/store.py`, `data/precedent.rl` (generated)
- Modify: `src/patch_precedent/cli.py` to add `build-store [--out PATH]` and `verify-store`
- Test: `tests/test_store.py`

**Interfaces:**
- Manifest schema. Every URL is a permalink built as `https://github.com/relatedb/relate/blob/<UPSTREAM_SHA>/<path>#L<a>-L<b>`. Line ranges come from the spec's Upstream inputs table.
  - `[upstream] repo, revision`
  - `[[decision]] id="ADR-0585", title, status="Proposed", rule="install.sh consults no GitHub API endpoint", reason, source_path, context_lines=[8,38], consequence_lines=[89,97]`. Write `reason` as 2–3 plain-English sentences: anonymous GitHub API requests are limited to 60/hour per IP, and users behind shared egress (VPNs, corporate NAT, Cloudflare WARP) exhausted that quota and the one-line installer broke. State the scope too: only ADR-0068's installer auth clause is superseded, and version selection still uses releases.json.
  - `[[citation]] file="distribution/install.sh", decision="ADR-0585", lines=[120,128], curated=true`
  - `[[commit]] sha=IMPLEMENTING_SHA, subject="fix(installer): download release assets over the direct route, no GitHub API (LABS-1482, ADR-0585)", implements="ADR-0585"`
  - `[[check]]` ×2: `decision`, `name` (exact TAP description), `kind` (`"static"` / `"runtime"`), `number_at_pin` (7 / 193), `file="scripts/tests/test_install_sh.sh"`, `lines` ([129,135] / [610,615]), and `evidence`. For #7 the evidence is "the script spells a GitHub API endpoint". For #193 it is "a GitHub API request was attempted and recorded in the harness's stubbed curl log".
- Graph built: `(:File {path})-[:CITES {url, curated}]->(:Decision {id,title,status,rule,reason,url,consequences_url})-[:CHECKED_BY]->(:Check {name,kind,number_at_pin,url,evidence})`, `(:Commit {sha,subject,url})-[:IMPLEMENTS]->(:Decision)`, `(:Upstream {repo,revision})`.
- Produces:
  - `load_manifest(path: Path) -> dict`, which validates required keys and raises `ValueError` naming the missing key.
  - `build_store(manifest: Path, out: Path) -> None`, which replaces `out`.
  - `open_readonly(path: Path) -> relate.Connection`.
  - `evidence_for_paths(conn, paths: Sequence[str]) -> dict[str, list[dict]]`. Each path maps to rows with keys `file, decision, title, status, rule, reason, decision_url, citation_url, consequences_url, implementation, commit_subject, commit_url, check, check_kind, check_number_at_pin, check_url, check_evidence`, sorted by `check_number_at_pin`. An unlinked path maps to `[]`.
  - `snapshot(conn) -> list[tuple]`: all node labels and properties, plus all relationship (type, endpoint keys, properties), sorted.

- [ ] **Step 1: Write tests:**
  - `test_build_and_query`: build into tmp, then `evidence_for_paths(["distribution/install.sh"])` gives 2 rows with decision `ADR-0585`, implementation `5ac3880…`, and checks #7 and #193.
  - `test_unlinked_path_empty`: `["README.md"]` gives `{"README.md": []}`.
  - `test_rebuild_snapshot_equal`: two builds give equal `snapshot`s.
  - `test_readonly_leaves_bytes`: hash before, open read-only, query, close, hash unchanged.
  - `test_manifest_missing_key`.
- [ ] **Step 2:** Implement. Run `uv run patch-precedent build-store`, which writes `data/precedent.rl`. `verify-store` builds into a temp file, compares `snapshot`s with the committed store, and exits 0 when they are equal.
- [ ] **Step 3:** `uv run pytest tests/test_store.py` passes; `uv run patch-precedent verify-store` exits 0 and prints the node/rel counts.

### Task 5: `explain <patch-file>` (read-only)

**Files:**
- Create: `src/patch_precedent/report.py` (`render_evidence_chain`, used by Task 7 too)
- Modify: `src/patch_precedent/cli.py`
- Test: `tests/test_explain.py`

**Interfaces:**
- Consumes: `read_patch`, `open_readonly` and `evidence_for_paths`, all with `STORE_PATH`.
- Produces: `render_evidence_chain(path: str, rows: list[dict], observed: dict[str, TapResult] | None = None) -> str`. It prints `file → ADR → checks`, the rule, the reason, the status (`Proposed`, with the implementing commit as evidence), and the permalinks. When `observed` is given, keyed by check name, it adds the observed `ok`/`not ok N` per check. With no rows it prints `<path>: no linked decision`.
- CLI `explain PATCH_FILE [--store PATH]` exits 0. It never imports `upstream` and never runs a subprocess.

- [ ] **Step 1: Write tests:**
  - `test_explain_release_lookup` (capsys): the output contains `distribution/install.sh`, `ADR-0585`, both check descriptions, `5ac38808`, and `60`, from the reason.
  - `test_explain_unlinked`: a synthetic patch on `README.md` prints `README.md: no linked decision`.
  - `test_explain_offline`: `PATCH_PRECEDENT_CACHE` is set to a nonexistent dir and still succeeds.
  - `test_explain_store_unchanged`: the hash of `data/precedent.rl` is unchanged.
- [ ] **Step 2:** Implement. Running `uv run patch-precedent explain fixtures/installer/wording.patch` prints the same chain as the release-lookup patch.

### Task 6: Replay recording and the graph join

**Files:**
- Create: `src/patch_precedent/replay.py`, `fixtures/installer/expectations.toml`
- Test: `tests/test_replay.py`

**Interfaces:**
- Consumes: `RunResult` (Task 3), `PatchInfo`/`TapReport` (Task 2), and the store (Task 4).
- Produces:
  - `record_runs(store_copy: Path, runs: Sequence[RunResult]) -> list[str]` (drift warnings). For each run with a patch: `MERGE (p:Patch {id})` SET `label, sha256`. `MERGE (f:File {path})` per changed file, then `MERGE (p)-[:CHANGES]->(f)`. `MERGE (r:Run {id: p.id})` SET `base, command, exit_code, passed, failed, total, status, log`, then `MERGE (r)-[:APPLIED]->(p)`. For each TAP result whose description equals a `Check.name`: `MERGE (o:Observation {id: p.id + "|" + check name})` SET `tap ("ok"/"not ok"), number`, then `MERGE (p)-[:PRODUCED]->(o)-[:FOR_CHECK]->(c)`. Each check name missing from a run's TAP is returned as a drift warning naming the check and the run.
  - `JOIN_QUERY`: the spec's "Relate traversal" Cypher verbatim, plus `o.number AS tap_number`.
  - `join_rows(conn) -> list[dict]`.
  - `load_expectations(path) -> dict` and `check_expectations(runs, expectations) -> list[str]`, which returns mismatch messages. `expectations.toml` holds a `[baseline]` block (`exit=0, passed=194, failed=0`) and one `[[patch]]` per fixture, keyed by `sha256` with `exit, passed, failed, failing=[descriptions]`. These are acceptance criteria only. They never feed the displayed results.

- [ ] **Step 1: Write tests.** Build synthetic `RunResult`s from `tests/data/*.tap` and a copied store.
  - `test_join_four_rows`: the rows are exactly A/#7 `ok`, A/#193 `ok`, B/#7 `not ok`, B/#193 `not ok`. Each has file `distribution/install.sh`, decision `ADR-0585`, and implementation `5ac38808547d11f55b02333624cc3e88b46566eb`.
  - `test_record_twice_no_duplicates`: calling `record_runs` twice on the same copy still gives 4 rows and 2 `Observation`s per patch.
  - `test_expectations_mismatch_detected`: swap the TAP of the two runs and expect 2 mismatch messages.
  - `test_drift_warning`: a TAP missing #193's description gives a warning naming it.
- [ ] **Step 2:** Implement. Run `uv run pytest tests/test_replay.py`. Expect PASS.

### Task 7: `demo installer` end to end

**Files:**
- Modify: `src/patch_precedent/report.py`, `src/patch_precedent/cli.py`
- Test: `tests/test_demo.py` (`@pytest.mark.upstream`)

**Interfaces:**
- Consumes: everything above.
- Produces: `run_demo(scenario: str = "installer", fixtures_dir: Path | None = None, runs_root: Path | None = None) -> int`. CLI: `demo installer [--fixtures DIR] [--runs-dir DIR]`.
- Flow:
  1. `ensure_upstream()`.
  2. Create `run_dir = runs_root/<UTC yyyymmddTHHMMSSZ>`.
  3. Run the baseline, then each `*.patch` in `fixtures_dir`, sorted by filename. For each patch, print its label, sha256[:12], changed files, and the diff text before running it.
  4. Copy `STORE_PATH` to `run_dir/"replay.rl"` and call `record_runs`.
  5. Print the comparison table. Columns: Input · Changed · Harness exit · Passed/failed · one column per linked check, showing the observed `ok`/`not ok N` from that run's TAP.
  6. For each patch, print `render_evidence_chain` with its observations.
  7. Print the 4 `join_rows` as a table.
  8. Print a derived verdict per patch. If a linked check failed: "violates ADR-0585: <rule>" followed by each failing check's `evidence` text. If all linked checks passed: "consistent with ADR-0585 as far as checks #7, #193 cover". If nothing is linked: "no linked decision".
  9. Print paths for the run dir, each `.log`, `replay.rl` and `summary.json`.
  10. Write `summary.json`, holding runs, rows, warnings and mismatches.
- If the baseline is not `pass`, every patch verdict is shown as `inconclusive (baseline not green)` and the exit code is 2. The spec requires this.
- Exit codes: `0` when the baseline passed, no run was inconclusive, and `check_expectations` is empty. `2` if any run was inconclusive. `3` on an expectation mismatch. `4` on `UpstreamUnavailable`, which prints its message. The harness's own exit 1 for B is displayed, not propagated.

- [ ] **Step 1: Write upstream tests:**
  - `test_demo_matches_acceptance`: exit 0; `summary.json` has baseline 194/0/0, wording 194/0/0, and release-lookup 192/2/1 failing exactly #7 and #193; 4 join rows.
  - `test_demo_twice_identical_and_store_untouched`: two runs give equal sorted join rows, and the sha256 of `data/precedent.rl` is unchanged.
  - `test_failing_baseline_marks_all_inconclusive` (unit, in `tests/test_report.py`): build the verdicts from synthetic `RunResult`s where the baseline is `fail`. Every patch verdict is inconclusive and the computed exit code is 2. To make this testable, factor `compute_verdicts(runs, rows) -> tuple[list[str], int]` out of `run_demo`.
  - `test_demo_renamed_fixtures`: copy the fixtures into tmp as `release-lookup.patch` ← wording content and `wording.patch` ← release-lookup content, then run with `--fixtures`. The patch whose label is now "wording" fails #7 and #193, and the exit code is still 0, because expectations are keyed by sha256.
- [ ] **Step 2:** Implement. Run `uv run patch-precedent demo installer` and confirm it matches the "Spike-verified facts" table. Run `uv run pytest -m upstream`. Expect PASS.

### Task 8: README, NOTICE, store provenance

**Files:**
- Create: `README.md`, `NOTICE`
- Test: the commands in the README are run verbatim in Task 9.

- [ ] **Step 1: Write the README.** It covers:
  - one-paragraph pitch;
  - prerequisites: macOS (the only tested platform), git, uv, internet on first run only;
  - the judge commands: `uv run patch-precedent demo installer`, `uv run patch-precedent explain fixtures/installer/release-lookup.patch`;
  - an example output excerpt, pasted from a real run;
  - the graph model and the join Cypher;
  - store provenance: `evidence/installer.toml`, then `build-store`/`verify-store`. Explain why the bytes differ between rebuilds while the snapshots match. Say the links are curated by hand, with permalinks;
  - cache location and offline replays;
  - run artifacts under `runs/`;
  - upstream SHA and the `relate-db==1.1.0` pin;
  - limitations: macOS only, supplied fixtures only, no MCP or explorer yet;
  - an "AI tools used" disclosure placeholder for the owner to complete.
- [ ] **Step 2: Write the NOTICE.** It states that Relate is © its authors under Apache-2.0 and that the decision text and line references come from relatedb/relate at the pinned SHA. It labels both patches as authored demonstration inputs.

### Task 9: Judge-path verification (orchestrator runs this itself)

- [ ] **Step 1:** In the project, `uv run pytest` and `uv run pytest -m upstream` both pass. `git status` is clean after committing.
- [ ] **Step 2:** `git clone <project> $TMP/judge && cd $TMP/judge && uv run patch-precedent demo installer` exits 0, and the output matches the acceptance table. Run it again. The join rows are identical and `git status` is clean.
- [ ] **Step 3:** With a cold cache (`PATCH_PRECEDENT_CACHE=$TMP/cold`), the first demo fetches from upstream and succeeds. With the network irrelevant, `explain` works from `/tmp` via `uv run --project $TMP/judge patch-precedent explain $TMP/judge/fixtures/installer/release-lookup.patch`.
- [ ] **Step 4:** Rename check through the CLI, as in `test_demo_renamed_fixtures`.
- [ ] **Step 5:** Dispatch the final Opus whole-repo review. Fix confirmed findings via a Sonnet implementer.
- [ ] **Step 6:** Report to the owner: the exact command, the observed three-run comparison, the four graph rows, the store path, the log paths, and any discrepancy or limitation.
