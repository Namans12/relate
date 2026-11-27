import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.cli import main
from patch_precedent.site import build as build_mod
from patch_precedent.site.build import build_site
from patch_precedent.site.data import SiteDataError

SLUGS = ["installer-release-lookup", "installer-token-header", "installer-wording",
         "release-always-rotate", "release-wording", "release-docs-only"]
PAGES = ["index.html", "home.html", "results.html", "use.html", "relate.html"] + [
    f"scenarios/{s}.html" for s in SLUGS]
ALLOWED = ("https://github.com/Namans12/relate", "https://github.com/relatedb/relate/",
           "https://fonts.googleapis.com", "https://fonts.gstatic.com", "https://relate.devpost.com")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    build_site(pins.project_root(), out)
    return out


def _htmls(site: Path):
    return sorted(site.rglob("*.html"))


class _Scan(HTMLParser):
    """Collects urls, ids and text outside data-verbatim, script and style elements."""

    VOID = {"meta", "link", "img", "br", "hr", "input", "path", "circle", "rect"}

    def __init__(self):
        super().__init__()
        self.urls, self.ids, self.text, self.stack = [], set(), [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k) is not None:
                self.urls.append(a[k])
        if a.get("id"):
            self.ids.add(a["id"])
        if tag not in self.VOID:
            self.stack.append((tag, "data-verbatim" in a or tag in ("script", "style")))

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k) is not None:
                self.urls.append(a[k])
        if a.get("id"):
            self.ids.add(a["id"])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not any(skip for _, skip in self.stack):
            self.text.append(data)


def _scan(path: Path) -> _Scan:
    s = _Scan()
    s.feed(path.read_text(encoding="utf-8"))
    return s


def test_og_image_only_with_base_url(tmp_path):
    root = pins.project_root()
    build_site(root, tmp_path / "a")
    assert "og:image" not in (tmp_path / "a" / "index.html").read_text()
    build_site(root, tmp_path / "b", base_url="https://x.example/")
    t = (tmp_path / "b" / "index.html").read_text()
    assert 'content="https://x.example/lockup.png"' in t and 'content="https://x.example/"' in t
    assert 'property="og:title"' in t and 'property="og:description"' in t


@pytest.mark.parametrize("page", PAGES)
def test_page_exists(site, page):
    assert (site / page).is_file()


def test_intro_assets_written(site):
    for f in ("lockup.png", ".nojekyll", "assets/site.css", "assets/site.js", "assets/intro.js",
              "assets/c-art.js", "assets/pixelcraft/pixelcraft-banner.js"):
        assert (site / f).is_file(), f


def test_relative_links_resolve(site):
    for page in _htmls(site):
        sc = _scan(page)
        here = page.parent
        for url in sc.urls:
            if re.match(r"^[a-z][a-z0-9+.-]*:", url) or url.startswith("//"):
                continue
            path, _, frag = url.partition("#")
            if not path:
                assert frag == "" or frag in sc.ids, (page.name, url)
                continue
            target = (here / path.split("?")[0]).resolve()
            assert target.exists(), (page.name, url)
            if frag and target.suffix == ".html":
                assert frag in _scan(target).ids, (page.name, url)


def test_external_links_allowlisted(site):
    for page in _htmls(site):
        for url in _scan(page).urls:
            if re.match(r"^https?://", url):
                assert url.startswith(ALLOWED), (page.name, url)


def test_no_forbidden_dashes_outside_verbatim(site):
    for page in _htmls(site):
        text = "".join(_scan(page).text)
        assert "–" not in text and "—" not in text, page.name
    for f in (site / "assets").rglob("*"):
        if f.suffix in {".css", ".js", ".svg"}:
            body = f.read_text(encoding="utf-8")
            assert "–" not in body and "—" not in body, f.name


def test_no_gpl_or_hack4hack(site):
    blob = "".join(p.read_text(errors="ignore") for p in site.rglob("*")
                   if p.suffix in {".html", ".js", ".css"})
    for bad in ("neo4j-viz", "nvl", "Hack4Hack", "pixelcraft.jpg"):
        assert bad not in blob
    assert not (site / "assets/pixelcraft/pixelcraft.jpg").exists()


def test_pixelcraft_renders_nothing_without_src(site):
    js = (site / "assets/pixelcraft/pixelcraft-banner.js").read_text()
    assert "if (!src) return;" in js


def test_uiverse_credit_kept(site):
    assert ("From Uiverse.io by adamgiebl - https://uiverse.io/adamgiebl/new-bird-34"
            in (site / "index.html").read_text())


def test_built_with_relate_once(site):
    assert sum(p.read_text().count("Built with Relate") for p in site.rglob("*.html")) <= 1


def test_built_with_relate_exactly_once(site):
    assert (site / "home.html").read_text().count("Built with Relate") == 1


def test_no_local_paths(site):
    assert all("/Users/" not in p.read_text(errors="ignore")
               for p in site.rglob("*") if p.is_file() and p.suffix != ".png")


def test_noscript_fallback(site):
    t = (site / "index.html").read_text()
    assert "<noscript>" in t and 'src="lockup.png"' in t and 'href="home.html"' in t


def test_intro_wiring(site):
    js = (site / "assets/intro.js").read_text()
    assert "drawCStacked" in js and "prefers-reduced-motion" in js and "home.html" in js
    assert "450" in js and "Escape" in js


def test_reveal_hidden_only_with_js(site):
    css = (site / "assets/site.css").read_text()
    assert ".js .reveal" in css
    assert not re.search(r"(^|[}\s])\.reveal\s*\{[^}]*opacity:\s*0", css)
    assert "#686D79" in css


def test_shared_layout(site):
    t = (site / "index.html").read_text()
    assert "no-js" in t
    # nav and footer live in base.html.j2; check through the template source
    base = (Path(build_site.__code__.co_filename).parent / "templates" / "base.html.j2").read_text()
    for needle in ("Relate is a product of Neo4j. Not affiliated.", 'aria-live="polite"',
                   'id="sr-status"', "Run the demo", "menu-btn", "Patch Precedent · MIT"):
        assert needle in base, needle


def test_copy_announces(site):
    assert 'aria-live="polite"' in (site / "home.html").read_text()


def test_missing_required_template_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(build_mod, "REQUIRED", ("intro.html.j2", "nope.html.j2"))
    with pytest.raises(SiteDataError, match="nope.html.j2"):
        build_site(pins.project_root(), tmp_path / "s")


def test_no_fraunces_and_visible_focus(site):
    for f in site.rglob("*"):
        if f.suffix in {".html", ".js", ".css"}:
            body = f.read_text(errors="ignore")
            assert "Fraunces" not in body and "F2C9B9" not in body, f.name


def test_cli_site_build(tmp_path, capsys):
    assert main(["site", "--out", str(tmp_path / "s")]) == 0
    assert "pages to" in capsys.readouterr().out


def test_cli_rejects_non_https_base_url(tmp_path):
    assert main(["site", "--out", str(tmp_path / "s"), "--base-url", "http://x.example"]) == 2


def test_cli_site_missing_recording_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("patch_precedent.cli.project_root", lambda: tmp_path)
    assert main(["site", "--out", str(tmp_path / "s")]) == 2
    assert "missing input file" in capsys.readouterr().err


def test_vercel_json_copied_into_output(tmp_path):
    root = pins.project_root()
    build_site(root, tmp_path)
    assert (tmp_path / "vercel.json").read_text() == (root / "vercel.json").read_text()
