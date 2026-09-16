"""Build an event-window return dashboard from macro dates and stored prices."""
# ruff: noqa: E501
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from portfolio_analysis.config import Portfolio
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.store import Store


def _impact(series: dict[str, float], event_date: str) -> dict[str, float | None]:
    dates = sorted(series)
    before = [d for d in dates if d < event_date]
    on_or_after = [d for d in dates if d >= event_date]
    if not before or not on_or_after:
        return {"before_1d": None, "after_1d": None, "after_5d": None, "after_20d": None}
    i = dates.index(on_or_after[0])
    base = series[before[-1]]
    def change(offset: int) -> float | None:
        j = i + offset
        return None if j >= len(dates) else series[dates[j]] / base - 1
    return {"before_1d": series[on_or_after[0]] / base - 1, "after_1d": change(1), "after_5d": change(5), "after_20d": change(20)}


def event_dashboard_data(portfolio: Portfolio, store: Store, calendar: MacroSource) -> dict[str, Any]:
    symbols = [portfolio.benchmark, *portfolio.symbols]
    prices = {symbol: store.adjusted_series(symbol) for symbol in symbols}
    # Include SPY when it has been fetched, making the S&P 500 proxy available
    # without forcing a network request during offline dashboard generation.
    if store.price_bar_count("SPY"):
        symbols.insert(0, "SPY")
        prices["SPY"] = store.adjusted_series("SPY")
    events = []
    for kind, rows in calendar.catalog().items():
        for row in rows:
            events.append({"type": kind, "date": row["date"], "url": row["url"], "action": row.get("action"), "change_bp": row.get("change_bp"), "target_range": row.get("target_range"), "decision_source": row.get("source"), "impact": {s: _impact(prices[s], row["date"]) for s in symbols}})
    return {"symbols": symbols, "events": sorted(events, key=lambda e: (e["date"], e["type"])), "benchmark": portfolio.benchmark}


def render_event_dashboard(data: dict[str, Any], out_dir: Path) -> Path:
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    options = "".join(f'<option>{html.escape(s)}</option>' for s in data["symbols"])
    target = out_dir / "event-impact.html"
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenPaw · Event impact</title>
<style>body{{font:14px system-ui;margin:0;background:#f5f4ef;color:#21231f}}main{{max-width:1100px;margin:auto;padding:28px}}h1{{font:40px Georgia;font-weight:500}}.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}select{{padding:10px;border:1px solid #ccc;border-radius:6px;background:#fffefa}}table{{border-collapse:collapse;width:100%;background:#fffefa;margin:12px 0 24px}}td,th{{padding:11px;text-align:right;border-bottom:1px solid #ddd}}td:first-child,th:first-child{{text-align:left}}.up{{color:#176b3a}}.down{{color:#ae3d35}}a{{color:#955424}}.note{{color:#65685f;font-size:12px}}</style><main><p>OPENPAW / EVENT STUDY</p><h1>Price response around macro events</h1><p>Choose a release type and date to see the magnitude across every available instrument. Returns use the last trading close before the release and the next 1, 5, or 20 sessions. Timing is association, not causation.</p><div class="controls"><label>Event <select id="type"></select></label><label>Date <select id="date"></select></label><label>Focus <select id="symbol">{options}</select></label></div><p id="source"></p><h2>All instruments</h2><p class="note">Positive values are gains; negative values are losses. The largest absolute move is highlighted by the data, without claiming the event caused it.</p><table><thead><tr><th>Instrument</th><th>Release session</th><th>+1 session</th><th>+5 sessions</th><th>+20 sessions</th></tr></thead><tbody id="matrix"></tbody></table><h2>Focused instrument</h2><table><thead><tr><th>Window</th><th>Return</th></tr></thead><tbody id="body"></tbody></table></main><script type="application/json" id="data">{payload}</script><script>const d=JSON.parse(document.getElementById('data').textContent),$=x=>document.getElementById(x),types=[...new Set(d.events.map(e=>e.type))];$('type').innerHTML=types.map(x=>`<option>${{x}}</option>`).join('');function dates(){{const t=$('type').value;$('date').innerHTML=d.events.filter(e=>e.type===t).map(e=>`<option value="${{e.date}}">${{e.date}}</option>`).join('');}}function cell(v){{return v==null?'n/a':(v*100).toFixed(2)+'%';}}function draw(){{const e=d.events.find(e=>e.type===$('type').value&&e.date===$('date').value),s=$('symbol').value,i=e.impact[s];$('source').innerHTML=`<a href="${{e.url}}" target="_blank">Source calendar</a> · ${{e.type}} release on ${{e.date}}`;$('matrix').innerHTML=d.symbols.map(x=>{{const m=e.impact[x];return `<tr><td><strong>${{x}}</strong></td>${{[m.before_1d,m.after_1d,m.after_5d,m.after_20d].map(v=>`<td class="${{v>=0?'up':'down'}}">${{cell(v)}}</td>`).join('')}}</tr>`;}}).join('');const rows=[['Release session vs prior close',i.before_1d],['1 session after',i.after_1d],['5 sessions after',i.after_5d],['20 sessions after',i.after_20d]];$('body').innerHTML=rows.map(([n,v])=>`<tr><td>${{n}}</td><td class="${{v>=0?'up':'down'}}">${{cell(v)}}</td></tr>`).join('');}}$('type').onchange=()=>{{dates();draw();}};$('date').onchange=draw;$('symbol').onchange=draw;dates();draw();</script>''')
    rendered = target.read_text()
    rendered = rendered.replace(
        '<p id="source"></p>',
        '<p id="source"></p><p id="decision" class="note"></p>',
    )
    rendered += "<script>function showDecision(){const e=d.events.find(e=>e.type===type.value&&e.date===date.value);const x=document.getElementById('decision');if(e&&e.action){const label=e.action==='hold'?'held the target range':e.action==='hike'?'raised the target range':'lowered the target range';x.textContent=`FOMC decision: ${label} (${e.change_bp>0?'+':''}${e.change_bp} bp); target ${e.target_range}. Policy source: ${e.decision_source}`;}else{x.textContent='';}}type.addEventListener('change',showDecision);date.addEventListener('change',showDecision);showDecision();</script>"
    target.write_text(rendered)
    return target
