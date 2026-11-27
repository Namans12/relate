import re
import xml.etree.ElementTree as ET

import pytest

from patch_precedent import pins
from patch_precedent.site.data import load_site_data
from patch_precedent.site.graph import patch_graph_svg, schema_svg

DATA = load_site_data(pins.project_root())


def _page(slug):
    return next(p for p in DATA.patches if p.slug.endswith(slug))


def test_token_header_graph_nodes_and_classes():
    page = _page("token-header")
    svg = patch_graph_svg(page)
    assert svg.count('class="node n-check') == 3
    assert svg.count("n-check-fail") == 1 and "#64" in svg
    assert 'class="node n-decision' in svg and "ADR-0585" in svg
    assert svg.count("n-scanned") == len(page.also_cites)
    assert 'role="img"' in svg and 'width="100%"' in svg and "<script" not in svg


def test_docs_only_graph_has_none_marker():
    svg = patch_graph_svg(_page("docs-only"))
    assert "n-none" in svg and "n-decision" not in svg and "no linked decision" in svg


def test_graph_is_deterministic():
    assert patch_graph_svg(_page("installer-wording")) == patch_graph_svg(_page("installer-wording"))


def test_graph_is_wellformed_xml_and_edges_match_nodes():
    for p in DATA.patches:
        root = ET.fromstring(patch_graph_svg(p))
        ids = {g.get("data-id") for g in root.iter("{http://www.w3.org/2000/svg}g")}
        for e in root.iter("{http://www.w3.org/2000/svg}path"):
            assert e.get("data-from") in ids and e.get("data-to") in ids


def test_schema_svg_counts():
    svg = schema_svg(DATA.store)
    ET.fromstring(svg)
    for label in ("File", "Decision", "Check", "Commit", "Patch", "Run", "Observation"):
        assert label in svg
    assert f">{DATA.store.by_label['Decision']}<" in svg and f">{DATA.store.by_label['File']}<" in svg


def test_no_forbidden_dashes_outside_verbatim():
    for p in DATA.patches:
        root = ET.fromstring(patch_graph_svg(p))
        for g in root.iter("{http://www.w3.org/2000/svg}g"):
            if g.get("data-verbatim") is not None:
                continue
            text = "".join(g.itertext())
            assert not re.search("[–—]", text), text


def test_schema_replay_only_labels_are_marked_not_zero():
    root = ET.fromstring(schema_svg(DATA.store))
    ns = "{http://www.w3.org/2000/svg}"
    for g in root.iter(ns + "g"):
        text = "".join(t.text or "" for t in g.iter(ns + "text"))
        title = g.find(ns + "title").text
        if g.get("data-id") in ("Run", "Patch", "Observation"):
            assert "n-replay" in g.get("class") and "per demo run" in text and "0" not in text.split()
            assert "replay copy" in title
        else:
            assert "n-replay" not in g.get("class")


def test_commit_uses_eight_hex_chars():
    page = _page("token-header")
    assert page.decisions[0].commit_sha[:8] in patch_graph_svg(page)


def test_multi_file_patch_edges():
    import dataclasses
    page = _page("token-header")
    f0 = page.diff[0]
    two = dataclasses.replace(page, diff=(f0, dataclasses.replace(f0, path="other/thing.py")))
    root = ET.fromstring(patch_graph_svg(two))
    edges = [(e.get("data-from"), e.get("data-to")) for e in root.iter("{http://www.w3.org/2000/svg}path")]
    assert ("file:distribution/install.sh", "dec:ADR-0585") in edges
    assert ("file:other/thing.py", "dec:ADR-0585") not in edges
    scanned = [f for f, t in edges if t.startswith("scan:")]
    assert scanned and set(scanned) == {"patch"}
    one = ET.fromstring(patch_graph_svg(page))
    assert {e.get("data-from") for e in one.iter("{http://www.w3.org/2000/svg}path")
            if e.get("data-to", "").startswith("scan:")} == {"file:distribution/install.sh"}
