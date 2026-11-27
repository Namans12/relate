# Website and terminal UI design

Date: 2026-11-27. Status: draft for approval (builder check done).

## Intent

Patch Precedent is our entry for the Relate by Neo4j Hackathon. It checks a patch against the architecture decisions behind the code it touches and the tests that prove those decisions. The engine, the evaluation and the CLI are finished (Milestones 1-3, on `main`).

Judges will spend a few minutes with the entry. Right now the only way to see it is to clone the repo and read terminal output. This work gives them two things:

1. **A static website** that is the "link to a working demo" the rules accept. It shows the six patches, what the graph says about each one, what the replay observed, and the agent evaluation. It should be eye-catching, professional and easy to read, and every fact on it must come from the project's real data.
2. **A styled terminal experience**, so a judge who does clone and run `demo all` or `explain` sees clean, well-aligned, coloured output in the same palette.

The judging weights are Relate and connected context 30, functionality 25, usefulness 20, docs 15, creativity 10. The site should make the use of Relate visible (the graph, and the Cypher that produced each panel), and make the project easy to run.

## Goals

- One command, `uv run patch-precedent site`, builds the whole site from the committed graph store, a committed recorded demo run, and the published eval results. Nothing on the site is typed by hand except short editorial copy kept in one content file.
- The site is plain HTML, CSS and a little vanilla JS. It works on GitHub Pages under a project path (`https://namans12.github.io/relate/`), opened from a local folder, and with JavaScript off (minus animation).
- The look follows the approved mockups in `docs/superpowers/specs/2026-11-27-site-mockups/`. They are layout and style references only: their numbers and copy are hand-typed, and the welcome page still uses Fraunces.
- `demo all` and `explain` print styled output when writing to a terminal, and exactly today's output when piped or when `NO_COLOR` is set.

## Non-goals

- No server, no running patches in the browser, no live Relate queries in the browser.
- No React, Node or npm.
- No change to the engine, the graph schema, the evaluation or its numbers.
- No new scenarios or patches.

## Anti-goals (would make this a failure even if it works)

- A number, verdict, check or title on the site that disagrees with the CLI or `eval/results/20261127T040059Z/`.
- Filler copy: taglines, marketing phrases, text that repeats what the page already shows, or "hover over the logo" style hints.
- Any em dash (U+2014) or en dash (U+2013) in headings, titles, labels or prose on the site or in the styled terminal output. Use a normal hyphen. This includes text that comes from upstream, such as ADR titles. Exception, decided by the user: verbatim source text shown as code keeps its characters (see Text rule).
- Layout that breaks, overflows sideways or misaligns at any width from 320px to 1920px.
- Shipping GPL code (neo4j-viz) in the MIT site, or anything that suggests Neo4j or Relate endorse the project, or a modified Relate logo.
- A "Run the demo" button that pretends to run something live.
- Styled terminal output that changes what tests, scripts or the README excerpt see.

## Constraints

- Python 3.12, uv, `relate-db==1.1.0`. New dependencies: `jinja2` and `rich`, pinned with `==` like the existing ones.
- Licence: MIT. The site may ship only code under compatible licences: our own, Pixelcraft (see below), and the Uiverse button (MIT, credit comment kept verbatim).
- `runs/` is gitignored, so the site cannot read a live run on GitHub. It reads a committed recording (see "Recorded run").
- Feature freeze 4 Dec 2026; target finish 9 Dec; deadline 11 Dec 6:00 PM PST.
- GitHub Pages must be enabled by the repo owner (`Namans12`); we cannot do it.

## Approaches considered

| | What it is | Trade-offs |
|---|---|---|
| **A. Python static-site generator (chosen)** | A `site` subcommand renders Jinja2 templates plus vanilla JS from the store, a recorded run and the eval results | One toolchain; can't drift from data; nothing for judges to install. Less componentised than React; interactivity is hand-written (already prototyped); graph drawing is our own code |
| B. React and Vite in `web/` | A JS app reading a JSON export | Nicer components and hot reload. Second toolchain and CI; judges need npm or committed build output; a JSON contract to maintain; slower before the freeze; Neo4j's React graph package raises the same licence question |
| C. Hand-written static pages | HTML typed by hand | Fastest to start, but every number can drift from the data. Ruled out |

The user chose A. The graph is drawn as our own SVG instead of neo4j-viz, because neo4j-viz 1.14.0 is GPL-3.0-only, ships 2.5 MB and 4.5 MB JS bundles, and its colours and legend don't match the palette.

## Decided design

### Design system ("Paper & Ink")

Taken from `site.css` in the mockups folder, with one accessibility fix.

- Colours: bg `#FAF7F2`, surface `#FFFFFF`, sunk `#F3EEE4`, line `#E7E0D3`, line-2 `#D9D1C2`, ink `#1B1F2A`, ink-2 `#4A4F5C`, ink-3 `#686D79` (was `#7A7F8C`, which is about 3.7:1 on bg and fails WCAG AA for small text; `#686D79` is about 4.8:1), accent `#B4472A`, bright `#E36B47`, pass `#2F7D57` on `#E2F1E8`, fail `#B4472A` on `#FBE3DA`, none `#ECE7DC`.
- Fonts: Playfair Display for the title and all headings (the welcome mockup still uses Fraunces; switch it), Inter for body, JetBrains Mono for code. Loaded from Google Fonts.
- Spacing scale 4/8/12/16/24/32/48/72/104. Content width 1200px.
- Motion: scroll reveal via IntersectionObserver (fade and 12px rise). Every animation turns off under `prefers-reduced-motion`.
- Text rule (decided by the user):
  - **Hyphens everywhere except verbatim code.** No em or en dashes in headings, titles, labels or prose, including upstream ADR titles and scanned decision titles; the build replaces U+2013 and U+2014 with a hyphen in those.
  - **Verbatim stays verbatim.** These keep their characters exactly as in the source, so copied text matches upstream: diff lines, check names shown in code font, Cypher, and the recorded terminal transcript lines that echo upstream text.
  - **Enforced by a test.** Verbatim text is wrapped in elements marked `data-verbatim` (`pre`, `code`). The dash test strips those elements and then fails if either character remains in any built file.
  - **Our own CLI separators.** The "—" separators our own CLI prints are our text, not upstream's: styled mode prints hyphens instead. Plain mode is unchanged.

### Pages

All links are relative so the site works under `/relate/` and from a local folder.

1. **`index.html`, intro.** As `intro-v2.html`:
   - Pixelcraft `hover-drift` banner of the title lockup "Patch Precedent" in Playfair, layout C, drawn by `c-art.js`.
   - Fading polka dots, a fixed (non-magnetic) Uiverse "new-bird-34" Enter button recoloured to the palette, and a GitHub icon top right linking to `https://github.com/Namans12/relate`.
   - Enter, a click, or the Escape key fades into `home.html`.
   - `og:image` uses the absolute URL `https://namans12.github.io/relate/lockup.png`. This is the one non-relative URL, and it is allowlisted in the link test. *(Claude's call.)*
   - Below 600px wide, a **stacked lockup**: the mark above "Patch" and "Precedent" on two lines, so the title stays legible. This is a new `drawC` variant.
   - **No-JS and reduced-motion fallback:** a pre-rendered PNG of the lockup (`lockup.png`), also used as the Open Graph image.
2. **`home.html`, welcome.** As `welcome.html`:
   - Nav: mark, links, GitHub icon, and "Run the demo" with a play icon.
   - Hero: eyebrow "Built with Relate" (the only place that phrase appears), h1 "Every patch has a precedent.", the lede, the primary "Run the demo" button, "Explore the scenarios", and a copyable clone command.
   - The token-header evidence chain card.
   - "Three steps, one graph." (Cite / Replay / Explain).
   - "Six patches, two decisions.": a scroll-snap carousel with dots and arrow buttons, keyboard-operable.
   - "Agents with and without the graph.": the dark results panel with animated bars.
   - "Run it in a minute.": tabs plus a terminal.
   - Footer.
3. **`scenarios/<scenario>-<patch>.html` × 6:** `installer-release-lookup`, `installer-token-header`, `installer-wording`, `release-always-rotate`, `release-wording`, `release-docs-only`. The slug includes the scenario because `wording` exists in both. Each page follows `scenario.html`:
   - a sidebar of all six patches with pass/fail/none dots;
   - a header with 4 stat tiles;
   - a verdict callout;
   - a line-numbered diff;
   - a decision card with GitHub permalinks at the pinned upstream commit;
   - a checks table with the observed result per check;
   - the graph (see below);
   - a collapsed "also cites" list for scanned citations;
   - a collapsed "Query it yourself" block showing the Cypher used for this page's evidence. The query is shown with this patch's real values filled in as literals, so it runs as-is in `relate` or the MCP `read_cypher` tool. To read the query text from source, inline query strings in `store.py` and `replay.py` may move to module-level constants. That is a no-behaviour-change refactor and the only engine edit allowed; the existing tests must stay green. *(Claude's call.)*;
   - a copyable `explain` command;
   - prev/next pager.
   - **Empty states** *(Claude's call)*:
     - The callout's colour and wording come from the verdict in the recording ("violates ADR-NNNN", "consistent with ADR-NNNN", "no linked decision"), not from the content heading.
     - `release-docs-only` has no decision card. In its place is a card saying which file changed and that no decision cites it, plus the harness result ("6 of 6 checks passed"). Its graph shows only patch and file nodes, with a dashed "no linked decision" marker.
     - The two `wording` pages show a pass callout, and every check in the table reads "passed".
4. **`results.html`:** as the mockup: metric bar cards, the "Read these first" honesty box, the headline table and the per-case table (stacked full-width).
   - Numbers come from `eval/results/20261127T040059Z/results.json` and `scored.jsonl`. The per-case "Expected" verdict comes from `eval/cases.toml`.
   - The "Read these first" sentences live in `site/content.toml` as templates. Every number in them is a placeholder filled from computed data, for example `{replay_found_k}` of `{graph_runs}`. A placeholder with no computed value fails the build, so a sentence can't drift from the data. Disclosures that need a new figure (for example "3 of 18 graph runs altered the patch") get that figure computed from `scored.jsonl` in `data.py`. *(Claude's call.)*
5. **`use.html`:** as the mockup. Six numbered steps with copy buttons, plus a table of commands and exit codes.
6. **`relate.html`, "How it uses Relate".** A short page covering:
   - the graph schema (labels and relationships, drawn as an SVG);
   - the store's real node and relationship counts;
   - the main Cypher queries, copied from the source at build time;
   - the read-only MCP tool and `relate serve --mcp`;
   - which Relate capabilities are used: embedded store, Cypher, parameter binding, read-only opens, the relate CLI's MCP server.

   It doubles as the submission's capability statement. It names Relate only to identify the product and uses no Relate logo.

### Graph panel

Built in Python at build time, with no JS library:

- The subgraph for each patch is queried from `data/precedent.rl`: patch, then files, then decision, then checks and commit, plus scanned decisions.
- Observed results come from the recorded run.
- The layout is a fixed layered left-to-right arrangement (patch, file, decision, checks), computed in Python. It is deterministic, so builds are reproducible.
- It is rendered as inline SVG in palette colours, with failing checks in fail colour and passing checks in pass colour.
- Vanilla JS adds hover highlight and a tooltip with node properties. Without JS it still reads correctly.

### "Run the demo" on a static site

The panel lives in a `#demo` section on `home.html`. On every other page, the nav's "Run the demo" links to `home.html#demo`, which scrolls to the panel and starts it. *(Claude's call.)*

The play button opens the **recorded run** in an animated terminal panel:

- the real `demo all` output in the styled terminal format, replayed with its real relative timing compressed to a total of about 12 seconds;
- a skip-to-end control;
- a label: "Recorded run, <UTC date>, run <id>";
- the command to run it locally, with a copy button.

Nothing claims to be live. Without JS, the full transcript is shown as static text.

### Recorded run

A new subcommand records a demo run for the site:

```bash
uv run patch-precedent site record
```

- It runs `demo all` (a real run, about 45 s) with Rich forced to a 100-column styled terminal, and captures each output line with its elapsed time. Each line is stored as styled spans (text plus a palette style name) so the site renders it in HTML with the site's colours. This depends on the terminal UI work, so that comes first in the plan. *(Claude's call.)*
- It also stores the computed verdict per patch (violates / consistent / no decision, with the decision id), so pages never recompute it.
- It writes `recorded/demo-all.json`, committed. The file holds the run id, the upstream URL and SHA, the Relate version, per-scenario per-patch results (status, exit code, passed/failed/total, failing check numbers and names), the observed result per check, and the timed transcript lines.
- Absolute local paths are reduced to repo-relative ones, so no home directory reaches the public site.
- `site` reads only this file for run data. It never reads `runs/`.

### Editorial copy

Short human copy that the data can't provide lives in `site/content.toml`: each patch's one-line verdict heading (for example "Breaks the installer's no-token rule") and its one-paragraph summary, the hero lede, and the step descriptions. The build checks that every patch in the recording has an entry and that no copy contains a forbidden dash.

### Site build command

```bash
uv run patch-precedent site [--out _site]
```

- It writes the site to `_site/` (gitignored).
- It exits non-zero if the store, the recording, the eval results or any content entry is missing.
- It prints the output path and page count.

A GitHub Actions workflow (`.github/workflows/pages.yml`) runs it on push to `main` and deploys with the official Pages actions. It needs no upstream fetch and no demo run, so it runs on `ubuntu-latest` in well under a minute.

### Code layout

- `src/patch_precedent/site/`
  - `data.py`: gathers everything from the store, recording, eval results and content into plain dataclasses.
  - `graph.py`: subgraph query and layout to SVG.
  - `build.py`: renders templates and copies static files.
  - `record.py`: implements `site record`.
  - `templates/`: Jinja2 templates with shared macros for nav, footer, copy block, badge and stat tile.
  - `static/`: `site.css`, `site.js`, `c-art.js`, `lockup.png`, vendored `pixelcraft/`.
- `site/content.toml`, `recorded/demo-all.json`.
- `tests/test_site_*.py`.

### Pixelcraft

- Vendored into `static/pixelcraft/` from the already-patched copy in `docs/superpowers/specs/2026-11-27-site-mockups/pixelcraft/` (the original is `/Users/naman/Pixelcraft/web/component/`). The patch: the scatter "hole" colour and the poster background read `--pixelcraft-bg`, so the scatter blends with the page and there is no off-colour cursor blob.
- The bundled Hack4Hack artwork (`pixelcraft.jpg`) and its alt text are removed. The element must require a `src`.
- The original folder is untouched.
- Pixelcraft is the user's own code. The user confirmed it ships under this repo's MIT licence. NOTICE credits Pixelcraft and the Uiverse button.

### Terminal UI (`rich`)

As `terminal.html`:

- **When styling applies.** Styled output is used only when stdout is a TTY, `NO_COLOR` is unset, and `--plain` is not passed. Otherwise the output is byte-for-byte what it is today, so tests, scripts and the README excerpt are unaffected.
- **`demo all` / `demo <scenario>`:**
  - A header panel: tool name, command, upstream short SHA, Relate version, "read-only store".
  - Per scenario: the decision and check count, then one aligned row per run (pass/fail mark, label, passed, failed, exit code, duration, failing check numbers).
  - A "Verdicts" list.
  - A final line: runs matching expectations, overall exit code, total time, run directory.
  - The diffs and graph join tables print below the summary, in the same style. Styled mode reorders and styles; it doesn't hide information, except as noted under `explain`.
- **`explain`:**
  - Patch label and changed files, then per decision: id, title, status, rule, why, commit, and the checks table.
  - Then the "also cites" line.
  - GitHub permalinks print only with `--links`.
- **Colours** are the site palette mapped to a dark terminal, as in `terminal.html`. Output fits 80 columns, and long values wrap rather than break alignment.

### Tests (what "done" is checked by)

- **Build.** The site builds from a clean checkout into a temp dir, and every page listed above exists.
- **Dashes.** No U+2013 or U+2014 in any built file outside `data-verbatim` elements. An upstream ADR title containing an em dash comes out with a hyphen. The `always-rotate` diff and check #2's name keep theirs inside verbatim code.
- **Links.** Every relative `href` and `src` resolves to a built file. External links go only to the GitHub repo, the upstream repo at the pinned SHA, Google Fonts, and relate.devpost.com.
- **Data consistency:**
  - each patch page's status, exit code, counts and failing checks equal the recording;
  - results-page numbers equal `results.json`;
  - store counts on `relate.html` equal the store.
- **Licences.** No `neo4j`, `nvl` or GPL file in `_site/`. Pixelcraft contains no Hack4Hack strings.
- **Terminal.**
  - The plain-mode output of `demo` and `explain` is unchanged (existing tests stay green).
  - Styled mode is tested with Rich forced to a fixed-width terminal (snapshot of `explain` for one fixture), and contains no forbidden dashes.
- **Recording.** `site record` strips absolute paths (no `/Users/` in `recorded/demo-all.json`).

### Responsive and accessibility

- **Widths.** Checked at 320, 375, 768, 1024, 1440 and 1920. The sidebar becomes a horizontal chip row below 960px; nav links collapse to a menu button below 720px; the intro switches to the stacked lockup below 600px.
- **Keyboard.** All controls work by keyboard with a visible focus ring: carousel arrows, tabs, copy buttons, menu, terminal skip.
- **Copy buttons** announce "Copied" to screen readers.

## Left to the builder

- Exact Jinja template split and macro names.
- The graph's spacing constants and tooltip styling, within the palette.
- Pinned versions of `jinja2` and `rich` (current stable releases at build time).
- How `site record` captures timing, as long as the output is the real `demo all` output.
- The `lockup.png` rendering method, for example a one-off headless browser render committed as a file.
