"""Preview renderer. NOT the Plan 4 `render` command - a throwaway to see the
shape of the data before Plans 2-4 are written. Events and reasons do not exist
yet, so the attribution half of every card is deliberately empty."""
import json, math, sqlite3, pathlib, html

ROOT = pathlib.Path(".")
con = sqlite3.connect(ROOT / "data/prices.sqlite"); con.row_factory = sqlite3.Row
def series(t):
    return {r["date"]: r["adj_close"] for r in
            con.execute("SELECT date, adj_close FROM price_bar WHERE ticker=? ORDER BY date", (t,))}
meta, qqq = series("META"), series("QQQ")
art = json.loads((ROOT / "data/moves/META.json").read_text())
moves = {m["date"]: m for m in art["moves"]}

dates = sorted(set(meta) & set(qqq))
b_m, b_q = meta[dates[0]], qqq[dates[0]]
# Indexed to 100 at the series start: one shared axis, never two y-scales.
im = [meta[d] / b_m * 100 for d in dates]
iq = [qqq[d] / b_q * 100 for d in dates]

W, H = 1000, 400
L, R, T, B = 58, 18, 18, 30
lo, hi = min(min(im), min(iq)), max(max(im), max(iq))
# Log scale: the subject is percentage moves, so equal % should be equal distance.
ly0, ly1 = math.log10(lo * 0.94), math.log10(hi * 1.06)
def px(i): return L + i * (W - L - R) / (len(dates) - 1)
def py(v): return T + (ly1 - math.log10(v)) / (ly1 - ly0) * (H - T - B)
def path(vals): return "M" + " L".join(f"{px(i):.1f} {py(v):.2f}" for i, v in enumerate(vals))

ticks = [t for t in (30, 50, 75, 100, 150, 200, 300, 400) if lo * 0.94 <= t <= hi * 1.06]
years, seen = [], set()
for i, d in enumerate(dates):
    if d[:4] not in seen: seen.add(d[:4]); years.append((i, d[:4]))

mk = []
for d, m in moves.items():
    if d not in dates: continue
    i = dates.index(d); z = m["z"]
    r = 4 + 5 * min(1.0, (abs(z) - 2.5) / 6.0)
    mk.append({"i": i, "d": d, "x": round(px(i), 1), "y": round(py(im[i]), 2),
               "r": round(r, 2), "up": z > 0, **{k: m[k] for k in
               ("ret", "benchmark_return", "beta", "abnormal_return", "sigma_60", "z")}})
mk.sort(key=lambda m: abs(m["z"]))

cov = art["coverage"]; p = art["params"]
big = max(mk, key=lambda m: abs(m["z"]))
rate = cov["flagged_days"] / cov["evaluated_days"]

def tile(v, lab, sub):
    return (f'<div class="tile"><div class="tv">{v}</div><div class="tl">{lab}</div>'
            f'<div class="ts">{sub}</div></div>')

rows = "".join(
    f'<tr data-d="{m["d"]}"><td class="dt">{m["d"]}</td>'
    f'<td class="n {"up" if m["up"] else "dn"}">{m["ret"]*100:+.2f}%</td>'
    f'<td class="n">{m["benchmark_return"]*100:+.2f}%</td><td class="n">{m["beta"]:.2f}</td>'
    f'<td class="n {"up" if m["up"] else "dn"}">{m["abnormal_return"]*100:+.2f}%</td>'
    f'<td class="n">{m["sigma_60"]*100:.2f}%</td>'
    f'<td class="n b">{m["z"]:+.2f}</td></tr>'
    for m in sorted(mk, key=lambda m: m["d"]))

doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>META - abnormal move map</title><style>
*{{box-sizing:border-box}}
.viz-root{{color-scheme:light;--surface-1:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;
--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;--dn:#e34948;--up:#2a78d6;
--border:rgba(11,11,11,.10)}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme=light])) .viz-root{{
color-scheme:dark;--surface-1:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
--muted:#898781;--grid:#2c2c2a;--axis:#383835;--dn:#e66767;--up:#3987e5;
--border:rgba(255,255,255,.10)}}}}
:root[data-theme=dark] .viz-root{{color-scheme:dark;--surface-1:#1a1a19;--plane:#0d0d0d;
--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--dn:#e66767;
--up:#3987e5;--border:rgba(255,255,255,.10)}}
body{{margin:0;background:var(--plane);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
color:var(--ink)}}
.viz-root{{max-width:1060px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:19px;margin:0 0 2px;letter-spacing:-.01em}}
.sub{{color:var(--ink2);font-size:13px;margin:0 0 20px}}
.hd{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}}
button{{font:inherit;color:var(--ink2);background:var(--surface-1);border:1px solid var(--border);
border-radius:7px;padding:5px 11px;cursor:pointer}}
button:hover{{color:var(--ink)}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}}
.tile{{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:12px 14px}}
.tv{{font-size:24px;letter-spacing:-.02em}} .tl{{font-size:12px;color:var(--ink2);margin-top:1px}}
.ts{{font-size:11px;color:var(--muted);margin-top:3px}}
.card,.panel{{background:var(--surface-1);border:1px solid var(--border);border-radius:10px}}
.panel{{padding:8px 10px 4px;position:relative}}
svg{{display:block;width:100%;height:auto}}
.lg{{display:flex;gap:16px;flex-wrap:wrap;align-items:center;padding:2px 6px 8px;
font-size:12px;color:var(--ink2)}}
.lg i{{display:inline-block;vertical-align:middle;margin-right:6px}}
.sw{{width:20px;height:0;border-top:2px solid var(--ink)}}
.sw.q{{border-top:2px dashed var(--muted)}}
.dot{{width:10px;height:10px;border-radius:50%}}
.grid2{{display:grid;grid-template-columns:1.15fr 1fr;gap:12px;margin-top:12px;align-items:start}}
.card{{padding:14px 16px}}
.ct{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:9px}}
.cd{{font-size:17px;letter-spacing:-.01em;margin-bottom:10px}}
.kv{{display:grid;grid-template-columns:auto 1fr;gap:3px 14px;font-size:13px}}
.kv dt{{color:var(--ink2)}} .kv dd{{margin:0;text-align:right;font-variant-numeric:tabular-nums}}
.up{{color:var(--up)}} .dn{{color:var(--dn)}} .b{{font-weight:600}}
.pend{{margin-top:12px;padding:10px 12px;border:1px dashed var(--border);border-radius:8px;
font-size:12px;color:var(--muted)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{text-align:right;font-weight:500;color:var(--muted);padding:5px 8px;border-bottom:1px solid var(--axis);
position:sticky;top:0;background:var(--surface-1)}}
th:first-child,.dt{{text-align:left}}
td{{padding:4px 8px;border-bottom:1px solid var(--grid);font-variant-numeric:tabular-nums}}
tbody tr{{cursor:pointer}} tbody tr:hover td{{background:var(--plane)}}
tbody tr.sel td{{background:var(--plane);box-shadow:inset 2px 0 0 var(--ink)}}
.scroll{{max-height:340px;overflow:auto}}
.tip{{position:absolute;pointer-events:none;background:var(--surface-1);border:1px solid var(--border);
border-radius:7px;padding:6px 9px;font-size:12px;box-shadow:0 2px 10px rgba(0,0,0,.10);
opacity:0;transition:opacity .08s;font-variant-numeric:tabular-nums;white-space:nowrap}}
foot,.foot{{display:block;margin-top:18px;font-size:12px;color:var(--muted);max-width:74ch}}
.mk{{cursor:pointer}} .mk:hover circle{{stroke-width:3}}
</style></head><body><div class="viz-root">

<div class="hd"><div>
<h1>META &mdash; abnormal single-day moves</h1>
<p class="sub">{cov['evaluated'][0]} to {cov['evaluated'][1]} &middot; beta-adjusted against QQQ &middot;
flagged when |z| &ge; {p['z_threshold']}</p></div>
<button id="tg">Toggle theme</button></div>

<div class="tiles">
{tile(cov['flagged_days'], 'days flagged', f"of {cov['evaluated_days']:,} evaluated")}
{tile(f"{rate*100:.2f}%", 'flag rate', 'normal dist. would give 1.24%')}
{tile(f"{big['z']:+.1f}", 'largest |z|', f"{big['d']} &middot; {big['ret']*100:+.1f}%")}
{tile(f"{p['beta_window']}d", 'beta window', f"sigma over {p['sigma_window']}d, both ending t-1")}
</div>

<div class="panel"><div id="tip" class="tip"></div>
<svg viewBox="0 0 {W} {H}" role="img" aria-label="Indexed price of META and QQQ with abnormal moves marked">
{''.join(f'<line x1="{L}" y1="{py(t):.1f}" x2="{W-R}" y2="{py(t):.1f}" stroke="var(--grid)" stroke-width="1"/>'
         f'<text x="{L-9}" y="{py(t)+4:.1f}" text-anchor="end" font-size="11" fill="var(--muted)">{t}</text>'
         for t in ticks)}
{''.join(f'<text x="{px(i):.1f}" y="{H-9}" text-anchor="middle" font-size="11" fill="var(--muted)">{y}</text>'
         for i, y in years)}
<line x1="{L}" y1="{H-B}" x2="{W-R}" y2="{H-B}" stroke="var(--axis)" stroke-width="1"/>
<path d="{path(iq)}" fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="5 4"
      stroke-linejoin="round" opacity=".85"/>
<path d="{path(im)}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round"/>
<line id="ch" x1="0" y1="{T}" x2="0" y2="{H-B}" stroke="var(--axis)" stroke-width="1" opacity="0"/>
{''.join(f'<g class="mk" data-d="{m["d"]}"><circle cx="{m["x"]}" cy="{m["y"]}" r="{m["r"]}" '
         f'fill="var(--{"up" if m["up"] else "dn"})" stroke="var(--surface-1)" stroke-width="2"/></g>'
         for m in mk)}
<rect id="hit" x="{L}" y="{T}" width="{W-L-R}" height="{H-T-B}" fill="transparent"/>
</svg>
<div class="lg">
<span><i class="sw"></i>META (indexed to 100, log scale)</span>
<span><i class="sw q"></i>QQQ benchmark</span>
<span><i class="dot" style="background:var(--dn)"></i>abnormal move down</span>
<span><i class="dot" style="background:var(--up)"></i>abnormal move up</span>
<span style="color:var(--muted)">marker size &prop; |z|</span>
</div></div>

<div class="grid2">
<div class="card"><div class="ct">Verified &mdash; computed, never inferred</div>
<div class="cd" id="cd">&nbsp;</div><dl class="kv" id="kv"></dl>
<div class="pend"><b>Reported claims, events and the LLM reason are not built yet.</b>
Plan 2 collects EDGAR filings, earnings dates, Alpha Vantage news, FRED macro releases and
HackerNews in a [-2,+1] trading-day window. Plan 3 adds the attribution and the placebo /
sign-flip controls. Nothing on this page was inferred by a model.</div></div>
<div class="card" style="padding:0"><div class="scroll"><table>
<thead><tr><th>Date</th><th>Return</th><th>QQQ</th><th>Beta</th><th>Abnormal</th><th>&sigma;<sub>60</sub></th><th>z</th></tr></thead>
<tbody id="tb">{rows}</tbody></table></div></div>
</div>

<p class="foot">Retrospective only &mdash; this explains past moves and makes no predictive claim.
Beta is estimated on a trailing {p['beta_window']}-day OLS regression ending the day before, and
&sigma;<sub>60</sub> on the {p['sigma_window']} abnormal returns before that, so the bar a day must
clear never includes the day itself. Prices are Yahoo adjusted closes; the first fetched year is
consumed as beta warm-up, which is why six years are ingested to evaluate five.</p>

<script>
const M = {json.dumps(mk)}, D = {json.dumps(dates)}, IM = {json.dumps([round(v,3) for v in im])},
      IQ = {json.dumps([round(v,3) for v in iq])};
const L={L},R={R},T={T},B={B},W={W},H={H};
const pct = v => (v*100).toFixed(2)+'%';
function show(d){{
  const m = M.find(x=>x.d===d); if(!m) return;
  document.getElementById('cd').innerHTML =
    `${{m.d}} &nbsp;<span class="${{m.up?'up':'dn'}} b">${{pct(m.ret)}}</span>`;
  document.getElementById('kv').innerHTML = [
    ['Return', pct(m.ret)], ['QQQ same day', pct(m.benchmark_return)],
    ['Beta (250d OLS)', m.beta.toFixed(3)],
    ['Abnormal return', pct(m.abnormal_return)],
    ['&sigma; of abnormal (60d)', pct(m.sigma_60)],
    ['z', m.z.toFixed(2)],
    ['Naive (beta=1) difference', pct(m.ret - m.benchmark_return)],
  ].map(([k,v])=>`<dt>${{k}}</dt><dd>${{v}}</dd>`).join('');
  document.querySelectorAll('#tb tr').forEach(r=>r.classList.toggle('sel', r.dataset.d===d));
  const row = document.querySelector(`#tb tr[data-d="${{d}}"]`); if(row) row.scrollIntoView({{block:'nearest'}});
}}
document.querySelectorAll('.mk').forEach(g=>g.addEventListener('click',()=>show(g.dataset.d)));
document.querySelectorAll('#tb tr').forEach(r=>r.addEventListener('click',()=>show(r.dataset.d)));
const svg=document.querySelector('svg'), tip=document.getElementById('tip'), ch=document.getElementById('ch');
document.getElementById('hit').addEventListener('mousemove', e=>{{
  const bb=svg.getBoundingClientRect(), sx=(e.clientX-bb.left)/bb.width*W;
  let i=Math.round((sx-L)/(W-L-R)*(D.length-1)); i=Math.max(0,Math.min(D.length-1,i));
  const x=L+i*(W-L-R)/(D.length-1);
  ch.setAttribute('x1',x); ch.setAttribute('x2',x); ch.setAttribute('opacity','1');
  const hit=M.find(m=>m.i===i);
  tip.innerHTML=`<b>${{D[i]}}</b><br>META ${{IM[i].toFixed(1)}} &middot; QQQ ${{IQ[i].toFixed(1)}}`+
    (hit?`<br><span class="${{hit.up?'up':'dn'}}">abnormal ${{pct(hit.abnormal_return)}} &middot; z ${{hit.z.toFixed(2)}}</span>`:'');
  tip.style.opacity=1;
  tip.style.left=Math.min(bb.width-190, x/W*bb.width+12)+'px';
  tip.style.top=(e.clientY-bb.top-10)+'px';
}});
document.getElementById('hit').addEventListener('mouseleave',()=>{{tip.style.opacity=0;ch.setAttribute('opacity','0');}});
document.getElementById('tg').addEventListener('click',()=>{{
  const cur=document.documentElement.getAttribute('data-theme');
  const dark=cur? cur==='dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.setAttribute('data-theme', dark?'light':'dark');
}});
show({json.dumps(big['d'])});
</script></div></body></html>"""

out = ROOT / "out"; out.mkdir(exist_ok=True)
(out / "META-preview.html").write_text(doc)
print(f"wrote out/META-preview.html  ({len(doc)/1024:.0f} KB, {len(mk)} markers, {len(dates)} days)")
