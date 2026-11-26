# Patch Precedent

Two scenarios, each replaying authored patches against an unmodified upstream test harness and explaining the results through a Relate graph.

**installer.** Two patches touch the same installer file, `distribution/install.sh`. The Relate graph links that file to ADR-0585 ("the installer downloads release assets over the direct route"), the commit that implemented it, and the two regression checks that guard it. Replaying both patches through the unmodified upstream test harness shows that only the release-lookup patch, which probes the GitHub release API to improve an error message, breaks the ADR's no-GitHub-API rule. The wording patch passes.

**release.** ADR-0580 says a post-release version advance must never rotate `CHANGELOG.md`. A patch to `scripts/release-bump.sh` that always rotates looks harmless because rotation is idempotent, but it breaks that rule and fails check #2 of the release harness. A rewording patch passes, and a docs-only patch to `CONTRIBUTING.md`, which cites no decision, is the control.

Evidence (graph) and observation (test runs) stay separate: the committed graph is usable before any patch runs, and the replay adds observations on a copy.

## Run it

Prerequisites:

- macOS (the only platform this has been tested on)
- git
- [uv](https://docs.astral.sh/uv/)
- Internet access on the first run only. The first run needs it for uv to fetch Python 3.12 and `relate-db==1.1.0`, and for the demo to fetch the upstream source (about 15 MB), cached as a bare clone at `~/.cache/patch-precedent/relate.git` (override the directory with `PATCH_PRECEDENT_CACHE`). Later runs need no network.

Get the code:

```bash
git clone https://github.com/Namans12/relate.git && cd relate
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

Each later `demo` run takes about 25 seconds on the tested Mac.

Show the source chain behind a patch without fetching upstream or executing anything:

```bash
uv run patch-precedent explain fixtures/installer/release-lookup.patch
```

`explain` works on any diff against Relate at the pinned commit, not only the fixtures. For a file that cites no decision, such as the release scenario's control, the last line of its output is:

```bash
uv run patch-precedent explain fixtures/release/docs-only.patch
```

```text
CONTRIBUTING.md: no linked decision
```

## Scenarios

| Scenario | Decision | Harness | Patches | Observed outcome |
|---|---|---|---|---|
| `installer` | ADR-0585, the installer downloads release assets over the direct route | `sh scripts/tests/test_install_sh.sh` (194 checks) | `release-lookup`, `wording` | `release-lookup` violates (exit 1, 192 / 2, fails #7 and #193); `wording` consistent (exit 0, 194 / 0) |
| `release` | ADR-0580, post-release workspace versioning: an advance never rotates `CHANGELOG.md` | `sh scripts/tests/test_release_advance.sh` (6 checks) | `always-rotate`, `wording`, `docs-only` | `always-rotate` violates (exit 1, 5 / 1, fails #2); `wording` consistent (exit 0, 6 / 0); `docs-only` has no linked decision (exit 0, 6 / 0) |

The release scenario's rotation patch drops the `--skip-changelog` guard in `scripts/release-bump.sh` on the argument that rotation is idempotent. Check #2 shows that an advance then rewrites `CHANGELOG.md`.

## What you'll see

An excerpt of a real `demo all` run. `…` marks omitted sections (per-scenario headers, the baselines, the per-patch diffs, the graph join tables, the artifact paths and the installer's comparison and graph evidence).

```text
== overall ==
scenario   runs  matched  exit
installer  3     3/3      0
release    4     4/4      0
overall exit 0

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

== verdicts ==
release-lookup: violates ADR-0585 — install.sh consults no GitHub API endpoint
    #7 static: the script spells a GitHub API endpoint
    #193 runtime: a GitHub API request was attempted and recorded in the harness's stubbed curl log
    harness exit 1, 192 passed / 2 failed
wording: consistent with ADR-0585 as far as checks #7, #193 cover

replay check: 3/3 runs match fixtures/installer/expectations.toml (by content sha256)
  release-lookup — expected regression reproduced; demo replay succeeded

…
```

The demo shows outcomes only from observed runs and live graph queries. It prints each verdict from the harness's TAP output joined to the graph; nothing is hard-coded by filename.

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

- `evidence/scanned/citations.tsv` lists every explicit `ADR-NNNN` mention outside `docs/adr` at the pinned commit (path, ADR, first line, count): 6,837 citations across 1,982 files and 514 ADRs. `evidence/scanned/decisions.tsv` lists all 567 ADR records with title, status and path.
- Both files are generated by `scan-citations` and never interpreted. The scan output is deterministic: a second scan wrote byte-identical files. `explain` shows scanned citations separately as "also cites (scanned from source, not reviewed)", and a verdict uses only decisions that have curated checks.

Commands:

- `uv run patch-precedent scan-citations [--out-dir DIR]` regenerates the two TSVs from the upstream cache (default `evidence/scanned/`). It prints `scanned 6837 citations across 1982 files and 514 ADRs; 567 decisions (567 with records) at 5f7a510713c3`. Of the store and evidence commands, only this one needs the upstream cache.
- `uv run patch-precedent build-store [--evidence-dir DIR] [--out PATH]` builds the store from the curated and scanned files. It reads only `evidence/` and needs no network.
- `uv run patch-precedent verify-store [--evidence-dir DIR] [--store PATH]` compares the committed store with a fresh build of the evidence. It prints `store matches manifest: 2556 nodes, 6843 relationships` and exits 0.
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

`build-store` returns 0 on success. `verify-store` returns 0 when the store matches the manifest and 1 when it does not or is missing.

## Run artifacts

Runs are git-ignored. `demo installer` or `demo release` writes `runs/<UTC timestamp>/<scenario>/`; `demo all` writes `runs/<UTC timestamp>/{installer,release}/` plus `runs/<UTC timestamp>/summary.json` (each scenario's summary and the overall exit). Each scenario directory contains, per case, `<label>.log` (the harness output) and `<label>.exit` (its exit code, `none` or `timeout`), plus `replay.rl` (the store copy with replay nodes) and `summary.json` (runs, join rows, warnings, mismatches, verdicts and exit code).

## Tests

```bash
uv run pytest             # unit tests, offline
uv run pytest -m upstream # runs the real upstream harness, about 2-3 minutes
```

## Pins

- Upstream: `https://github.com/relatedb/relate.git` at `5f7a510713c3feac146133e77d8c5bb72bae1b11`
- Implementing commits: `5ac38808547d11f55b02333624cc3e88b46566eb` (ADR-0585), `d79d8b150561f56b4940876a067d6b7e4781d2bc` (ADR-0580)
- `relate-db==1.1.0`, Python 3.12

## Limitations

- Only tested on macOS.
- Only the supplied fixtures run; there is no arbitrary patch execution. `explain` reads any patch but executes nothing.
- Links between files, decisions and checks are curated by hand, not extracted. Only ADR-0585 and ADR-0580 have curated checks; the scanned citations are an index, not a review.
- No MCP server or browser explorer yet.
- If the upstream harness skips any check on your machine (for example, `ssh-keygen` is unavailable), the demo reports the run as inconclusive (exit 2) instead of trusting it.
- ADR-0585 and ADR-0580 have status "Proposed" upstream.

## AI tools used

Patch Precedent was built with significant AI assistance, disclosed here as the hackathon rules require.

- **Claude Code (Anthropic)** turned the project plan into an implementation plan and ran the build. Claude Opus planned each task and reviewed every change and the final branch. Claude Sonnet subagents wrote the code, tests and documentation.
- **The project owner** chose the idea, approved the plan, and made the integration, licensing and publication decisions.
- **Not AI-generated:** Relate, the upstream installer, its test harness and ADR-0585, ADR-0580 and the release script come from relatedb/relate at the pinned commit (see [NOTICE](NOTICE)).
- **No model at run time:** the demo and `explain` call no AI service and need no API key.
- **Verified, not described:** every result, test count and output excerpt in this README comes from real local runs of the code in this repository.

## License and attribution

Patch Precedent is released under the [MIT License](LICENSE). It references and excerpts relatedb/relate, which is Apache-2.0; [NOTICE](NOTICE) lists exactly what is used. The patches in `fixtures/installer/` and `fixtures/release/` are authored demonstration inputs, not upstream changes.
