"""Render the static website into a directory of plain files."""
from __future__ import annotations

import posixpath
import shutil
from pathlib import Path

import jinja2

from .data import SiteData, SiteDataError, load_site_data, prose

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"
REQUIRED = ("intro.html.j2", "home.html.j2", "results.html.j2", "use.html.j2", "relate.html.j2",
            "scenario.html.j2")


def _rel(ctx: jinja2.runtime.Context, target: str) -> str:
    """Relative URL from the page being rendered to a site path (an optional #fragment is kept)."""
    page = ctx["page"]
    path, sep, frag = target.partition("#")
    start = posixpath.dirname(page) or "."
    if not path:
        url = ""
    else:
        url = posixpath.relpath(path, start)
        if path.endswith("/") and not url.endswith("/"):
            url += "/"
    return url + sep + frag if (url or frag) else "./"


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True,
        undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        keep_trailing_newline=True)
    env.filters["prose"] = prose
    env.filters["rel"] = jinja2.pass_context(_rel)
    return env


def _pages(data: SiteData, available: set[str]) -> list[tuple[str, str, dict]]:
    """(output path, template, extra context) for every page whose template exists."""
    # a missing required template is an error unless allow_missing (see build_site)
    pages: list[tuple[str, str, dict]] = [("index.html", "intro.html.j2", {})]
    for out, tpl in (("home.html", "home.html.j2"), ("results.html", "results.html.j2"),
                     ("use.html", "use.html.j2"), ("relate.html", "relate.html.j2")):
        pages.append((out, tpl, {}))
    for p in data.patches:
        pages.append((f"scenarios/{p.slug}.html", "scenario.html.j2", {"patch": p}))
    return [pg for pg in pages if pg[1] in available]


def build_site(root: Path, out: Path, base_url: str | None = None,
               allow_missing: bool = False) -> list[Path]:
    root, out = Path(root), Path(out)
    if base_url is not None:
        base_url = base_url.rstrip("/")
    data = load_site_data(root)
    env = _env()
    available = {p.name for p in TEMPLATES.glob("*.j2")}
    missing = [t for t in REQUIRED if t not in available]
    if missing and not allow_missing:
        raise SiteDataError(f"missing template: {missing[0]}")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(STATIC, out / "assets")
    lockup = STATIC / "lockup.png"
    if lockup.is_file():
        shutil.copy2(lockup, out / "lockup.png")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    home = data.content["home"]
    written: list[Path] = []
    for page, tpl, extra in _pages(data, available):
        html = env.get_template(tpl).render(
            page=page, data=data, c=data.content, base_url=base_url,
            og_description=home["lede"], **extra)
        dest = out / page
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        written.append(dest)
    return written
