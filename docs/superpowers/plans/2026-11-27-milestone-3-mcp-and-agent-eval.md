# Patch Precedent · Milestone 3 (MCP Evidence Tool and Agent Evaluation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coding agents can query Patch Precedent's Relate graph over MCP, read-only, and get evidence-backed answers. A published, reproducible experiment measures what that access changes. It runs six patch-review cases with and without the graph, using the same model, prompt, repo search and budget.

**Architecture:**
- A small Python MCP server, `patch-precedent mcp` on stdio, exposes one read-only tool, `precedent_for_patch(diff)`. It reads the committed store for decision chains and scanned citations, and the latest replay stores for each linked check's observed result.
- Relate's own MCP server (`relate serve --mcp stdio --read-only`, v1.3.0) is documented and smoke-tested as the raw Cypher view of the same store.
- An `eval` command drives headless Claude Code (`claude -p`, Sonnet) across the cases and arms. It records stream-json transcripts with arrival timestamps, then scores them deterministically into committed results.

**Tech Stack:** as in Milestones 1–2, plus the `mcp` Python SDK (2.3.0) and the Claude Code CLI, which the evaluation needs but `demo` and `explain` do not.

**Spec:** `/Users/naman/Documents/ChatGPT/Buildathon/HACKATHON_PLAN.md`, row "27 Nov–4 Dec": "Add one read-only MCP tool if the CLI is stable. Compare six predefined cases with and without graph access using the same model, repo search, prompts and budget. Publish outcomes, unsupported warnings and time to first correct citation. Freeze features on 4 Dec." Milestones 1–2 constraints still apply.

**Owner decisions (27 Nov):**
- Claude Code with Sonnet runs the evaluation.
- 3 repeats per case and arm, giving 36 runs.
- The graph arm gets evidence-backed verdicts: each linked check's observed replay result.
- Relate's native MCP server is spiked and documented.

## Global Constraints

- Everything from Milestones 1–2 still holds: read-only committed store, content identity, `$param` binding, offline `explain`/`verify-store`, and results only from fresh runs and graph queries.
- `demo all` and `explain` must still run without the Claude CLI, without an API key, and without the relate CLI binary.
- The MCP tool is read-only. It opens every store with `read_only=True`, never runs a harness, and never writes outside its own process.
- **Fairness.** Both arms get the byte-identical prompt, the same model (`--model sonnet`), the same tools (`Read Grep Glob`), the same budget (`--max-turns 25`), the same isolation flags, and the same clean worktree of the pinned upstream. The only difference is the `--mcp-config` file: empty for the baseline, Patch Precedent's server for the graph arm.
- **Isolation flags,** spike-verified on Claude Code 2.1.292: `--restricted --strict-mcp-config --mcp-config <file> --tools Read Grep Glob --allowedTools <list> --model sonnet --max-turns 25 --output-format stream-json --verbose --no-session-persistence`, with stdin from `/dev/null`. `--restricted` ignores user, project and local settings, so the owner's plugins and hooks don't load; it uses the normal login. The worktree must be clean after every run.
- **New installer fixture,** byte-exact: `fixtures/installer/token-header.patch`, sha256 `5146b525a26dbcaf1cba5c3fa781d77a5ffd5085b1295a3c68faec6f565906ba`. It contains 10 lines with tabs. The spike copy is `/private/tmp/claude-501/-Users-naman--claude-spares-spare-zlhnQL/93e0637a-f31b-4e1e-a996-0118460b3a22/scratchpad/m3/token-header.patch`, and its TAP capture is `…/m3/token-header.tap`.
- **Pinned relate CLI:** `relate-darwin-arm64` v1.3.0, sha256 `b1d2d2f59fca696b0c2df35364c8a198a317b6fa733f0b8ff21b8fdcb7e30bc6`, 30,220,448 bytes. It is cached at `~/.cache/patch-precedent/relate-cli-1.3.0/relate-darwin-arm64` after being verified against the release `SHA256SUMS`.
- Feature freeze: 4 Dec 2026.

## Spike-verified facts (27 Nov)

- **Relate MCP.** `relate serve --mcp stdio --read-only --database <copy of data/precedent.rl>`:
  - it lists exactly `read_cypher` and `get_schema`;
  - it answers parameterised Cypher on our store;
  - it leaves the file byte-identical;
  - it takes about 0.4 s.
- **Token-header patch** (sends `Authorization: Bearer $GITHUB_TOKEN` "for the authenticated rate limit"):
  - the harness exits 1 with 193 passed and 1 failed;
  - it fails only `#64 token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)`, which is `scripts/tests/test_install_sh.sh` lines 314–315.
  - ADR-0585 Decision §2 says "**No token.** `GITHUB_TOKEN` is not read".
- **Headless agents** with no graph, using Sonnet and the flags above:
  - release-lookup: correct ADR and both checks in 7 turns, 18 s, $0.08;
  - always-rotate: correct ADR and check #2 in 6 turns, 9 s, $0.03.

  Both stated "I didn't run the tests", so their test-outcome claims were inferred, not observed. In the graph arm, an agent given only Relate's generic `read_cypher` never called it. Hence a domain tool with an explicit description.

## The six cases

| id | scenario · fixture | expected verdict | decisions | linked checks: expected outcome |
|---|---|---|---|---|
| C1 | installer · release-lookup | violates | ADR-0585 | #7 fails, #193 fails, #64 passes |
| C2 | installer · wording | consistent | ADR-0585 | #7, #193 and #64 all pass |
| C3 | installer · token-header | violates | ADR-0585 | #64 fails, #7 and #193 pass |
| C4 | release · always-rotate | violates | ADR-0580 | #2 fails, #3 passes |
| C5 | release · wording | consistent | ADR-0580 | #2 and #3 pass |
| C6 | release · docs-only | no_decision | — | — |

## Review Focus

1. **Fairness drift.** Any difference between arms other than the MCP config is a bug. Owned by Task 4, which needs a test asserting the two command lines differ only in `--mcp-config` and in the MCP tool names in `--allowedTools`.
2. **Patch text arriving altered.** The agent passes the diff through the tool, possibly with tabs, CRLF or trailing whitespace changed. The tool must still identify the patch: a normalised content key gives the same key for the fixture bytes and for a whitespace-mangled copy. If it can't, it says "no replay evidence for this patch" and never guesses. Owned by Task 2.
3. **No replay yet.** The MCP tool must work with no `runs/`: it returns chains and citations with `observed: "not observed"` plus a hint to run `demo all`. Owned by Task 3.
4. **Scoring robustness.** Score a final answer with no parsable JSON line, or with extra prose, as a failed run (`parse_error`), never a crash. The unsupported-claim rule must be deterministic and tested on fixtures. Owned by Task 5.
5. **Results honesty.** The published results must show every run, including failures and any baseline wins, the exact command lines, the model id reported by the CLI, and the spend. Nothing may be cherry-picked. Owned by Task 6 and Task 7.

---

## Execution model

Same as Milestones 1–2:
- the Opus controller dispatches one fresh Sonnet implementer per task, then an Opus task review, sequentially;
- implementers commit their own work;
- there is one final whole-branch review and one fix wave;
- the branch is `m3-mcp-eval`, from `main`.

Task 6 (running the evaluation) is run by the controller, because it spends the owner's usage.

## File Structure (new or changed)

```
src/patch_precedent/
  identity.py      # NEW  normalised patch key
  evidence.py      # NEW  precedent_for_patch(): chains + citations + observed results (pure, read-only)
  mcp_server.py    # NEW  stdio MCP server exposing one tool
  relate_cli.py    # NEW  fetch + verify pinned relate CLI; build MCP config JSON
  eval/            # NEW  cases.py, runner.py, score.py, report.py
  cli.py           # + mcp, fetch-relate-cli, eval run|score|report
evidence/installer.toml                     # + check #64
fixtures/installer/token-header.patch, expectations.toml   # + C3
eval/cases.toml                             # NEW six cases with ground truth
eval/prompt.md                              # NEW the single shared prompt template
eval/results/<ts>/{runs.jsonl,results.json,RESULTS.md,transcripts/*.jsonl}   # NEW committed outputs
tests/data/installer/token-header.tap, tests/test_{identity,evidence,mcp_server,relate_cli,eval_*}.py
```

---

### Task 1: Token-header case and ADR-0585's third check

**Files:** `fixtures/installer/token-header.patch`, `fixtures/installer/expectations.toml`, `evidence/installer.toml`, `data/precedent.rl` (rebuilt), `tests/data/token-header.tap`, plus the tests that pin installer numbers (test_demo, test_report, test_replay, test_store and test_explain, as affected).

- [ ] **Step 1:** Copy the fixture and its TAP capture from the spike and assert the sha256. Add the expectation `exit=1 passed=193 failed=1 failing=["token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)"]`.
- [ ] **Step 2:** In `evidence/installer.toml`, add a third ADR-0585 check:
  - `name` = the exact #64 description;
  - `kind="runtime"`, `number_at_pin=64`;
  - `lines=[314,315]` (verify with `git show`);
  - `harness="scripts/tests/test_install_sh.sh"`;
  - `evidence="an install with GITHUB_TOKEN set sent an Authorization header"`.

  Then run `build-store` and `verify-store`. Store counts become +1 node and +1 relationship.
- [ ] **Step 3:** Update the tests to the new truths:
  - installer runs are baseline 194/0, release-lookup 192/2, token-header 193/1 and wording 194/0;
  - there are 9 installer join rows, with token-header failing exactly #64, and release-lookup and wording showing #64 ok;
  - `explain` on release-lookup lists 3 checks.
- [ ] **Step 4:** Run `uv run pytest`, `uv run pytest -m upstream` and `uv run patch-precedent demo all` (exit 0; installer 4/4, release 4/4).

### Task 2: Normalised patch key and the evidence query

**Files:** `src/patch_precedent/identity.py`, `src/patch_precedent/evidence.py`, `tests/test_identity.py`, `tests/test_evidence.py`

**Interfaces:**
- `patch_key(text: str) -> str`:
  - normalise in this order:
    1. `text.splitlines()`, which also handles CRLF;
    2. strip every whitespace character from each line (`re.sub(r"\s+", "", line)`), so tab, space and trailing-whitespace mangling cannot change the key;
    3. drop the lines that are now empty;
    4. join with `"\n"`.
  - return `"pk:" + sha256(normalised.encode()).hexdigest()[:16]`.
  - Document that this key identifies the patch for evidence lookup only. Verdict identity in the demo stays the byte sha256.
- `latest_replays(runs_root: Path) -> dict[str, Path]` maps scenario name to the newest `replay.rl` found under `runs_root/*/<scenario>/replay.rl`, newest by directory name.
- `precedent_for_patch(diff: str, store: Path, runs_root: Path) -> dict` is pure and read-only. It returns:
```
{"patch_key": "pk:…", "changed_files": [...],
 "replay": {"scenario": "...", "run": "<ts>", "label": "<fixture label>"} | null,
 "files": [{"path": "...",
            "decisions": [{"id","title","status","rule","reason","decision_url","citation_url","commit","commit_url",
                           "checks": [{"name","kind","number_at_pin","url","evidence",
                                       "observed": "ok"|"not ok"|"not observed","tap_number": int|null}]}],
            "also_cites": [{"id","title","status","citation_url"}]}],
 "note": "<one sentence on what 'observed' means and where it came from>"}
```
  - Chains come from `evidence_for_paths` and citations from `cited_decisions`, against the committed store.
  - Observed results come from the replay store whose Patch has a matching `patch_key` (store it on Patch nodes during `record_runs`; see Step 2) and from that run's Observation nodes.
  - When nothing matches, `replay` is null and every check reads `"not observed"`.
  - It never computes or returns a verdict.

- [ ] **Step 1: Tests:**
  - `test_key_ignores_whitespace_mangling`: the fixture bytes, a CRLF version, a trailing-space version and a tab-to-spaces version all give the same key.
  - `test_key_distinguishes_patches`: all six fixtures give distinct keys.
  - `test_precedent_without_replay`: run against a tmp runs dir; checks read "not observed" and replay is null.
  - `test_precedent_with_replay` (upstream): after `demo all` into tmp, C1 shows #7 and #193 as `not ok` and #64 as `ok`; C3 shows #64 `not ok`; C6 has no decisions and empty `also_cites`.
  - `test_precedent_readonly`: the store hashes are unchanged.
- [ ] **Step 2:** Implement. Extend `replay.record_runs` to set `Patch.patch_key`, and extend `store._KEY` only if needed. Keep the Milestone 1 and 2 tests green.

### Task 3: The MCP server, one read-only tool

**Files:** `src/patch_precedent/mcp_server.py`, `cli.py` (`mcp [--store PATH] [--runs-dir DIR]`), `pyproject.toml` (add `mcp==2.3.0`), `tests/test_mcp_server.py`

**Interfaces:**
- One tool, `precedent_for_patch`, with input `{diff: string}` and output the JSON from Task 2 as text content. Annotations: `readOnlyHint: true`, `openWorldHint: false`.
- The tool description is fixed copy that tells an agent when to call it: "Given a unified diff against relatedb/relate at the pinned commit, returns the architectural decisions (ADRs) governing each changed file, their rules and reasons, the regression checks that guard them, and each check's observed result from Patch Precedent's replay of this exact patch. Read-only."
- The server's `instructions` are one sentence pointing to the tool.
- Startup errors (missing store) go to stderr with exit 2. A tool error returns `isError: true` with a one-line message, never a traceback.

- [ ] **Step 1: Tests:**
  - `test_tools_list`: exactly one tool, with the read-only annotation.
  - `test_tool_call_c1`: drive the server over stdio from a subprocess with raw JSON-RPC (`initialize`, `notifications/initialized`, `tools/list`, `tools/call`), using a tmp runs dir from a recorded replay fixture or a synthetic replay store built with `record_runs`.
  - `test_tool_error_is_clean`
  - `test_server_never_writes`: the hashes of every store it touched are unchanged.
- [ ] **Step 2:** Implement with the SDK's stdio server. Keep the MCP import lazy inside the `mcp` subcommand, so `demo` and `explain` don't import it.

### Task 4: Relate CLI fetch and the evaluation runner

**Files:** `src/patch_precedent/relate_cli.py`, `src/patch_precedent/eval/{cases.py,runner.py}`, `eval/cases.toml`, `eval/prompt.md`, `cli.py` (`fetch-relate-cli`, `eval run`), `tests/test_relate_cli.py`, `tests/test_eval_runner.py`

**Interfaces:**
- `ensure_relate_cli() -> Path`:
  - downloads `relate-darwin-arm64` from the v1.3.0 GitHub release over https into `cache_dir()/relate-cli-1.3.0/`;
  - verifies the pinned sha256, and on a mismatch deletes the file and raises;
  - is a no-op when the verified file is already present;
  - on other platforms raises with a one-line "macOS arm64 only" message.
- `relate_mcp_config(store_copy: Path) -> dict` builds Relate's own MCP server entry: `serve --mcp stdio --read-only --database …`.
  - It is used for docs and an upstream smoke test, `test_relate_mcp_reads_store`, which checks `tools/list` gives exactly `read_cypher` and `get_schema`, and a `read_cypher` query gives install.sh's 6 cited ADRs.
  - It is not used by an evaluation arm.
- `eval/cases.toml` holds the six cases in the table above: id, scenario, fixture path, expected verdict, decisions, and per-check expected outcome by exact description.
- `eval/prompt.md` is the single template. Its text is the spike prompt (`…/m3/prompt.txt`), extended so the final JSON line also carries `"check_outcomes": {"<exact description>": "fails"|"passes"|"unknown"}`, plus one sentence: "Say "unknown" for any check whose result you did not observe."
- `build_command(case, arm, paths) -> list[str]` produces the exact argv. Arms are `baseline` (an empty MCP config, allowedTools `Read Grep Glob`) and `graph` (MCP config `patch-precedent mcp --store <store> --runs-dir <runs>`, launched through the project's uv, plus `mcp__precedent__precedent_for_patch`).
- `run_eval(cases, arms, repeats, out_dir, *, worktree, runs_root) -> Path`. It:
  - refuses to start unless a `demo all` replay exists for both scenarios in `runs_root`;
  - creates one clean detached worktree of the pin, reused across runs and asserted clean after each run;
  - runs each case × arm × repeat sequentially in a deterministic interleaved order: repeat-major, then case, then arm alternating;
  - streams stdout lines, prefixing each with its arrival `t_ms` since process start, to `out_dir/transcripts/<case>-<arm>-r<k>.jsonl`;
  - appends one summary line per run to `runs.jsonl`: case, arm, repeat, exit, duration_ms, the `num_turns` and `total_cost_usd` the CLI reported, the model id from init, and the argv.

  A run whose process fails is recorded with an error, and the evaluation continues.
- CLI: `eval run [--repeats 3] [--cases C1,…] [--arms baseline,graph] [--out eval/results/<ts>]`.

- [ ] **Step 1: Tests:**
  - `test_arms_differ_only_in_mcp`: diff the two argv lists for the same case. Only `--mcp-config`'s value and the MCP entries in `--allowedTools` may differ. (Review Focus 1.)
  - `test_prompt_identical_across_arms`
  - `test_run_order_interleaved`
  - `test_refuses_without_replay`
  - `test_checksum_mismatch_deletes`: unit, with a fake download.
  - `test_relate_mcp_reads_store`: upstream.
- [ ] **Step 2:** Implement. Do not run any `claude` command in tests: put a `runner` seam behind an injectable `spawn` function, and have a fake spawn replay a recorded spike transcript.

### Task 5: Deterministic scoring and the results report

**Files:** `src/patch_precedent/eval/{score.py,report.py}`, `cli.py` (`eval score`, `eval report`), `tests/test_eval_score.py`, `tests/data/eval/*.jsonl` (copies of the two spike transcripts plus hand-made edge cases)

**Interfaces:**
- `parse_final(result_text) -> dict | None` takes the last line that parses as a JSON object.
- `score_run(case, transcript_events, final) -> dict` returns:
  - `verdict_correct`;
  - `decisions_precision` and `decisions_recall`;
  - `checks_recall`, by exact description against the case's linked checks;
  - `outcome_accuracy`, over the checks the agent marked fails or passes, against ground truth;
  - `unsupported_claims`;
  - `time_to_first_correct_citation_ms`;
  - `turns` and `cost_usd`.
  - `unsupported_claims` is the count of `check_outcomes` entries set to `fails` or `passes` where the transcript holds no tool_result whose text contains that check's exact description together with an observed status (`"observed": "ok"` or `"observed": "not ok"`). In the baseline arm, every non-`unknown` outcome is unsupported by construction. This is the spec's "unsupported warnings".
  - `time_to_first_correct_citation_ms` is the `t_ms` of the first assistant text or tool_use input that contains the case's expected ADR id. It is null for C6 or if the ADR is never cited.
  - `parse_error: true` when there is no final JSON. All other metrics are then null, and the run counts as a failure.
- `summarise(scored_runs) -> dict` aggregates per arm and per case × arm: verdict accuracy (k/n), mean decisions recall, mean checks recall, total and mean unsupported claims, outcome accuracy, the median time to first correct citation, mean turns, and total cost.
- `render_results_md(summary, runs, meta) -> str` produces `RESULTS.md`: the headline table per arm, the per-case table, every run listed, the exact commands, the model id, the CLI version, the date, the total spend, and a "Limitations" paragraph covering six cases, three repeats, one model, and an evidence source that is the project's own replay.

- [ ] **Step 1: Tests**, on fixture transcripts:
  - the two real spike transcripts score correctly (verdict, decisions, checks, and time to the first ADR mention);
  - a baseline answer claiming "fails" scores 1 unsupported claim per check;
  - a graph answer whose transcript contains the tool result scores 0;
  - a missing JSON line gives `parse_error`;
  - extra prose after the JSON is handled;
  - C6 gives a null citation time.
- [ ] **Step 2:** Implement. Scoring and reporting are pure, with no network and no `claude`.

### Task 6: Run the evaluation (controller)

- [ ] `uv run patch-precedent demo all`, which provides the replay evidence for the graph arm.
- [ ] Smoke test: `uv run patch-precedent eval run --cases C1 --repeats 1`. Inspect both transcripts for isolation (the init event's tools, MCP servers and plugins), confirm the graph arm calls `precedent_for_patch`, and confirm the worktree is clean.
- [ ] Full run: `eval run --repeats 3`, which is 36 runs. Expect roughly $2–6 of usage and 15–30 minutes. Then run `eval score` and `eval report`.
- [ ] Commit `eval/results/<ts>/`. Commit the transcripts if they total ≤ 10 MB; otherwise gzip them.

### Task 7: README, NOTICE and the MCP setup docs

- [ ] A README section "Give your coding agent the graph" covers:
  - the `.mcp.json` snippet for `patch-precedent mcp`, copy-paste ready for Claude Code, plus a one-line `claude mcp add` alternative;
  - the optional Relate native MCP snippet, via `patch-precedent fetch-relate-cli` and `relate serve --mcp stdio --read-only --database <copy>`, with a sample `read_cypher` query.
- [ ] A README section "Does the graph help? (measured)" holds the headline table copied from `RESULTS.md` verbatim, a link to the full results, and how to reproduce: `demo all`, then `eval run`. State that the evaluation needs a Claude Code login and spends usage. `demo`, `explain` and `mcp` don't.
- [ ] Update the installer excerpt and numbers: there are now 4 installer runs and 3 linked checks. Regenerate the excerpt verbatim from a fresh `demo all`.
- [ ] NOTICE: add the token-header fixture context and the #64 check description; Relate CLI v1.3.0 (Apache-2.0), downloaded at run time and not vendored; and the `mcp` SDK, through its license.
- [ ] Run every documented command.

### Task 8: Judge-path verification, final review, merge (controller)

- [ ] Fresh clone:
  - `demo all` twice: exit 0, identical rows, store unchanged, git clean;
  - the `mcp` server smoke test over stdio from `/tmp`;
  - `explain` offline;
  - `verify-store`;
  - `eval score` and `eval report` regenerate the committed `RESULTS.md` byte-identically from the committed transcripts.
- [ ] Final Opus whole-branch review, one fix wave, merge to `main`, push. This must happen by 4 Dec.
