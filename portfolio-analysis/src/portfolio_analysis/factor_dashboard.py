"""Cross-stock factor comparison dashboard (issue #24).

One self-contained offline page comparing trailing beta / annualized alpha
trajectories across every configured stock: two time-series charts sharing one
x-axis, a dual-handle sliding bar for the time frame, per-stock toggle chips,
and hover values. No external resources and no iframes - the same offline
constraint as the single-stock charts.
"""

# The embedded HTML is intentionally kept in one readable template string.
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path

from portfolio_analysis.config import Portfolio
from portfolio_analysis.moves import aligned_returns, annualize_alpha, ols_regression
from portfolio_analysis.store import Store

#: Trailing OLS window, in sessions, matching the single-stock regime panel.
FACTOR_WINDOW = 250

#: Line colors, assigned in config order and cycled for large universes.
_PALETTE = (
    "#955424", "#1f6feb", "#d97706", "#dc2626", "#16a34a",
    "#7c3aed", "#0891b2", "#0e7c7b", "#b4236f", "#5b6b00",
)


def factor_dashboard_data(
    portfolio: Portfolio, store: Store, window: int = FACTOR_WINDOW
) -> dict[str, object]:
    """Daily trailing OLS beta / annualized alpha per ticker vs the benchmark.

    Returns ``{"dates", "stocks", "window", "benchmark", "asof"}`` where
    ``dates`` is the sorted union of the per-ticker aligned dates and each
    stock carries ``beta``/``alpha`` arrays parallel to it. Entries inside the
    ``window``-session warmup and degenerate OLS windows (zero variance) are
    ``None`` - gaps, never invented numbers - so the page draws broken line
    segments instead of fabricating continuity. A ticker the benchmark never
    overlaps still appears with an all-``None`` series; a ticker or benchmark
    with no prices at all is a configuration error and raises.
    """
    benchmark = portfolio.benchmark
    bench = store.adjusted_series(benchmark)
    if not bench:
        raise ValueError(f"no prices for benchmark {benchmark}")
    per_ticker: dict[str, tuple[list[str], list[float | None], list[float | None], str]] = {}
    for entry in portfolio.entries:
        prices = store.adjusted_series(entry.symbol)
        if not prices:
            raise ValueError(f"no prices for {entry.symbol}")
        dates, asset_ret, bench_ret = aligned_returns(prices, bench)
        beta: list[float | None] = [None] * len(dates)
        alpha: list[float | None] = [None] * len(dates)
        for i in range(window - 1, len(dates)):
            seg = slice(i - window + 1, i + 1)
            try:
                b, a = ols_regression(asset_ret[seg], bench_ret[seg])
            except ValueError:
                continue  # degenerate window: leave a gap, never a guess
            beta[i] = b
            alpha[i] = annualize_alpha(a)
        per_ticker[entry.symbol] = (dates, beta, alpha, entry.name)
    master = sorted({d for dates, _, _, _ in per_ticker.values() for d in dates})
    at = {d: i for i, d in enumerate(master)}
    stocks: dict[str, dict[str, object]] = {}
    for pos, (symbol, (dates, beta, alpha, name)) in enumerate(per_ticker.items()):
        # Reindex onto the shared date axis; dates a ticker lacks stay None
        # so the union never invents observations for it.
        bcol: list[float | None] = [None] * len(master)
        acol: list[float | None] = [None] * len(master)
        for d, bv, av in zip(dates, beta, alpha, strict=True):
            j = at[d]
            bcol[j] = None if bv is None else round(bv, 4)
            acol[j] = None if av is None else round(av, 5)
        stocks[symbol] = {
            "color": _PALETTE[pos % len(_PALETTE)],
            "name": name,
            "beta": bcol,
            "alpha": acol,
        }
    return {
        "dates": master,
        "stocks": stocks,
        "window": window,
        "benchmark": benchmark,
        "asof": master[-1] if master else "",
    }


def render_factor_dashboard(data: dict[str, object], out_dir: Path) -> Path:
    """Write the self-contained ``factors.html`` page."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "factors.html"
    # JSON is inert text. Escape HTML delimiters so a hostile ticker symbol
    # in the config cannot end the script element.
    payload = json.dumps(data, allow_nan=False)
    payload = (
        payload.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    target.write_text(_PAGE.replace("__DATA__", "const DATA = " + payload + ";"))
    return target


_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Factor comparison · Beta &amp; Alpha over time</title>
<style>
:root{color-scheme:light;--bg:#f5f4ef;--paper:#fffefa;--ink:#21231f;--muted:#65685f;--line:#dedfd6;--accent:#955424}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:auto;padding:24px 28px 60px}
.top{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:6px}
.brand{font-size:12px;font-weight:750;letter-spacing:.14em;color:var(--muted)}
h1{font:500 32px/1.15 Georgia,serif;margin:18px 0 4px}
p.sub{color:var(--muted);margin:0 0 14px}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:14px 0}
.chip{border:1px solid var(--line);background:var(--paper);border-radius:20px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:7px;color:var(--ink)}
.chip .dot{width:10px;height:10px;border-radius:50%;flex:none}
.chip.off{opacity:.35}
.chip:hover{border-color:var(--accent)}
.presets{display:flex;gap:6px;margin-left:auto}
.presets button{border:1px solid var(--line);background:var(--paper);border-radius:7px;padding:6px 10px;font:inherit;font-size:13px;cursor:pointer;color:var(--ink)}
.presets button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.chart-block{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:16px 16px 8px;margin:14px 0}
.chart-block h2{font-size:16px;margin:0 0 2px}
.chart-block .cap{font-size:12px;color:var(--muted);margin:0 0 6px}
.chart{position:relative}
.chart svg{display:block;width:100%;height:auto;touch-action:none}
.tip{position:absolute;pointer-events:none;background:#21231f;color:#f5f4ef;border-radius:8px;padding:8px 10px;font-size:12px;line-height:1.6;display:none;white-space:nowrap;z-index:5;box-shadow:0 4px 14px rgba(0,0,0,.25)}
.tip .tdate{font-weight:700;margin-bottom:2px}
.tip .row{display:flex;align-items:center;gap:6px}
.tip .dot{width:8px;height:8px;border-radius:50%;flex:none}
#sliderWrap{margin:26px 4px 0}
#slider{position:relative;height:34px;touch-action:none}
#track{position:absolute;top:14px;left:0;right:0;height:6px;border-radius:3px;background:#e3e2d8}
#fill{position:absolute;top:14px;height:6px;border-radius:3px;background:var(--accent)}
.handle{position:absolute;top:7px;width:20px;height:20px;border-radius:50%;background:#fff;border:2px solid var(--accent);cursor:ew-resize;transform:translateX(-50%);box-shadow:0 1px 4px rgba(0,0,0,.2);z-index:2}
#rangeLabels{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-top:2px}
.note{font-size:12px;color:var(--muted);margin-top:22px}
</style></head><body><main>
<div class="top"><span class="brand">OPENPAW / MARKET NOTES</span></div>
<h1>Beta &amp; Alpha across stocks.</h1>
<p class="sub" id="subline">Trailing factor trajectories. Drag the handles to change the time frame; tap a stock to show/hide it. Hover a chart for values.</p>
<div class="controls" id="chips"></div>
<div class="chart-block"><h2>Beta over time</h2><p class="cap">Benchmark sensitivity. Zero line dashed.</p><div class="chart" id="betaBox"><svg id="betaSvg" viewBox="0 0 1000 340" preserveAspectRatio="none"></svg><div class="tip" id="betaTip"></div></div></div>
<div class="chart-block"><h2>Alpha over time</h2><p class="cap">Annualized trailing residual, not a forecast. Zero line dashed.</p><div class="chart" id="alphaBox"><svg id="alphaSvg" viewBox="0 0 1000 340" preserveAspectRatio="none"></svg><div class="tip" id="alphaTip"></div></div></div>
<div id="sliderWrap">
<div class="controls" style="margin:0 0 4px"><span style="font-size:13px;color:var(--muted)">Time frame</span><div class="presets" style="margin-left:8px" id="presets">
<button data-n="all" class="on">All</button><button data-n="756">3Y</button><button data-n="252">1Y</button><button data-n="126">6M</button>
</div></div>
<div id="slider"><div id="track"></div><div id="fill"></div><div class="handle" id="h0"></div><div class="handle" id="h1"></div></div>
<div id="rangeLabels"><span id="d0"></span><span id="d1"></span></div>
</div>
<p class="note" id="noteline"></p>
</main>
<script>
__DATA__
const ORDER = Object.keys(DATA.stocks);
const visible = new Set(ORDER);
const N = DATA.dates.length;
let i0 = 0, i1 = N - 1;
const W = 1000, H = 340, PADL = 52, PADR = 8, PADT = 10, PADB = 26;
const $ = id => document.getElementById(id);
const fmtDate = d => { const [y,m,dd] = d.split('-').map(Number); return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1] + ' ' + y; };
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');
$('subline').textContent = 'Trailing ' + DATA.window + '-session OLS vs ' + DATA.benchmark + ' (as of ' + fmtDate(DATA.asof) + '). Drag the handles to change the time frame; tap a stock to show/hide it. Hover a chart for values.';
$('noteline').textContent = '\\u03b2 = slope of stock returns on ' + DATA.benchmark + ' \\u00b7 \\u03b1 = intercept, annualized \\u00d7252 \\u00b7 R\\u00b2 and \\u03b1 slope live on each stock\\u2019s own chart.';

/* ---------- chips ---------- */
const chipsEl = $('chips');
for (const t of ORDER) {
  const c = DATA.stocks[t];
  const b = document.createElement('button');
  b.className = 'chip'; b.dataset.t = t;
  b.innerHTML = '<span class="dot" style="background:' + c.color + '"></span>' + esc(t);
  b.onclick = () => { visible.has(t) ? visible.delete(t) : visible.add(t); b.classList.toggle('off', !visible.has(t)); render(); };
  chipsEl.appendChild(b);
}
const allBtn = document.createElement('button');
allBtn.className = 'chip'; allBtn.textContent = 'All';
allBtn.onclick = () => { ORDER.forEach(t => visible.add(t)); [...chipsEl.children].forEach(x => x.classList.remove('off')); render(); };
const noneBtn = document.createElement('button');
noneBtn.className = 'chip'; noneBtn.textContent = 'None';
noneBtn.onclick = () => { visible.clear(); [...chipsEl.children].forEach(x => { if (x.dataset.t) x.classList.add('off'); }); render(); };
chipsEl.append(allBtn, noneBtn);

/* ---------- chart drawing ---------- */
function yDomain(key) {
  let lo = Infinity, hi = -Infinity;
  for (const t of visible) {
    const v = DATA.stocks[t][key];
    for (let i = i0; i <= i1; i++) { const x = v[i]; if (x == null) continue; if (x < lo) lo = x; if (x > hi) hi = x; }
  }
  if (!isFinite(lo)) { lo = -1; hi = 1; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08; return [lo - pad, hi + pad];
}
function draw(svgId, key, fmt) {
  const svg = $(svgId);
  const [lo, hi] = yDomain(key);
  const X = i => PADL + (i - i0) / Math.max(1, i1 - i0) * (W - PADL - PADR);
  const Y = v => PADT + (1 - (v - lo) / (hi - lo)) * (H - PADT - PADB);
  let s = '';
  // gridlines + y labels (4)
  for (let g = 0; g <= 3; g++) {
    const v = lo + (hi - lo) * g / 3, y = Y(v);
    s += '<line x1="' + PADL + '" y1="' + y.toFixed(1) + '" x2="' + (W - PADR) + '" y2="' + y.toFixed(1) + '" stroke="#e9e8dd" stroke-width="1"/>';
    s += '<text x="' + (PADL - 6) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" font-size="11" fill="#65685f">' + esc(fmt(v)) + '</text>';
  }
  // zero line
  if (lo < 0 && hi > 0) { const y = Y(0); s += '<line x1="' + PADL + '" y1="' + y.toFixed(1) + '" x2="' + (W - PADR) + '" y2="' + y.toFixed(1) + '" stroke="#b9b8aa" stroke-width="1" stroke-dasharray="5 4"/>'; }
  // x ticks (<=6)
  const nt = Math.min(6, i1 - i0 + 1);
  for (let k = 0; k < nt; k++) {
    const i = Math.round(i0 + (i1 - i0) * k / Math.max(1, nt - 1));
    const x = X(i);
    s += '<text x="' + x.toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle" font-size="11" fill="#65685f">' + fmtDate(DATA.dates[i]) + '</text>';
  }
  // series (split on nulls so gaps stay gaps)
  for (const t of visible) {
    const c = DATA.stocks[t], vals = c[key];
    let d = '', started = false;
    for (let i = i0; i <= i1; i++) {
      const v = vals[i]; if (v == null) { started = false; continue; }
      d += (started ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1);
      started = true;
    }
    if (d) s += '<path d="' + d + '" fill="none" stroke="' + c.color + '" stroke-width="1.8"/>';
  }
  svg.innerHTML = s;
  svg._geom = { key, fmt, X, lo, hi };
}
function render() {
  draw('betaSvg', 'beta', v => v.toFixed(2));
  draw('alphaSvg', 'alpha', v => (v * 100).toFixed(1) + '%');
  $('d0').textContent = fmtDate(DATA.dates[i0]);
  $('d1').textContent = fmtDate(DATA.dates[i1]);
  const L = N - 1;
  $('h0').style.left = (i0 / L * 100) + '%';
  $('h1').style.left = (i1 / L * 100) + '%';
  $('fill').style.left = (i0 / L * 100) + '%';
  $('fill').style.width = ((i1 - i0) / L * 100) + '%';
}

/* ---------- hover ---------- */
function hover(boxId, svgId, tipId) {
  const box = $(boxId), svg = $(svgId), tip = $(tipId);
  box.addEventListener('pointermove', e => {
    const g = svg._geom; if (!g) return;
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width * W;
    const frac = Math.min(1, Math.max(0, (px - PADL) / (W - PADL - PADR)));
    const i = Math.round(i0 + frac * (i1 - i0));
    const gx = g.X(i) / W * r.width;
    let rows = '';
    for (const t of visible) {
      const c = DATA.stocks[t], v = c[g.key][i];
      if (v == null) continue;
      rows += '<div class="row"><span class="dot" style="background:' + c.color + '"></span><span>' + esc(t) + '</span><b>' + esc(g.fmt(v)) + '</b></div>';
    }
    if (!rows) { tip.style.display = 'none'; return; }
    tip.innerHTML = '<div class="tdate">' + fmtDate(DATA.dates[i]) + '</div>' + rows;
    tip.style.display = 'block';
    tip.style.left = Math.min(r.width - 170, Math.max(4, gx + 12)) + 'px';
    tip.style.top = '8px';
    drawGuide(svgId, gx, r);
  });
  box.addEventListener('pointerleave', () => { tip.style.display = 'none'; drawGuide(svgId, -1); });
}
function drawGuide(svgId, gxPx, r) {
  const svg = $(svgId), g = svg._geom; if (!g || !r) return;
  const x = gxPx < 0 ? -1 : gxPx / r.width * W;
  let el = svg.querySelector('.guide');
  if (x < 0) { if (el) el.remove(); return; }
  if (!el) { el = document.createElementNS('http://www.w3.org/2000/svg', 'line'); el.setAttribute('class', 'guide'); svg.appendChild(el); }
  el.setAttribute('x1', x); el.setAttribute('x2', x);
  el.setAttribute('y1', PADT); el.setAttribute('y2', H - PADB);
  el.setAttribute('stroke', '#955424'); el.setAttribute('stroke-width', '1'); el.setAttribute('stroke-dasharray', '4 3');
}
hover('betaBox', 'betaSvg', 'betaTip');
hover('alphaBox', 'alphaSvg', 'alphaTip');

/* ---------- range slider ---------- */
const slider = $('slider');
const MIN_GAP = 30;
function setRange(a, b) {
  a = Math.max(0, Math.min(N - 1, Math.round(a)));
  b = Math.max(0, Math.min(N - 1, Math.round(b)));
  if (b - a < MIN_GAP) {
    if (a === i0) b = Math.min(N - 1, a + MIN_GAP);
    else a = Math.max(0, b - MIN_GAP);
  }
  i0 = Math.min(a, b); i1 = Math.max(a, b);
  document.querySelectorAll('#presets button').forEach(x => x.classList.remove('on'));
  render();
}
function drag(handle, isStart) {
  handle.addEventListener('pointerdown', e => {
    e.preventDefault(); handle.setPointerCapture(e.pointerId);
    const move = ev => {
      const r = slider.getBoundingClientRect();
      const frac = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      const v = frac * (N - 1);
      if (isStart) setRange(v, i1); else setRange(i0, v);
    };
    const up = () => { handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', up); };
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', up);
  });
}
drag($('h0'), true); drag($('h1'), false);
document.querySelectorAll('#presets button').forEach(b => b.onclick = () => {
  const n = b.dataset.n;
  if (n === 'all') setRange(0, N - 1); else setRange(N - 1 - (+n), N - 1);
  document.querySelectorAll('#presets button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
});
render();
</script></body></html>
"""
