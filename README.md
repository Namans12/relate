# Patch Precedent

Two patches touch the same installer file, `distribution/install.sh`. The Relate graph links that file to ADR-0585 ("the installer downloads release assets over the direct route"), the commit that implemented it, and the two regression checks that guard it. Replaying both patches through the unmodified upstream test harness shows that only the release-lookup patch, which probes the GitHub release API to improve an error message, breaks the ADR's no-GitHub-API rule. The wording patch passes. Evidence (graph) and observation (test runs) stay separate: the committed graph is usable before any patch runs, and the replay adds observations on a copy.

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

Replay the baseline and both fixture patches against the upstream harness and explain the results:

```bash
uv run patch-precedent demo installer
```

Each later `demo` run takes about 25 seconds on the tested Mac.

Show the source chain behind a patch without fetching upstream or executing anything:

```bash
uv run patch-precedent explain fixtures/installer/release-lookup.patch
```

## What you'll see

An excerpt of a real `demo installer` run. `…` marks omitted sections (the header, the per-patch diffs and the artifact paths).

```text
…
== comparison ==
Input           Changed                  Exit  Passed/failed  #7 static  #193 runtime
--------------  -----------------------  ----  -------------  ---------  ------------
baseline        — (unpatched)            0     194 / 0        ok 7       ok 193
release-lookup  distribution/install.sh  1     192 / 2        not ok 7   not ok 193
wording         distribution/install.sh  0     194 / 0        ok 7       ok 193

== graph evidence ==
distribution/install.sh
  cites ADR-0585 · The installer downloads release assets over the direct route [Proposed]
    rule      install.sh consults no GitHub API endpoint
    why       Anonymous GitHub API requests are limited to 60 per hour per IP address,
              and users behind shared egress (VPNs, corporate NAT, Cloudflare WARP)
              exhausted that quota, so the one-line installer broke. Release assets are
              now fetched over the direct download route instead. Only ADR-0068's
              installer authentication clause is superseded; version selection still
              uses releases.json.
    citation  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/distribution/install.sh#L120-L128
    decision  https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/docs/adr/0585-installer-downloads-via-direct-route.md#L8-L38
    scope     https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/docs/adr/0585-installer-downloads-via-direct-route.md#L89-L97
    commit    5ac38808 fix(installer): download release assets over the direct route, no GitHub API (LABS-1482, ADR-0585) (https://github.com/relatedb/relate/commit/5ac38808547d11f55b02333624cc3e88b46566eb)
    checks
      #7    static   drift guard: install.sh consults no GitHub API endpoint (ADR-0585)
            release-lookup → not ok 7
            wording → ok 7
            https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/tests/test_install_sh.sh#L129-L135
      #193  runtime  no case made a GitHub API request (ADR-0585)
            release-lookup → not ok 193
            wording → ok 193
            https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/scripts/tests/test_install_sh.sh#L610-L615

== graph join (replay.rl) ==
MATCH (p:Patch)-[:CHANGES]->(f:File)-[:CITES]->(d:Decision)-[:CHECKED_BY]->(t:Check),
      (p)-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(t),
      (c:Commit)-[:IMPLEMENTS]->(d)
RETURN p.id AS patch, f.path AS file, d.id AS decision, d.reason AS reason,
       c.sha AS implementation, t.name AS assertion, o.tap AS observed,
       p.label AS label, o.number AS tap_number
ORDER BY patch, assertion

patch               label           file                     decision  implementation  assertion                                                           observed
------------------  --------------  -----------------------  --------  --------------  ------------------------------------------------------------------  ----------
patch:635b00b21f4b  release-lookup  distribution/install.sh  ADR-0585  5ac38808        drift guard: install.sh consults no GitHub API endpoint (ADR-0585)  not ok 7
patch:635b00b21f4b  release-lookup  distribution/install.sh  ADR-0585  5ac38808        no case made a GitHub API request (ADR-0585)                        not ok 193
patch:96278d65b413  wording         distribution/install.sh  ADR-0585  5ac38808        drift guard: install.sh consults no GitHub API endpoint (ADR-0585)  ok 7
patch:96278d65b413  wording         distribution/install.sh  ADR-0585  5ac38808        no case made a GitHub API request (ADR-0585)                        ok 193

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

Single-file mode: the evidence store is one Relate `.rl` file committed in the repo, opened in-process with `relate.connect` (no server, no sidecar files). `explain` and the demo's evidence queries open it with `read_only=True`; each replay writes to its own copy, `runs/<timestamp>/replay.rl`.

All queries use bound parameters. Replays write to a copy because opening a Relate file read-write rewrites it, even for a read-only query; this keeps `data/precedent.rl` byte-unchanged and `git status` clean after a demo.

For each case the demo makes a clean checkout of the pinned upstream revision, applies the patch with `git apply` (after `git apply --check`), and runs the upstream harness, `sh scripts/tests/test_install_sh.sh`, unmodified.

## Evidence and provenance

- `evidence/installer.toml` is a hand-curated manifest. Its links point to permalinks at the pinned upstream SHA, with line ranges checked against that revision.
- Check the committed store against a fresh build of the manifest with `uv run patch-precedent verify-store` (prints `store matches manifest: 6 nodes, 4 relationships` and exits 0). To experiment with a rebuild, write it elsewhere: `uv run patch-precedent build-store --out /tmp/precedent.rl`. The default output is `data/precedent.rl` and overwrites the committed store; restore it with `git checkout data/precedent.rl`.
- Rebuilding does not reproduce identical bytes, so file hashes differ between builds. `verify-store` therefore compares sorted snapshots of all nodes and relationships, which do match.
- `fixtures/installer/expectations.toml` holds acceptance criteria keyed by patch content sha256. The demo checks itself against it (a disagreement is reported as a mismatch). The file decides only whether the replay matched; it is never displayed as results.
- Patch identity is content: `id = "patch:" + sha256[:12]`. File names are display labels only, so renaming a fixture does not change its verdict.

## Exit codes

`demo`:

| Code | Meaning |
|---:|---|
| 0 | Every patch had a conclusive verdict and the observations matched `expectations.toml`. A patch that violates an ADR still exits 0 if that was expected. |
| 2 | Inconclusive or unusable input. Causes: unknown scenario; missing fixtures directory; baseline not green; a patch that did not apply cleanly; a harness timeout; no TAP output, or truncated or malformed TAP; an empty TAP plan (no checks ran); skipped checks (e.g. `ssh-keygen` unavailable); harness exit code and TAP failure count disagreeing; or none of a patch's linked checks appearing in the TAP output. The run is reported as inconclusive, never as pass or fail. |
| 3 | Observations disagree with `expectations.toml`, a patch's content has no entry in it, or the graph join disagrees with the TAP output it was recorded from. |
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
- If the upstream harness skips any check on your machine (for example, `ssh-keygen` is unavailable), the demo reports the run as inconclusive (exit 2) instead of trusting it.
- ADR-0585 has status "Proposed" upstream.

## AI tools used

Patch Precedent was built with significant AI assistance, disclosed here as the hackathon rules require.

- **Claude Code (Anthropic)** turned the project plan into an implementation plan and ran the build. Claude Opus planned each task and reviewed every change and the final branch. Claude Sonnet subagents wrote the code, tests and documentation.
- **The project owner** chose the idea, approved the plan, and made the integration, licensing and publication decisions.
- **Not AI-generated:** Relate, the upstream installer, its test harness and ADR-0585 come from relatedb/relate at the pinned commit (see [NOTICE](NOTICE)).
- **No model at run time:** the demo and `explain` call no AI service and need no API key.
- **Verified, not described:** every result, test count and output excerpt in this README comes from real local runs of the code in this repository.

## License and attribution

Patch Precedent is released under the [MIT License](LICENSE). It references and excerpts relatedb/relate, which is Apache-2.0; [NOTICE](NOTICE) lists exactly what is used. Both patches in `fixtures/installer/` are authored demonstration inputs, not upstream changes.
