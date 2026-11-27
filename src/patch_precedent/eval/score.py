"""Deterministic scoring of evaluation runs. Pure: no network, no `claude`, no clock.

Transcript lines are `{"t_ms", "event"}`, `{"t_ms", "raw"}` or bare stream-json objects
(t_ms is then None). Everything here is a function of the transcript, the final JSON and
the case ground truth.
"""
import json
import math
import statistics
from pathlib import Path
from typing import Iterable

from .cases import Case

CLAIMS = ("fails", "passes")
ARM_ORDER = ("baseline", "graph")


INFRA_PREFIXES = ("spawn failed", "no init event", "graph arm init lacks", "mcp server ",
                  "baseline arm has MCP tools")


def error_class(error: str | None) -> str | None:
    """None for a clean run; "infrastructure" (excluded) or "agent" (scored as failed).

    The runner joins error strings with "; ". Any infrastructure part makes the run
    infrastructure; every other string, including unknown ones, is an agent failure so
    failures are never hidden.
    """
    if not error:
        return None
    if any(part.startswith(INFRA_PREFIXES) for part in error.split("; ")):
        return "infrastructure"
    return "agent"


def norm(text: str) -> str:
    """The one check-name normaliser: whitespace runs become single spaces, then strip."""
    return " ".join(str(text).split())


def load_events(path: Path) -> list[dict]:
    """Return [{"t_ms": int | None, "event": dict}]; `raw` lines and non-JSON lines are dropped."""
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        if isinstance(obj.get("event"), dict) and "t_ms" in obj:
            out.append({"t_ms": obj["t_ms"], "event": obj["event"]})
        elif "raw" in obj and "t_ms" in obj and "type" not in obj:
            continue
        elif "type" in obj:
            out.append({"t_ms": None, "event": obj})
    return out


def _strip_fence(line: str) -> str:
    s = line.strip()
    if s.startswith("```"):
        s = s[3:]
        if s.lower().startswith("json"):
            s = s[4:]
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def parse_final(result_text: str) -> dict | None:
    """The LAST line of the text that parses as a JSON object (code fences stripped)."""
    for line in reversed((result_text or "").splitlines()):
        s = _strip_fence(line)
        if not s.startswith("{"):
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _content_blocks(event: dict) -> list[dict]:
    content = (event.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _assistant_text(event: dict) -> str:
    return "\n".join(b["text"] for b in _content_blocks(event)
                     if b.get("type") == "text" and isinstance(b.get("text"), str))


def final_from_events(events: list[dict]) -> dict | None:
    """From the result event; with no result event, from the last assistant text block."""
    results = [e["event"] for e in events if e["event"].get("type") == "result"]
    if results:
        text = results[-1].get("result")
        return parse_final(text if isinstance(text, str) else "")
    for e in reversed(events):
        if e["event"].get("type") != "assistant":
            continue
        texts = [b["text"] for b in _content_blocks(e["event"])
                 if b.get("type") == "text" and isinstance(b.get("text"), str)]
        if texts:
            return parse_final(texts[-1])
    return None


def _tool_result_texts(event: dict) -> Iterable[str]:
    if event.get("type") != "user":
        return
    for b in _content_blocks(event):
        if b.get("type") != "tool_result":
            continue
        c = b.get("content")
        if isinstance(c, str):
            yield c
        elif isinstance(c, list):
            yield "".join(x["text"] for x in c
                          if isinstance(x, dict) and isinstance(x.get("text"), str))


def supported_checks(events: list[dict]) -> set[str]:
    """Normalised names of checks with a replay-observed result in a precedent_for_patch tool result."""
    out = set()
    for e in events:
        for text in _tool_result_texts(e["event"]):
            try:
                payload = json.loads(text)
            except ValueError:
                continue
            if not (isinstance(payload, dict) and isinstance(payload.get("files"), list)):
                continue
            for f in payload["files"]:
                for d in (f.get("decisions") or []) if isinstance(f, dict) else []:
                    for c in (d.get("checks") or []) if isinstance(d, dict) else []:
                        if isinstance(c, dict) and c.get("observed") in ("ok", "not ok") \
                                and isinstance(c.get("name"), str):
                            out.add(norm(c["name"]))
    return out


def tool_replay_found(events: list[dict]) -> bool | None:
    """Did the LAST precedent_for_patch call return an observed replay?

    None when the run made no such call (always so for the baseline). Otherwise True when that
    call's tool_result JSON has a non-null `replay`, False when `replay` is null or the result
    is missing or unparseable.
    """
    ids, last = [], None
    for e in events:
        ev = e["event"]
        if ev.get("type") == "assistant":
            for b in _content_blocks(ev):
                if b.get("type") == "tool_use" and isinstance(b.get("name"), str) \
                        and b["name"].endswith("precedent_for_patch"):
                    ids.append(b.get("id"))
    if not ids:
        return None
    for e in events:
        ev = e["event"]
        if ev.get("type") != "user":
            continue
        for b in _content_blocks(ev):
            if b.get("type") == "tool_result" and b.get("tool_use_id") == ids[-1]:
                last = b
    if last is None:
        return False
    c = last.get("content")
    text = c if isinstance(c, str) else "".join(
        x["text"] for x in c if isinstance(x, dict) and isinstance(x.get("text"), str)) \
        if isinstance(c, list) else ""
    try:
        payload = json.loads(text)
    except ValueError:
        return False
    return isinstance(payload, dict) and payload.get("replay") is not None


def _first_citation_ms(case: Case, events: list[dict]) -> int | None:
    """t_ms of the first assistant TEXT block naming the expected ADR (tool inputs never count:
    a patch passed to a tool can itself contain the ADR id)."""
    if not case.decisions:
        return None
    adr = case.decisions[0]
    for e in events:
        ev = e["event"]
        if ev.get("type") == "assistant" and adr in _assistant_text(ev):
            return e["t_ms"]
    return None


def _result_event(events: list[dict]) -> dict:
    results = [e["event"] for e in events if e["event"].get("type") == "result"]
    return results[-1] if results else {}


def _str_list(v) -> list[str]:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def score_run(case: Case, events: list[dict], final: dict | None, row: dict | None = None) -> dict:
    row = row or {}
    res = _result_event(events)
    turns = row.get("num_turns") if row.get("num_turns") is not None else res.get("num_turns")
    cost = row.get("total_cost_usd") if row.get("total_cost_usd") is not None \
        else res.get("total_cost_usd")
    keys = ("decisions_exact", "decisions_precision", "decisions_recall", "checks_recall",
            "catching_checks_recall", "tool_replay_found", "outcome_marked", "outcome_correct",
            "outcome_accuracy", "unsupported_claims", "time_to_first_correct_citation_ms")
    out = {"parse_error": final is None, "verdict": None, "verdict_correct": False,
           **{k: None for k in keys}, "turns": turns, "cost_usd": cost}
    out["tool_replay_found"] = tool_replay_found(events)  # a transcript fact: kept on failures
    if final is None:
        return out

    verdict = final.get("verdict")
    out["verdict"] = verdict if isinstance(verdict, str) else None
    out["verdict_correct"] = verdict == case.verdict

    listed, expected = set(_str_list(final.get("decisions"))), set(case.decisions)
    correct = listed & expected
    out["decisions_exact"] = listed == expected
    out["decisions_precision"] = len(correct) / len(listed) if listed else None
    out["decisions_recall"] = len(correct) / len(expected) if expected else None

    truth = {norm(k): v for k, v in case.check_outcomes.items()}
    if truth:
        out["checks_recall"] = len({norm(c) for c in _str_list(final.get("checks"))} & set(truth)) \
            / len(truth)

    catching = {k for k, v in truth.items() if v == "fails"}
    if catching:
        out["catching_checks_recall"] = len(
            {norm(c) for c in _str_list(final.get("checks"))} & catching) / len(catching)

    claims = final.get("check_outcomes")
    claims = {norm(k): v for k, v in claims.items()} if isinstance(claims, dict) else {}
    marked = {k: v for k, v in claims.items() if v in CLAIMS}
    support = supported_checks(events)
    out["unsupported_claims"] = sum(1 for k in marked if k not in support)
    linked = {k: v for k, v in marked.items() if k in truth}
    out["outcome_marked"] = len(linked)
    out["outcome_correct"] = sum(1 for k, v in linked.items() if truth[k] == v)
    out["outcome_accuracy"] = out["outcome_correct"] / len(linked) if linked else None
    out["time_to_first_correct_citation_ms"] = _first_citation_ms(case, events)
    return out


def score_row(case: Case, row: dict, results_dir: Path) -> dict:
    """Score one runs.jsonl row; carries the identity fields the report needs.

    An agent-class failure is scored as a failed run: verdict incorrect, other metrics null,
    turns and cost kept.
    """
    events = load_events(Path(results_dir) / row["transcript"]) if row.get("transcript") else []
    scored = score_run(case, events, final_from_events(events), row)
    cls = error_class(row.get("error"))
    if cls == "agent":
        scored = {k: (None if k not in ("turns", "cost_usd", "tool_replay_found") else v)
                  for k, v in scored.items()}
        scored.update(parse_error=False, verdict_correct=False)
    return {"case": row["case"], "arm": row["arm"], "repeat": row["repeat"],
            "error": row.get("error"), "error_class": cls, "model": row.get("model"),
            "argv": row.get("argv"), "outcome_linked": len(case.check_outcomes), **scored}


def _mean(xs: list[float]) -> float | None:
    return math.fsum(sorted(xs)) / len(xs) if xs else None


def _metrics(runs: list[dict]) -> dict:
    def vals(key):
        return [r[key] for r in runs if r.get(key) is not None]

    unsup, cites = vals("unsupported_claims"), vals("time_to_first_correct_citation_ms")
    marked, correct = sum(vals("outcome_marked")), sum(vals("outcome_correct"))
    recalls, turns, costs = vals("checks_recall"), vals("turns"), vals("cost_usd")
    catching, dec_recalls = vals("catching_checks_recall"), vals("decisions_recall")
    replays = vals("tool_replay_found")
    return {
        "n": len(runs),
        "verdict_k": sum(1 for r in runs if r.get("verdict_correct") is True),
        "decisions_exact_k": sum(1 for r in runs if r.get("decisions_exact") is True),
        "checks_recall_mean": _mean(recalls), "checks_recall_n": len(recalls),
        "catching_recall_mean": _mean(catching), "catching_recall_n": len(catching),
        "decisions_recall_mean": _mean(dec_recalls), "decisions_recall_n": len(dec_recalls),
        "replay_found_k": sum(1 for v in replays if v is True), "replay_found_n": len(replays),
        "unsupported_total": sum(unsup), "unsupported_n": len(unsup),
        "unsupported_mean": _mean(unsup),
        "outcome_marked": marked, "outcome_correct": correct,
        "outcome_linked": sum(vals("outcome_linked")),
        "outcome_accuracy": correct / marked if marked else None,
        "citation_median_s": statistics.median(cites) / 1000 if cites else None,
        "citation_n": len(cites),
        "turns_mean": _mean(turns), "turns_n": len(turns),
        "cost_total": math.fsum(sorted(costs)), "cost_n": len(costs),
    }


def _arm_key(arm: str) -> tuple:
    return (ARM_ORDER.index(arm), arm) if arm in ARM_ORDER else (len(ARM_ORDER), arm)


def summarise(scored: list[dict]) -> dict:
    """Aggregate per arm and per case x arm. Infrastructure failures are excluded and listed;
    agent failures stay in every denominator."""
    kept = [r for r in scored if error_class(r.get("error")) != "infrastructure"]
    excluded = [{"case": r["case"], "arm": r["arm"], "repeat": r["repeat"], "error": r["error"],
                 "class": "infrastructure", "cost_usd": r.get("cost_usd")}
                for r in sorted(scored, key=lambda r: (r["case"], _arm_key(r["arm"]), r["repeat"]))
                if error_class(r.get("error")) == "infrastructure"]
    arms = sorted({r["arm"] for r in kept}, key=_arm_key)
    cases = sorted({r["case"] for r in kept})
    return {
        "arms": {a: _metrics([r for r in kept if r["arm"] == a]) for a in arms},
        "cases": {c: {a: _metrics([r for r in kept if r["case"] == c and r["arm"] == a])
                      for a in arms if any(r["case"] == c and r["arm"] == a for r in kept)}
                  for c in cases},
        "excluded": excluded,
    }
