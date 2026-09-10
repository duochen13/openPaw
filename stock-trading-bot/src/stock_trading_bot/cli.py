"""Command-line entry point.

Reports and paper evaluation only. This tool has no brokerage integration and
places no orders.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime

from stock_trading_bot.config import load_run_config, load_watchlist, resolve_path
from stock_trading_bot.ingest import prices
from stock_trading_bot.naming import safe_ticker_component
from stock_trading_bot.store import Store

#: Fields that decide whether a re-fetched bar carries new information.
_PRICE_FIELDS = prices._PRICE_FIELDS


def _ingest(args: argparse.Namespace) -> int:
    # A bare-word argument is unambiguous in a way a scraped comment is not, so
    # a company name or alias resolves here without needing a cashtag.
    watchlist = load_watchlist()
    symbol = watchlist.resolve(args.ticker) or safe_ticker_component(args.ticker)

    cfg = load_run_config()
    store = Store.open(args.db or resolve_path(cfg["paths"]["db"]))
    try:
        bars = prices.fetch_bars(
            symbol,
            observed_at=datetime.now(UTC),
            latency_budget=cfg["latency_budget_seconds"],
        )
        written, unchanged = 0, 0
        for bar in bars:
            existing = store.latest_price_bar(symbol, str(bar["session_date"]))
            if existing is not None and all(
                existing[field] == bar[field] for field in _PRICE_FIELDS
            ):
                unchanged += 1
                continue
            try:
                store.insert_price_bar(**bar)
                written += 1
            except sqlite3.IntegrityError:
                # Identical observation timestamp; nothing new to record.
                unchanged += 1
        print(f"{symbol}: {written} bar(s) written, {unchanged} unchanged")
    finally:
        store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stock-trading",
        description="Point-in-time equity research. Reports and paper evaluation only.",
    )
    sub = parser.add_subparsers(dest="command")

    ingest = sub.add_parser("ingest", help="fetch and store raw daily bars")
    ingest.add_argument("ticker", help="ticker, company name, or watchlist alias")
    ingest.add_argument("--db", default=None, help="override the configured database")
    ingest.set_defaults(func=_ingest)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_usage()
        return 2
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
