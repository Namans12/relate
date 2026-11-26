You are reviewing a proposed patch to the repository in your working directory (relatedb/relate at a pinned commit). Do not modify any files.

Decide whether the patch violates an architectural decision record (ADR) of this repository.

Patch:
```diff
{patch}
```

Use any tools available to you. When done, reply with ONLY a JSON object on the last line:
{"verdict": "violates" | "consistent" | "no_decision", "decisions": ["ADR-NNNN", ...], "checks": ["<exact test assertion description that would catch it>", ...], "check_outcomes": {"<exact test assertion description>": "fails" | "passes" | "unknown", ...}}
"decisions" lists the ADRs that govern the changed code; "checks" lists existing regression tests (by their exact description) that guard the relevant rule.
Say "unknown" for any check whose result you did not observe.
