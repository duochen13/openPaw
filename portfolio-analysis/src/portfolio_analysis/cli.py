"""Command-line entry point.

This tool explains past price moves. It has no brokerage integration, places
no orders, and produces no forward-looking signal (spec §2).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from portfolio_analysis import freshness, fundamentals, prices
from portfolio_analysis import kpis as kpis_module
from portfolio_analysis import moves as moves_module
from portfolio_analysis import positions as positions_module
from portfolio_analysis.artifacts import MovesArtifact, write_moves
from portfolio_analysis.collection import collect_events
from portfolio_analysis.config import PROJECT_ROOT, Portfolio, load_portfolio
from portfolio_analysis.dashboard import render_dashboard
from portfolio_analysis.event_dashboard import event_dashboard_data, render_event_dashboard
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.reddit import collect_reddit_for_events
from portfolio_analysis.factor_dashboard import (
    factor_dashboard_data,
    render_factor_dashboard,
)
from portfolio_analysis.http import (
    CachedHttp,
    ProviderError,
    QuotaExhausted,
    RateLimitLedger,
)
from portfolio_analysis.render import render_chart
from portfolio_analysis.store import Store


def _selected_symbols(portfolio: Portfolio, requested: str | None) -> list[str] | None:
    """The universe, or the single resolved symbol. None means unresolvable."""
    if requested is None:
        return list(portfolio.chart_symbols)
    symbol = portfolio.resolve(requested)
    return None if symbol is None else [symbol]


def _price_targets(portfolio: Portfolio, symbols: list[str]) -> list[str]:
    """Every ticker a price ingest fetches: the symbols, each symbol's
    benchmark, and the industry benchmarks that ride along with the compare
    view."""
    targets = list(symbols)
    for symbol in symbols:
        bench = portfolio.benchmark_for(symbol)
        if bench not in targets:
            targets.append(bench)
        industry = portfolio.industry_benchmark(symbol)
        if industry and industry not in targets:
            targets.append(industry)
    return targets


def _check_benchmarks(portfolio: Portfolio, symbols: list[str]) -> str | None:
    """Refuse a self-benchmark before any work starts (#57).

    A symbol measured against itself yields alpha = 0, beta = 1 by
    construction - a chart that says nothing. Returns the error message,
    or None when every symbol has a proper benchmark.
    """
    for symbol in symbols:
        try:
            portfolio.benchmark_for(symbol)
        except ValueError as exc:
            return str(exc)
    return None


def _ingest_prices(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, getattr(args, "ticker", None))
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2

    # The benchmark is fetched alongside the universe, never separately. Beta
    # cannot be computed without it, so an ingest that skips it leaves a store
    # that looks complete and is not. Industry benchmarks ride along the same
    # way: the compare view cannot draw the third line without them.
    targets = _price_targets(portfolio, symbols)

    store = Store.open(args.db or portfolio.path("db"))
    try:
        for symbol in targets:
            bars = prices.fetch_yahoo(
                symbol,
                years=portfolio.price_years,
                yahoo_ticker=portfolio.yahoo_ticker(symbol),
            )
            written = store.upsert_price_bars(bars)
            first = bars[0]["date"] if bars else "-"
            last = bars[-1]["date"] if bars else "-"
            print(f"{symbol}: {written} bar(s) upserted, {first} .. {last}")
    finally:
        store.close()
    return 0


#: Fundamentals refresh interval. Quarterly EPS changes on earnings day;
#: re-fetching daily keeps the store fresh without hammering the vendor.
_FUNDAMENTALS_TTL = timedelta(hours=24)


def _fundamentals_fresh(store: Store, symbol: str) -> bool:
    fetched_at = store.eps_fetched_at(symbol)
    if not fetched_at:
        return False
    try:
        age = datetime.now(UTC) - datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    return age < _FUNDAMENTALS_TTL


def _kpi_fresh(store: Store, symbol: str, metric_keys: list[str]) -> bool:
    if not metric_keys:
        return True
    fetched_at = store.kpi_fetched_at(symbol)
    if not fetched_at:
        return False
    try:
        age = datetime.now(UTC) - datetime.fromisoformat(fetched_at)
    except ValueError:
        return False
    return age < _FUNDAMENTALS_TTL


#: Sessions behind the last completed one before a build warns on stderr.
_STALE_WARN_SESSIONS = 2


def _latest_bar_day(store: Store, symbol: str) -> date | None:
    """The latest stored price date for a symbol, or None when empty."""
    series = store.adjusted_series(symbol)
    if not series:
        return None
    return date.fromisoformat(max(series))


def _prices_need_refresh(
    portfolio: Portfolio, store: Store, symbols: list[str], now: datetime
) -> tuple[bool, int]:
    """Check every ingest target; refresh if any bar predates the last
    completed session. Returns (needed, worst_sessions_behind)."""
    needed = False
    worst = 0
    for symbol in _price_targets(portfolio, symbols):
        stale, behind = freshness.price_staleness(_latest_bar_day(store, symbol), now)
        needed = needed or stale
        worst = max(worst, behind)
    return needed, worst


def _fundamentals_need_refresh(portfolio: Portfolio, store: Store, symbols: list[str]) -> bool:
    """True when any symbol's EPS or KPI fetch is older than the TTL."""
    try:
        kpi_config = kpis_module.load_kpi_config()
    except kpis_module.ConfigError:
        kpi_config = {}
    for symbol in symbols:
        # Symbols without fundamentals (indices) have nothing to fetch.
        if portfolio.is_index(symbol):
            continue
        if not _fundamentals_fresh(store, symbol):
            return True
        if not _kpi_fresh(store, symbol, kpi_config.get(symbol, [])):
            return True
    return False


def _refresh_if_stale(args: argparse.Namespace, portfolio: Portfolio, symbols: list[str]) -> int:
    """Freshness pre-flight for the user-facing triggers (#56).

    - `--offline`: fetches nothing, exactly like the old default.
    - `--refresh`: forces both price ingest and fundamentals refetch.
    - otherwise: ingest prices only when the latest bar is older than the
      last completed trading session; refetch fundamentals only when the
      stored fetch is older than the TTL (fresh symbols are skipped).
    """
    if getattr(args, "offline", False):
        return 0
    force = getattr(args, "force", False) or getattr(args, "refresh", False)
    if getattr(args, "refresh", False):
        args.refresh_prices = True
    # _fetch_fundamentals reads args.force directly; the dashboard parser
    # does not define --force, so make sure the attribute exists.
    args.force = force
    db = args.db or portfolio.path("db")
    store = Store.open(db)
    try:
        now = datetime.now(UTC)
        price_stale, _ = _prices_need_refresh(portfolio, store, symbols, now)
        missing = any(
            not store.price_bar_count(target) for target in _price_targets(portfolio, symbols)
        )
        fund_stale = _fundamentals_need_refresh(portfolio, store, symbols)
    finally:
        store.close()
    if (getattr(args, "refresh_prices", False) or price_stale or missing) and _ingest_prices(
        args
    ):
        return 1
    if (getattr(args, "force", False) or fund_stale) and _fetch_fundamentals(args):
        return 1
    return 0


def _warn_if_price_stale(
    args: argparse.Namespace, portfolio: Portfolio, symbols: list[str]
) -> None:
    """Stderr warning when the build runs on data >= 2 sessions old, so a
    skipped or failed fetch is loud instead of silent."""
    store = Store.open(args.db or portfolio.path("db"))
    try:
        _, behind = _prices_need_refresh(portfolio, store, symbols, datetime.now(UTC))
    finally:
        store.close()
    if behind >= _STALE_WARN_SESSIONS:
        print(
            f"warning: building on prices {behind} trading sessions behind "
            "the last completed session; run with --refresh to update",
            file=sys.stderr,
        )


def _fetch_fundamentals(args: argparse.Namespace) -> int:
    """Fetch quarterly fundamentals from SEC EDGAR for the universe.

    One companyfacts fetch per ticker backs both the P/E panel (issue #28,
    quarterly diluted EPS) and the business-KPI section (issue #29,
    config/kpi_metrics.yaml). A network/provider failure keeps stored data
    rather than crash, same as before.
    """
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, getattr(args, "ticker", None))
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2

    try:
        kpi_config = kpis_module.load_kpi_config()
    except kpis_module.ConfigError as exc:
        # KPIs are additive: a broken KPI config must not take down EPS.
        print(f"fetch-fundamentals: {exc}; continuing with EPS only")
        kpi_config = {}

    cache = portfolio.path("cache")
    http = CachedHttp(cache, ledger=RateLimitLedger(cache / "quota.json"))
    store = Store.open(args.db or portfolio.path("db"))
    try:
        for symbol in symbols:
            if portfolio.is_index(symbol):
                # Indices have no CIK and no EDGAR fundamentals; their
                # charts render those sections as n/a (#57).
                print(f"{symbol}: index has no fundamentals; skipping")
                continue
            metric_keys = kpi_config.get(symbol, [])
            if (
                not args.force
                and _fundamentals_fresh(store, symbol)
                and _kpi_fresh(store, symbol, metric_keys)
            ):
                print(f"{symbol}: fresh, skipping (use --force to refetch)")
                continue
            cik = portfolio.entry(symbol).cik
            try:
                facts = fundamentals.fetch_companyfacts(cik, http.get_json)
                quarters = fundamentals.parse_quarterly_eps(facts)
            except (
                fundamentals.VendorResponseError,
                ProviderError,
                QuotaExhausted,
            ) as exc:
                print(f"{symbol}: fetch failed, keeping stored quarters: {exc}")
                continue
            rows = [
                {
                    "ticker": symbol,
                    "quarter": q["quarter"],
                    "filed": q["filed"],
                    "eps": q["eps"],
                    "source": "edgar",
                }
                for q in quarters
            ]
            written = store.upsert_eps_quarters(rows)
            first = quarters[0]["quarter"] if quarters else "-"
            last = quarters[-1]["quarter"] if quarters else "-"
            print(f"{symbol}: {written} quarter(s) upserted, {first} .. {last}")
            # Operating EPS (ex-investment gains, issue #70): derived from
            # the same companyfacts at fetch time; the upsert is idempotent
            # so refetch rewrites restated quarters cleanly.
            op_quarters = fundamentals.parse_operating_eps(facts)
            op_rows = [
                {
                    "ticker": symbol,
                    "quarter": q["quarter"],
                    "filed": q["filed"],
                    "eps": q["eps"],
                    "source": "derived:ex-investment-gains",
                }
                for q in op_quarters
            ]
            op_written = store.upsert_operating_eps_quarters(op_rows)
            op_adjusted = sum(1 for q in op_quarters if q["eps"] is not None)
            print(
                f"{symbol}: {op_written} operating EPS quarter(s) upserted "
                f"({op_adjusted} with values)"
            )
            if metric_keys:
                kpi_series = kpis_module.build_kpi_series(facts, metric_keys)
                kpi_rows = [
                    {
                        "ticker": symbol,
                        "metric": key,
                        "quarter": q,
                        "filed": f,
                        "value": v,
                        "source": "edgar",
                    }
                    for key, series in kpi_series.items()
                    for q, f, v in series
                ]
                kpi_written = store.upsert_kpi_quarters(kpi_rows)
                missing = sorted(k for k in metric_keys if k not in kpi_series)
                detail = f" ({', '.join(sorted(kpi_series))})" if kpi_series else ""
                if missing:
                    detail += f"; no EDGAR data for {', '.join(missing)}"
                print(f"{symbol}: {kpi_written} KPI quarter(s) upserted{detail}")
    finally:
        store.close()
    return 0


def _detect_moves(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2
    if error := _check_benchmarks(portfolio, symbols):
        print(f"detect-moves: {error}", file=sys.stderr)
        return 2

    moves_dir = Path(args.moves_dir) if args.moves_dir else portfolio.path("moves")
    store = Store.open(args.db or portfolio.path("db"))
    try:
        benchmark_series: dict[str, dict[str, float]] = {}
        for symbol in symbols:
            benchmark = portfolio.benchmark_for(symbol)
            if benchmark not in benchmark_series:
                series = store.adjusted_series(benchmark)
                if not series:
                    print(
                        f"no prices for benchmark {benchmark}; "
                        "run `ingest-prices` first - beta cannot be computed without it",
                        file=sys.stderr,
                    )
                    return 1
                benchmark_series[benchmark] = series

        for symbol in symbols:
            benchmark = portfolio.benchmark_for(symbol)
            asset_series = store.adjusted_series(symbol)
            if not asset_series:
                print(f"no prices for {symbol}; run `ingest-prices` first", file=sys.stderr)
                return 1

            found, coverage = moves_module.compute_moves(
                symbol,
                benchmark,
                asset_series,
                benchmark_series[benchmark],
                portfolio.move_params,
            )
            store.replace_moves(symbol, [m.as_row() for m in found])
            path = write_moves(
                moves_dir,
                MovesArtifact(
                    ticker=symbol,
                    benchmark=benchmark,
                    params=portfolio.move_params,
                    coverage=coverage,
                    moves=found,
                ),
            )
            evaluated = (
                f"{coverage.evaluated[0]} .. {coverage.evaluated[1]}"
                if coverage.evaluated
                else "none (series shorter than the beta window)"
            )
            print(
                f"{symbol}: {coverage.flagged_days} flagged of "
                f"{coverage.evaluated_days} evaluated ({evaluated}) -> {path}"
            )
    finally:
        store.close()
    return 0


def _collect_events(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(f"{args.ticker!r} is not in the portfolio", file=sys.stderr)
        return 2
    cache = Path(args.cache_dir) if args.cache_dir else portfolio.path("cache")
    http = CachedHttp(cache, ledger=RateLimitLedger(cache / "quota.json"))
    try:
        result = collect_events(
            portfolio,
            symbols,
            db=Path(args.db) if args.db else portfolio.path("db"),
            moves_dir=Path(args.moves_dir) if args.moves_dir else portfolio.path("moves"),
            events_dir=Path(args.events_dir) if args.events_dir else portfolio.path("events"),
            http=http,
            macro=MacroSource(Path(args.macro_calendar)),
            only_date=args.date,
            rebuild=args.rebuild,
            keyless=args.keyless,
        )
    except (OSError, ValueError, ProviderError) as exc:
        print(f"collect-events: {exc}", file=sys.stderr)
        return 1
    print(
        f"{result.completed} completed, {result.remaining} remaining "
        f"({result.deferred} awaiting sessions)"
        + ("; quota exhausted, rerun after reset" if result.quota_exhausted else "")
    )
    return 0


def _render(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(f"{args.ticker!r} is not in config/portfolio.yaml", file=sys.stderr)
        return 2
    if error := _check_benchmarks(portfolio, symbols):
        print(f"render: {error}", file=sys.stderr)
        return 2
    try:
        for symbol in symbols:
            target = render_chart(
                portfolio,
                symbol,
                db=Path(args.db) if args.db else portfolio.path("db"),
                moves_dir=Path(args.moves_dir) if args.moves_dir else portfolio.path("moves"),
                events_dir=Path(args.events_dir) if args.events_dir else portfolio.path("events"),
                out_dir=Path(args.out_dir) if args.out_dir else portfolio.path("out"),
            )
            print(f"{symbol}: chart written -> {target}")
    except (OSError, ValueError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 1
    return 0


def _dashboard(args: argparse.Namespace) -> int:
    """Multi-stock builds go stale the same way single charts do, so
    `dashboard` gets the identical freshness treatment as `chart` (#56)."""
    portfolio = load_portfolio()
    symbols = list(portfolio.chart_symbols)
    if _refresh_if_stale(args, portfolio, symbols):
        return 1
    _warn_if_price_stale(args, portfolio, symbols)
    try:
        target = render_dashboard(
            portfolio, Path(args.out_dir) if args.out_dir else portfolio.path("out")
        )
    except OSError as exc:
        print(f"dashboard: {exc}", file=sys.stderr)
        return 1
    print(f"dashboard written -> {target}")
    return 0


def _import_robinhood_csv(args: argparse.Namespace) -> int:
    """Import a Robinhood CSV export: positions snapshot or order history (#65).

    The flavor is auto-detected from the headers unless --kind forces one.
    Positions behavior is unchanged; an order-history CSV populates
    config/trades.yaml, which the per-stock dashboards render as buy/sell
    markers.
    """
    src = Path(args.file)
    if not src.is_file():
        print(f"import-robinhood-csv: no such file: {src}", file=sys.stderr)
        return 2
    kind = args.kind
    if kind == "auto":
        try:
            kind = positions_module.detect_robinhood_csv_kind(src)
        except ValueError as exc:
            print(f"import-robinhood-csv: {exc}", file=sys.stderr)
            return 1
    if kind == "orders":
        return _import_robinhood_orders(args, src)
    if args.start_date or args.end_date:
        print(
            "import-robinhood-csv: --start-date/--end-date only apply to order "
            "history; ignoring for a positions import",
            file=sys.stderr,
        )
    return _import_robinhood_positions(args, src)


def _import_robinhood_orders(args: argparse.Namespace, src: Path) -> int:
    """Import a Robinhood order-history CSV export into config/trades.yaml."""
    try:
        result = positions_module.parse_robinhood_orders_csv(
            src, start_date=args.start_date, end_date=args.end_date
        )
    except ValueError as exc:
        print(f"import-robinhood-csv: {exc}", file=sys.stderr)
        return 1
    if not result.trades:
        print(
            f"import-robinhood-csv: no buy/sell trades found in {src} "
            f"({len(result.skipped)} rows skipped, {result.filtered_out} filtered by date)",
            file=sys.stderr,
        )
        return 1
    print(f"trades from {src}:")
    for trade in result.trades:
        print(
            f"  {trade.date} {trade.side:4s} {trade.symbol:6s} "
            f"{trade.qty:>10g} @ ${trade.price:,.2f}"
        )
    for skip in result.skipped:
        print(f"  skipped row {skip.row} ({skip.symbol or '?'}): {skip.reason}")
    if result.filtered_out:
        print(f"  {result.filtered_out} trade(s) outside --start-date/--end-date")
    if args.dry_run:
        print("dry run: trades not written")
        return 0
    target = positions_module.write_trades(result, args.out)
    trades = positions_module.load_trades(target)
    assert trades is not None
    print(f"wrote {len(trades)} trades -> {target}")
    return 0


def _import_robinhood_positions(args: argparse.Namespace, src: Path) -> int:
    """Import a Robinhood positions CSV export into the holdings snapshot (#55).

    v1 is CSV-only and read-only: zero credentials, zero ToS risk. The
    snapshot is timestamped so a stale import is visible in the dashboards.
    """
    try:
        result = positions_module.parse_robinhood_csv(src)
    except ValueError as exc:
        print(f"import-robinhood-csv: {exc}", file=sys.stderr)
        return 1
    if not result.positions:
        print(
            f"import-robinhood-csv: no equity positions found in {src} "
            f"({len(result.skipped)} rows skipped)",
            file=sys.stderr,
        )
        return 1
    print(f"positions from {src}:")
    for pos in result.positions:
        print(f"  {pos.symbol:6s} {pos.shares:>10g} shares @ ${pos.avg_cost:,.2f}")
    for skip in result.skipped:
        print(f"  skipped row {skip.row} ({skip.symbol or '?'}): {skip.reason}")
    if args.dry_run:
        print("dry run: snapshot not written")
        return 0
    target = positions_module.write_snapshot(result, args.out)
    snapshot = positions_module.load_snapshot(target)
    assert snapshot is not None
    print(
        f"wrote {len(snapshot.positions)} positions -> {target} "
        f"(snapshot {snapshot.imported_at.isoformat()})"
    )
    return 0


def _factor_dashboard(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    store = Store.open(args.db or portfolio.path("db"))
    # Holdings are optional: a missing snapshot renders the page exactly as
    # before; a corrupt one fails loud instead of silently hiding positions.
    try:
        snapshot = positions_module.load_snapshot()
    except ValueError as exc:
        print(f"factor-dashboard: {exc}", file=sys.stderr)
        return 1
    try:
        data = factor_dashboard_data(portfolio, store, snapshot=snapshot)
    except ValueError as exc:
        print(f"factor-dashboard: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    try:
        target = render_factor_dashboard(
            data, Path(args.out_dir) if args.out_dir else portfolio.path("out")
        )
    except OSError as exc:
        print(f"factor-dashboard: {exc}", file=sys.stderr)
        return 1
    print(f"factor dashboard written -> {target}")
    return 0


def _event_dashboard(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    reddit_dir = (
        Path(args.reddit_dir)
        if args.reddit_dir
        else (portfolio.path("reddit") if "reddit" in portfolio.paths else None)
    )
    store = Store.open(args.db or portfolio.path("db"))
    try:
        data = event_dashboard_data(
            portfolio,
            store,
            MacroSource(Path(args.macro_calendar)),
            reddit_dir=reddit_dir,
        )
    finally:
        store.close()
    target = render_event_dashboard(
        data, Path(args.out_dir) if args.out_dir else portfolio.path("out")
    )
    print(f"event dashboard written -> {target}")
    return 0


def _collect_reddit(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    cache = Path(args.cache_dir) if args.cache_dir else portfolio.path("cache")
    if args.reddit_dir:
        reddit_dir = Path(args.reddit_dir)
    elif "reddit" in portfolio.paths:
        reddit_dir = portfolio.path("reddit")
    else:
        reddit_dir = PROJECT_ROOT / "data" / "reddit"
    reddit_dir.mkdir(parents=True, exist_ok=True)
    # Same CachedHttp + quota-ledger construction as collect-events: the
    # ledger at <cache>/quota.json is what makes collection resumable across
    # runs and quota exhaustion non-destructive.
    http = CachedHttp(cache, ledger=RateLimitLedger(cache / "quota.json"))
    try:
        result = collect_reddit_for_events(
            MacroSource(Path(args.macro_calendar)),
            reddit_dir,
            http,
            daily_limit=args.daily_limit,
            rebuild=args.rebuild,
        )
    except (OSError, ValueError, ProviderError) as exc:
        print(f"collect-reddit: {exc}", file=sys.stderr)
        return 1
    print(
        f"{result.completed} completed, {result.remaining} remaining"
        + ("; quota exhausted, rerun after reset" if result.quota_exhausted else "")
    )
    return 0


def _chart(args: argparse.Namespace) -> int:
    """The user-facing trigger: prices -> moves -> events -> HTML, no model calls.

    Freshness (#56): prices auto-refresh when the latest bar is older than
    the last completed trading session, fundamentals refetch only when the
    stored fetch is stale. --refresh forces both; --offline fetches nothing.
    """
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(
            f"{args.ticker!r} is not in config/portfolio.yaml; add its symbol and CIK first",
            file=sys.stderr,
        )
        return 2
    if error := _check_benchmarks(portfolio, symbols):
        print(f"chart: {error}", file=sys.stderr)
        return 2
    if _refresh_if_stale(args, portfolio, symbols):
        return 1
    _warn_if_price_stale(args, portfolio, symbols)
    result = _detect_moves(args)
    if result:
        return result
    event_result = 0
    if not args.skip_events:
        event_result = _collect_events(args)
        if event_result:
            print(
                "Event collection is incomplete; rendering the evidence available so far.",
                file=sys.stderr,
            )
    render_result = _render(args)
    return render_result or event_result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="portfolio-analysis",
        description="Retrospective attribution of large single-day equity moves.",
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest-prices", help="fetch adjusted daily bars")
    ingest.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    ingest.add_argument("--db", default=None, help="override the configured database")
    ingest.set_defaults(func=_ingest_prices)

    fetch_fund = sub.add_parser(
        "fetch-fundamentals",
        help="fetch quarterly fundamentals: EPS for P/E and business KPIs (#28, #29)",
    )
    fetch_fund.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    fetch_fund.add_argument("--db", default=None, help="override the configured database")
    fetch_fund.add_argument(
        "--force", action="store_true", help="refetch even if stored data is fresh"
    )
    fetch_fund.set_defaults(func=_fetch_fundamentals)

    import_csv = sub.add_parser(
        "import-robinhood-csv",
        help="import a Robinhood CSV export: positions snapshot or order history",
    )
    import_csv.add_argument("file", help="Robinhood positions or order-history CSV export")
    import_csv.add_argument(
        "--kind",
        choices=["auto", "positions", "orders"],
        default="auto",
        help="CSV flavor: auto-detect from headers (default), or force one",
    )
    import_csv.add_argument(
        "--out",
        default=None,
        help="output path (default config/positions.yaml, or config/trades.yaml for orders)",
    )
    import_csv.add_argument(
        "--start-date",
        default=None,
        help="orders only: keep trades on or after YYYY-MM-DD (default: all)",
    )
    import_csv.add_argument(
        "--end-date",
        default=None,
        help="orders only: keep trades on or before YYYY-MM-DD (default: all)",
    )
    import_csv.add_argument(
        "--dry-run", action="store_true", help="parse and print, write nothing"
    )
    import_csv.set_defaults(func=_import_robinhood_csv)

    detect = sub.add_parser("detect-moves", help="flag days whose abnormal return is large")
    detect.add_argument(
        "ticker",
        nargs="?",
        default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    detect.add_argument("--db", default=None, help="override the configured database")
    detect.add_argument(
        "--moves-dir", default=None, help="override the configured artifact directory"
    )
    detect.set_defaults(func=_detect_moves)

    collect = sub.add_parser("collect-events", help="assemble dated evidence for flagged moves")
    collect.add_argument("ticker", nargs="?", default=None)
    collect.add_argument("--db", default=None)
    collect.add_argument("--moves-dir", default=None)
    collect.add_argument("--events-dir", default=None)
    collect.add_argument("--cache-dir", default=None)
    collect.add_argument("--date", default=None, help="collect a single flagged YYYY-MM-DD")
    collect.add_argument(
        "--macro-calendar", default=str(PROJECT_ROOT / "config/macro_calendar.yaml")
    )
    collect.add_argument(
        "--rebuild", action="store_true", help="rebuild bundles using cached responses"
    )
    collect.add_argument("--keyless", action="store_true", help="collect SEC, HN and macro only")
    collect.set_defaults(func=_collect_events)

    render = sub.add_parser("render", help="build a self-contained price and event chart offline")
    dashboard = sub.add_parser(
        "dashboard", help="build an offline dashboard linking all configured stock charts"
    )
    dashboard.add_argument("--out-dir", default=None)
    dashboard.add_argument("--db", default=None)
    dashboard.add_argument(
        "--refresh",
        action="store_true",
        help="force price ingest and fundamentals refetch before building",
    )
    dashboard.add_argument(
        "--offline", action="store_true", help="fetch nothing; build from stored data"
    )
    dashboard.set_defaults(func=_dashboard)
    factor_dashboard = sub.add_parser(
        "factor-dashboard",
        help="build a cross-stock beta/alpha comparison dashboard",
    )
    factor_dashboard.add_argument("--db", default=None)
    factor_dashboard.add_argument("--out-dir", default=None)
    factor_dashboard.set_defaults(func=_factor_dashboard)
    event_dashboard = sub.add_parser(
        "event-dashboard", help="compare returns around macro release dates"
    )
    event_dashboard.add_argument("--db", default=None)
    event_dashboard.add_argument("--out-dir", default=None)
    event_dashboard.add_argument(
        "--reddit-dir",
        default=None,
        help="directory of per-event Reddit JSON files; omit to use the configured path",
    )
    event_dashboard.add_argument(
        "--macro-calendar", default=str(PROJECT_ROOT / "config/macro_calendar.yaml")
    )
    event_dashboard.set_defaults(func=_event_dashboard)
    collect_reddit = sub.add_parser(
        "collect-reddit", help="collect ranked Reddit commentary for macro events"
    )
    collect_reddit.add_argument("--cache-dir", default=None)
    collect_reddit.add_argument(
        "--reddit-dir", default=None, help="override the configured reddit directory"
    )
    collect_reddit.add_argument(
        "--macro-calendar", default=str(PROJECT_ROOT / "config/macro_calendar.yaml")
    )
    collect_reddit.add_argument(
        "--daily-limit",
        type=int,
        default=400,
        help="max Arctic Shift requests per day (quota exhaustion stops the run)",
    )
    collect_reddit.add_argument(
        "--rebuild", action="store_true", help="re-collect even completed events"
    )
    collect_reddit.set_defaults(func=_collect_reddit)
    chart = sub.add_parser("chart", help="run the pipeline and generate a price/event HTML chart")
    for command in (render, chart):
        command.add_argument("ticker", nargs="?", default=None)
        command.add_argument("--db", default=None)
        command.add_argument("--moves-dir", default=None)
        command.add_argument("--events-dir", default=None)
        command.add_argument("--out-dir", default=None)
    render.set_defaults(func=_render)
    chart.add_argument("--cache-dir", default=None)
    chart.add_argument("--macro-calendar", default=str(PROJECT_ROOT / "config/macro_calendar.yaml"))
    chart.add_argument("--keyless", action="store_true", help="collect SEC, HN and macro only")
    chart.add_argument(
        "--skip-events", action="store_true", help="render existing evidence offline"
    )
    chart.add_argument("--refresh-prices", action="store_true", help="fetch prices even if stored")
    chart.add_argument(
        "--refresh",
        action="store_true",
        help="force price ingest and fundamentals refetch before building",
    )
    chart.add_argument(
        "--offline", action="store_true", help="fetch nothing; build from stored data"
    )
    chart.add_argument("--rebuild", action="store_true", help="rebuild event bundles from cache")
    chart.set_defaults(func=_chart, date=None)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage()
        return 2
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
