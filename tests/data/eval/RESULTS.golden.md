# Patch Precedent: agent evaluation results

Model: claude-sonnet-5-5. Claude Code CLI: 2.1.0 (Claude Code). Run date: 2026-11-27. Upstream pin: 149adbb71aa163c5711d79edb6162140bf2671a7. Repeats per case and arm: 1. Arms: baseline, graph. Both arms receive the identical prompt (eval/prompt.md with the patch inserted) and identical flags, with file tools only (Read, Grep, Glob) in a clean worktree of the pin. The only differences are the MCP config file and the MCP tool name in the allowed-tools list: the `graph` arm also gets `mcp__precedent__precedent_for_patch`, which returns the ADRs, tests and each test's observed replay result for the patch; the `baseline` arm has no MCP server. Total spend over all 4 recorded runs, including excluded ones: $0.78.

## Headline

| Metric | baseline (n=2) | graph (n=1) |
|---|---|---|
| Verdict correct (k/n runs) | 2/2 | 1/1 |
| Decisions exact (k/n runs) | 2/2 | 1/1 |
| Mean checks recall (cases with linked checks) | 75% (n=2) | 100% (n=1) |
| Unsupported claims, total | 3 (n=2) | 0 (n=1) |
| Unsupported claims, mean per run | 1.50 (n=2) | 0.00 (n=1) |
| Outcome accuracy (pooled over marked checks) | 100% (3/3 marked checks) | 100% (3/3 marked checks) |
| Median time to first correct citation, seconds | 1.5 (n=1) | 1.5 (n=1) |
| Mean turns | 6.5 (n=2) | 5.0 (n=1) |
| Total cost, USD | $0.43 (n=2) | $0.25 (n=1) |

## Per case

| Case | Arm | n | Verdict | Decisions exact | Checks recall | Unsupported | Outcome acc. | Median citation s | Mean turns | Cost |
|---|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 1 | 1/1 | 1/1 | 100% | 3 | 100% (3/3) | 1.5 (n=1) | 7.0 | $0.40 |
| C1 | graph | 1 | 1/1 | 1/1 | 100% | 0 | 100% (3/3) | 1.5 (n=1) | 5.0 | $0.25 |
| C4 | baseline | 1 | 1/1 | 1/1 | 50% | 0 | n/a (0/0) | n/a (n=0) | 6.0 | $0.03 |

## Every run

| Case | Arm | Repeat | Verdict given | Correct | Unsupported | Citation s | Turns | Cost | Error |
|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 1 | violates | yes | 3 | 1.5 | 7 | $0.4000 |  |
| C1 | graph | 1 | violates | yes | 0 | 1.5 | 5 | $0.2500 |  |
| C4 | baseline | 1 | violates | yes | 0 | n/a | 6 | $0.0307 |  |
| C4 | graph | 1 | consistent | no | 0 | n/a | 3 | $0.1000 | exit code 1 |

## Excluded runs

| Case | Arm | Repeat | Error | Cost |
|---|---|---|---|---|
| C4 | graph | 1 | exit code 1 | $0.10 |

Excluded runs are left out of every metric above (including cost totals) and appear in the spend sentence at the top.

## Method

Scoring is deterministic and offline: it reads each run's final JSON and transcript and compares them with the ground truth in `eval/cases.toml`.

- Final answer: the last line of the run's result text that parses as a JSON object. If the run has no result event, the last assistant text block is used. A run with no such JSON is a parse error: it counts as an incorrect verdict and as not exact, and its other metrics are blank.
- Verdict correct: the final `verdict` equals the case's verdict.
- Decisions exact: the set of listed ADR ids equals the case's set. Precision and recall are stored per run in scored.jsonl.
- Check names are compared after collapsing whitespace runs to single spaces and stripping the ends.
- Checks recall: the share of the case's linked checks that the agent listed. Cases with no linked checks (C6) are left out of this mean.
- Outcome accuracy: among the case's linked checks that the agent marked `fails` or `passes` in `check_outcomes`, the share equal to ground truth. Pooled over all marked checks; blank when none were marked. A missing `check_outcomes` means none marked.
- Unsupported claims: the number of `check_outcomes` entries marked `fails` or `passes` with no support. Support means a tool result in the transcript that parses as the `precedent_for_patch` JSON and contains a check of the same normalised name with `observed` equal to `ok` or `not ok`. Text that merely mentions a check is not support, and `not observed` is not support. Entries marked `unknown` are not counted.
- Time to first correct citation: seconds from run start to the first assistant message (text or tool-call input) that contains the case's expected ADR id. Blank for C6 and when the ADR is never cited.
- Turns and cost come from the run record, falling back to the result event.
- Runs whose record has an error (non-zero exit, timeout, tool-set mismatch, access outside the worktree, dirty worktree) are excluded from all metrics and listed above.
- n is shown with each figure; means skip runs where the value is blank.

## Commands

Exact command lines from runs.jsonl for one run of each arm on C1; the prompt is `<prompt from eval/prompt.md>` with the patch inserted.

baseline (C1):

```sh
claude -p <prompt from eval/prompt.md> --restricted --mcp-config /x/mcp-baseline.json --allowedTools Read Grep Glob --model sonnet
```

graph (C1):

```sh
claude -p <prompt from eval/prompt.md> --restricted --mcp-config /x/mcp-graph.json --allowedTools Read Grep Glob mcp__precedent__precedent_for_patch --model sonnet
```

## Limitations

- Six cases, one repository, one model, and a small number of repeats: the figures are counts over few runs, not estimates of general behaviour.
- The graph arm's evidence is Patch Precedent's own replay of the same fixtures that define the ground truth, so what that arm is shown matches what it is scored against.
- The baseline arm runs in restricted mode and cannot run the test suite, so any outcome it reports for a check is an inference from reading files.
- Elapsed times include model and tool latency and vary between runs.
