import json
import re

import pytest

from patch_precedent import pins
from patch_precedent.site.build import build_site


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build_site(pins.project_root(), out, allow_missing=True)
    return out


def _read(site, name):
    return (site / name).read_text(encoding="utf-8")


def _rec():
    return json.loads((pins.project_root() / "recorded/demo-all.json").read_text())


def test_home_sections(site):
    t = _read(site, "home.html")
    assert all(f'id="{i}"' in t for i in ("top", "how", "scenarios", "demo", "results", "use"))


def test_home_carousel_has_six_cards(site):
    assert _read(site, "home.html").count("data-card") == 6


def test_demo_panel_has_full_transcript(site):
    assert _read(site, "home.html").count('class="t-line"') == len(_rec()["transcript"])


def test_demo_transcript_is_verbatim_and_replayable(site):
    t = _read(site, "home.html")
    assert re.search(r"<pre[^>]*data-verbatim[^>]*data-replay|<pre[^>]*data-replay[^>]*data-verbatim", t)


def test_demo_label_names_run(site):
    t = _read(site, "home.html")
    assert "Recorded run" in t and _rec()["run_id"] in t and "UTC" in t


def test_home_results_numbers(site):
    t = _read(site, "home.html")
    assert "16/18" in t and "18/18" in t
    assert "Mean turns (lower is better)" in t and "Unsupported claims (lower is better)" in t


def test_tabs_aria(site):
    t = _read(site, "home.html")
    assert 'role="tablist"' in t and t.count('role="tab"') == 3 and t.count('role="tabpanel"') == 3


def test_hooks_and_links(site):
    t = _read(site, "home.html")
    for hook in ("data-carousel", "data-tabs", "data-copy", "data-replay"):
        assert hook in t
    assert 'href="#demo"' in t and 'href="#scenarios"' in t and 'href="results.html"' in t
    assert "scenarios/installer-token-header.html" in t


def test_docs_only_card_summarises_tests(site):
    assert "6 of 6 tests ok" in _read(site, "home.html")
