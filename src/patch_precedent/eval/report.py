"""Render RESULTS.md. Byte-deterministic: a pure function of (summary, scored runs, meta)."""
import math
import os
import re
import shlex

from .. import pins
from .runner import GRAPH_TOOL
from .score import _arm_key, _metrics, error_class

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


def scrub(text: str, results_dirs: tuple[str, ...] = ()) -> str:
    """Remove absolute local paths: worktree, results dir(s), project root, then home."""
    text = re.sub(r"/[^\s'\"]*?patch-precedent-agent-[^/\s'\"]+/relate", "<worktree>", text)
    pairs = [(str(d).rstrip("/"), "<results>") for d in results_dirs if str(d).rstrip("/")]
    pairs.append((str(pins.project_root()).rstrip("/"), "<project>"))
    pairs.append((os.path.expanduser("~").rstrip("/"), "~"))
    for path, label in sorted(pairs, key=lambda p: -len(p[0])):
        if path:
            text = text.replace(path, label)
    return text


def _pick_pair(scored: list[dict]) -> tuple[str, dict | None, dict | None]:
    """The case (C1 if it has argv for either arm, else the first with argv) and its two runs."""
    withargv = [r for r in scored if r.get("argv")]
    cases = sorted({r["case"] for r in withargv})
    if not cases:
        return "C1", None, None
    case = "C1" if "C1" in cases else cases[0]

    def first(arm):
        c = sorted((r for r in withargv if r["case"] == case and r["arm"] == arm),
                   key=lambda r: r["repeat"])
        return c[0] if c else None
    return case, first("baseline"), first("graph")


def _fairness(case: str, base: dict | None, graph: dict | None) -> str:
    if not (base and graph):
        return (f"WARNING: the arm difference could not be computed from the recorded commands "
                f"(need a baseline and a graph run of {case}).")
    a, b = list(base["argv"]), list(graph["argv"])
    diff, ok = [], True
    if b.count(GRAPH_TOOL) == 1 and a.count(GRAPH_TOOL) == 0:
        b.remove(GRAPH_TOOL)
        diff.append(f"the MCP tool `{GRAPH_TOOL}` in `--allowedTools` (graph only)")
    else:
        ok = False
    if len(a) != len(b):
        ok = False
    else:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                if i > 0 and a[i - 1] == "--mcp-config":
                    diff.insert(0, f"the value of `--mcp-config` (`{x}` vs `{y}`)")
                else:
                    ok = False
                    diff.append(f"unexpected difference at argument {i}: `{x}` vs `{y}`")
    text = (f"Compared on {case}, the baseline and graph commands differ only in: "
            + "; ".join(diff) + ".") if diff else f"Compared on {case}, the commands are identical."
    if not ok:
        text += (" WARNING: the commands differ in more than the `--mcp-config` value and the "
                 "MCP tool in `--allowedTools`.")
    return text


def _headline_rows(m: dict) -> list[str]:
    return [
        _kn(m["verdict_k"], m["n"]),
        _kn(m["decisions_exact_k"], m["n"]),
        f"{_pct(m['checks_recall_mean'])} (n={m['checks_recall_n']})",
        _kn(m["outcome_marked"], m["outcome_linked"]),
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
    "Outcomes marked (of linked checks)",
    "Unsupported claims, total",
    "Unsupported claims, mean per run",
    "Outcome accuracy (pooled over marked checks)",
    "Median time to first correct citation, seconds",
    "Mean turns",
    "Total cost, USD",
]


def _commands(case: str, base: dict | None, graph: dict | None) -> list[str]:
    out = []
    for arm, r in (("baseline", base), ("graph", graph)):
        out += [f"{arm} ({case}):", ""]
        if r is None:
            out += ["(no run with a recorded command for this arm)", ""]
            continue
        argv = list(r["argv"])
        if "-p" in argv and argv.index("-p") + 1 < len(argv):
            argv[argv.index("-p") + 1] = PLACEHOLDER
        cmd = shlex.join(argv).replace(shlex.quote(PLACEHOLDER), PLACEHOLDER)
        out += ["```sh", cmd, "```", ""]
    return out


def render_results_md(summary: dict, scored_runs: list[dict], meta: dict,
                      results_dir: str | None = None) -> str:
    runs = sorted(scored_runs, key=lambda r: (r["case"], _arm_key(r["arm"]), r["repeat"]))
    arms = list(meta.get("arms") or sorted({r["arm"] for r in runs}, key=_arm_key))
    arm_m = {a: summary["arms"].get(a) or _metrics([]) for a in arms}
    case_ids = meta.get("cases") or sorted({r["case"] for r in runs})
    pair_case, pair_base, pair_graph = _pick_pair(runs)
    models = sorted({r["model"] for r in runs if r.get("model")})
    spend = math.fsum(sorted(r["cost_usd"] for r in runs if r.get("cost_usd") is not None))
    date = str(meta.get("date", ""))[:10]
    L = ["# Patch Precedent: agent evaluation results", ""]
    L.append(
        f"Model: {', '.join(models) or NA}. Claude Code CLI: {meta.get('claude_version', NA)}. "
        f"Run date: {date}. Upstream pin: {meta.get('upstream_sha', NA)}. "
        f"Repeats per case and arm: {meta.get('repeats', NA)}. Arms: {', '.join(arms)}. "
        "Both arms receive the identical prompt (eval/prompt.md with the patch inserted) and "
        "flags, with file tools only (Read, Grep, Glob) in a clean worktree of the pin. "
        "The `graph` arm also gets the MCP tool `mcp__precedent__precedent_for_patch`, which "
        "returns the ADRs, tests and each test's observed replay result for the patch; the "
        "`baseline` arm has no MCP server. "
        + _fairness(pair_case, pair_base, pair_graph) + " "
        f"Total spend over all {len(runs)} recorded runs, including excluded ones: {_usd(spend)}.")
    L.append("")

    L += ["## Headline", ""]
    cols = [_headline_rows(arm_m[a]) for a in arms]
    L += _table(["Metric", *[f"{a} (n={arm_m[a]['n']})" for a in arms]],
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
                         _kn(m["outcome_marked"], m["outcome_linked"]),
                         m["unsupported_total"],
                         f"{_pct(m['outcome_accuracy'])} ({_kn(m['outcome_correct'], m['outcome_marked'])})",
                         f"{_num(m['citation_median_s'])} (n={m['citation_n']})",
                         _num(m["turns_mean"]), _usd(m["cost_total"])])
    L += _table(["Case", "Arm", "n", "Verdict", "Decisions exact", "Checks recall",
                 "Marked/linked", "Unsupported", "Outcome acc.", "Median citation s", "Mean turns", "Cost"], rows)
    L.append("")

    L += ["## Every run", ""]
    rows = []
    for r in runs:
        cls = error_class(r.get("error"))
        given = ("(agent failure)" if cls == "agent" else
                 "(parse error)" if r.get("parse_error") else (r.get("verdict") or "(none)"))
        ms = r.get("time_to_first_correct_citation_ms")
        rows.append([r["case"], r["arm"], r["repeat"], given,
                     "yes" if r.get("verdict_correct") else "no",
                     NA if r.get("unsupported_claims") is None else r["unsupported_claims"],
                     NA if ms is None else f"{ms / 1000:.1f}",
                     NA if r.get("turns") is None else r["turns"],
                     NA if r.get("cost_usd") is None else f"${r['cost_usd']:.4f}",
                     cls or "-", r.get("error") or ""])
    L += _table(["Case", "Arm", "Repeat", "Verdict given", "Correct", "Unsupported",
                 "Citation s", "Turns", "Cost", "Class", "Error"], rows)
    L.append("")

    L += ["## Excluded runs", ""]
    if summary["excluded"]:
        L += _table(["Case", "Arm", "Repeat", "Class", "Error", "Cost"],
                    [[x["case"], x["arm"], x["repeat"], x["class"], x["error"],
                      _usd(x.get("cost_usd"))]
                     for x in summary["excluded"]])
        L += ["", "Excluded runs are left out of every aggregate (including cost totals) "
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
          "message text that contains the case's expected ADR id. Blank for "
          "C6 and when the ADR is never cited.",
          "- Turns and cost come from the run record, falling back to the result event.",
          "- Run errors have two classes. Infrastructure errors (spawn failure, no init event, "
          "graph tool missing or MCP server not connected, MCP tools present in the baseline) are "
          "excluded from every aggregate and listed under Excluded runs. Agent errors (non-zero "
          "exit including the turn limit, timeout, file access outside the worktree, dirty "
          "worktree) are scored as failed runs: verdict incorrect, counted in every k/n "
          "denominator, other metrics blank, turns and cost kept. Unrecognised error text is "
          "treated as an agent error.",
          "- Outcomes marked: the number of linked checks the agent marked `fails` or `passes`, "
          "out of all linked checks across the runs shown.",
          "- The baseline arm has no tool that reports observed test results, so any \"fails\" "
          "or \"passes\" it gives is unsupported by construction. Answering \"unknown\" never "
          "counts as unsupported and never lowers outcome accuracy. A claim is \"supported\" when "
          "the agent saw an observed result for that check; whether the claim matches that result "
          "is measured separately by outcome accuracy. Medians of time to first correct citation "
          "skip runs that never cite the expected ADR; their count is shown as n.",
          "- n is shown with each figure; means skip runs where the value is blank.",
          ""]

    L += ["## Commands", "",
          f"Exact command lines from runs.jsonl for one run of each arm on {pair_case}; "
          f"the prompt is `{PLACEHOLDER}` with the patch inserted.", ""]
    L += _commands(pair_case, pair_base, pair_graph)

    L += ["## Limitations", "",
          f"- {len(case_ids)} cases, {meta.get('repeats', NA)} repeat(s) per case and arm, one model, "
          "one repository: the figures are counts over few runs, not estimates of general "
          "behaviour.",
          "- The graph arm's evidence is Patch Precedent's own replay of the same fixtures that "
          "define the ground truth, so what that arm is shown matches what it is scored against.",
          "- Neither arm can run the test suite (its tools are Read, Grep and Glob only), so any "
          "outcome an agent reports without tool evidence is an inference from reading files.",
          "- Elapsed times include model and tool latency and vary between runs.",
          ""]
    dirs = {os.path.dirname(r["argv"][r["argv"].index("--mcp-config") + 1])
            for r in runs if r.get("argv") and "--mcp-config" in r["argv"]
            and r["argv"].index("--mcp-config") + 1 < len(r["argv"])}
    if results_dir:
        dirs.add(str(results_dir))
    return scrub("\n".join(L), tuple(sorted(dirs)))
