"""Render RESULTS.md. Byte-deterministic: a pure function of (summary, scored runs, meta)."""
import shlex
from collections import Counter

from .score import _arm_key

NA = "n/a"
PLACEHOLDER = "<prompt from eval/prompt.md>"


def _kn(k: int, n: int) -> str:
    return f"{k}/{n}"


def _pct(x: float | None) -> str:
    return NA if x is None else f"{x * 100:.0f}%"


def _num(x: float | None, nd: int = 1) -> str:
    return NA if x is None else f"{x:.{nd}f}"


def _usd(x: float | None) -> str:
    return NA if x is None else f"${x:.2f}"


def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return lines


def _headline_rows(m: dict) -> list[str]:
    return [
        _kn(m["verdict_k"], m["n"]),
        _kn(m["decisions_exact_k"], m["n"]),
        f"{_pct(m['checks_recall_mean'])} (n={m['checks_recall_n']})",
        f"{m['unsupported_total']} (n={m['unsupported_n']})",
        f"{_num(m['unsupported_mean'], 2)} (n={m['unsupported_n']})",
        f"{_pct(m['outcome_accuracy'])} ({_kn(m['outcome_correct'], m['outcome_marked'])} marked checks)",
        f"{_num(m['citation_median_s'])} (n={m['citation_n']})",
        f"{_num(m['turns_mean'])} (n={m['turns_n']})",
        f"{_usd(m['cost_total'])} (n={m['cost_n']})",
    ]


HEADLINE_LABELS = [
    "Verdict correct (k/n runs)",
    "Decisions exact (k/n runs)",
    "Mean checks recall (cases with linked checks)",
    "Unsupported claims, total",
    "Unsupported claims, mean per run",
    "Outcome accuracy (pooled over marked checks)",
    "Median time to first correct citation, seconds",
    "Mean turns",
    "Total cost, USD",
]


def _commands(scored: list[dict]) -> list[str]:
    out = []
    for arm in ("baseline", "graph"):
        picks = sorted((r for r in scored if r["case"] == "C1" and r["arm"] == arm and r.get("argv")),
                       key=lambda r: r["repeat"])
        out.append(f"{arm} (C1):")
        out.append("")
        if not picks:
            out += ["(no C1 run recorded for this arm)", ""]
            continue
        argv = list(picks[0]["argv"])
        if "-p" in argv and argv.index("-p") + 1 < len(argv):
            argv[argv.index("-p") + 1] = PLACEHOLDER
        cmd = shlex.join(argv).replace(shlex.quote(PLACEHOLDER), PLACEHOLDER)
        out += ["```sh", cmd, "```", ""]
    return out


def render_results_md(summary: dict, scored_runs: list[dict], meta: dict) -> str:
    runs = sorted(scored_runs, key=lambda r: (r["case"], _arm_key(r["arm"]), r["repeat"]))
    arms = list(summary["arms"])
    models = sorted({r["model"] for r in runs if r.get("model")})
    spend = sum(r["cost_usd"] for r in runs if r.get("cost_usd") is not None)
    date = str(meta.get("date", ""))[:10]
    meta_arms = meta.get("arms") or arms

    L = ["# Patch Precedent: agent evaluation results", ""]
    L.append(
        f"Model: {', '.join(models) or NA}. Claude Code CLI: {meta.get('claude_version', NA)}. "
        f"Run date: {date}. Upstream pin: {meta.get('upstream_sha', NA)}. "
        f"Repeats per case and arm: {meta.get('repeats', NA)}. Arms: {', '.join(meta_arms)}. "
        "Both arms receive the identical prompt (eval/prompt.md with the patch inserted) and "
        "identical flags, with file tools only (Read, Grep, Glob) in a clean worktree of the pin. "
        "The only differences are the MCP config file and the MCP tool name in the allowed-tools "
        "list: the `graph` arm also gets `mcp__precedent__precedent_for_patch`, which returns the "
        "ADRs, tests and each test's observed replay result for the patch; the `baseline` arm "
        "has no MCP server. "
        f"Total spend over all {len(runs)} recorded runs, including excluded ones: {_usd(spend)}.")
    L.append("")

    L += ["## Headline", ""]
    cols = [_headline_rows(summary["arms"][a]) for a in arms]
    L += _table(["Metric", *[f"{a} (n={summary['arms'][a]['n']})" for a in arms]],
                [[lab, *[c[i] for c in cols]] for i, lab in enumerate(HEADLINE_LABELS)])
    L.append("")

    L += ["## Per case", ""]
    rows = []
    for case, by_arm in summary["cases"].items():
        for arm in arms:
            m = by_arm.get(arm)
            if m is None:
                continue
            rows.append([case, arm, m["n"], _kn(m["verdict_k"], m["n"]),
                         _kn(m["decisions_exact_k"], m["n"]), _pct(m["checks_recall_mean"]),
                         m["unsupported_total"],
                         f"{_pct(m['outcome_accuracy'])} ({_kn(m['outcome_correct'], m['outcome_marked'])})",
                         f"{_num(m['citation_median_s'])} (n={m['citation_n']})",
                         _num(m["turns_mean"]), _usd(m["cost_total"])])
    L += _table(["Case", "Arm", "n", "Verdict", "Decisions exact", "Checks recall",
                 "Unsupported", "Outcome acc.", "Median citation s", "Mean turns", "Cost"], rows)
    L.append("")

    L += ["## Every run", ""]
    rows = []
    for r in runs:
        given = "(parse error)" if r.get("parse_error") else (r.get("verdict") or "(none)")
        ms = r.get("time_to_first_correct_citation_ms")
        rows.append([r["case"], r["arm"], r["repeat"], given,
                     "yes" if r.get("verdict_correct") else "no",
                     NA if r.get("unsupported_claims") is None else r["unsupported_claims"],
                     NA if ms is None else f"{ms / 1000:.1f}",
                     NA if r.get("turns") is None else r["turns"],
                     NA if r.get("cost_usd") is None else f"${r['cost_usd']:.4f}",
                     r.get("error") or ""])
    L += _table(["Case", "Arm", "Repeat", "Verdict given", "Correct", "Unsupported",
                 "Citation s", "Turns", "Cost", "Error"], rows)
    L.append("")

    L += ["## Excluded runs", ""]
    if summary["excluded"]:
        L += _table(["Case", "Arm", "Repeat", "Error", "Cost"],
                    [[x["case"], x["arm"], x["repeat"], x["error"], _usd(x.get("cost_usd"))]
                     for x in summary["excluded"]])
        L += ["", "Excluded runs are left out of every metric above (including cost totals) "
              "and appear in the spend sentence at the top."]
    else:
        L.append("none")
    L.append("")

    L += ["## Method", "",
          "Scoring is deterministic and offline: it reads each run's final JSON and transcript "
          "and compares them with the ground truth in `eval/cases.toml`.", "",
          "- Final answer: the last line of the run's result text that parses as a JSON object. "
          "If the run has no result event, the last assistant text block is used. A run with no "
          "such JSON is a parse error: it counts as an incorrect verdict and as not exact, and its "
          "other metrics are blank.",
          "- Verdict correct: the final `verdict` equals the case's verdict.",
          "- Decisions exact: the set of listed ADR ids equals the case's set. Precision and "
          "recall are stored per run in scored.jsonl.",
          "- Check names are compared after collapsing whitespace runs to single spaces and "
          "stripping the ends.",
          "- Checks recall: the share of the case's linked checks that the agent listed. Cases "
          "with no linked checks (C6) are left out of this mean.",
          "- Outcome accuracy: among the case's linked checks that the agent marked `fails` or "
          "`passes` in `check_outcomes`, the share equal to ground truth. Pooled over all marked "
          "checks; blank when none were marked. A missing `check_outcomes` means none marked.",
          "- Unsupported claims: the number of `check_outcomes` entries marked `fails` or "
          "`passes` with no support. Support means a tool result in the transcript that parses "
          "as the `precedent_for_patch` JSON and contains a check of the same normalised name "
          "with `observed` equal to `ok` or `not ok`. Text that merely mentions a check is not "
          "support, and `not observed` is not support. Entries marked `unknown` are not counted.",
          "- Time to first correct citation: seconds from run start to the first assistant "
          "message (text or tool-call input) that contains the case's expected ADR id. Blank for "
          "C6 and when the ADR is never cited.",
          "- Turns and cost come from the run record, falling back to the result event.",
          "- Runs whose record has an error (non-zero exit, timeout, tool-set mismatch, access "
          "outside the worktree, dirty worktree) are excluded from all metrics and listed above.",
          "- n is shown with each figure; means skip runs where the value is blank.",
          ""]

    L += ["## Commands", "",
          "Exact command lines from runs.jsonl for one run of each arm on C1; "
          f"the prompt is `{PLACEHOLDER}` with the patch inserted.", ""]
    L += _commands(runs)

    L += ["## Limitations", "",
          "- Six cases, one repository, one model, and a small number of repeats: the figures "
          "are counts over few runs, not estimates of general behaviour.",
          "- The graph arm's evidence is Patch Precedent's own replay of the same fixtures that "
          "define the ground truth, so what that arm is shown matches what it is scored against.",
          "- The baseline arm runs in restricted mode and cannot run the test suite, so any "
          "outcome it reports for a check is an inference from reading files.",
          "- Elapsed times include model and tool latency and vary between runs.",
          ""]
    return "\n".join(L)
