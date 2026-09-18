"""Build an event-window return dashboard from macro dates and stored prices."""
# ruff: noqa: E501
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from portfolio_analysis.config import Portfolio
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.reddit import (
    MAX_COMMENTS,
    RedditComment,
    rank_reddit_comments,
)
from portfolio_analysis.store import Store

#: Issue #7: the policy or economic variable each release moves. Plain labels
#: kept next to the data so the context block never invents specifics.
_EVENT_VARIABLES = {
    "FOMC": "federal funds target range",
    "CPI": "Consumer Price Index (headline inflation)",
    "PCE": "PCE price index (the Fed's preferred inflation gauge)",
}

_ACTION_VERBS = {"hold": "held", "hike": "raised", "cut": "lowered"}


def _format_bp(change_bp: Any) -> str:
    try:
        bp = int(change_bp)
    except (TypeError, ValueError):
        return "n/a"
    return f"{bp:+d} bp"


def _event_context(kind: str, row: dict[str, Any], as_of: str) -> dict[str, Any]:
    """Structured, source-backed context for one macro event (issue #7).

    Everything here derives from the checked-in calendar and the FOMC
    decisions file. Market surprise is not tracked in those sources, so it
    is reported as unknown rather than inferred.
    """
    decision: dict[str, Any] | None = None
    action = row.get("action")
    if kind == "FOMC" and action:
        verb = _ACTION_VERBS.get(str(action), str(action))
        # The catalog row carries the decisions file verbatim: its "source"
        # key is the decision's authoritative source (event_dashboard_data
        # renames it to "decision_source" for the event payload).
        decision = {
            "action": action,
            "change_bp": row.get("change_bp"),
            "target_range": row.get("target_range"),
            "source": row.get("source"),
        }
        summary = (
            f"FOMC {verb} the federal funds target range "
            f"({_format_bp(row.get('change_bp'))}) to {row.get('target_range')} "
            f"on {row.get('date')}; decision source: {row.get('source')}."
        )
    elif kind == "FOMC":
        summary = (
            f"FOMC statement day on {row.get('date')}; "
            "no decision record in the checked-in file."
        )
    elif kind == "CPI":
        summary = f"CPI release on {row.get('date')}; source: BLS release schedule."
    elif kind == "PCE":
        summary = f"PCE release on {row.get('date')}; source: BEA release schedule."
    else:
        summary = f"{kind} release on {row.get('date')}."
    return {
        "subtype": kind,
        "decision": decision,
        "surprise": None,  # expectations are not in the checked-in sources
        "affected_variable": _EVENT_VARIABLES.get(kind, "n/a"),
        "source_timestamp": as_of,
        "summary": summary,
    }


def _reddit_comment_from_dict(item: dict[str, Any]) -> RedditComment | None:
    try:
        comment_id = item["comment_id"]
    except KeyError:
        return None
    if not isinstance(comment_id, str) or not comment_id:
        return None
    permalink = item.get("permalink")
    body = item.get("body")
    try:
        return RedditComment(
            comment_id=comment_id,
            score=int(item.get("score") or 0),
            author=str(item.get("author") or "[unknown]"),
            created_utc=int(item.get("created_utc") or 0),
            subreddit=str(item.get("subreddit") or ""),
            permalink=permalink if isinstance(permalink, str) else "",
            body=body if isinstance(body, str) else "",
        )
    except (TypeError, ValueError):
        return None


def _reddit_for_event(
    reddit_dir: Path | None, kind: str, event_date: str
) -> dict[str, Any]:
    """Attach Reddit commentary for one event (issue #7).

    The per-event files written by collect-reddit already hold ranked
    comments, but the cap is enforced again here, after deduplication and
    before rendering, so hand-edited or older files cannot leak extra
    comments into the dashboard. Missing data is explicit: "not_collected"
    when collection never ran, the stored status otherwise.
    """
    if reddit_dir is None:
        return {"status": "not_collected", "comments": []}
    path = reddit_dir / f"{kind}_{event_date}.json"
    if not path.exists():
        return {"status": "not_collected", "comments": []}
    try:
        payload = json.loads(path.read_text())
    except (ValueError, OSError):
        return {"status": "error: unreadable file", "comments": []}
    if not isinstance(payload, dict):
        return {"status": "error: unreadable file", "comments": []}
    status = payload.get("status", "error: missing status")
    raw = payload.get("comments")
    comments: list[RedditComment] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            comment = _reddit_comment_from_dict(item)
            if comment is not None:
                comments.append(comment)
    ranked = rank_reddit_comments(comments, limit=MAX_COMMENTS)
    return {
        "status": str(status),
        "comments": [comment.as_dict() for comment in ranked],
    }


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


def event_dashboard_data(portfolio: Portfolio, store: Store, calendar: MacroSource, reddit_dir: Path | None = None) -> dict[str, Any]:
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
            events.append({"type": kind, "date": row["date"], "url": row["url"], "action": row.get("action"), "change_bp": row.get("change_bp"), "target_range": row.get("target_range"), "decision_source": row.get("source"), "context": _event_context(kind, row, calendar.as_of), "reddit": _reddit_for_event(reddit_dir, kind, row["date"]), "impact": {s: _impact(prices[s], row["date"]) for s in symbols}})
    return {"symbols": symbols, "events": sorted(events, key=lambda e: (e["date"], e["type"])), "benchmark": portfolio.benchmark}


def render_event_dashboard(data: dict[str, Any], out_dir: Path) -> Path:
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    options = "".join(f'<option>{html.escape(s)}</option>' for s in data["symbols"])
    target = out_dir / "event-impact.html"
    out_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenPaw · Event impact</title>
<style>body{{font:14px system-ui;margin:0;background:#f5f4ef;color:#21231f}}main{{max-width:1100px;margin:auto;padding:28px}}h1{{font:40px Georgia;font-weight:500}}.controls{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}select{{padding:10px;border:1px solid #ccc;border-radius:6px;background:#fffefa}}table{{border-collapse:collapse;width:100%;background:#fffefa;margin:12px 0 24px}}td,th{{padding:11px;text-align:right;border-bottom:1px solid #ddd}}td:first-child,th:first-child{{text-align:left}}.up{{color:#176b3a}}.down{{color:#ae3d35}}a{{color:#955424}}.note{{color:#65685f;font-size:12px}}.comment{{border-top:1px solid #ddd;padding:10px 0}}.comment p{{margin:6px 0}}.comment .meta{{font-size:12px;color:#65685f}}code{{background:#efece4;padding:1px 5px;border-radius:4px}}</style><main><p>OPENPAW / EVENT STUDY</p><h1>Price response around macro events</h1><p>Choose a release type and date to see the magnitude across every available instrument. Returns use the last trading close before the release and the next 1, 5, or 20 sessions. Timing is association, not causation.</p><div class="controls"><label>Event <select id="type"></select></label><label>Date <select id="date"></select></label><label>Focus <select id="symbol">{options}</select></label></div><p id="source"></p><h2>All instruments</h2><p class="note">Positive values are gains; negative values are losses. The largest absolute move is highlighted by the data, without claiming the event caused it.</p><table><thead><tr><th>Instrument</th><th>Release session</th><th>+1 session</th><th>+5 sessions</th><th>+20 sessions</th></tr></thead><tbody id="matrix"></tbody></table><h2>Focused instrument</h2><table><thead><tr><th>Window</th><th>Return</th></tr></thead><tbody id="body"></tbody></table><h2>Event context</h2><div id="context"></div><h2>Community commentary (Reddit)</h2><p class="note">Reddit comments are community commentary, not verified facts or causal explanations.</p><div id="reddit"></div></main><script type="application/json" id="data">{payload}</script><script>const d=JSON.parse(document.getElementById('data').textContent),$=x=>document.getElementById(x),types=[...new Set(d.events.map(e=>e.type))];function esc(s){{return String(s).replace(/[&<>"']/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}});}}function contextHtml(e){{const c=e.context;const dec=c.decision?`${{esc(c.decision.action)}} (${{esc(String(c.decision.change_bp))}} bp) → ${{esc(String(c.decision.target_range))}}`:'n/a';return `<p><strong>${{esc(c.subtype)}}</strong> · ${{esc(c.summary)}}</p><p class="note">Affected variable: ${{esc(c.affected_variable)}} · Decision: ${{dec}} · Surprise vs expectations: not tracked · Calendar as of ${{esc(c.source_timestamp)}}</p>`;}}function redditHtml(e){{const r=e.reddit||{{status:'not_collected',comments:[]}};if(r.status==='not_collected')return '<p class="note">No Reddit data collected for this event yet. Run <code>portfolio-analysis collect-reddit</code> to gather it.</p>';if(r.status==='no_results')return '<p class="note">No Reddit comments found in this event window.</p>';if(r.status!=='ok')return `<p class="note">Reddit collection status: ${{esc(r.status)}}. Prior evidence is unchanged; rerun <code>portfolio-analysis collect-reddit</code> to retry.</p>`;if(!r.comments.length)return '<p class="note">No usable Reddit comments in this window.</p>';return r.comments.map(function(cm){{const sub=esc(cm.subreddit),who=esc(cm.author);const link=cm.url&&cm.url.indexOf('https://www.reddit.com/')===0?`<a href="${{esc(cm.url)}}" target="_blank" rel="noopener">r/${{sub}}</a>`:`r/${{sub}}`;const when=new Date(cm.created_utc*1000).toISOString().slice(0,16).replace('T',' ')+' UTC';return `<div class="comment"><p class="meta">${{link}} · u/${{who}} · score ${{cm.score}} · ${{when}}</p><p>${{esc(cm.excerpt)}}</p></div>`;}}).join('');}}$('type').innerHTML=types.map(x=>`<option>${{x}}</option>`).join('');function dates(){{const t=$('type').value;$('date').innerHTML=d.events.filter(e=>e.type===t).map(e=>`<option value="${{e.date}}">${{e.date}}</option>`).join('');}}function cell(v){{return v==null?'n/a':(v*100).toFixed(2)+'%';}}function draw(){{const e=d.events.find(e=>e.type===$('type').value&&e.date===$('date').value),s=$('symbol').value,i=e.impact[s];$('source').innerHTML=`<a href="${{e.url}}" target="_blank">Source calendar</a> · ${{e.type}} release on ${{e.date}}`;$('matrix').innerHTML=d.symbols.map(x=>{{const m=e.impact[x];return `<tr><td><strong>${{x}}</strong></td>${{[m.before_1d,m.after_1d,m.after_5d,m.after_20d].map(v=>`<td class="${{v>=0?'up':'down'}}">${{cell(v)}}</td>`).join('')}}</tr>`;}}).join('');const rows=[['Release session vs prior close',i.before_1d],['1 session after',i.after_1d],['5 sessions after',i.after_5d],['20 sessions after',i.after_20d]];$('body').innerHTML=rows.map(([n,v])=>`<tr><td>${{n}}</td><td class="${{v>=0?'up':'down'}}">${{cell(v)}}</td>`).join('');$('context').innerHTML=contextHtml(e);$('reddit').innerHTML=redditHtml(e);}}$('type').onchange=()=>{{dates();draw();}};$('date').onchange=draw;$('symbol').onchange=draw;dates();draw();</script>''')
    rendered = target.read_text()
    rendered = rendered.replace(
        '<p id="source"></p>',
        '<p id="source"></p><p id="decision" class="note"></p>',
    )
    rendered += "<script>function showDecision(){const e=d.events.find(e=>e.type===type.value&&e.date===date.value);const x=document.getElementById('decision');if(e&&e.action){const label=e.action==='hold'?'held the target range':e.action==='hike'?'raised the target range':'lowered the target range';x.textContent=`FOMC decision: ${label} (${e.change_bp>0?'+':''}${e.change_bp} bp); target ${e.target_range}. Policy source: ${e.decision_source}`;}else{x.textContent='';}}type.addEventListener('change',showDecision);date.addEventListener('change',showDecision);showDecision();</script>"
    target.write_text(rendered)
    return target
