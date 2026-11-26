# Patch Precedent

Two patches touch the same installer file, `distribution/install.sh`. The Relate graph links that file to ADR-0585 ("the installer downloads release assets over the direct route"), the commit that implemented it, and the two regression checks that guard it. Replaying both patches through the unmodified upstream test harness shows that only the release-lookup patch, which probes the GitHub release API to improve an error message, breaks the ADR's no-GitHub-API rule. The wording patch passes. Evidence (graph) and observation (test runs) stay separate: the committed graph is usable before any patch runs, and the replay adds observations on a copy.

## Run it

Prerequisites:

- macOS (the only platform this has been tested on)
- git
- [uv](https://docs.astral.sh/uv/)
- Internet access on the first run only. The upstream repo is cached as a bare clone at `~/.cache/patch-precedent/relate.git` (override the directory with `PATCH_PRECEDENT_CACHE`). Later runs need no network.

Replay the baseline and both fixture patches against the upstream harness and explain the results:

```bash
uv run patch-precedent demo installer
```

Show the source chain behind a patch without fetching upstream or executing anything:

```bash
uv run patch-precedent explain fixtures/installer/release-lookup.patch
```

## What you'll see

An excerpt of a real `demo installer` run. `…` marks omitted sections (the per-patch diffs, the full evidence chains and the artifact paths).

```text
…
== comparison ==
Input           Changed                  Exit  Passed/failed  #7 static  #193 runtime
--------------  -----------------------  ----  -------------  ---------  ------------
baseline        upstream                 0     194 / 0        ok 7       ok 193
release-lookup  distribution/install.sh  1     192 / 2        not ok 7   not ok 193
wording         distribution/install.sh  0     194 / 0        ok 7       ok 193

…

== graph join (replay.rl) ==
MATCH (p:Patch)-[:CHANGES]->(f:File)-[:CITES]->(d:Decision)-[:CHECKED_BY]->(t:Check),
      (p)-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(t),
      (c:Commit)-[:IMPLEMENTS]->(d)
RETURN p.id AS patch, f.path AS file, d.id AS decision, d.reason AS reason,
       c.sha AS implementation, t.name AS assertion, o.tap AS observed,
       p.label AS label, o.number AS tap_number
ORDER BY patch, assertion

patch           file                     decision  implementation  assertion                                                           observed
--------------  -----------------------  --------  --------------  ------------------------------------------------------------------  --------
release-lookup  distribution/install.sh  ADR-0585  5ac38808        drift guard: install.sh consults no GitHub API endpoint (ADR-0585)  not ok
release-lookup  distribution/install.sh  ADR-0585  5ac38808        no case made a GitHub API request (ADR-0585)                        not ok
wording         distribution/install.sh  ADR-0585  5ac38808        drift guard: install.sh consults no GitHub API endpoint (ADR-0585)  ok
wording         distribution/install.sh  ADR-0585  5ac38808        no case made a GitHub API request (ADR-0585)                        ok

== verdicts ==
release-lookup: violates ADR-0585 — install.sh consults no GitHub API endpoint
    #7 static: the script spells a GitHub API endpoint
    #193 runtime: a GitHub API request was attempted and recorded in the harness's stubbed curl log
    harness exit 1, 192 passed / 2 failed
wording: consistent with ADR-0585 as far as checks #7, #193 cover

```

The demo shows outcomes only from observed runs and live graph queries. It prints each verdict from the harness's TAP output joined to the graph; nothing is hard-coded by filename.

## How it works

Committed store (`data/precedent.rl`, always opened read-only):

```text
(File)-[:CITES]->(Decision)-[:CHECKED_BY]->(Check)
(Commit)-[:IMPLEMENTS]->(Decision)
(Upstream)   pinned repo and revision
```

Added only in a per-run copy (`runs/<timestamp>/replay.rl`):

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

All queries use bound parameters. Replays write to a copy because opening a Relate file read-write rewrites it, even for a read-only query; this keeps `data/precedent.rl` byte-unchanged and `git status` clean after a demo.

For each case the demo makes a clean checkout of the pinned upstream revision, applies the patch with `git apply` (after `git apply --check`), and runs the upstream harness, `sh scripts/tests/test_install_sh.sh`, unmodified.

## Evidence and provenance

- `evidence/installer.toml` is a hand-curated manifest. Its links point to permalinks at the pinned upstream SHA, with line ranges checked against that revision.
- Rebuild the store with `uv run patch-precedent build-store`; check the committed store against a fresh build of the manifest with `uv run patch-precedent verify-store` (prints `store matches manifest: 6 nodes, 4 relationships` and exits 0).
- Rebuilding does not reproduce identical bytes, so file hashes differ between builds. `verify-store` therefore compares sorted snapshots of all nodes and relationships, which do match.
- `fixtures/installer/expectations.toml` holds acceptance criteria keyed by patch content sha256. The demo checks itself against it (a disagreement is reported as a mismatch) but never displays it as results.
- Patch identity is content: `id = "patch:" + sha256[:12]`. File names are display labels only, so renaming a fixture does not change its verdict.

## Exit codes

`demo`:

| Code | Meaning |
|---:|---|
| 0 | Every patch had a conclusive verdict and the observations matched `expectations.toml`. A patch that violates an ADR still exits 0 if that was expected. |
| 2 | Inconclusive: unknown scenario, missing fixtures directory, baseline not green, a patch that did not apply, a harness timeout, or truncated or missing TAP. |
| 3 | Observations disagree with `expectations.toml`. |
| 4 | Upstream cache missing and the upstream repo is unreachable (first run needs internet). |

`explain`:

| Code | Meaning |
|---:|---|
| 0 | Chain printed (also when the patch has no changed files or a file has no linked decision). |
| 2 | Patch file or store not found. |

`build-store` returns 0 on success. `verify-store` returns 0 when the store matches the manifest and 1 when it does not or is missing.

## Run artifacts

Each `demo` run writes `runs/<UTC timestamp>/` (git-ignored) containing, per case, `<label>.log` (the harness output) and `<label>.exit` (its exit code, `none` or `timeout`), plus `replay.rl` (the store copy with replay nodes) and `summary.json` (runs, join rows, warnings, mismatches, verdicts and exit code).

## Tests

```bash
uv run pytest             # unit tests, offline
uv run pytest -m upstream # runs the real upstream harness, about 2-3 minutes
```

## Pins

- Upstream: `https://github.com/relatedb/relate.git` at `5f7a510713c3feac146133e77d8c5bb72bae1b11`
- Implementing commit: `5ac38808547d11f55b02333624cc3e88b46566eb`
- `relate-db==1.1.0`, Python 3.12

## Limitations

- Only tested on macOS.
- Only the supplied fixtures run; there is no arbitrary patch execution.
- Links between files, decisions and checks are curated by hand, not extracted.
- No MCP server or browser explorer yet.
- ADR-0585 has status "Proposed" upstream.

## AI tools used

This project was built with Claude Code: Claude Opus planned the work and reviewed every task, and Claude Sonnet subagents wrote the implementation and tests. All verification runs, test results and demo output in this README come from real local runs.

> Owner: confirm or edit this disclosure before submission.

## License and attribution

See [NOTICE](NOTICE). Relate is Apache-2.0; both patches in `fixtures/installer/` are authored demonstration inputs, not upstream changes.
