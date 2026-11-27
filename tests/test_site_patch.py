import re

import pytest

from patch_precedent import pins
from patch_precedent.site.build import build_site

SLUGS = ["installer-release-lookup", "installer-token-header", "installer-wording",
         "release-always-rotate", "release-wording", "release-docs-only"]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build_site(pins.project_root(), out)
    return out


def _read(site, name):
    return (site / name).read_text(encoding="utf-8")


def test_six_patch_pages(site):
    assert sorted(p.name for p in (site / "scenarios").glob("*.html")) == sorted(
        f"{s}.html" for s in SLUGS)


def test_token_header_page_numbers(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert "193 / 1" in t and ">#64<" in t and "ADR-0585" in t
    assert "Breaks the installer&#39;s no-token rule" in t
    assert "Installer · ADR-0585" in t and "callout-fail" in t


def test_docs_only_empty_state(site):
    t = _read(site, "scenarios/release-docs-only.html")
    assert "cites no decision" in t and "6 of 6" in t and "n-none" in t
    assert "Decision</a>" not in t and "callout-none" in t
    assert "Release · no linked decision" in t


def test_wording_pass_callout(site):
    assert "callout-pass" in _read(site, "scenarios/installer-wording.html")


def test_check_name_verbatim_keeps_dash(site):
    t = _read(site, "scenarios/release-always-rotate.html")
    assert "byte-identical — no heading inserted" in t


def test_query_blocks_present(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert t.count("MATCH (f:File {path: 'distribution/install.sh'})") >= 1


def test_sidebar_current(site):
    t = _read(site, "scenarios/release-wording.html")
    assert re.search(r'class="item on" href="release-wording.html" aria-current="page"', t)


def test_sidebar_groups_and_dots(site):
    t = _read(site, "scenarios/installer-wording.html")
    assert "ADR-0585" in t and "ADR-0580" in t
    assert t.count("d-fail") >= 3 and t.count("d-pass") >= 2


def test_pager_links(site):
    first = _read(site, "scenarios/installer-release-lookup.html")
    last = _read(site, "scenarios/release-docs-only.html")
    mid = _read(site, "scenarios/installer-wording.html")
    assert "<small>Previous</small>" not in first and "<small>Next</small>" in first
    assert "<small>Next</small>" not in last and "<small>Previous</small>" in last
    assert 'href="installer-token-header.html"' in mid and 'href="release-always-rotate.html"' in mid


def test_graph_inline_and_scrollable(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert '<div class="graph-scroll">' in t and 'class="patch-graph"' in t
    assert "iframe" not in t


def test_commit_is_eight_chars(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert "Commit 5ac38808<" in t and "Commit 5ac388085" not in t


def test_also_cited_and_explain(site):
    t = _read(site, "scenarios/installer-token-header.html")
    assert "scanned from source, not reviewed" in t and "uv run patch-precedent explain" in t
    assert "Drawn from the Relate store" in t and "read_cypher" in t


def test_docs_only_harness_line_from_data(site):
    t = _read(site, "scenarios/release-docs-only.html")
    assert "The release harness still ran: 6 of 6 checks passed." in t
    assert t.count("6 of 6") == 1


def test_citation_label_from_url(site):
    t2 = _read(site, "scenarios/installer-token-header.html")
    assert "Citation in distribution/install.sh<" in t2
    assert "Also cited by distribution/install.sh" in t2 and "5 ADRs" in t2


def test_pager_names_scenario(site):
    t = _read(site, "scenarios/installer-wording.html")
    assert "Installer · token-header" in t and "Release · always-rotate" in t
