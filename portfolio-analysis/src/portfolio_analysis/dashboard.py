"""Static portfolio dashboard that links the self-contained stock charts."""

# The embedded HTML is intentionally kept in one readable template string.
# ruff: noqa: E501

from __future__ import annotations

import html
from pathlib import Path

from portfolio_analysis.config import Portfolio


def render_dashboard(portfolio: Portfolio, out_dir: Path) -> Path:
    """Write an offline dashboard with a selector and one chart frame."""
    rows = []
    options = []
    for entry in portfolio.entries:
        symbol = html.escape(entry.symbol, quote=True)
        name = html.escape(entry.name)
        href = f"{symbol}.html"
        options.append(f'<option value="{symbol}.html">{symbol} · {name}</option>')
        rows.append(
            f'<a class="card" href="{href}"><strong>{symbol}</strong>'
            f'<span>{name}</span><em>Open chart →</em></a>'
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_text(
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OpenPaw · Portfolio dashboard</title>
<style>
:root{color-scheme:light;--bg:#f5f4ef;--paper:#fffefa;--ink:#21231f;--muted:#65685f;--line:#dedfd6;--accent:#955424}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,sans-serif}main{max-width:1300px;margin:auto;padding:28px 32px 44px}.top{display:flex;justify-content:space-between;align-items:end;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:24px}.brand{font-size:12px;font-weight:750;letter-spacing:.14em}.muted{color:var(--muted)}h1{font:500 42px/1.1 Georgia,serif;margin:26px 0 8px}.picker{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:22px 0 14px}select{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:7px;background:var(--paper);color:var(--ink);min-width:260px}.frame{height:760px;width:100%;border:1px solid var(--line);border-radius:12px;background:var(--paper)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:20px 0}.card{display:flex;flex-direction:column;gap:3px;padding:15px;background:var(--paper);border:1px solid var(--line);border-radius:9px;color:var(--ink);text-decoration:none}.card:hover{border-color:var(--accent)}.card strong{font-size:20px}.card span{font-size:12px;color:var(--muted)}.card em{font-size:11px;color:var(--accent);font-style:normal;margin-top:8px}@media(max-width:700px){main{padding:20px 16px}.top{display:block}h1{font-size:34px}.frame{height:640px}}
</style></head><body><main><div class="top"><span class="brand">OPENPAW / MARKET NOTES</span><span class="muted">Portfolio dashboard</span></div>
<h1>Stocks in context.</h1><p class="muted">Choose a stock to inspect its price history, unusual moves, and collected event evidence. Each chart is self-contained and works offline.</p>
<div class="picker"><label for="stock">Stock</label><select id="stock">__OPTIONS__</select></div>
<iframe class="frame" id="chart" title="Selected stock chart"></iframe><div class="cards">__CARDS__</div>
<script>const select=document.getElementById('stock'),frame=document.getElementById('chart');function openChart(){frame.src=select.value;history.replaceState(null,'','#'+select.value.replace('.html',''));}select.addEventListener('change',openChart);const wanted=location.hash.slice(1);if(wanted&&[...select.options].some(o=>o.value===wanted+'.html'))select.value=wanted+'.html';openChart();</script>
</main></body></html>"""
        .replace("__OPTIONS__", "".join(options))
        .replace("__CARDS__", "".join(rows))
    )
    return target
