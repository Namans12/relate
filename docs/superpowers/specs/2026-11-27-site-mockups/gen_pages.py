import os, sys, html
sys.argv=[sys.argv[0], sys.argv[1]]
from gen_scenario import HEAD, nav, REVEAL
d=sys.argv[1]
def bars(label,b,g,bw,gw):
    return f'''<div class="card reveal"><div class="label" style="font:600 12px Inter;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">{label}</div>
<div style="display:grid;grid-template-columns:70px 1fr 56px;align-items:center;gap:10px;margin-top:14px;font-size:13px"><span class="muted">baseline</span><div style="height:8px;border-radius:4px;background:var(--sunk)"><div style="height:100%;width:{bw}%;border-radius:4px;background:#8C8577"></div></div><b class="mono" style="font:500 13px 'JetBrains Mono';text-align:right">{b}</b>
<span class="muted">graph</span><div style="height:8px;border-radius:4px;background:var(--sunk)"><div style="height:100%;width:{gw}%;border-radius:4px;background:var(--bright)"></div></div><b class="mono" style="font:500 13px 'JetBrains Mono';text-align:right">{g}</b></div></div>'''
head_rows=[("Verdict correct","16/18","18/18"),("Decisions exact","13/18","18/18"),("Decision recall (mean)","87%","100%"),("Checks recall (all linked checks)","37%","91%"),("Catching-checks recall","100%","100%"),("Graph tool returned observed results","n/a","15/18"),("Outcomes marked (of linked checks)","4/39","30/39"),("Unsupported claims","4","0"),("Outcome accuracy (marked checks)","100% (4/4)","100% (30/30)"),("Median time to first correct citation","12.4 s","7.5 s"),("Mean turns","6.2","2.1"),("Total cost","$0.73","$0.38")]
trs="".join(f'<tr><td>{m}</td><td class="k">{b}</td><td class="k" style="color:var(--ink)">{g}</td></tr>' for m,b,g in head_rows)
cases=[("C1","installer · release-lookup","violates","3/3","3/3","8.7","2.0"),("C2","installer · wording","consistent","2/3","3/3","9.7","2.3"),("C3","installer · token-header","violates","3/3","3/3","4.7","2.0"),("C4","release · always-rotate","violates","3/3","3/3","4.7","2.0"),("C5","release · wording","consistent","3/3","3/3","4.3","2.0"),("C6","release · docs-only","no decision","2/3","3/3","5.3","2.0")]
def vb(x): return f'<span class="badge {"b-pass" if x=="3/3" else "b-fail"}">{x}</span>'
crows="".join(f'<tr><td class="k">{c}</td><td><b style="font-weight:600">{n.split(' · ')[1]}</b><br><small class="muted">{n.split(' · ')[0]}</small></td><td class="hide-sm"><span class="pill">{v}</span></td><td>{vb(b)}</td><td>{vb(g)}</td><td class="k hide-sm">{tb} / {tg}</td></tr>' for c,n,v,b,g,tb,tg in cases)
results=HEAD("Results - Patch Precedent")+nav("Results")+f'''
<main class="wrap" style="padding-top:48px;padding-bottom:72px">
 <div class="reveal" style="max-width:720px"><div class="eyebrow">Measured</div><h1 style="margin:10px 0 12px">Agents with and without the graph.</h1>
 <p class="muted">Claude Sonnet reviewed each of 6 patches 3 times per arm. Same prompt, tools and turn budget; the graph arm adds one read-only MCP tool.</p></div>
 <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:32px" class="mgrid">
  {bars("Verdict correct","16/18","18/18",89,100)}{bars("Mean turns","6.2","2.1",100,34)}{bars("Unsupported test claims","4","0",100,0)}{bars("Cost","$0.73","$0.38",100,52)}
 </div>
 <div class="reveal" style="display:flex;gap:16px;align-items:flex-start;background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--bright);border-radius:var(--r);padding:20px 24px;margin-top:24px">
  <div><h3 style="margin-bottom:6px">Read these first</h3><ul class="muted" style="padding-left:18px;display:grid;gap:4px;font-size:14.5px">
   <li>Both arms found every check that fails (100%). The checks-recall gap comes from passing checks.</li>
   <li>The baseline cannot observe test results, so its test claims are unsupported by construction.</li>
   <li>In 3 of 18 graph runs the agent altered the patch when passing it to the tool, so no evidence came back.</li>
   <li>The prompt does not define "consistent" versus "no decision"; both baseline verdict misses sit on that line.</li></ul></div></div>
 <div style="display:grid;grid-template-columns:1fr;gap:24px;margin-top:24px" class="twocol">
  <div class="card reveal"><div class="card-head"><span class="label">Headline</span></div><table class="t"><thead><tr><th>Metric</th><th>Baseline</th><th>Graph</th></tr></thead><tbody>{trs}</tbody></table></div>
  <div class="card reveal"><div class="card-head"><span class="label">Per case, verdict correct</span></div><table class="t"><thead><tr><th>Case</th><th>Patch</th><th class="hide-sm">Expected</th><th>Base</th><th>Graph</th><th class="hide-sm">Turns</th></tr></thead><tbody>{crows}</tbody></table>
  <div class="links-row"><a class="lnk" href="#">All 36 runs and the method</a><a class="lnk" href="#">Agent transcripts</a></div></div>
 </div>
</main>
<style>@media (max-width:960px){{.mgrid{{grid-template-columns:repeat(2,minmax(0,1fr))!important}}.twocol{{grid-template-columns:1fr!important}}}}</style>'''+REVEAL+'</body></html>'
open(os.path.join(d,"results.html"),"w").write(results)

def code(title,lines,out=""):
    body="\n".join(f'<span class="p">$</span> {html.escape(l)}' for l in lines)
    if out: body+="\n\n"+out
    return f'<div class="code cmd"><div class="code-bar"><span>{title}</span><button class="copy">COPY</button></div><pre>{body}</pre></div>'
mcpjson=html.escape('{\n  "mcpServers": {\n    "precedent": {\n      "command": "uv",\n      "args": ["run", "--project", "<path-to-relate-clone>",\n               "--quiet", "patch-precedent", "mcp"]\n    }\n  }\n}')
steps=[
 ("1","Clone",code("terminal",["git clone https://github.com/Namans12/relate.git","cd relate"]),"macOS with git and uv. The first run also downloads Relate's source once."),
 ("2","Run the demo",code("terminal",["uv run patch-precedent demo all"],'<span style="color:#8C8577">scenario   runs  matched  exit</span>\ninstaller  4     <span style="color:#8FD0A8">4/4</span>      0\nrelease    4     <span style="color:#8FD0A8">4/4</span>      0'),"Replays every patch against the real upstream tests and explains the result. About 45 seconds."),
 ("3","Explain any patch",code("terminal",["uv run patch-precedent explain fixtures/installer/token-header.patch"]),"Read-only and offline. Works on any diff against Relate."),
 ("4","Give your agent the graph",f'<div class="code"><div class="code-bar"><span>.mcp.json</span><button class="copy">COPY</button></div><pre style="padding:16px">{mcpjson}</pre></div>'+code("or in one line",["claude mcp add --scope project precedent -- uv run --project <path-to-relate-clone> --quiet patch-precedent mcp"]),"One read-only tool, precedent_for_patch. Run the demo first so it can return observed results."),
 ("5","Relate's own MCP server",code("optional, macOS arm64",["uv run patch-precedent fetch-relate-cli","<path printed above> serve --mcp stdio --read-only --database <copy of data/precedent.rl>"]),"Raw Cypher over the same graph. Point it at a copy of the store."),
 ("6","Re-score the published evaluation",code("offline, no usage",["uv run patch-precedent eval score --results eval/results/20261127T040059Z","uv run patch-precedent eval report --results eval/results/20261127T040059Z"]),"Rebuilds RESULTS.md byte for byte from the committed transcripts."),
]
st="".join(f'''<div class="reveal" style="display:grid;grid-template-columns:48px minmax(0,1fr);gap:16px;padding:28px 0;border-top:1px solid var(--line)"><div style="width:40px;height:40px;border-radius:50%;background:var(--ink);color:#FAF7F2;display:grid;place-items:center;font:600 15px 'JetBrains Mono'">{n}</div><div style="display:grid;gap:12px"><div><h3>{t}</h3><p class="muted" style="font-size:14.5px;margin-top:4px">{note}</p></div>{c}</div></div>''' for n,t,c,note in steps)
cmds=[("demo all | installer | release","Replay patches and explain results","0 ok · 2 inconclusive · 3 mismatch · 4 no upstream"),("explain PATCH","Show the decision chain for a diff","0 ok · 2 missing file or store"),("mcp","Serve the read-only MCP tool","0 · 2 missing store"),("verify-store","Check the store matches its evidence","0 match · 1 differs"),("scan-citations","Re-scan ADR mentions upstream","0 · 4 no upstream"),("eval run | score | report","Agent evaluation","0 · 2 refused · 4 no upstream")]
ct="".join(f'<tr><td class="k">{c}</td><td>{w}</td><td class="hide-sm muted" style="font-size:13px">{e}</td></tr>' for c,w,e in cmds)
use=HEAD("Use it - Patch Precedent")+nav("Use it")+f'''
<main class="wrap" style="padding-top:48px;padding-bottom:72px;max-width:920px">
 <div class="reveal"><div class="eyebrow">Use it</div><h1 style="margin:10px 0 12px">Run it in a minute.</h1>
 <div style="display:flex;gap:8px;flex-wrap:wrap"><span class="pill">macOS</span><span class="pill">git</span><span class="pill">uv</span><span class="pill">no API key</span></div></div>
 <div style="margin-top:24px">{st}</div>
 <div class="card reveal" style="margin-top:12px"><div class="card-head"><span class="label">All commands</span><span class="muted" style="font-size:13px">uv run patch-precedent ...</span></div><table class="t"><thead><tr><th>Command</th><th>Does</th><th class="hide-sm">Exit codes</th></tr></thead><tbody>{ct}</tbody></table></div>
</main>'''+REVEAL+'</body></html>'
open(os.path.join(d,"use.html"),"w").write(use)
print("ok")
