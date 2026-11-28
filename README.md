# Patch Precedent

Two scenarios, each replaying authored patches against an unmodified upstream test harness and explaining the results through a Relate graph.

**Live site:** [patch-precedent.vercel.app](https://patch-precedent.vercel.app)

**installer.** Three patches touch the same installer file, `distribution/install.sh`. The Relate graph links that file to ADR-0585 ("the installer downloads release assets over the direct route"), the commit that implemented it, and the three regression checks that guard it. Replaying the patches through the unmodified upstream test harness shows that two of them break the ADR: the release-lookup patch probes the GitHub release API to improve an error message, and the token-header patch sends `GITHUB_TOKEN` as an `Authorization` header for a better rate limit. The wording patch passes.

**release.** ADR-0580 says a post-release version advance must never rotate `CHANGELOG.md`. A patch to `scripts/release-bump.sh` that always rotates looks harmless because rotation is idempotent, but it breaks that rule and fails check #2 of the release harness. A rewording patch passes, and a docs-only patch to `CONTRIBUTING.md`, which cites no decision, is the control.

Evidence (graph) and observation (test runs) stay separate: the committed graph is usable before any patch runs, and the replay adds observations on a copy.

The graph is also exposed to coding agents as a read-only MCP tool, and its effect on an agent's answers is measured; see [Give your coding agent the graph](#give-your-coding-agent-the-graph) and [Does the graph help? (measured)](#does-the-graph-help-measured).

## Run it

Prerequisites:

- macOS (the only platform this has been tested on)
- git
- [uv](https://docs.astral.sh/uv/)
- Internet access on the first run only. The first run needs it for uv to fetch Python 3.12 and `relate-db==1.1.0`, and for the demo to fetch the upstream source (about 15 MB), cached as a bare clone at `~/.cache/patch-precedent/relate.git` (override the directory with `PATCH_PRECEDENT_CACHE`). Later runs need no network.

Get the code:

```bash
git clone https://github.com/Namans12/patch-precedent.git && cd patch-precedent
```

Run both scenarios, replaying each baseline and its fixture patches against the upstream harness and explaining the results:

```bash
uv run patch-precedent demo all
```

One scenario at a time:

```bash
uv run patch-precedent demo installer
uv run patch-precedent demo release
```

`demo all` takes about 45 seconds on the tested Mac once the upstream cache is warm.

Show the source chain behind a patch without fetching upstream or executing anything:

```bash
uv run patch-precedent explain fixtures/installer/release-lookup.patch
```

`explain` works on any diff against Relate at the pinned commit, not only the fixtures. For a file that cites no decision, such as the release scenario's control, the full output is:

```bash
uv run patch-precedent explain fixtures/release/docs-only.patch
```

```text
patch    docs-only (sha256 8ea2fb7d08c0)
changes  CONTRIBUTING.md
mode     read-only: no upstream fetch, no patch executed

CONTRIBUTING.md: no linked decision
```

## Website

A static site is generated from the committed evidence and recordings: an overview with the recorded demo, one page per patch (diff, decision, checks, graph and the Cypher behind it), the evaluation results, a Relate page with the store and its four queries, and setup steps. It is live at [patch-precedent.vercel.app](https://patch-precedent.vercel.app), which is also the hackathon demo link.

Build it locally and view it:

```bash
uv run patch-precedent site
python3 -m http.server -d _site
```

Refresh the recording the site replays (`recorded/demo-all.json`, committed):

```bash
uv run patch-precedent site record
```

Deploy with the Vercel CLI from a local build. This needs your own Vercel login, and Node is needed only for this optional step:

```bash
uv run patch-precedent site --out _site --base-url https://patch-precedent.vercel.app
npx vercel deploy _site --prod
```

`src/patch_precedent/site/static/lockup.png` is rendered from `c-art.js` by `site/tools/render-lockup.html` in headless Chrome (the command is in the file).

`--base-url` is only needed for link previews (the absolute `og:image` URL); without it the site builds and works the same, with relative links throughout. The build copies `vercel.json` into `_site/`, because Vercel reads it from the deployed folder. `_site/` is not committed. `--out` replaces only an empty directory or one a previous `site` build made (it carries a `.patch-precedent-site` marker); it refuses the project root, its parents, files and any other non-empty directory.

### Terminal output

In a terminal, `demo`, `demo all` and `explain` print styled output. The output is plain text when it is piped, when `NO_COLOR` is set, or when `--plain` is passed; the plain output is what is quoted in this README and is compared against a golden file in the tests. `explain --links` adds GitHub permalinks to the upstream files and commits (styled output only).

## Scenarios

| Scenario | Decision | Harness | Patches | Observed outcome |
|---|---|---|---|---|
| `installer` | ADR-0585, the installer downloads release assets over the direct route | `sh scripts/tests/test_install_sh.sh` (194 checks) | `release-lookup`, `token-header`, `wording` | `release-lookup` violates ADR-0585 (exit 1, 192 / 2, fails #7 and #193); `token-header` violates ADR-0585 (exit 1, 193 / 1, fails only #64); `wording` consistent (exit 0, 194 / 0) |
| `release` | ADR-0580, post-release workspace versioning: an advance never rotates `CHANGELOG.md` | `sh scripts/tests/test_release_advance.sh` (6 checks) | `always-rotate`, `wording`, `docs-only` | `always-rotate` violates ADR-0580 (exit 1, 5 / 1, fails #2); `wording` consistent (exit 0, 6 / 0); `docs-only` has no linked decision (exit 0, 6 / 0) |

The token-header patch makes `fetch_url` send `Authorization: Bearer $GITHUB_TOKEN` when the variable is set, for the authenticated rate limit. ADR-0585 says `GITHUB_TOKEN` is not read, and check #64 (`token set: no Authorization header anywhere`) fails; the static check #7 and the runtime check #193 still pass, so only the linked check that watches that clause catches it.

The release scenario's rotation patch drops the `--skip-changelog` guard in `scripts/release-bump.sh` on the argument that rotation is idempotent. Check #2 shows that an advance then rewrites `CHANGELOG.md`.

## What you'll see

An excerpt of a real `demo all` run. `…` marks omitted sections: the baselines, the per-patch diffs, the graph join tables and the artifact paths in both scenarios, and the installer scenario's comparison and graph evidence. The release scenario's comparison, graph evidence and control line are shown as printed.

```text
### scenario: installer
…

== verdicts ==
release-lookup: violates ADR-0585 — install.sh consults no GitHub API endpoint and does not read GITHUB_TOKEN
    #7 static: the script spells a GitHub API endpoint
    #193 runtime: a GitHub API request was attempted and recorded in the harness's stubbed curl log
    harness exit 1, 192 passed / 2 failed
token-header: violates ADR-0585 — install.sh consults no GitHub API endpoint and does not read GITHUB_TOKEN
    #64 runtime: an install with GITHUB_TOKEN set sent an Authorization header
    harness exit 1, 193 passed / 1 failed
wording: consistent with ADR-0585 as far as checks #7, #64, #193 cover

replay check: 4/4 runs match fixtures/installer/expectations.toml (by content sha256)
  release-lookup — expected regression reproduced; demo replay succeeded
  token-header — expected regression reproduced; demo replay succeeded

…

### scenario: release
…

== comparison ==
Input          Changed                  Exit  Passed/failed  #2 runtime  #3 runtime
-------------  -----------------------  ----  -------------  ----------  ----------
baseline       — (unpatched)            0     6 / 0          ok 2        ok 3
always-rotate  scripts/release-bump.sh  1     5 / 1          not ok 2    ok 3
docs-only      CONTRIBUTING.md          0     6 / 0          ok 2        ok 3
wording        scripts/release-bump.sh  0     6 / 0          ok 2        ok 3

== graph evidence ==
scripts/release-bump.sh
  cites ADR-0580 · Post-release workspace versioning [Proposed]
    rule      An advance never rotates CHANGELOG.md; the changelog rotates only at a release cut
    why       After each release the workspace advances to the next unreleased version,
              so main never carries a released version. The advance performs the
              version-surface sweep without the changelog rotation, because an advance
              is not a release cut and rotating then would mint a release section for a
              version that never shipped. The released version therefore exists only on
              the tagged commit and on the registries.
    citation  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/release-bump.sh#L224-L238
    decision  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/docs/adr/0580-post-release-workspace-versioning.md#L26-L45
    scope     https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/docs/adr/0580-post-release-workspace-versioning.md#L66-L78
    commit    d79d8b15 fix(release): close the cargo package drift window with a post-release version advance (LABS-1443, ADR-0580) (#233) (https://github.com/relatedb/relate/commit/d79d8b150561f56b4940876a067d6b7e4781d2bc)
    checks
      #2    runtime  advance: empty-[Unreleased] CHANGELOG.md byte-identical — no heading inserted, [Unreleased] ref unchanged
            always-rotate → not ok 2
            wording → ok 2
            https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/tests/test_release_advance.sh#L45-L46
      #3    runtime  advance: the version surfaces still advanced
            always-rotate → ok 3
            wording → ok 3
            https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/tests/test_release_advance.sh#L48-L49
  also cites (scanned from source, not reviewed)
    ADR-0278 · npm distribution [Accepted]  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/release-bump.sh#L18
    ADR-0560 · crates.io and PyPI distribution [Proposed]  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/release-bump.sh#L184
    ADR-0616 · npm platform packages resolve as file: links in the repository, registry pins injected at pack time [Proposed]  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/release-bump.sh#L193

CONTRIBUTING.md: no linked decision

…

== verdicts ==
always-rotate: violates ADR-0580 — An advance never rotates CHANGELOG.md; the changelog rotates only at a release cut
    #2 runtime: an advance rewrote CHANGELOG.md, minting a release section for a version that never shipped
    harness exit 1, 5 passed / 1 failed
docs-only: no linked decision
wording: consistent with ADR-0580 as far as checks #2, #3 cover

replay check: 4/4 runs match fixtures/release/expectations.toml (by content sha256)
  always-rotate — expected regression reproduced; demo replay succeeded

…

== overall ==
scenario   runs  matched  exit
installer  4     4/4      0
release    4     4/4      0
overall exit 0
```

The demo shows outcomes only from observed runs and live graph queries. It prints each verdict from the harness's TAP output joined to the graph; nothing is hard-coded by filename.

## Give your coding agent the graph

`patch-precedent mcp` serves one read-only [MCP](https://modelcontextprotocol.io) tool over stdio, `precedent_for_patch(diff)`. Give it a unified diff against Relate at the pinned commit and it returns the decisions (ADRs) governing each changed file with their rule and reason, the regression checks that guard them, and each check's observed result from Patch Precedent's replay of that exact patch (replays exist for the six fixture patches after `demo all`; any other diff gets `not observed`). It opens the committed store with `read_only=True`, never runs a harness and writes nothing.

For Claude Code, add this to a `.mcp.json` in the project where you want the tool, replacing `<path-to-patch-precedent>` with the absolute path of this repository's clone:

```json
{"mcpServers": {"precedent": {"command": "uv", "args": ["run", "--project", "<path-to-patch-precedent>", "--quiet", "patch-precedent", "mcp"]}}}
```

The equivalent one-liner:

```bash
claude mcp add --scope project precedent -- uv run --project <path-to-patch-precedent> --quiet patch-precedent mcp
```

The tool needs a prior `uv run patch-precedent demo all` to report observed results; without a replay, every check reads `"not observed"`. Matching is by the patch's changed lines, ignoring whitespace and context, so a diff whose tabs or trailing spaces were altered in transit still finds its replay.

A trimmed real result for `fixtures/installer/token-header.patch` (`…` marks omitted fields and the omitted "also cites" list):

```text
{
  "patch_key": "pk:c864bd567ac3290b",
  "changed_files": ["distribution/install.sh"],
  "replay": {"scenario": "installer", "run": "20261127T040959Z", "label": "token-header"},
  "files": [{
    "path": "distribution/install.sh",
    "decisions": [{
      "id": "ADR-0585",
      "title": "The installer downloads release assets over the direct route",
      "status": "Proposed",
      "rule": "install.sh consults no GitHub API endpoint and does not read GITHUB_TOKEN",
      …
      "checks": [
        {"name": "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)",
         "kind": "static", "number_at_pin": 7, "observed": "ok", …},
        {"name": "token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)",
         "kind": "runtime", "number_at_pin": 64, "observed": "not ok", …},
        {"name": "no case made a GitHub API request (ADR-0585)",
         "kind": "runtime", "number_at_pin": 193, "observed": "ok", …}
      ]
    }],
    …
  }],
  …
}
```

Each check also carries a permalink at the pinned upstream SHA and what a failure means. The `run` timestamp comes from your local `runs/` directory, so yours will differ; `patch_key` is computed from the diff's changed lines and is the same everywhere.

### Relate's own MCP server

Relate ships an MCP server of its own, which can query the store directly. This is optional and separate from the tool above. `fetch-relate-cli` downloads the pinned v1.3.0 `relate` binary for macOS arm64, verifies its SHA-256 and prints its path (cached under `~/.cache/patch-precedent/`):

```bash
uv run patch-precedent fetch-relate-cli
```

Point the server at a copy of the store, not at `data/precedent.rl` itself (opening a Relate file read-write rewrites it, as noted under How it works):

```bash
cp data/precedent.rl /tmp/precedent-copy.rl
<path printed by fetch-relate-cli> serve --mcp stdio --read-only --database /tmp/precedent-copy.rl
```

As an `.mcp.json` entry (use absolute paths):

```json
{"mcpServers": {"relate": {"command": "<path printed by fetch-relate-cli>", "args": ["serve", "--mcp", "stdio", "--read-only", "--database", "<copy of data/precedent.rl>"]}}}
```

It exposes two tools, `read_cypher` and `get_schema`. A sample `read_cypher` call, with the statement in `statement` and bound values in `parameters`:

```text
statement:  MATCH (d:Decision {id: $id})-[:CHECKED_BY]->(c:Check)
            RETURN c.number_at_pin AS n, c.name AS name ORDER BY n
parameters: {"id": "ADR-0585"}
```

It returns three rows: #7 `drift guard: install.sh consults no GitHub API endpoint (ADR-0585)`, #64 `token set: no Authorization header anywhere (GITHUB_TOKEN never rides a request)` and #193 `no case made a GitHub API request (ADR-0585)`. This server knows only the committed graph; it has no replay results, which is what `precedent_for_patch` adds.

## Does the graph help? (measured)

The headline table from [`eval/results/20261127T040059Z/RESULTS.md`](eval/results/20261127T040059Z/RESULTS.md), copied verbatim:

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

Setup: 6 cases (three installer patches, two release patches and one docs-only control; ground truth in `eval/cases.toml`), 3 repeats per case and arm, 36 runs in all, with Claude Sonnet through Claude Code. Both arms get the identical prompt and tools (`Read`, `Grep`, `Glob`) in a clean worktree of the pinned upstream; the graph arm adds one MCP tool, `precedent_for_patch`.

The robust differences in this run: the graph arm listed exactly the expected decisions in 18/18 runs against 13/18, took fewer turns (2.1 vs 6.2 mean) and cost less ($0.38 vs $0.73). Verdicts were near-equal (18/18 vs 16/18), and both baseline misses fall on a boundary the prompt does not define. The baseline made 4 unsupported claims against 0, and all 4 matched the observed results (see outcome accuracy). Five disclosures qualify those numbers; each is also in the RESULTS.md limitations:

- The graph arm's tool returns Patch Precedent's own replay of these same six patches, so the comparison shows whether an agent uses that evidence, not how well the graph generalises.
- Checks recall counts every linked check, including checks expected to pass, and the graph tool lists all linked checks. The catching-checks recall row counts only the checks expected to fail: 100% (n=9) for both arms, so the checks-recall gap (37% vs 91%) comes entirely from passing checks.
- Decision recall is 87% (n=15) for the baseline and 100% (n=15) for the graph arm. Expected decisions are Patch Precedent's curated per-file decisions, which the graph tool returns directly; listing extra ADRs lowers "decisions exact" but not decision recall.
- The graph tool returned observed results in 15 of the 18 runs. In the 3 runs where it reported no replay (C1 r1, C1 r2, C3 r1), the agent had altered the patch while copying it into the tool call (a context line was rewritten as an added line), so the changed-lines key did not match, and those agents answered "unknown" for the check outcomes they gave.
- eval/prompt.md does not define the difference between "consistent" and "no_decision". Both baseline verdict misses are choices on that boundary (C2 r2 answered no_decision; C6 r1 answered consistent with no ADR), and C2 r1 gave the same answer as C6 r1 but was scored correct.

The method note in RESULTS.md says:

> The baseline arm has no tool that reports observed test results, so any "fails" or "passes" it gives is unsupported by construction. Answering "unknown" never counts as unsupported and never lowers outcome accuracy. A claim is "supported" when the agent saw an observed result for that check; whether the claim matches that result is measured separately by outcome accuracy. Medians of time to first correct citation skip runs that never cite the expected ADR; their count is shown as n.

Read the full per-case table, every run, the exact command lines and the limitations in [RESULTS.md](eval/results/20261127T040059Z/RESULTS.md); the agent transcripts are in [`eval/results/20261127T040059Z/transcripts/`](eval/results/20261127T040059Z/transcripts/).

Re-score the published run (offline, no usage):

```bash
uv run patch-precedent eval score --results eval/results/20261127T040059Z
uv run patch-precedent eval report --results eval/results/20261127T040059Z
```

Run your own evaluation (uses Claude Code usage; needs a logged-in Claude Code CLI):

```bash
uv run patch-precedent demo all
uv run patch-precedent eval run --repeats 3
uv run patch-precedent eval score
uv run patch-precedent eval report
```

`eval score` and `eval report` without `--results` pick up the newest directory under `eval/results/`.

`eval run` needs a logged-in Claude Code CLI and spends usage (the published run cost $1.11 in total, per RESULTS.md); it writes a new directory `eval/results/<UTC timestamp>/`. `demo`, `explain` and `mcp` need neither the CLI nor an API key. `eval score` and `eval report` are offline; on the committed results they rewrite `scored.jsonl`, `results.json` and `RESULTS.md` with identical bytes (`git diff --exit-code` stays clean).

## How it works

Committed store (`data/precedent.rl`, always opened read-only):

```text
(File)-[:CITES]->(Decision)-[:CHECKED_BY]->(Check)
(Commit)-[:IMPLEMENTS]->(Decision)
(Upstream)   pinned repo and revision
```

The store merges the hand-curated manifests (`evidence/installer.toml`, `evidence/release.toml`) with the scanned citation index (`evidence/scanned/*.tsv`) into one file.

Added only in a per-run copy (`runs/<timestamp>/<scenario>/replay.rl`):

```text
(Patch)-[:CHANGES]->(File)
(Run)-[:APPLIED]->(Patch)
(Patch)-[:PRODUCED]->(Observation)-[:FOR_CHECK]->(Check)
```

The join that connects a patch to the rules and checks behind the files it touches:

```cypher
MATCH (p:Patch)-[:CHANGES]->(f:File)-[:CITES]->(d:Decision)-[:CHECKED_BY]->(t:Check),
      (p)-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(t),
      (c:Commit)-[:IMPLEMENTS]->(d)
RETURN p.id AS patch, f.path AS file, d.id AS decision, d.reason AS reason,
       c.sha AS implementation, t.name AS assertion, o.tap AS observed,
       p.label AS label, o.number AS tap_number
ORDER BY patch, assertion
```

Single-file mode: the evidence store is one Relate `.rl` file committed in the repo, opened in-process with `relate.connect` (no server, no sidecar files). `explain` and the demo's evidence queries open it with `read_only=True`; each replay writes to its own copy, `runs/<timestamp>/<scenario>/replay.rl`.

All queries use bound parameters. Replays write to a copy because opening a Relate file read-write rewrites it, even for a read-only query; this keeps `data/precedent.rl` byte-unchanged and `git status` clean after a demo.

For each case the demo makes a clean checkout of the pinned upstream revision, applies the patch with `git apply` (after `git apply --check`), and runs the scenario's upstream harness (`sh scripts/tests/test_install_sh.sh` or `sh scripts/tests/test_release_advance.sh`) unmodified.

## Evidence and provenance

Curated evidence:

- `evidence/installer.toml` and `evidence/release.toml` are hand-reviewed manifests holding each decision's rule, reason and checks. Links point to permalinks at the pinned upstream SHA, with line ranges checked against that revision.

Scanned evidence:

- `evidence/scanned/citations.tsv` lists every explicit `ADR-NNNN` mention outside `docs/adr` at the pinned commit (path, ADR, first line, count): 6,837 (file, ADR) citation pairs, from 14,182 mentions, across 1,982 files and 514 ADRs. `evidence/scanned/decisions.tsv` lists all 567 ADR records with title, status and path.
- Both files are generated by `scan-citations` and never interpreted. The scan output is deterministic: a second scan wrote byte-identical files. `explain` shows scanned citations separately as "also cites (scanned from source, not reviewed)", and a verdict uses only decisions that have curated checks.

Commands:

- `uv run patch-precedent scan-citations [--out-dir DIR]` regenerates the two TSVs from the upstream cache (default `evidence/scanned/`). It prints `scanned 6837 citations across 1982 files and 514 ADRs; 567 decisions (567 with records) at 5f7a510713c3`. Of the store and evidence commands, only this one needs the upstream cache.
- `uv run patch-precedent build-store [--evidence-dir DIR] [--out PATH]` builds the store from the curated and scanned files. It reads only `evidence/` and needs no network.
- `uv run patch-precedent verify-store [--evidence-dir DIR] [--store PATH]` compares the committed store with a fresh build of the evidence. It prints `store matches manifest: 2557 nodes, 6844 relationships` and exits 0.
- To experiment with a rebuild, write it elsewhere: `uv run patch-precedent build-store --out /tmp/precedent.rl`. The default output is `data/precedent.rl` and overwrites the committed store; restore it with `git checkout data/precedent.rl`. The committed store is about 3 MB.
- Rebuilding does not reproduce identical bytes, so file hashes differ between builds. `verify-store` therefore compares sorted snapshots of all nodes and relationships, which do match.
- `fixtures/<scenario>/expectations.toml` holds acceptance criteria keyed by patch content sha256. The demo checks itself against it (a disagreement is reported as a mismatch). The file decides only whether the replay matched; it is never displayed as results.
- Patch identity is content: `id = "patch:" + sha256[:12]`. File names are display labels only, so renaming a fixture does not change its verdict.

## Exit codes

`demo <scenario>`, and `demo all` for the overall exit:

| Code | Meaning |
|---:|---|
| 0 | Every patch had a conclusive verdict and the observations matched `expectations.toml`. A patch that violates an ADR still exits 0 if that was expected. |
| 2 | Inconclusive or unusable input. Causes: unknown scenario; missing fixtures directory; baseline not green; a patch that did not apply cleanly; a harness timeout; no TAP output, or truncated or malformed TAP; an empty TAP plan (no checks ran); skipped checks (e.g. `ssh-keygen` unavailable); harness exit code and TAP failure count disagreeing; or none of a patch's linked checks appearing in the TAP output. The run is reported as inconclusive, never as pass or fail. |
| 3 | Observations disagree with `expectations.toml`, a patch's content has no entry in it, or the graph join disagrees with the TAP output it was recorded from. |
| 4 | Upstream cache missing and the upstream repo is unreachable (first run needs internet). |

`demo all` runs the scenarios in order and prints each one's results even if an earlier one failed. Its overall exit is the worst scenario exit, by precedence 4, then 2, then 3, then 0.

Why the overall exit is 0 when patches fail: the demo's exit says whether the replay matched expectations, not whether every patch passed. In the output above `always-rotate` and `release-lookup` fail their harnesses as expected, so both scenarios and the overall run exit 0. Each patch's own harness exit is in the comparison tables.

`explain`:

| Code | Meaning |
|---:|---|
| 0 | Chain printed (also when the patch has no changed files or a file has no linked decision). |
| 2 | Patch file or store not found. |

`site`:

| Code | Meaning |
|---:|---|
| 0 | `site` (build): the pages were written. `site record`: the recording was written. |
| 2 | `site`: missing recording or evidence input, `--base-url` not starting with `https://`, or `--out` refused (it is the project root or one of its parents, a file, or a non-empty directory that a previous build did not create). `site record`: `--base-url` given, or no single new run directory found. |
| 3, 4 | `site record` only: the demo's own exit (mismatch, no upstream), passed through; nothing is written. |

`build-store` returns 0 on success. `verify-store` returns 0 when the store matches the manifest and 1 when it does not or is missing.

`mcp`:

| Code | Meaning |
|---:|---|
| 0 | The server ran and its client closed the connection. |
| 2 | Store file not found. |

`fetch-relate-cli` prints the path of the verified binary and exits 0. It exits 4 when the download, the checksum verification or the file write fails, or when the platform is not macOS arm64.

`eval run`:

| Code | Meaning |
|---:|---|
| 0 | Results directory written. |
| 2 | Refused or unusable input: unknown case id, `--repeats` below 1, or a precondition the runner refuses (for example, no prior `demo all`). |
| 4 | Upstream cache missing and the upstream repo is unreachable. |

`eval score` and `eval report` return 0 on success and 2 when the results directory, or a file they need in it (`runs.jsonl`, `scored.jsonl`, `meta.json`), is missing, or when `runs.jsonl` names an unknown case.

## Run artifacts

Runs are git-ignored. `demo installer` or `demo release` writes `runs/<UTC timestamp>/<scenario>/`; `demo all` writes `runs/<UTC timestamp>/{installer,release}/` plus `runs/<UTC timestamp>/summary.json` (each scenario's summary and the overall exit). Each scenario directory contains, per case, `<label>.log` (the harness output) and `<label>.exit` (its exit code, `none` or `timeout`), plus `replay.rl` (the store copy with replay nodes) and `summary.json` (runs, join rows, warnings, mismatches, verdicts and exit code).

## Tests

```bash
uv run pytest             # unit tests, offline
uv run pytest -m upstream # runs the real upstream harness, about 2-3 minutes
```

## Pins

- Upstream: `https://github.com/relatedb/relate.git` at `5f7a510713c3feac146133e77d8c5bb72bae1b11`
- Relate CLI (optional, for Relate's own MCP server): v1.3.0, `relate-darwin-arm64`, checksum-verified
- `mcp==2.3.0` (Python SDK)
- `jinja2==3.1.6` and `rich==15.0.0` (site templates and styled terminal output)
- Implementing commits: `5ac38808547d11f55b02333624cc3e88b46566eb` (ADR-0585), `d79d8b150561f56b4940876a067d6b7e4781d2bc` (ADR-0580)
- `relate-db==1.1.0`, Python 3.12

## Limitations

- Only tested on macOS.
- Only the supplied fixtures run; there is no arbitrary patch execution. `explain` reads any patch but executes nothing.
- Decision rules, reasons and check links are curated by hand; file→ADR citations are scanned automatically from explicit `ADR-NNNN` mentions and are not reviewed. Only ADR-0585 and ADR-0580 have curated checks.
- The website is static: it shows the committed evidence and replays a recorded demo run. It does not run patches or live queries in the browser.
- The evaluation covers 6 cases on one repository with one model, so its figures are counts over few runs. The graph arm's observed results come from Patch Precedent's own replay of the same fixtures that define the ground truth.
- `fetch-relate-cli` is for macOS arm64 only.
- If the upstream harness skips any check on your machine (for example, `ssh-keygen` is unavailable), the demo reports the run as inconclusive (exit 2) instead of trusting it.
- ADR-0585 and ADR-0580 have status "Proposed" upstream.

## AI tools used

Patch Precedent was built with significant AI assistance, disclosed here as the hackathon rules require.

- **Claude Code (Anthropic)** turned the project plan into an implementation plan and ran the build. Claude Opus planned each task and reviewed every change and the final branch. Claude Sonnet subagents wrote the code, tests and documentation.
- **The website, terminal UI and recording** were also built with Claude Code, with Claude Opus orchestrating and reviewing and Claude Sonnet subagents implementing. The title lockup drawing in `src/patch_precedent/site/static/c-art.js` was adapted from a draft generated with Google Gemini.
- **Planning documents** (specs and implementation plans written with Claude Code) were removed from `main`; they are in the git history at commit `1cc7213`.
- **The project owner** chose the idea, approved the plan, and made the integration, licensing and publication decisions.
- **Not AI-generated:** Relate, the upstream installer, its test harness and ADR-0585, ADR-0580 and the release script come from relatedb/relate at the pinned commit (see [NOTICE](NOTICE)).
- **No model at run time:** the demo, `explain` and `mcp` call no AI service and need no API key. The one exception is `eval run`, which runs Claude Sonnet through Claude Code as the agent under test.
- **Verified, not described:** every result, test count and output excerpt in this README comes from real local runs of the code in this repository.

## License and attribution

Patch Precedent is released under the [MIT License](LICENSE). It references and excerpts relatedb/relate, which is Apache-2.0; [NOTICE](NOTICE) lists exactly what is used. The patches in `fixtures/installer/` and `fixtures/release/` are authored demonstration inputs, not upstream changes.
