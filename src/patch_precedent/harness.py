"""Run the unmodified upstream installer harness against a patched checkout."""
import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import pins
from .diffparse import PatchInfo
from .tap import TapReport, parse_tap
from .upstream import clean_checkout, ensure_upstream

Status = Literal["pass", "fail", "inconclusive"]


@dataclass(frozen=True)
class RunResult:
    label: str
    patch: PatchInfo | None
    base_sha: str
    command: str
    exit_code: int | None
    tap: TapReport | None
    log_path: Path
    status: Status
    reason: str | None


def classify(
    apply_ok: bool,
    timed_out: bool,
    exit_code: int | None,
    tap: TapReport | None,
) -> tuple[Status, str | None]:
    if not apply_ok:
        return "inconclusive", "the patch did not apply cleanly to the pinned upstream"
    if timed_out:
        return "inconclusive", (
            f"the harness timed out after {pins.HARNESS_TIMEOUT_S} seconds"
        )
    if tap is None:
        return "inconclusive", "no TAP output was produced by the harness"
    if not tap.complete:
        return "inconclusive", "the TAP output is incomplete (truncated or malformed)"
    if not tap.results:
        return "inconclusive", "the harness ran no checks (empty TAP plan)"
    if tap.skipped > 0:
        return "inconclusive", (
            f"{tap.skipped} checks were skipped, so the patched installer may not "
            "have been built"
        )
    if exit_code is None:
        return "inconclusive", "the harness produced no exit code"
    if exit_code == 0 and tap.failed == 0:
        return "pass", None
    if exit_code != 0 and tap.failed > 0:
        return "fail", None
    return "inconclusive", (
        f"exit code {exit_code} and TAP result ({tap.failed} failed) disagree"
    )


def run_case(label: str, patch: PatchInfo | None, run_dir: Path) -> RunResult:
    ensure_upstream()
    sha = pins.UPSTREAM_SHA
    command = " ".join(pins.HARNESS_CMD)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / f"{label}.log"
    exit_path = run_dir / f"{label}.exit"

    def result(exit_code, tap, status, reason):
        return RunResult(label, patch, sha, command, exit_code, tap, log_path, status, reason)

    with clean_checkout(sha, run_dir / "checkouts" / label) as checkout:
        if patch is not None:
            p = str(Path(patch.path).resolve())
            for args in (["--check", p], [p]):
                r = subprocess.run(
                    ["git", "apply", *args], cwd=checkout, capture_output=True, text=True
                )
                if r.returncode != 0:
                    log_path.write_text(r.stderr or r.stdout)
                    exit_path.write_text("none\n")
                    return result(None, None, *classify(False, False, None, None))
        timed_out = False
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                list(pins.HARNESS_CMD),
                cwd=checkout,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                exit_code: int | None = proc.wait(timeout=pins.HARNESS_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                timed_out = True
                exit_code = None
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        exit_path.write_text(f"{'timeout' if timed_out else exit_code}\n")
        tap = parse_tap(log_path.read_text(errors="replace"))
        return result(exit_code, tap, *classify(True, timed_out, exit_code, tap))
