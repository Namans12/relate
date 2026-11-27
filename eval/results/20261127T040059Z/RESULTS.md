# Patch Precedent: agent evaluation results

Model: claude-sonnet-5-5. Claude Code CLI: 2.1.292 (Claude Code). Run date: 2026-11-27. Upstream pin: 5f7a510713c3feac146133e77d8c5bb72bae1b11. Repeats per case and arm: 3. Arms: baseline, graph. Both arms receive the identical prompt (eval/prompt.md with the patch inserted) and flags, with file tools only (Read, Grep, Glob) in a clean worktree of the pin. The `graph` arm also gets the MCP tool `mcp__precedent__precedent_for_patch`, which returns the ADRs, tests and each test's observed replay result for the patch; the `baseline` arm has no MCP server. Compared on C1, the baseline and graph commands differ only in: the value of `--mcp-config` (`<results>/mcp-baseline.json` vs `<results>/mcp-graph.json`); the MCP tool `mcp__precedent__precedent_for_patch` in `--allowedTools` (graph only). Total spend over all 36 recorded runs, including excluded ones: $1.11.

## Headline

| Metric | baseline (n=18) | graph (n=18) |
|---|---|---|
| Verdict correct (k/n runs) | 16/18 | 18/18 |
| Decisions exact (k/n runs) | 13/18 | 18/18 |
| Decision recall (mean) | 87% (n=15) | 100% (n=15) |
| Mean checks recall (cases with linked checks) | 37% (n=15) | 91% (n=15) |
| Catching-checks recall (mean; cases with a check expected to fail) | 100% (n=9) | 100% (n=9) |
| Graph tool returned observed results (k/n runs that called it) | n/a | 15/18 |
| Outcomes marked (of linked checks) | 4/39 | 30/39 |
| Unsupported claims, total | 4 (n=18) | 0 (n=18) |
| Unsupported claims, mean per run | 0.22 (n=18) | 0.00 (n=18) |
| Outcome accuracy (pooled over marked checks) | 100% (4/4 marked checks) | 100% (30/30 marked checks) |
| Median time to first correct citation, seconds | 12.4 (n=13) | 7.5 (n=15) |
| Mean turns | 6.2 (n=18) | 2.1 (n=18) |
| Total cost, USD | $0.73 (n=18) | $0.38 (n=18) |

## Per case

| Case | Arm | n | Verdict | Decisions exact | Checks recall | Catching-checks recall | Marked/linked | Unsupported | Outcome acc. | Median citation s | Mean turns | Cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 3 | 3/3 | 3/3 | 67% | 100% | 3/9 | 3 | 100% (3/3) | 20.8 (n=3) | 8.7 | $0.18 |
| C1 | graph | 3 | 3/3 | 3/3 | 78% | 100% | 3/9 | 0 | 100% (3/3) | 6.9 (n=3) | 2.0 | $0.06 |
| C2 | baseline | 3 | 2/3 | 0/3 | 0% | n/a | 0/9 | 0 | n/a (0/0) | 27.1 (n=1) | 9.7 | $0.19 |
| C2 | graph | 3 | 3/3 | 3/3 | 100% | n/a | 9/9 | 0 | 100% (9/9) | 7.6 (n=3) | 2.3 | $0.07 |
| C3 | baseline | 3 | 3/3 | 1/3 | 33% | 100% | 1/9 | 1 | 100% (1/1) | 10.6 (n=3) | 4.7 | $0.12 |
| C3 | graph | 3 | 3/3 | 3/3 | 78% | 100% | 6/9 | 0 | 100% (6/6) | 7.6 (n=3) | 2.0 | $0.07 |
| C4 | baseline | 3 | 3/3 | 3/3 | 50% | 100% | 0/6 | 0 | n/a (0/0) | 10.5 (n=3) | 4.7 | $0.08 |
| C4 | graph | 3 | 3/3 | 3/3 | 100% | 100% | 6/6 | 0 | 100% (6/6) | 8.7 (n=3) | 2.0 | $0.08 |
| C5 | baseline | 3 | 3/3 | 3/3 | 33% | n/a | 0/6 | 0 | n/a (0/0) | 9.0 (n=3) | 4.3 | $0.08 |
| C5 | graph | 3 | 3/3 | 3/3 | 100% | n/a | 6/6 | 0 | 100% (6/6) | 5.7 (n=3) | 2.0 | $0.06 |
| C6 | baseline | 3 | 2/3 | 3/3 | n/a | n/a | 0/0 | 0 | n/a (0/0) | n/a (n=0) | 5.3 | $0.08 |
| C6 | graph | 3 | 3/3 | 3/3 | n/a | n/a | 0/0 | 0 | n/a (0/0) | n/a (n=0) | 2.0 | $0.04 |

## Every run

| Case | Arm | Repeat | Verdict given | Correct | Unsupported | Tool replay found | Citation s | Turns | Cost | Class | Error |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | baseline | 1 | violates | yes | 1 | n/a | 15.4 | 8 | $0.0609 | - |  |
| C1 | baseline | 2 | violates | yes | 1 | n/a | 20.8 | 9 | $0.0600 | - |  |
| C1 | baseline | 3 | violates | yes | 1 | n/a | 20.8 | 9 | $0.0621 | - |  |
| C1 | graph | 1 | violates | yes | 0 | no | 7.5 | 2 | $0.0212 | - |  |
| C1 | graph | 2 | violates | yes | 0 | no | 6.8 | 2 | $0.0213 | - |  |
| C1 | graph | 3 | violates | yes | 0 | yes | 6.9 | 2 | $0.0215 | - |  |
| C2 | baseline | 1 | consistent | yes | 0 | n/a | n/a | 8 | $0.0672 | - |  |
| C2 | baseline | 2 | no_decision | no | 0 | n/a | n/a | 10 | $0.0634 | - |  |
| C2 | baseline | 3 | consistent | yes | 0 | n/a | 27.1 | 11 | $0.0608 | - |  |
| C2 | graph | 1 | consistent | yes | 0 | yes | 10.8 | 3 | $0.0300 | - |  |
| C2 | graph | 2 | consistent | yes | 0 | yes | 7.6 | 2 | $0.0208 | - |  |
| C2 | graph | 3 | consistent | yes | 0 | yes | 5.6 | 2 | $0.0210 | - |  |
| C3 | baseline | 1 | violates | yes | 0 | n/a | 13.4 | 6 | $0.0421 | - |  |
| C3 | baseline | 2 | violates | yes | 0 | n/a | 8.9 | 4 | $0.0333 | - |  |
| C3 | baseline | 3 | violates | yes | 1 | n/a | 10.6 | 4 | $0.0452 | - |  |
| C3 | graph | 1 | violates | yes | 0 | no | 7.6 | 2 | $0.0228 | - |  |
| C3 | graph | 2 | violates | yes | 0 | yes | 8.5 | 2 | $0.0243 | - |  |
| C3 | graph | 3 | violates | yes | 0 | yes | 7.6 | 2 | $0.0227 | - |  |
| C4 | baseline | 1 | violates | yes | 0 | n/a | 12.4 | 5 | $0.0306 | - |  |
| C4 | baseline | 2 | violates | yes | 0 | n/a | 10.5 | 4 | $0.0210 | - |  |
| C4 | baseline | 3 | violates | yes | 0 | n/a | 10.4 | 5 | $0.0253 | - |  |
| C4 | graph | 1 | violates | yes | 0 | yes | 9.9 | 2 | $0.0294 | - |  |
| C4 | graph | 2 | violates | yes | 0 | yes | 6.0 | 2 | $0.0217 | - |  |
| C4 | graph | 3 | violates | yes | 0 | yes | 8.7 | 2 | $0.0243 | - |  |
| C5 | baseline | 1 | consistent | yes | 0 | n/a | 14.5 | 6 | $0.0371 | - |  |
| C5 | baseline | 2 | consistent | yes | 0 | n/a | 7.8 | 3 | $0.0171 | - |  |
| C5 | baseline | 3 | consistent | yes | 0 | n/a | 9.0 | 4 | $0.0238 | - |  |
| C5 | graph | 1 | consistent | yes | 0 | yes | 6.3 | 2 | $0.0232 | - |  |
| C5 | graph | 2 | consistent | yes | 0 | yes | 5.1 | 2 | $0.0188 | - |  |
| C5 | graph | 3 | consistent | yes | 0 | yes | 5.7 | 2 | $0.0187 | - |  |
| C6 | baseline | 1 | consistent | no | 0 | n/a | n/a | 5 | $0.0333 | - |  |
| C6 | baseline | 2 | no_decision | yes | 0 | n/a | n/a | 6 | $0.0267 | - |  |
| C6 | baseline | 3 | no_decision | yes | 0 | n/a | n/a | 5 | $0.0191 | - |  |
| C6 | graph | 1 | no_decision | yes | 0 | yes | n/a | 2 | $0.0150 | - |  |
| C6 | graph | 2 | no_decision | yes | 0 | yes | n/a | 2 | $0.0109 | - |  |
| C6 | graph | 3 | no_decision | yes | 0 | yes | n/a | 2 | $0.0111 | - |  |

## Excluded runs

none

## Method

Scoring is deterministic and offline: it reads each run's final JSON and transcript and compares them with the ground truth in `eval/cases.toml`.

- Final answer: the last line of the run's result text that parses as a JSON object. If the run has no result event, the last assistant text block is used. A run with no such JSON is a parse error: it counts as an incorrect verdict and as not exact, and its other metrics are blank.
- Verdict correct: the final `verdict` equals the case's verdict.
- Decisions exact: the set of listed ADR ids equals the case's set. Precision and recall are stored per run in scored.jsonl.
- Check names are compared after collapsing whitespace runs to single spaces and stripping the ends.
- Checks recall: the share of the case's linked checks that the agent listed. Cases with no linked checks (C6) are left out of this mean.
- Catching-checks recall: the same share, restricted to the case's checks whose expected outcome is `fails`. Cases with no such check (C2, C5, C6) are left out of this mean.
- Decision recall: the share of the case's expected ADR ids that the agent listed; C6 has none and is left out of the mean.
- Graph tool returned observed results: for a run that called `precedent_for_patch`, whether the last such call's result had a non-null `replay`. Runs that made no call (every baseline run) are not counted.
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
claude -p <prompt from eval/prompt.md> --restricted --strict-mcp-config --mcp-config <results>/mcp-baseline.json --tools Read Grep Glob --allowedTools Read Grep Glob --model sonnet --max-turns 25 --output-format stream-json --verbose --no-session-persistence
```

graph (C1):

```sh
claude -p <prompt from eval/prompt.md> --restricted --strict-mcp-config --mcp-config <results>/mcp-graph.json --tools Read Grep Glob --allowedTools Read Grep Glob mcp__precedent__precedent_for_patch --model sonnet --max-turns 25 --output-format stream-json --verbose --no-session-persistence
```

## Limitations

- 6 cases, 3 repeat(s) per case and arm, one model, one repository: the figures are counts over few runs, not estimates of general behaviour.
- The graph arm's evidence is Patch Precedent's own replay of the same fixtures that define the ground truth, so what that arm is shown matches what it is scored against.
- Neither arm can run the test suite (its tools are Read, Grep and Glob only), so any outcome an agent reports without tool evidence is an inference from reading files.
- The prompt asks for the checks "that would catch it"; "checks recall" counts every linked check, including checks expected to pass, and the graph tool lists all linked checks. "Catching-checks recall" counts only the checks expected to fail.
- eval/prompt.md does not define the difference between "consistent" and "no_decision". Both baseline verdict misses are choices on that boundary (C2 r2 answered no_decision; C6 r1 answered consistent with no ADR), and C2 r1 gave the same answer as C6 r1 but was scored correct.
- In 3/18 runs that called the graph tool, the tool reported no replay (C1 r1 (graph), C1 r2 (graph), C3 r1 (graph)). In those runs the agent had altered the patch while copying it into the tool call (a context line was rewritten as an added line), so the changed-lines key did not match, and those agents answered "unknown" for the check outcomes they gave.
- Expected decisions are Patch Precedent's curated per-file decisions, which the graph tool returns directly; listing extra ADRs lowers "decisions exact" but not decision recall.
- Elapsed times include model and tool latency and vary between runs.
