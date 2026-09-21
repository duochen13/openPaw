#!/usr/bin/env python3
"""Backtest alpha slope reversal signals (issues #19, #39).

For each stock, compute the daily trailing-250-session OLS alpha vs QQQ
(trailing-only: alpha(t) uses returns up to and including t, never the
future), derive the 20-session slope, and score two signal definitions by
their forward EXCESS return vs QQQ over 20/60/120 trading days:

  alpha_cross  alpha crosses from <= 0 to > 0
  slope_cross  slope crosses from <= 0 to > 0

Issue #39 removed alpha acceleration from the product, so the acceleration
and combo signal definitions are gone; only slope-only signals remain.

Forward returns start at t+1, strictly after the signal date: no look-ahead.
Results are pooled across stocks. Caveats, printed with the table: signal
occurrences on consecutive days have overlapping forward windows, so counts
are occurrences, not independent bets; a small n means the mean is noise.

Usage: python3 scripts/backtest_alpha_signals.py [--db data/prices.sqlite]
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from portfolio_analysis.moves import aligned_returns
from portfolio_analysis.signals import (
    SLOPE_SPAN,
    rolling_alpha_daily,
    rolling_slope,
)

STOCKS = ("NOW", "CRM", "META", "GOOGL", "NVDA", "ORCL", "TSLA")
BENCHMARK = "QQQ"
ALPHA_WINDOW = 250
HORIZONS = (20, 60, 120)
SIGNALS = ("alpha_cross", "slope_cross")


def load_prices(db: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with sqlite3.connect(db) as conn:
        for ticker, date, adj in conn.execute("SELECT ticker, date, adj_close FROM price_bar"):
            out.setdefault(ticker, {})[date] = adj
    return out


def cross_up(series: list[float | None], i: int) -> bool:
    prev, cur = series[i - 1], series[i]
    return prev is not None and cur is not None and prev <= 0 < cur


def forward_excess(
    stock_rets: list[float], bench_rets: list[float], i: int, horizon: int
) -> float | None:
    """Gross-return difference over sessions (i+1 .. i+horizon), vs benchmark."""
    seg_s = stock_rets[i + 1 : i + 1 + horizon]
    seg_b = bench_rets[i + 1 : i + 1 + horizon]
    if len(seg_s) < horizon or len(seg_b) < horizon:
        return None
    return math.prod(1 + r for r in seg_s) - math.prod(1 + r for r in seg_b)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prices.sqlite")
    args = ap.parse_args()
    prices = load_prices(Path(args.db))
    missing = [s for s in (*STOCKS, BENCHMARK) if s not in prices]
    if missing:
        raise SystemExit(f"missing price series in {args.db}: {missing}")

    pooled: dict[str, dict[int, list[float]]] = {
        name: {h: [] for h in HORIZONS} for name in SIGNALS
    }
    per_stock: dict[str, dict[str, int]] = {
        s: {name: 0 for name in SIGNALS} for s in STOCKS
    }

    for stock in STOCKS:
        dates, sret, bret = aligned_returns(prices[stock], prices[BENCHMARK])
        alpha = rolling_alpha_daily(sret, bret, ALPHA_WINDOW)
        slope = rolling_slope(alpha, SLOPE_SPAN)
        for i in range(1, len(dates)):
            fired = {
                "alpha_cross": cross_up(alpha, i),
                "slope_cross": cross_up(slope, i),
            }
            for name, hit in fired.items():
                if not hit:
                    continue
                per_stock[stock][name] += 1
                for h in HORIZONS:
                    excess = forward_excess(sret, bret, i, h)
                    if excess is not None:
                        pooled[name][h].append(excess)

    print("# Alpha reversal signal backtest (issue #19)\n")
    print(
        f"Universe: {', '.join(STOCKS)} vs {BENCHMARK} | "
        f"alpha window: {ALPHA_WINDOW} sessions | slope span: {SLOPE_SPAN} sessions\n"
        f"Signal at close t; forward excess return vs {BENCHMARK} over t+1..t+h.\n"
    )
    print(f"{'signal':<12}{'horizon':>8}{'n':>7}{'mean':>10}{'median':>10}{'hit_rate':>10}")
    for name in SIGNALS:
        for h in HORIZONS:
            xs = pooled[name][h]
            if not xs:
                print(f"{name:<12}{h:>8}{0:>7}{'n/a':>10}{'n/a':>10}{'n/a':>10}")
                continue
            mean = st.fmean(xs)
            median = st.median(xs)
            hit = sum(1 for x in xs if x > 0) / len(xs)
            print(
                f"{name:<12}{h:>8}{len(xs):>7}"
                f"{mean:>+9.2%}{median:>+9.2%}{hit:>9.1%}"
            )
    print("\nOccurrences per stock (all horizons share the same signal dates):")
    print(f"{'stock':<8}" + "".join(f"{name:>13}" for name in SIGNALS))
    for stock in STOCKS:
        print(f"{stock:<8}" + "".join(f"{per_stock[stock][n]:>13}" for n in SIGNALS))
    print(
        "\nCaveats: trailing-only, no look-ahead; occurrences on consecutive days "
        "have overlapping forward windows (counts are occurrences, not independent "
        "bets); signals with small n have noisy means - treat them as descriptive, "
        "not predictive. These are regime-change signals for validation, not buy signals."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
