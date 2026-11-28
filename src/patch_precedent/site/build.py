"""Render the static website into a directory of plain files."""
from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path

import jinja2
import markupsafe

from .. import evidence as _evidence, replay as _replay, store as _store
from .graph import patch_graph_svg, schema_svg
from .data import RESULTS_DIR, SiteData, SiteDataError, load_site_data, prose

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
STATIC = HERE / "static"
REQUIRED = ("intro.html.j2", "home.html.j2", "results.html.j2", "use.html.j2", "relate.html.j2",
            "scenario.html.j2", "404.html.j2")


def _rel(ctx: jinja2.runtime.Context, target: str) -> str:
    """Relative URL from the page being rendered to a site path (an optional #fragment is kept)."""
    page = ctx["page"]
    if ctx.get("absolute_links"):
        # The 404 page is served at whatever path was missed, so relative links would break.
        return "/" + target.lstrip("/")
    path, sep, frag = target.partition("#")
    start = posixpath.dirname(page) or "."
    if not path:
        url = ""
    else:
        url = posixpath.relpath(path, start)
        if path.endswith("/") and not url.endswith("/"):
            url += "/"
    return url + sep + frag if (url or frag) else "./"


def _text(value: str) -> markupsafe.Markup:
    """Escape for element content only (& < >), so quotes in verbatim code stay literal."""
    return markupsafe.Markup(str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _cited_file(url: str) -> str:
    """Repo path a citation URL points at: the part after /blob/<sha>/, before #L."""
    m = re.search(r"/blob/[0-9a-f]{7,40}/([^#]+)", url)
    return m.group(1) if m else url


def _code(value: str) -> markupsafe.Markup:
    """Escape text, turning `backtick` spans into <code> elements."""
    parts = str(markupsafe.escape(value)).split("`")
    out = "".join(f"<code>{x}</code>" if i % 2 else x for i, x in enumerate(parts))
    return markupsafe.Markup(out)


def _relate_queries() -> dict[str, str]:
    return {"evidence": _store._EVIDENCE_QUERY, "cited": _store._CITED_QUERY,
            "join": _replay.JOIN_QUERY, "observed": _evidence._OBSERVED_QUERY}


def _env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True,
        undefined=jinja2.StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        keep_trailing_newline=True)
    env.filters["prose"] = prose
    env.filters["text"] = _text
    env.filters["cited_file"] = _cited_file
    env.filters["code"] = _code
    env.globals["results_dir"] = RESULTS_DIR
    env.globals["graph_svg"] = patch_graph_svg
    env.globals["schema_svg"] = schema_svg
    env.globals["relate_queries"] = _relate_queries()
    env.filters["rel"] = jinja2.pass_context(_rel)
    return env


MARKER = ".patch-precedent-site"


def _pages(data: SiteData) -> list[tuple[str, str, dict]]:
    """(output path, template, extra context) for every page."""
    pages: list[tuple[str, str, dict]] = [("index.html", "intro.html.j2", {})]
    for out, tpl in (("home.html", "home.html.j2"), ("results.html", "results.html.j2"),
                     ("use.html", "use.html.j2"), ("relate.html", "relate.html.j2")):
        pages.append((out, tpl, {}))
    for p in data.patches:
        pages.append((f"scenarios/{p.slug}.html", "scenario.html.j2", {"patch": p}))
    # Vercel serves /404.html for any missing path.
    pages.append(("404.html", "404.html.j2", {"absolute_links": True}))
    return pages


def _prepare_out(root: Path, out: Path) -> None:
    """Create a clean output directory, replacing only an empty dir or a previous build."""
    resolved, project = out.resolve(), root.resolve()
    if resolved == project or resolved in project.parents:
        raise SiteDataError(f"refusing to build into {out}: it is the project root or one of its parents")
    if out.exists() or out.is_symlink():
        if not out.is_dir() or out.is_symlink():
            raise SiteDataError(f"refusing to replace {out}: it is not a directory")
        if any(out.iterdir()):
            if not (out / MARKER).is_file():
                raise SiteDataError(
                    f"refusing to replace {out}: it is not empty and was not made by `site build` "
                    f"(no {MARKER} file); choose an empty or new directory")
            shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)


def build_site(root: Path, out: Path, base_url: str | None = None) -> list[Path]:
    root, out = Path(root), Path(out)
    if base_url is not None:
        base_url = base_url.rstrip("/")
    data = load_site_data(root)
    env = _env()
    available = {p.name for p in TEMPLATES.glob("*.j2")}
    missing = [t for t in REQUIRED if t not in available]
    if missing:
        raise SiteDataError(f"missing template: {missing[0]}")

    _prepare_out(root, out)
    (out / MARKER).write_text("Built by `patch-precedent site`; safe to replace.\n", encoding="utf-8")
    shutil.copytree(STATIC, out / "assets")
    lockup = STATIC / "lockup.png"
    if lockup.is_file():
        shutil.copy2(lockup, out / "lockup.png")
    # Vercel reads vercel.json from the deployed folder, not the repo root.
    vercel = root / "vercel.json"
    if vercel.is_file():
        shutil.copy2(vercel, out / "vercel.json")

    home = data.content["home"]
    written: list[Path] = []
    for page, tpl, extra in _pages(data):
        html = env.get_template(tpl).render(
            page=page, data=data, c=data.content, base_url=base_url,
            og_description=home["lede"], **extra)
        dest = out / page
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        written.append(dest)
    return written
