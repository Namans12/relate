# Patch Precedent: agent evaluation results

Model: claude-sonnet-5-5. Claude Code CLI: 2.1.0 (Claude Code). Run date: 2026-11-27. Upstream pin: 149adbb71aa163c5711d79edb6162140bf2671a7. Repeats per case and arm: 1. Arms: baseline, graph. Both arms receive the identical prompt (eval/prompt.md with the patch inserted) and flags, with file tools only (Read, Grep, Glob) in a clean worktree of the pin. The `graph` arm also gets the MCP tool `mcp__precedent__precedent_for_patch`, which returns the ADRs, tests and each test's observed replay result for the patch; the `baseline` arm has no MCP server. Compared on C1, the baseline and graph commands differ only in: the value of `--mcp-config` (`<results>/mcp-baseline.json` vs `<results>/mcp-graph.json`); the MCP tool `mcp__precedent__precedent_for_patch` in `--allowedTools` (graph only). Total spend over all 5 recorded runs, including excluded ones: $0.78.

## Headline

| Metric | baseline (n=2) | graph (n=2) |
|---|---|---|
| Verdict correct (k/n runs) | 2/2 | 1/2 |
| Decisions exact (k/n runs) | 2/2 | 1/2 |
| Mean checks recall (cases with linked checks) | 75% (n=2) | 100% (n=1) |
| Outcomes marked (of linked checks) | 3/5 | 3/5 |
| Unsupported claims, total | 3 (n=2) | 0 (n=1) |
| Unsupported claims, mean per run | 1.50 (n=2) | 0.00 (n=1) |
| Outcome accuracy (pooled over marked checks) | 100% (3/3 marked checks) | 100% (3/3 marked checks) |
| Median time to first correct citation, seconds | 1.5 (n=1) | 1.5 (n=1) |
| Mean turns | 6.5 (n=2) | 4.0 (n=2) |
| Total cost, USD | $0.43 (n=2) | $0.35 (n=2) |

## Per case

| Case | Arm | n | Verdict | Decisions exact | Checks recall | Marked/linked | Unsupported | Outcome acc. | Median citation s | Mean turns | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 1 | 1/1 | 1/1 | 100% | 3/3 | 3 | 100% (3/3) | 1.5 (n=1) | 7.0 | $0.40 |
| C1 | graph | 1 | 1/1 | 1/1 | 100% | 3/3 | 0 | 100% (3/3) | 1.5 (n=1) | 5.0 | $0.25 |
| C4 | baseline | 1 | 1/1 | 1/1 | 50% | 0/2 | 0 | n/a (0/0) | n/a (n=0) | 6.0 | $0.03 |
| C4 | graph | 1 | 0/1 | 0/1 | n/a | 0/2 | 0 | n/a (0/0) | n/a (n=0) | 3.0 | $0.10 |

## Every run

| Case | Arm | Repeat | Verdict given | Correct | Unsupported | Citation s | Turns | Cost | Class | Error |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 1 | violates | yes | 3 | 1.5 | 7 | $0.4000 | - |  |
| C1 | graph | 1 | violates | yes | 0 | 1.5 | 5 | $0.2500 | - |  |
| C4 | baseline | 1 | violates | yes | 0 | n/a | 6 | $0.0307 | - |  |
| C4 | graph | 1 | (agent failure) | no | n/a | n/a | 3 | $0.1000 | agent | exit code 1 |
| C4 | graph | 2 | (parse error) | no | n/a | n/a | n/a | n/a | infrastructure | no init event: tool set not verified |

## Excluded runs

| Case | Arm | Repeat | Class | Error | Cost |
|---|---|---|---|---|---|
| C4 | graph | 2 | infrastructure | no init event: tool set not verified | n/a |

Excluded runs are left out of every aggregate (including cost totals) and appear in the spend sentence at the top.

## Method

Scoring is deterministic and offline: it reads each run's final JSON and transcript and compares them with the ground truth in `eval/cases.toml`.

- Final answer: the last line of the run's result text that parses as a JSON object. If the run has no result event, the last assistant text block is used. A run with no such JSON is a parse error: it counts as an incorrect verdict and as not exact, and its other metrics are blank.
- Verdict correct: the final `verdict` equals the case's verdict.
- Decisions exact: the set of listed ADR ids equals the case's set. Precision and recall are stored per run in scored.jsonl.
- Check names are compared after collapsing whitespace runs to single spaces and stripping the ends.
- Checks recall: the share of the case's linked checks that the agent listed. Cases with no linked checks (C6) are left out of this mean.
- Outcome accuracy: among the case's linked checks that the agent marked `fails` or `passes` in `check_outcomes`, the share equal to ground truth. Pooled over all marked checks; blank when none were marked. A missing `check_outcomes` means none marked.
- Unsupported claims: the number of `check_outcomes` entries marked `fails` or `passes` with no support. Support means a tool result in the transcript that parses as the `precedent_for_patch` JSON and contains a check of the same normalised name with `observed` equal to `ok` or `not ok`. Text that merely mentions a check is not support, and `not observed` is not support. Entries marked `unknown` are not counted.
- Time to first correct citation: seconds from run start to the first assistant message text that contains the case's expected ADR id. Blank for C6 and when the ADR is never cited.
- Turns and cost come from the run record, falling back to the result event.
- Run errors have two classes. Infrastructure errors (spawn failure, no init event, graph tool missing or MCP server not connected, MCP tools present in the baseline) are excluded from every aggregate and listed under Excluded runs. Agent errors (non-zero exit including the turn limit, timeout, file access outside the worktree, dirty worktree) are scored as failed runs: verdict incorrect, counted in every k/n denominator, other metrics blank, turns and cost kept. Unrecognised error text is treated as an agent error.
- Outcomes marked: the number of linked checks the agent marked `fails` or `passes`, out of all linked checks across the runs shown.
- The baseline arm has no tool that reports observed test results, so any "fails" or "passes" it gives is unsupported by construction. Answering "unknown" never counts as unsupported and never lowers outcome accuracy. A claim is "supported" when the agent saw an observed result for that check; whether the claim matches that result is measured separately by outcome accuracy. Medians of time to first correct citation skip runs that never cite the expected ADR; their count is shown as n.
- n is shown with each figure; means skip runs where the value is blank.

## Commands

Exact command lines from runs.jsonl for one run of each arm on C1; the prompt is `<prompt from eval/prompt.md>` with the patch inserted.

baseline (C1):

```sh
claude -p <prompt from eval/prompt.md> --restricted --mcp-config <results>/mcp-baseline.json --allowedTools Read Grep Glob --model sonnet
```

graph (C1):

```sh
claude -p <prompt from eval/prompt.md> --restricted --mcp-config <results>/mcp-graph.json --allowedTools Read Grep Glob mcp__precedent__precedent_for_patch --model sonnet
```

## Limitations

- 2 cases, 1 repeat(s) per case and arm, one model, one repository: the figures are counts over few runs, not estimates of general behaviour.
- The graph arm's evidence is Patch Precedent's own replay of the same fixtures that define the ground truth, so what that arm is shown matches what it is scored against.
- Neither arm can run the test suite (its tools are Read, Grep and Glob only), so any outcome an agent reports without tool evidence is an inference from reading files.
- Elapsed times include model and tool latency and vary between runs.
