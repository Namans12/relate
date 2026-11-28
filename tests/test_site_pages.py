import re

import pytest

from patch_precedent import pins
from patch_precedent.site.build import build_site


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build_site(pins.project_root(), out)
    return out


def _read(site, name):
    return (site / name).read_text(encoding="utf-8")


def test_results_numbers(site):
    t = _read(site, "results.html")
    for s in ("16/18", "18/18", "13/18", "6.2", "2.1", "$0.73", "$0.38", "3 of 18"):
        assert s in t


def test_results_caveats_count(site):
    assert _read(site, "results.html").count('class="caveat"') == 5


def test_results_links(site):
    t = _read(site, "results.html")
    assert "https://github.com/Namans12/patch-precedent/blob/main/eval/results/20261127T040059Z/RESULTS.md" in t
    assert 'href="use.html#rescore"' in t


def test_results_per_case_table_scrolls(site):
    t = _read(site, "results.html")
    assert t.count("<tr>\n            <td class=\"k\">C") == 6
    assert 'class="twrap"' in t


def test_use_steps(site):
    t = _read(site, "use.html")
    assert t.count('class="step"') == 6 and 'id="rescore"' in t


def test_use_commands_verbatim(site):
    t = _read(site, "use.html")
    for s in ("git clone https://github.com/Namans12/patch-precedent.git",
              "uv run patch-precedent explain fixtures/installer/token-header.patch",
              "claude mcp add --scope project precedent -- uv run --project &lt;path-to-patch-precedent&gt;",
              "serve --mcp stdio --read-only --database &lt;copy of data/precedent.rl&gt;",
              "eval score --results eval/results/20261127T040059Z",
              "eval report --results eval/results/20261127T040059Z",
              '"mcpServers"'):
        assert s in t, s


def test_relate_counts_and_queries(site):
    t = _read(site, "relate.html")
    assert "2,557" in t and "6,844" in t
    assert t.count("<pre data-verbatim") >= 4 and "precedent_for_patch" in t
    assert "Every query path opens the store read-only" not in t
    assert "only ever opened read-only" in t


def test_built_with_relate_only_on_home(site):
    hits = [p.name for p in site.rglob("*.html") if "Built with Relate" in p.read_text("utf-8")]
    assert hits == ["home.html"]


def test_no_dashes_in_new_pages(site):
    for name in ("results.html", "use.html", "relate.html"):
        body = re.sub(r"<pre.*?</pre>|<svg.*?</svg>", "", _read(site, name), flags=re.S)
        assert "–" not in body and "—" not in body, name


def test_lower_is_better_marked_once_per_source(site):
    t = _read(site, "results.html")
    # 4 cards + 4 headline rows + 3 per-case groups
    assert t.count("(lower is better)") == 11


def test_use_command_cells_are_verbatim_code(site):
    t = _read(site, "use.html")
    for s in ("<code data-verbatim>build-store</code>", "<code data-verbatim>demo all | installer | release</code>",
              "<code data-verbatim>site [build | record]</code>"):
        assert s in t, s


def test_lower_flag_drives_every_label(tmp_path, monkeypatch):
    from patch_precedent.site import data as data_mod
    real = data_mod._metrics

    def flipped(arms):
        return tuple({**m, "lower": False} if m["key"] == "turns" else m for m in real(arms))

    monkeypatch.setattr(data_mod, "_metrics", flipped)
    build_site(pins.project_root(), tmp_path)
    t = (tmp_path / "results.html").read_text(encoding="utf-8")
    assert t.count("(lower is better)") == 8  # 11 minus the turns card, row and per-case group
    assert not re.search(r"Mean turns\s*<span class=\"lower\"", t)
    assert not re.search(r"Turns\s*<span class=\"lower\"", t)
    assert "Mean turns (lower is better)" not in (tmp_path / "home.html").read_text(encoding="utf-8")
