"""Serial event backfill, resumable at both request and bundle boundaries."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from portfolio_analysis.artifacts import read_moves
from portfolio_analysis.bundle import (
    COLLECTOR_VERSION,
    build_bundle,
    canonical,
    move_payload,
    reusable,
    write_bundle,
)
from portfolio_analysis.calendar import TradingCalendar
from portfolio_analysis.config import Portfolio, PortfolioEntry
from portfolio_analysis.events.base import EventSource, dated_fact_label
from portfolio_analysis.events.earnings import EarningsSource
from portfolio_analysis.events.edgar import EdgarSource
from portfolio_analysis.events.hn import HackerNewsSource
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.news import NewsSource
from portfolio_analysis.http import CachedHttp, ProviderError, QuotaExhausted, atomic_json
from portfolio_analysis.moves import Move
from portfolio_analysis.store import Store


@dataclass(frozen=True)
class CollectionResult:
    completed: int
    remaining: int
    deferred: int
    quota_exhausted: bool = False


def event_sources(
    http: CachedHttp,
    entry: PortfolioEntry,
    macro: MacroSource,
    api_key: str,
) -> list[EventSource]:
    sources: list[EventSource] = [
        EdgarSource(http.get_json, cik=entry.cik),
        macro,
        HackerNewsSource(
            http.get_json,
            query=entry.aliases[0] if entry.aliases else entry.symbol,
            aliases=entry.aliases[1:],
        ),
    ]
    if api_key:
        sources.extend(
            [
                EarningsSource(http.get_json, api_key=api_key),
                NewsSource(http.get_json, api_key=api_key),
            ]
        )
    return sources


#: Fact keys that pin an event to a calendar day and may seed chart
#: annotations independently of the move filter. Forum/news chatter
#: (Documents, not verified facts) is deliberately excluded: only dated,
#: source-record facts earn an annotation.
_CATALOG_KINDS = {
    "filing": "filing",
    "earnings_reported": "earnings",
    "macro_release": "macro",
}


def write_event_catalog(
    *,
    portfolio: Portfolio,
    symbols: list[str],
    db: Path,
    events_dir: Path,
    http: CachedHttp,
    macro: MacroSource,
    api_key: str,
    report: Callable[[str], None] = print,
) -> None:
    """Write ``events_dir/<ticker>/event_dates.json`` per ticker.

    Dated events (earnings, SEC filings, macro releases) collected over the
    full price history, independent of the unusual-move filter: the event,
    not the move size, earns a chart annotation. Verified facts only -
    Reddit/HN/news documents are not dated evidence. A source that fails
    (quota, provider error, bad payload) is skipped with a report line; the
    catalog still writes whatever the other sources found.
    """
    store = Store.open(db)
    try:
        sessions = store.adjusted_series(portfolio.benchmark)
    finally:
        store.close()
    if not sessions:
        return
    start, end = min(sessions), max(sessions)
    for ticker in symbols:
        entry = portfolio.entry(ticker)
        dated: dict[str, list[dict[str, str]]] = {}
        # Only verified dated-fact sources. Forum/news sources are
        # deliberately not constructed here: their documents are chatter,
        # not dated evidence, and must never seed chart annotations.
        catalog_sources: list[EventSource] = [
            EdgarSource(http.get_json, cik=entry.cik),
            macro,
        ]
        if api_key:
            catalog_sources.append(EarningsSource(http.get_json, api_key=api_key))
        for source in catalog_sources:
            try:
                _, facts = source.collect(ticker, start, end)
            except (ProviderError, QuotaExhausted, ValueError, KeyError, TypeError) as exc:
                report(f"{ticker}: event catalog skipped {source.name} ({type(exc).__name__})")
                continue
            for fact in facts:
                labeled = dated_fact_label(fact.key, fact.value)
                if labeled is None:
                    continue
                label, day = labeled
                if not (start <= day <= end):
                    continue
                row = {
                    "kind": _CATALOG_KINDS[fact.key],
                    "label": label,
                    "date": day,
                    "detail": fact.detail,
                    # Sanitized with safe_url on read; stored raw here.
                    "url": str(fact.value.get("url") or fact.source),
                }
                bucket = dated.setdefault(day, [])
                if row not in bucket:
                    bucket.append(row)
        payload = {
            "schema_version": 1,
            "ticker": ticker,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "window": [start, end],
            "dates": {
                day: sorted(rows, key=lambda row: row["label"])
                for day, rows in sorted(dated.items())
            },
        }
        atomic_json(events_dir / ticker / "event_dates.json", payload)
        report(f"{ticker}: {len(dated)} dated events catalogued")


def collect_events(
    portfolio: Portfolio,
    symbols: list[str],
    *,
    db: Path,
    moves_dir: Path,
    events_dir: Path,
    http: CachedHttp,
    macro: MacroSource,
    only_date: str | None = None,
    rebuild: bool = False,
    keyless: bool = False,
    report: Callable[[str], None] = print,
) -> CollectionResult:
    api_key = "" if keyless else os.environ.get("ALPHAVANTAGE_API_KEY", "")
    store = Store.open(db)
    try:
        sessions = store.adjusted_series(portfolio.benchmark)
    finally:
        store.close()
    if not sessions:
        raise ValueError(f"no prices for {portfolio.benchmark}; run ingest-prices first")
    calendar = TradingCalendar(sessions)
    jobs: list[Move] = []
    for ticker in symbols:
        artifact = read_moves(moves_dir / f"{ticker}.json")
        if artifact.ticker != ticker or artifact.benchmark != portfolio.benchmark:
            raise ValueError("move artifact does not match configured ticker/benchmark")
        jobs.extend(move for move in artifact.moves if only_date is None or move.date == only_date)
    if only_date and not jobs:
        raise ValueError(f"no flagged move on {only_date}")
    completed = deferred = 0
    quota_exhausted = False
    for move in jobs:
        window = calendar.window(move.date, before=2, after=1)
        # Never spend a permanently cached news request on an unfinished window.
        if len(calendar.sessions_in(*window)) != 4:
            deferred += 1
            report(f"{move.ticker} {move.date}: deferred; [-2,+1] sessions not yet available")
            continue
        entry = portfolio.entry(move.ticker)
        sources = event_sources(http, entry, macro, api_key)
        missing = (
            {}
            if api_key
            else {"earnings": "missing_api_key", "alphavantage_news": "missing_api_key"}
        )
        key = hashlib.sha256(
            canonical(
                {
                    "collector_version": COLLECTOR_VERSION,
                    "move": move_payload(move),
                    "ticker": move.ticker,
                    "date": move.date,
                    "window": window,
                    "sources": sorted(source.name for source in sources),
                    "entry": {"cik": entry.cik, "aliases": entry.aliases},
                    "macro": macro.fingerprint,
                    "news_coverage_start": portfolio.news_coverage_start,
                }
            ).encode()
        ).hexdigest()
        target = events_dir / move.ticker / f"{move.date}.json"
        if not rebuild and reusable(target, key):
            completed += 1
            report(f"{move.ticker} {move.date}: reused")
            continue
        try:
            bundle = build_bundle(
                move,
                window=window,
                sources=sources,
                news_coverage_start=portfolio.news_coverage_start,
                source_status=missing,
                macro_coverage=macro.coverage(*window),
                collection_key=key,
            )
        except QuotaExhausted:
            quota_exhausted = True
            break
        except (KeyError, TypeError, ValueError) as exc:
            # Vendor payloads may contain credentials: don't put raw data in errors.
            raise ProviderError(
                f"{move.ticker} {move.date}: invalid source data ({type(exc).__name__})"
            ) from None
        write_bundle(events_dir, bundle)
        completed += 1
        coverage = bundle["coverage"]
        report(
            f"{move.ticker} {move.date}: {coverage['documents']} documents; "
            f"coverage {'complete' if coverage['complete'] else 'partial'} -> {target}"
        )
    # The dated-event catalog is independent of the move filter: even when
    # move collection hit quota, earnings/SEC/macro dates are cheap to
    # catalog and seed chart annotations on their own.
    write_event_catalog(
        portfolio=portfolio,
        symbols=symbols,
        db=db,
        events_dir=events_dir,
        http=http,
        macro=macro,
        api_key=api_key,
        report=report,
    )
    return CollectionResult(completed, len(jobs) - completed, deferred, quota_exhausted)
