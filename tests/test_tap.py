from patch_precedent.pins import project_root
from patch_precedent.tap import parse_tap

DATA = project_root() / "tests" / "data"


def load(name):
    return parse_tap((DATA / name).read_text())


def test_parse_release_lookup():
    r = load("release-lookup.tap")
    assert (r.passed, r.failed, r.planned) == (192, 2, 194)
    assert r.complete
    failing = [(x.number, x.description) for x in r.results if not x.ok]
    assert failing == [
        (7, "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)"),
        (193, "no case made a GitHub API request (ADR-0585)"),
    ]


def test_parse_wording_and_baseline():
    for name in ("wording.tap", "baseline.tap"):
        r = load(name)
        assert (r.passed, r.failed, r.complete) == (194, 0, True)


def test_truncated_incomplete():
    r = load("truncated.tap")
    assert r.complete is False
    assert r.planned is None


def test_skip_directive_stripped():
    r = parse_tap("ok 1 - thing # SKIP no curl\nok 2 - other # TODO later\nnot ok 3 - x\n1..3\n")
    assert [x.description for x in r.results] == ["thing", "other", "x"]
    assert (r.passed, r.failed, r.complete) == (2, 1, True)


def test_counts_from_results_not_comment():
    r = parse_tap("ok 1 - a\n1..1\n# pass 0, fail 9 (of 9)\n")
    assert (r.passed, r.failed, r.complete) == (1, 0, True)


def test_incomplete_cases():
    assert not parse_tap("ok 1 - a\nok 2 - b\n1..3\n").complete  # missing result
    assert not parse_tap("ok 1 - a\n").complete  # no plan
    assert not parse_tap("ok 1 - a\n1..1\n1..1\n").complete  # two plans
    assert not parse_tap("ok 1 - a\nok 1 - b\n1..2\n").complete  # duplicate numbers
    assert not parse_tap("ok 2 - a\n1..1\n").complete  # wrong number
    assert not parse_tap("ok 1 - a\nok 2 - b\n1..1\n").complete  # extra result
