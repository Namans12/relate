import json
import re
import shutil
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.pins import STORE_PATH
from patch_precedent.site.data import (SiteDataError, checks_phrase, failing_label, misses_sit, fill, literal_query, load_site_data,
                                       prose)
from patch_precedent.store import open_readonly

ROOT = pins.project_root()


@pytest.fixture(scope="module")
def data():
    return load_site_data(ROOT)


def test_prose_replaces_dashes():
    assert prose("Extension distribution — the first-party channel") == "Extension distribution - the first-party channel"
    assert prose("2019–2020") == "2019-2020"


def test_fill_raises_on_missing():
    with pytest.raises(SiteDataError, match=r"\{gone\}"):
        fill("x {gone}", {})
    assert fill("x {a}", {"a": 1}) == "x 1"


def test_literal_query_quotes():
    assert literal_query("MATCH (f {path: $path})", {"path": "a'b"}) == "MATCH (f {path: 'a\\'b'})"
    assert literal_query("$p", {"p": "a\\b"}) == "'a\\\\b'"
    with pytest.raises(SiteDataError):
        literal_query("MATCH $nope", {})


def test_six_patch_pages_match_recording(data):
    assert [p.slug for p in data.patches] == [
        "installer-release-lookup", "installer-token-header", "installer-wording",
        "release-always-rotate", "release-wording", "release-docs-only"]
    th = next(p for p in data.patches if p.label == "token-header")
    assert (th.passed, th.failed, th.exit_code, th.failing_numbers) == (193, 1, 1, [64])
    assert [c.number for c in th.decisions[0].checks] == [7, 64, 193]
    assert {c.number: c.observed for c in th.decisions[0].checks} == {7: "ok", 64: "not ok", 193: "ok"}
    assert th.fixture == "fixtures/installer/token-header.patch"
    assert th.scenario_title == "Installer"
    assert (th.prev_slug, th.next_slug) == ("installer-release-lookup", "installer-wording")
    assert "#64" in th.body and "{" not in th.body
    docs = next(p for p in data.patches if p.label == "docs-only")
    assert docs.decisions == () and docs.verdict["kind"] == "no_decision"
    assert "CONTRIBUTING.md" in docs.body and "6 of 6" in docs.harness_line
    assert data.home_chain.slug == "installer-token-header"


def test_consistent_body_has_rule(data):
    w = next(p for p in data.patches if p.slug == "release-wording")
    assert "ADR-0580: An advance never rotates CHANGELOG.md" in w.body
    assert "Both linked checks passed" in w.body


def test_diff_line_numbers(data):
    th = data.home_chain
    f = th.diff[0]
    assert f.path == "distribution/install.sh" and (f.added, f.removed) == (5, 0)
    assert f.lines[0].kind == "hunk"
    adds = [ln for ln in f.lines if ln.kind == "add"]
    assert len(adds) == 5 and all(ln.new is not None and ln.old is None for ln in adds)
    assert adds[0].new == 138


def test_titles_have_no_dashes(data):
    for p in data.patches:
        for t in [c.title for c in p.also_cites] + [x.title for x in p.decisions]:
            assert "—" not in t and "–" not in t


def test_query_literal_runs_against_store(data):
    conn = open_readonly(STORE_PATH)
    titles = [t for t, _ in data.home_chain.queries]
    assert titles[:2] == ["Decision chain", "Every cited decision"]
    for _title, q in data.home_chain.queries:
        assert list(conn.execute(q))


def test_eval_numbers_equal_results_json(data):
    m = {x["key"]: x for x in data.eval.metrics}
    assert len(data.eval.metrics) == 9
    assert (m["verdict"]["baseline"], m["verdict"]["graph"]) == ("16/18", "18/18")
    assert (m["turns"]["baseline"], m["turns"]["graph"]) == ("6.2", "2.1")
    assert (m["cost"]["baseline"], m["cost"]["graph"]) == ("$0.73", "$0.38")
    assert (m["unsupported"]["baseline"], m["unsupported"]["graph"]) == ("4", "0")
    assert (m["citation_time"]["baseline"], m["citation_time"]["graph"]) == ("12.4 s", "7.5 s")
    assert 0 <= m["turns"]["baseline_frac"] <= 1 and 0 <= m["turns"]["graph_frac"] <= 1
    assert len(data.eval.cases) == 6 and len(data.eval.per_run) == 36
    assert data.eval.cases[0]["id"] == "C1" and data.eval.cases[0]["expected"] == "violates"
    assert set(data.eval.per_run[0]) == {"case", "arm", "repeat", "verdict", "verdict_correct",
                                         "turns", "cost_usd", "tool_replay_found"}


def test_caveats_filled(data):
    assert any("3 of 18" in c for c in data.eval.caveats)
    assert len(data.eval.caveats) == 4
    assert all("{" not in c and "}" not in c for c in data.eval.caveats)
    assert "both baseline verdict misses sit on that line" in data.eval.caveats[3]
    assert "{" not in data.eval.intro and "Claude Sonnet" in data.eval.intro


def test_content_has_no_en_or_em_dashes():
    text = (ROOT / "site" / "content.toml").read_text(encoding="utf-8")
    assert "–" not in text and "—" not in text


def _copy_inputs(dst: Path) -> None:
    for rel in ("data", "recorded", "fixtures", "site", "evidence", "pyproject.toml"):
        src = ROOT / rel
        (shutil.copytree if src.is_dir() else shutil.copy)(src, dst / rel)
    (dst / "eval" / "results").mkdir(parents=True)
    shutil.copy(ROOT / "eval" / "cases.toml", dst / "eval" / "cases.toml")
    shutil.copytree(ROOT / "eval" / "results" / "20261127T040059Z",
                    dst / "eval" / "results" / "20261127T040059Z",
                    ignore=shutil.ignore_patterns("transcripts"))


def test_copy_loads(tmp_path):
    _copy_inputs(tmp_path)
    assert len(load_site_data(tmp_path).patches) == 6


def test_missing_content_entry_raises(tmp_path):
    _copy_inputs(tmp_path)
    p = tmp_path / "site" / "content.toml"
    text = p.read_text(encoding="utf-8")
    start = text.index('[patches."release/docs-only"]')
    end = text.find("\n[", start + 1)
    p.write_text(text[:start] + (text[end + 1:] if end != -1 else ""), encoding="utf-8")
    with pytest.raises(SiteDataError, match="release/docs-only"):
        load_site_data(tmp_path)


def test_missing_input_file_raises(tmp_path):
    _copy_inputs(tmp_path)
    (tmp_path / "recorded" / "demo-all.json").unlink()
    with pytest.raises(SiteDataError, match="demo-all.json"):
        load_site_data(tmp_path)


def test_unfilled_placeholder_raises(tmp_path):
    _copy_inputs(tmp_path)
    p = tmp_path / "site" / "content.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("{repeats}", "{nope}", 1), encoding="utf-8")
    with pytest.raises(SiteDataError, match=r"\{nope\}"):
        load_site_data(tmp_path)


def test_boundary_assertion(tmp_path):
    _copy_inputs(tmp_path)
    sp = tmp_path / "eval" / "results" / "20261127T040059Z" / "scored.jsonl"
    rows = [json.loads(line) for line in sp.read_text().splitlines()]
    for r in rows:
        if r["arm"] == "baseline" and r["case"] == "C1":
            r["verdict_correct"] = False
            r["verdict"] = "consistent"
            break
    sp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(SiteDataError, match="caveat 'boundary' no longer true"):
        load_site_data(tmp_path)


def test_store_stats(data):
    s = data.store
    assert (s.nodes, s.rels) == (2557, 6844)
    assert s.by_label["Decision"] == 567 and s.by_type["CITES"] == 6837


def test_count_helpers():
    assert checks_phrase(1) == "The linked check"
    assert checks_phrase(2) == "Both linked checks"
    assert checks_phrase(3) == "All 3 linked checks"
    assert failing_label([64]) == "Check #64"
    assert failing_label([193, 7]) == "Checks #7 and #193"
    assert failing_label([1, 2, 3]) == "Checks #1, #2 and #3"
    assert misses_sit(1) == "the one baseline verdict miss sits"
    assert misses_sit(2) == "both baseline verdict misses sit"
    assert misses_sit(5) == "all 5 baseline verdict misses sit"


def test_bodies_and_demo_strings(data):
    by = {p.slug: p.body for p in data.patches}
    assert "Checks #7 and #193 caught it: install.sh contains a GitHub API URL" in by["installer-release-lookup"]
    assert by["installer-token-header"].count("Check #64 caught it") == 1
    assert "All 3 linked checks passed" in by["installer-wording"]
    n = round(data.recording["elapsed_s"])
    assert data.content["home"]["demo_note"] == f"Runs locally in about {n} seconds."
    assert f"About {n} seconds." in data.content["use"]["steps"][1]["text"]
    for sec in ("home", "use", "relate"):
        assert "{" not in "".join(re.findall(r'"((?:[^"\\\\]|\\\\.)*)"', json.dumps(data.content[sec])))


def test_stray_placeholder_in_home_raises(tmp_path):
    _copy_inputs(tmp_path)
    p = tmp_path / "site" / "content.toml"
    p.write_text(p.read_text(encoding="utf-8").replace("{demo_seconds}", "{nope}", 1), encoding="utf-8")
    with pytest.raises(SiteDataError, match=r"\{nope\}"):
        load_site_data(tmp_path)
