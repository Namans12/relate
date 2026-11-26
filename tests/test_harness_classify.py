from patch_precedent.harness import classify
from patch_precedent.tap import TapReport, TapResult


def _tap(passed=3, failed=0, skipped=0, complete=True, results=None):
    if results is None:
        results = tuple(TapResult(i + 1, True, f"c{i}") for i in range(passed + failed))
    return TapReport(results, len(results) or 0, passed, failed, skipped, complete)


def test_apply_failure_inconclusive():
    status, reason = classify(False, False, None, None)
    assert status == "inconclusive" and "apply" in reason


def test_timeout_inconclusive():
    status, reason = classify(True, True, None, None)
    assert status == "inconclusive" and "time" in reason


def test_missing_tap_inconclusive():
    status, reason = classify(True, False, 0, None)
    assert status == "inconclusive" and "TAP" in reason


def test_incomplete_tap_inconclusive():
    status, reason = classify(True, False, 1, _tap(complete=False))
    assert status == "inconclusive" and "incomplete" in reason


def test_zero_results_inconclusive():
    tap = TapReport((), 0, 0, 0, 0, True)
    status, reason = classify(True, False, 0, tap)
    assert status == "inconclusive" and "no checks" in reason


def test_skipped_inconclusive():
    status, reason = classify(True, False, 0, _tap(skipped=2))
    assert status == "inconclusive" and "2" in reason and "skipped" in reason


def test_exit_tap_disagreement_inconclusive():
    status, reason = classify(True, False, 0, _tap(passed=2, failed=1))
    assert status == "inconclusive" and "disagree" in reason
    status, reason = classify(True, False, 1, _tap(passed=3, failed=0))
    assert status == "inconclusive" and "disagree" in reason


def test_pass():
    assert classify(True, False, 0, _tap()) == ("pass", None)


def test_failing_baseline_shape_is_fail_not_pass():
    status, reason = classify(True, False, 1, _tap(passed=2, failed=1))
    assert status == "fail" and reason is None
