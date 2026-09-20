"""Local, evidence-first bearish research. Standard library only; no trading or messaging."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from alerts import format_alert, qualifying

ROOT = Path(__file__).resolve().parent
STATUSES = {'self_disclosed', 'historical_filing', 'reported_unverified', 'reported_closed'}


def load_research(path=ROOT / 'data/research.json'):
    data = json.loads(path.read_text())
    sources = {s['id']: s for s in data['sources']}
    people = {p['id'] for p in data['investors']}
    if len(sources) != len(data['sources']):
        raise ValueError('Duplicate source ID')
    for source in sources.values():
        if urllib.parse.urlparse(source['url']).scheme != 'https':
            raise ValueError('Sources must use HTTPS')
    for group in ('positions', 'risks', 'discussions', 'events', 'reported_reactions', 'investors'):
        for row in data[group]:
            if not row.get('sources') or any(s not in sources for s in row['sources']):
                raise ValueError(f'Missing source in {group}')
    for p in data['positions']:
        if p['status'] not in STATUSES or p['investor'] not in people:
            raise ValueError('Invalid position attribution')
        if p['status'] == 'self_disclosed' and not any(sources[s]['kind'] == 'investor' for s in p['sources']):
            raise ValueError('Self-disclosed position needs primary investor evidence')
        if p['status'] == 'historical_filing' and not any(sources[s]['kind'] == 'filing' for s in p['sources']):
            raise ValueError('Historical filing needs a filing source')
        if p['as_of'] > data['research_as_of']:
            raise ValueError('Position postdates research cutoff')
    return data


def window_return(asset, benchmark, event_date, timing, sessions):
    """Use benchmark sessions, exact endpoints and a strictly preceding baseline.

    After-close releases use the next session. Unknown times produce a labeled
    date-window proxy, never a claim to isolate a post-release reaction.
    """
    calendar = sorted(benchmark)
    eligible = [d for d in calendar if d > event_date or (d == event_date and timing != 'after_close')]
    if not eligible:
        return {'status': 'unavailable', 'reason': 'No benchmark sessions after publication'}
    first = calendar.index(eligible[0])
    end_index = first + sessions - 1
    if first == 0 or end_index >= len(calendar):
        return {'status': 'unavailable', 'reason': 'Full benchmark window not yet available'}
    start, end = calendar[first - 1], calendar[end_index]
    dates = calendar[first - 1:end_index + 1]
    if any(d not in asset or not math.isfinite(asset[d]) or asset[d] <= 0 or not math.isfinite(benchmark[d]) or benchmark[d] <= 0 for d in dates):
        return {'status': 'unavailable', 'reason': 'Missing or invalid prices in required session window'}
    ret = asset[end] / asset[start] - 1
    bench = benchmark[end] / benchmark[start] - 1
    return {'status': 'available', 'baseline': start, 'first_session': calendar[first], 'end': end,
            'stock_return': ret, 'benchmark_return': bench, 'excess_return': ret - bench,
            'timing': 'date-window proxy; publication time unknown' if timing == 'unknown' else 'after-close publication; next session start'}


def market_data(data, db):
    if not db.is_file():
        return {'status': 'unavailable', 'reason': 'Price database missing', 'rows': [], 'coverage': {}}
    con = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True)
    symbols = {'QQQ'} | {t for event in data['events'] for t in event['tickers']}
    prices, coverage = {}, {}
    try:
        for symbol in sorted(symbols):
            rows = con.execute('SELECT date, adj_close, source, fetched_at FROM price_bar WHERE ticker=? AND date<=? ORDER BY date', (symbol, data['research_as_of'])).fetchall()
            prices[symbol] = {r[0]: r[1] for r in rows}
            coverage[symbol] = {'first': rows[0][0] if rows else None, 'last': rows[-1][0] if rows else None,
                                'source': sorted({r[2] for r in rows}), 'last_fetch': max((r[3] for r in rows), default=None)}
    finally:
        con.close()
    result = []
    for event in data['events']:
        for symbol in event['tickers']:
            for sessions in (1, 5, 20):
                row = window_return(prices[symbol], prices['QQQ'], event['date'], event['timing'], sessions)
                result.append(dict(event=event['id'], label=event['label'], investor=event['investor'], ticker=symbol,
                                   sessions=sessions, sources=event['sources'], confounders=event['confounders'], **row))
    return {'status': 'read_only_saved_prices', 'benchmark': 'QQQ', 'coverage': coverage, 'rows': result,
            'method': 'Adjusted-close cumulative return minus QQQ cumulative return over the same 1/5/20 trading sessions. This is simple benchmark excess, not beta-adjusted abnormal return, causation or investor P&L.'}


def markdown(data):
    sources = {s['id']: s for s in data['sources']}
    names = {p['id']: p['name'] for p in data['investors']}
    def refs(ids):
        return ' '.join(f"[{sources[i]['title']}]({sources[i]['url']})" for i in ids)
    lines = [f"# Bearish Challenger — {data['research_as_of']}", '', data['scope'], '',
             '## Reported positions', '', '| Investor | Ticker | Instrument | Evidence | As of |', '|---|---|---|---|---|']
    for p in data['positions']:
        lines.append(f"| {names[p['investor']]} | {p['ticker']} | {p['instrument']} | {p['status']} | {p['as_of']} |")
    for p in data['positions']:
        lines += ['', f"**{p['ticker']} / {p['instrument']}:** {p['note']} {refs(p['sources'])}"]
    lines += ['', '## Investors', '']
    for person in data['investors']:
        lines += [f"### {person['name']}", '', person['summary'], refs(person['sources']), '']
    lines += ['## Bearish risk chains', '']
    for risk in data['risks']:
        lines += [f"### {risk['title']}", '', f"Fact / sourced statement: {risk['fact']}", '',
                  f"Thesis: {risk['argument']}", '', ' → '.join(risk['chain']), '',
                  'Monitor: ' + '; '.join(risk['watch']), '',
                  risk['attribution'], refs(risk['sources']), '']
    lines += ['## X and Reddit', '']
    for d in data['discussions']:
        lines += [f"- **{d['date']} · {d['platform']} · {d['title']}** — {d['summary']} ({d['quality']}) {refs(d['sources'])}"]
    lines += ['', '## Market reaction', '', data['market'].get('method', data['market'].get('reason', '')), '',
              '| Event | Ticker | Sessions | Baseline → End | Stock | Excess vs QQQ |', '|---|---|---|---|---|---|']
    for r in data['market']['rows']:
        if r['status'] == 'available':
            lines.append(f"| {r['label']} | {r['ticker']} | {r['sessions']} | {r['baseline']} → {r['end']} | {r['stock_return']:+.2%} | {r['excess_return']:+.2%} |")
        else:
            lines.append(f"| {r['label']} | {r['ticker']} | {r['sessions']} | {r['reason']} | unavailable | unavailable |")
    for event in data['events']:
        lines += ['', f"{event['label']}: {event['confounders']} {refs(event['sources'])}"]
    for r in data['reported_reactions']:
        lines += ['', f"{r['date']}: {r['summary']} {refs(r['sources'])}"]
    lines += ['', '## Coverage and interpretation', '']
    for c in data['coverage']:
        lines.append(f"- **{c['channel']} — {c['status']}:** {c['detail']}")
    lines += ['', *['- ' + rule for rule in data['rules']], '', '## Price coverage', '', '```json', json.dumps(data['market']['coverage'], indent=2), '```', '']
    return '\n'.join(lines)


def build(db):
    data = load_research()
    data['market'] = market_data(data, db)
    data['built_at'] = datetime.now(timezone.utc).isoformat()
    inbox = ROOT / 'data/inbox.json'
    status = ROOT / 'data/collection-status.json'
    data['inbox'] = json.loads(inbox.read_text()) if inbox.exists() else []
    data['collection'] = json.loads(status.read_text()) if status.exists() else []
    payload = json.dumps(data, ensure_ascii=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    (ROOT / 'index.html').write_text((ROOT / 'template.html').read_text().replace('__DATA__', payload))
    (ROOT / 'reports/latest.md').write_text(markdown(data))
    (ROOT / 'data/market-reactions.json').write_text(json.dumps(data['market'], indent=2) + '\n')
    print('Dashboard:', ROOT / 'index.html')
    print('Report:', ROOT / 'reports/latest.md')


def parse_feed(raw, channel):
    tree = ET.fromstring(raw)
    atom = '{http://www.w3.org/2005/Atom}'
    records = []
    for item in list(tree.findall('.//item')) + list(tree.findall('.//' + atom + 'entry')):
        title = item.findtext('title') or item.findtext(atom + 'title') or ''
        link = item.findtext('link')
        if not link:
            candidates = item.findall(atom + 'link')
            link = next((n.get('href') for n in candidates if n.get('rel', 'alternate') == 'alternate'), None)
        if not link or urllib.parse.urlparse(link).scheme not in {'https', 'http'}:
            continue
        date = item.findtext('pubDate') or item.findtext(atom + 'published') or item.findtext(atom + 'updated')
        records.append({'id': hashlib.sha256((channel + '\n' + link).encode()).hexdigest()[:20],
                        'channel': channel, 'title': title, 'url': link, 'published': date,
                        'status': 'unreviewed_lead'})
    return records


def collect():
    """Collect feed metadata only. Never promote headlines to position evidence."""
    feeds = {'burry-primary': 'https://michaeljburry.substack.com/feed',
             'eisman-primary': 'https://realeismanplaybook.substack.com/feed'}
    for name in ('Michael Burry', 'Steve Eisman', 'Jeremy Grantham'):
        q = urllib.parse.urlencode({'q': '"' + name + '" AI', 'sort': 'new', 't': 'month', 'limit': '25'})
        feeds['reddit-' + name] = 'https://www.reddit.com/search.rss?' + q
    path = ROOT / 'data/inbox.json'
    existing = {r['id']: r for r in json.loads(path.read_text())} if path.exists() else {}
    statuses = []
    checked = datetime.now(timezone.utc).isoformat()
    for channel, url in feeds.items():
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'bearish-challenger/0.1 (personal research; feed metadata)'})
            with urllib.request.urlopen(request, timeout=12) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError('Feed exceeds 2 MB limit')
            records = parse_feed(raw, channel)
            for row in records:
                old = existing.get(row['id'], {})
                existing[row['id']] = dict(row, first_seen=old.get('first_seen', checked), last_seen=checked)
            statuses.append(dict(channel=channel, url=url, checked=checked, status='ok' if records else 'empty_feed', count=len(records)))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
            statuses.append(dict(channel=channel, url=url, checked=checked, status='failed', detail=str(exc)))
        print(channel + ': ' + statuses[-1]['status'], flush=True)
    statuses.append(dict(channel='X', checked=checked, status='manual_review_only', detail='No authenticated X API connection. Use source permalinks and record access limits.'))
    path.write_text(json.dumps(list(existing.values()), indent=2) + '\n')
    (ROOT / 'data/collection-status.json').write_text(json.dumps(statuses, indent=2) + '\n')
    return 1 if any(s['status'] == 'failed' for s in statuses) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'collect', 'report', 'alerts'])
    parser.add_argument('--db', type=Path, default=ROOT.parent / 'portfolio-analysis/data/prices.sqlite')
    args = parser.parse_args()
    if args.command == 'alerts':
        track = json.loads((ROOT / 'track.json').read_text())
        signals = json.loads((ROOT / 'data/signals.json').read_text())
        delivered_path = ROOT / 'data/delivered.json'
        delivered = json.loads(delivered_path.read_text()) if delivered_path.exists() else []
        for signal in qualifying(signals, track, delivered):
            print(format_alert(signal) + '\n')
        return 0
    if args.command == 'collect':
        return collect()
    if args.command == 'build':
        build(args.db)
    else:
        data = load_research()
        data['market'] = market_data(data, args.db)
        print(markdown(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
