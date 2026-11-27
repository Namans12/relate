import html, os, sys
d = sys.argv[1]
MARK = '<svg width="28" height="28" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="15" fill="#1B1F2A"/><g stroke="#FAF7F2" stroke-width="3.2" stroke-linecap="round"><path d="M27.5 28.5L17 18M38.5 28.5L48 18M27.5 39.5L17 49"/></g><path d="M38.8 39.8L46 47" stroke="#E36B47" stroke-width="3.2" stroke-linecap="round"/><rect x="11" y="11" width="13" height="15" rx="2.6" fill="#FAF7F2"/><circle cx="33" cy="34" r="8.5" fill="#1B1F2A" stroke="#E36B47" stroke-width="4.5"/><circle cx="48" cy="18" r="4.6" fill="#FAF7F2"/><circle cx="17" cy="49" r="4.6" fill="#FAF7F2"/><circle cx="48" cy="49" r="5.4" fill="#E36B47"/></svg>'
GH = '<svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
PLAY = '<svg width="11" height="11" viewBox="0 0 12 12" aria-hidden="true"><path d="M3 1.6v8.8a.6.6 0 00.9.52l7-4.4a.6.6 0 000-1.04l-7-4.4A.6.6 0 003 1.6z" fill="currentColor"/></svg>'
def nav(active):
    items=[("Overview","welcome.html"),("Scenarios","scenario.html"),("Results","results.html"),("Use it","use.html")]
    links="".join(f'<a href="{h}"{" class=\"on\"" if n==active else ""}>{n}</a>' for n,h in items)
    return f'''<header class="nav"><div class="wrap"><a class="brand" href="intro-v2.html">{MARK}Patch Precedent</a><nav class="links">{links}</nav><div class="nav-cta"><a class="icon-btn gh" href="https://github.com/Namans12/relate" target="_blank" rel="noopener" aria-label="GitHub repository">{GH}</a><a class="btn btn-primary" href="use.html"><span class="play-dot">{PLAY}</span>Run the demo</a><button class="icon-btn menu-btn" aria-label="Menu">≡</button></div></div></header>'''
HEAD = lambda title: f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"><link rel="stylesheet" href="site.css"></head><body>'''
REVEAL = '<script>const io=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting){e.target.classList.add("in");io.unobserve(e.target)}}),{threshold:.08});document.querySelectorAll(".reveal").forEach(el=>io.observe(el));document.querySelectorAll(".copy").forEach(b=>b.addEventListener("click",()=>{const t=b.closest(".code").querySelector("pre").innerText.replace(/^\\$ /gm,"");navigator.clipboard&&navigator.clipboard.writeText(t);b.textContent="COPIED";setTimeout(()=>b.textContent="COPY",1400)}))</script>'

# diff rendering
patch=open(os.path.join(d,"token-header.patch")).read().splitlines()
rows=[]; old=new=0
for line in patch:
    if line.startswith(("diff --git","index ","--- ","+++ ")): continue
    if line.startswith("@@"):
        import re; m=re.match(r"@@ -(\d+),?\d* \+(\d+)",line); old=int(m.group(1)); new=int(m.group(2))
        rows.append(f'<div class="ln hunk"><span class="n"></span><span></span><span>{html.escape(line)}</span></div>'); continue
    sign=line[:1]; body=html.escape(line[1:]).replace("\t","    ")
    if sign=="+": rows.append(f'<div class="ln add"><span class="n">{new}</span><span class="s">+</span><span>{body}</span></div>'); new+=1
    elif sign=="-": rows.append(f'<div class="ln del"><span class="n">{old}</span><span class="s">-</span><span>{body}</span></div>'); old+=1
    else: rows.append(f'<div class="ln"><span class="n">{new}</span><span></span><span>{body}</span></div>'); old+=1; new+=1
diff="".join(rows)

B="https://github.com/relatedb/relate/blob/5f7a510713c3feac146133e77d8c5bb72bae1b11/"
side=f'''<aside class="side">
<div class="group"><div class="gtitle">Installer <span>ADR-0585</span></div>
<a class="item" href="#"><span>release-lookup</span><i class="dot d-fail"></i></a>
<a class="item on" href="#"><span>token-header</span><i class="dot d-fail"></i></a>
<a class="item" href="#"><span>wording</span><i class="dot d-pass"></i></a></div>
<div class="group"><div class="gtitle">Release <span>ADR-0580</span></div>
<a class="item" href="#"><span>always-rotate</span><i class="dot d-fail"></i></a>
<a class="item" href="#"><span>wording</span><i class="dot d-pass"></i></a>
<a class="item" href="#"><span>docs-only</span><i class="dot d-none"></i></a></div>
</aside>'''
also=[("ADR-0115","Sign release checksums with SSHSIG for offline install and upgrade verification","Accepted"),("ADR-0250","Release discovery from a static releases.json on the website","Accepted"),("ADR-0431","Extension distribution - the first-party channel, the install verbs, and trust tiers","Proposed"),("ADR-0457","The signed release manifest carries the release version","Proposed"),("ADR-0586","Windows installs through a PowerShell installer","Proposed")]
also_html="".join(f'<li style="display:flex;gap:12px;align-items:baseline;padding:8px 0;border-top:1px solid var(--line)"><span class="mono" style="font-size:13px;min-width:78px">{a}</span><span style="flex:1">{t}</span><span class="pill">{s}</span></li>' for a,t,s in also)
page=HEAD("token-header - Patch Precedent")+nav("Scenarios")+f'''
<div class="wrap layout">{side}
<main class="stack">
  <div class="reveal">
    <div class="eyebrow">Installer · ADR-0585</div>
    <div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:10px 0 8px"><h1 class="mono" style="font-family:'Playfair Display'">token-header</h1><span class="badge b-fail">violates ADR-0585</span></div>
    <p class="muted" style="max-width:62ch">Sends GITHUB_TOKEN as an Authorization header, for the authenticated rate limit.</p>
  </div>
  <div class="stats reveal">
    <div class="stat"><small>Harness</small><b>193 / 1</b></div>
    <div class="stat"><small>Exit code</small><b>1</b></div>
    <div class="stat"><small>Linked checks</small><b>3</b></div>
    <div class="stat"><small>Failing</small><b class="mono" style="font:600 18px 'JetBrains Mono';color:var(--fail)">#64</b></div>
  </div>
  <div class="verdict reveal"><div class="ico">!</div><div><h3>Breaks the installer's no-token rule</h3><p class="muted">ADR-0585: install.sh consults no GitHub API endpoint and does not read GITHUB_TOKEN. Check #64 caught it: an install with GITHUB_TOKEN set sent an Authorization header.</p></div></div>
  <div class="code reveal"><div class="code-bar"><span>distribution/install.sh</span><span>+5 -0</span></div><pre>{diff}</pre></div>
  <div class="card reveal">
    <div class="card-head"><span class="label">Decision</span><span class="pill">Proposed</span></div>
    <h3>ADR-0585 · The installer downloads release assets over the direct route</h3>
    <p class="muted" style="margin-top:10px">Anonymous GitHub API requests are limited to 60 per hour per IP address, and users behind shared egress (VPNs, corporate NAT, Cloudflare WARP) exhausted that quota, so the one-line installer broke.</p>
    <div class="links-row"><a class="lnk" href="{B}docs/adr/0585-installer-downloads-via-direct-route.md#L8-L38">Decision</a><a class="lnk" href="{B}docs/adr/0585-installer-downloads-via-direct-route.md#L89-L97">Scope</a><a class="lnk" href="{B}distribution/install.sh#L120-L128">Citation in install.sh</a><a class="lnk" href="https://github.com/relatedb/relate/commit/5ac38808547d11f55b02333624cc3e88b46566eb">Commit 5ac38808</a></div>
  </div>
  <div class="card reveal">
    <div class="card-head"><span class="label">Checks guarding this decision</span><span class="muted" style="font-size:13px">observed in the replay</span></div>
    <table class="t"><thead><tr><th>Check</th><th class="hide-sm">Kind</th><th>What it asserts</th><th>Result</th></tr></thead><tbody>
      <tr><td class="k">#7</td><td class="hide-sm"><span class="pill">static</span></td><td>No GitHub API endpoint in install.sh</td><td><span class="badge b-pass">ok</span></td></tr>
      <tr><td class="k">#64</td><td class="hide-sm"><span class="pill">runtime</span></td><td>No Authorization header when GITHUB_TOKEN is set</td><td><span class="badge b-fail">not ok</span></td></tr>
      <tr><td class="k">#193</td><td class="hide-sm"><span class="pill">runtime</span></td><td>No case made a GitHub API request</td><td><span class="badge b-pass">ok</span></td></tr>
    </tbody></table>
  </div>
  <div class="card reveal">
    <div class="card-head"><span class="label">Graph</span><div class="legend"><span><i style="background:#1B1F2A"></i>patch</span><span><i style="background:#E36B47"></i>decision</span><span><i style="background:#D8CFBF"></i>check</span><span><i style="background:#2F7D57"></i>ok</span><span><i style="background:#B4472A"></i>not ok</span></div></div>
    <div class="graph"><iframe src="graph-token-header.html" title="Relate graph for token-header"></iframe></div>
  </div>
  <details class="card more reveal"><summary>Also cited by install.sh <span class="muted" style="font-weight:500;font-size:13px;margin-left:auto;margin-right:12px">5 ADRs, scanned from source, not reviewed</span></summary><ul style="list-style:none;margin-top:12px;font-size:14px">{also_html}</ul></details>
  <div class="code cmd reveal"><div class="code-bar"><span>Inspect it yourself</span><button class="copy">COPY</button></div><pre><span class="p">$</span> uv run patch-precedent explain fixtures/installer/token-header.patch</pre></div>
  <div class="pager reveal"><a href="#"><small>Previous</small><b>release-lookup</b></a><a href="#" style="text-align:right"><small>Next</small><b>wording</b></a></div>
</main></div>'''+REVEAL+'</body></html>'
open(os.path.join(d,"scenario.html"),"w").write(page)
print("written")
