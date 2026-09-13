"""Command-line entry point.

This tool explains past price moves. It has no brokerage integration, places
no orders, and produces no forward-looking signal (spec §2).
"""
from __future__ import annotations

import argparse
import sys

from portfolio_analysis import prices
from portfolio_analysis.config import Portfolio, load_portfolio
from portfolio_analysis.store import Store


def _selected_symbols(portfolio: Portfolio, requested: str | None) -> list[str] | None:
    """The universe, or the single resolved symbol. None means unresolvable."""
    if requested is None:
        return list(portfolio.symbols)
    symbol = portfolio.resolve(requested)
    return None if symbol is None else [symbol]


def _ingest_prices(args: argparse.Namespace) -> int:
    portfolio = load_portfolio()
    symbols = _selected_symbols(portfolio, args.ticker)
    if symbols is None:
        print(
            f"{args.ticker!r} is not in the portfolio; add it to config/portfolio.yaml",
            file=sys.stderr,
        )
        return 2

    # The benchmark is fetched alongside the universe, never separately. Beta
    # cannot be computed without it, so an ingest that skips it leaves a store
    # that looks complete and is not.
    targets = [*symbols, portfolio.benchmark]

    store = Store.open(args.db or portfolio.path("db"))
    try:
        for symbol in targets:
            bars = prices.fetch_yahoo(symbol, years=portfolio.price_years)
            written = store.upsert_price_bars(bars)
            first = bars[0]["date"] if bars else "-"
            last = bars[-1]["date"] if bars else "-"
            print(f"{symbol}: {written} bar(s) upserted, {first} .. {last}")
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="portfolio-analysis",
        description="Retrospective attribution of large single-day equity moves.",
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest-prices", help="fetch adjusted daily bars")
    ingest.add_argument(
        "ticker", nargs="?", default=None,
        help="ticker, company name, or alias; omit for the whole portfolio",
    )
    ingest.add_argument("--db", default=None, help="override the configured database")
    ingest.set_defaults(func=_ingest_prices)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage()
        return 2
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
