"""Record a real `demo all` run (styled transcript plus summary) for the website."""
from __future__ import annotations

import datetime
import json
import re
import time
from pathlib import Path

from .. import pins
from ..tui import STYLES, StyledReporter, make_console

_SGR = re.compile(r"\x1b\[([0-9;]*)m")
_RGB_TO_NAME = {
    tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)): k.removeprefix("pp.")
    for k, v in STYLES.items() if v.startswith("#")
}
_DROP_RUN_KEYS = {"log"}
_DROP_SCENARIO_KEYS = {"run_dir", "replay_store", "join_rows"}


class TimingSink:
    """Text file-like object that stamps each completed line with elapsed seconds."""

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self._partial = ""
        self.lines: list[tuple[float, str]] = []

    def write(self, text: str) -> int:
        self._partial += text
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            self.lines.append((time.monotonic() - self._t0, line))
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def ansi_to_spans(line: str) -> list[tuple[str, str]]:
    color: str | None = None
    bold = dim = False
    spans: list[tuple[str, str]] = []

    def style() -> str:
        return color or ("strong" if bold else "dim" if dim else "plain")

    def emit(text: str) -> None:
        if not text:
            return
        if spans and spans[-1][1] == style():
            spans[-1] = (spans[-1][0] + text, spans[-1][1])
        else:
            spans.append((text, style()))

    pos = 0
    for m in _SGR.finditer(line):
        emit(line[pos:m.start()])
        pos = m.end()
        codes = [int(c) if c else 0 for c in m.group(1).split(";")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                color, bold, dim = None, False, False
            elif c == 1:
                bold = True
            elif c == 2:
                dim = True
            elif c == 22:
                bold = dim = False
            elif c == 39:
                color = None
            elif c == 38 and codes[i + 1:i + 2] == [2] and i + 4 < len(codes):
                color = _RGB_TO_NAME.get(tuple(codes[i + 2:i + 5]))
                i += 4
            i += 1
    emit(line[pos:])
    return spans


def scrub(text: str) -> str:
    text = text.replace(str(pins.project_root()), ".")
    text = text.replace(str(Path.home()), "~")
    return re.sub(r"/Users/[^/\s]+", "~", text)


def _scrub_deep(value):
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, list):
        return [_scrub_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_deep(v) for k, v in value.items()}
    return value


def _observed(replay_store: Path, label: str) -> dict:
    import relate

    from ..store import open_readonly

    conn = open_readonly(replay_store)
    try:
        out = {}
        for r in conn.execute(
            "MATCH (p:Patch {label: $label})-[:PRODUCED]->(o:Observation)-[:FOR_CHECK]->(k:Check) "
            "RETURN k.name AS name, o.tap AS tap, o.number AS number", {"label": label}):
            d = r.data()
            out[d["name"]] = {"ok": d["tap"] == "ok", "number": d["number"]}
        return dict(sorted(out.items(), key=lambda kv: (kv[1]["number"] is None, kv[1]["number"] or 0)))
    except relate.Error:
        return {}
    finally:
        conn.close()


def record_demo(out: Path, runs_root: Path) -> int:
    from ..demo import run_all

    runs_root = Path(runs_root)
    before = {p.name for p in runs_root.iterdir()} if runs_root.is_dir() else set()
    sink = TimingSink()
    console = make_console(file=sink, width=100, force_terminal=True, color_system="truecolor")
    reporter = StyledReporter(console)
    try:
        code = run_all(runs_root, reporter=reporter)
    finally:
        reporter.finish()
    if code != 0:
        return code
    new = [p for p in runs_root.iterdir()
           if p.name not in before and (p / "summary.json").is_file()]
    if len(new) != 1:
        raise RuntimeError(f"expected exactly one new run directory under {runs_root}, got {new}")
    run_dir = new[0]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    scenarios = {}
    for name, sc in summary["scenarios"].items():
        store = Path(sc["replay_store"])
        runs = []
        for r in sc["runs"]:
            r = {k: v for k, v in r.items() if k not in _DROP_RUN_KEYS}
            r["observed"] = _observed(store, r["label"]) if r["patch_id"] else {}
            runs.append(r)
        scenarios[name] = {**{k: v for k, v in sc.items() if k not in _DROP_SCENARIO_KEYS},
                           "runs": runs}
    transcript = []
    for t, line in sink.lines:
        transcript.append({"t": round(t, 2),
                           "spans": [[scrub(x), s] for x, s in ansi_to_spans(line)]})
    rec = {
        "format": 1,
        "run_id": run_dir.name,
        "recorded_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "upstream": {"url": pins.UPSTREAM_URL, "sha": pins.UPSTREAM_SHA},
        "relate_version": pins.RELATE_VERSION,
        "overall_exit": summary["overall_exit"],
        "elapsed_s": summary["elapsed_s"],
        "scenarios": scenarios,
        "transcript": transcript,
    }
    rec = _scrub_deep(rec)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0
