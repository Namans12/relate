"""Parse TAP emitted by the upstream shell harness (scripts/tests/lib/tap.sh)."""
import re
from dataclasses import dataclass

_RESULT = re.compile(r"^(not ok|ok) (\d+)(?: - (.*))?$")
_PLAN = re.compile(r"^1\.\.(\d+)$")
_DIRECTIVE = re.compile(r"\s+#\s*(SKIP|TODO)\b.*$", re.IGNORECASE)


@dataclass(frozen=True)
class TapResult:
    number: int
    ok: bool
    description: str
    skipped: bool = False


@dataclass(frozen=True)
class TapReport:
    results: tuple[TapResult, ...]
    planned: int | None
    passed: int
    failed: int
    skipped: int
    complete: bool


def parse_tap(text: str) -> TapReport:
    results: list[TapResult] = []
    plans: list[int] = []
    for line in text.splitlines():
        line = line.rstrip("\r")
        m = _RESULT.match(line)
        if m:
            raw = m.group(3) or ""
            d = _DIRECTIVE.search(raw)
            ok = m.group(1) == "ok"
            skipped = ok and d is not None and d.group(1).upper() == "SKIP"
            results.append(
                TapResult(int(m.group(2)), ok, _DIRECTIVE.sub("", raw), skipped)
            )
            continue
        p = _PLAN.match(line)
        if p:
            plans.append(int(p.group(1)))
    planned = plans[0] if plans else None
    passed = sum(r.ok for r in results)
    complete = (
        len(plans) == 1
        and [r.number for r in results] == list(range(1, plans[0] + 1))
    )
    return TapReport(
        tuple(results),
        planned,
        passed,
        len(results) - passed,
        sum(r.skipped for r in results),
        complete,
    )
