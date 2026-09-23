#!/usr/bin/env python3
"""Backtest alpha slope reversal signals (issues #19, #39, #47).

For each stock, compute the daily trailing alpha vs QQQ (trailing-only:
alpha(t) uses returns up to and including t, never the future), derive the
20-session slope, and score two signal definitions by their forward EXCESS
return vs QQQ over 20/60/120 trading days:

  alpha_cross  alpha crosses from <= 0 to > 0
  slope_cross  slope crosses from <= 0 to > 0

Issue #39 removed alpha acceleration from the product, so the acceleration
and combo signal definitions are gone; only slope-only signals remain.

Issue #47: the backtest runs under BOTH weighting modes and compares them:

  fixed time weight  250-session equal-weight OLS (the original)
  enable time weight  WLS with exponential decay (half-life 60 sessions):
                      recent sessions dominate the alpha/slope fit

Issue #50: the backtest additionally varies the SLOPE estimator while holding
the WLS alpha fixed (half-life 60), comparing slope definitions head to head:

  wls-twopoint   WLS alpha + legacy two-point slope (span 20)
  wls            WLS alpha + WLS-regression slope (span 20, half-life 60)
  wls-slope10    WLS alpha + WLS-regression slope (span 10, half-life 60)
  wls-slope30    WLS alpha + WLS-regression slope (span 30, half-life 60)

The wls-twopoint vs wls pair isolates the estimator change (two-point vs WLS
regression at the same span); the span10/span30 pair shows the responsiveness
knob. All slope fits are trailing-only and causal.

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
    DEFAULT_WLS_HALF_LIFE,
    SLOPE_SPAN,
    rolling_alpha_daily,
    rolling_slope,
)

STOCKS = ("NOW", "CRM", "META", "GOOGL", "NVDA", "ORCL", "TSLA")
BENCHMARK = "QQQ"
ALPHA_WINDOW = 250
HORIZONS = (20, 60, 120)
SIGNALS = ("alpha_cross", "slope_cross")

#: (mode key, label, window, half_life, slope_method, slope_span).
#: Exactly one of window/half_life set. slope_method is "two-point" (legacy
#: (v[i]-v[i-span])/span) or "wls" (WLS regression over the trailing
#: slope_span alphas with half-life decay); issue #50.
MODES: tuple[tuple[str, str, int | None, float | None, str, int], ...] = (
    (
        "fixed",
        "fixed time weight (250-session OLS, two-point slope)",
        ALPHA_WINDOW,
        None,
        "two-point",
        SLOPE_SPAN,
    ),
    (
        "wls",
        f"enable time weight (WLS hl={DEFAULT_WLS_HALF_LIFE}, WLS slope span 20)",
        None,
        float(DEFAULT_WLS_HALF_LIFE),
        "wls",
        SLOPE_SPAN,
    ),
    (
        "wls-twopoint",
        f"WLS alpha hl={DEFAULT_WLS_HALF_LIFE} + two-point slope (span 20)",
        None,
        float(DEFAULT_WLS_HALF_LIFE),
        "two-point",
        SLOPE_SPAN,
    ),
    (
        "wls-slope10",
        f"WLS alpha hl={DEFAULT_WLS_HALF_LIFE} + WLS slope (span 10)",
        None,
        float(DEFAULT_WLS_HALF_LIFE),
        "wls",
        10,
    ),
    (
        "wls-slope30",
        f"WLS alpha hl={DEFAULT_WLS_HALF_LIFE} + WLS slope (span 30)",
        None,
        float(DEFAULT_WLS_HALF_LIFE),
        "wls",
        30,
    ),
)


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


def run_mode(
    prices: dict[str, dict[str, float]],
    window: int | None,
    half_life: float | None,
    slope_method: str,
    slope_span: int,
) -> tuple[dict[str, dict[int, list[float]]], dict[str, dict[str, int]]]:
    pooled: dict[str, dict[int, list[float]]] = {
        name: {h: [] for h in HORIZONS} for name in SIGNALS
    }
    per_stock: dict[str, dict[str, int]] = {s: {name: 0 for name in SIGNALS} for s in STOCKS}

    for stock in STOCKS:
        dates, sret, bret = aligned_returns(prices[stock], prices[BENCHMARK])
        alpha = rolling_alpha_daily(sret, bret, window, half_life=half_life)
        slope = (
            rolling_slope(alpha, slope_span, half_life=half_life)
            if slope_method == "wls"
            else rolling_slope(alpha, slope_span)
        )
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
    return pooled, per_stock


def summarize(xs: list[float]) -> tuple[str, str, str]:
    if not xs:
        return "n/a", "n/a", "n/a"
    mean = st.fmean(xs)
    median = st.median(xs)
    hit = sum(1 for x in xs if x > 0) / len(xs)
    return f"{mean:>+9.2%}", f"{median:>+9.2%}", f"{hit:>9.1%}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prices.sqlite")
    args = ap.parse_args()
    prices = load_prices(Path(args.db))
    missing = [s for s in (*STOCKS, BENCHMARK) if s not in prices]
    if missing:
        raise SystemExit(f"missing price series in {args.db}: {missing}")

    results: dict[str, dict[str, dict[int, list[float]]]] = {}
    per_stock: dict[str, dict[str, dict[str, int]]] = {}
    for key, _label, window, half_life, slope_method, slope_span in MODES:
        pooled, ps = run_mode(prices, window, half_life, slope_method, slope_span)
        results[key] = pooled
        per_stock[key] = ps

    print("# Alpha reversal signal backtest (issues #19, #47, #50)\n")
    print(
        f"Universe: {', '.join(STOCKS)} vs {BENCHMARK}\n"
        f"Signal at close t; forward excess return vs {BENCHMARK} over t+1..t+h.\n"
    )
    for key, label, _w, _h, _m, _s in MODES:
        print(f"## mode: {label}")
        print(f"{'signal':<12}{'horizon':>8}{'n':>7}{'mean':>10}{'median':>10}{'hit_rate':>10}")
        for name in SIGNALS:
            for h in HORIZONS:
                xs = results[key][name][h]
                mean, median, hit = summarize(xs)
                print(f"{name:<12}{h:>8}{len(xs):>7}{mean:>10}{median:>10}{hit:>10}")
        print("\nOccurrences per stock (all horizons share the same signal dates):")
        print(f"{'stock':<8}" + "".join(f"{name:>13}" for name in SIGNALS))
        for stock in STOCKS:
            print(f"{stock:<8}" + "".join(f"{per_stock[key][stock][n]:>13}" for n in SIGNALS))
        print()

    print("## comparison: enable time weight MINUS fixed time weight")
    print(f"{'signal':<12}{'horizon':>8}{'d_n':>7}{'d_mean':>10}{'d_hit_rate':>10}")
    for name in SIGNALS:
        for h in HORIZONS:
            xs_f = results["fixed"][name][h]
            xs_w = results["wls"][name][h]
            if not xs_f or not xs_w:
                print(f"{name:<12}{h:>8}{'n/a':>7}{'n/a':>10}{'n/a':>10}")
                continue
            d_n = len(xs_w) - len(xs_f)
            d_mean = st.fmean(xs_w) - st.fmean(xs_f)
            d_hit = sum(1 for x in xs_w if x > 0) / len(xs_w) - sum(1 for x in xs_f if x > 0) / len(
                xs_f
            )
            print(f"{name:<12}{h:>8}{d_n:>+7}{d_mean:>+9.2%}{d_hit:>+9.1%}")

    print("\n## comparison: slope estimators (WLS alpha held fixed, issue #50)")
    print(f"{'pair':<32}{'signal':<12}{'horizon':>8}{'d_n':>7}{'d_mean':>10}{'d_hit_rate':>10}")
    pairs = (
        ("wls-twopoint vs wls (estimator)", "wls-twopoint", "wls"),
        ("wls-slope10 vs wls (span)", "wls-slope10", "wls"),
        ("wls-slope30 vs wls (span)", "wls-slope30", "wls"),
    )
    for pair_label, key_a, key_b in pairs:
        for name in SIGNALS:
            for h in HORIZONS:
                xs_a = results[key_a][name][h]
                xs_b = results[key_b][name][h]
                if not xs_a or not xs_b:
                    print(f"{pair_label:<32}{name:<12}{h:>8}{'n/a':>7}{'n/a':>10}{'n/a':>10}")
                    continue
                d_n = len(xs_a) - len(xs_b)
                d_mean = st.fmean(xs_a) - st.fmean(xs_b)
                d_hit = sum(1 for x in xs_a if x > 0) / len(xs_a) - sum(
                    1 for x in xs_b if x > 0
                ) / len(xs_b)
                print(f"{pair_label:<32}{name:<12}{h:>8}{d_n:>+7}{d_mean:>+9.2%}{d_hit:>+9.1%}")
    print(
        "\nCaveats: trailing-only, no look-ahead; occurrences on consecutive days "
        "have overlapping forward windows (counts are occurrences, not independent "
        "bets); signals with small n have noisy means - treat them as descriptive, "
        "not predictive. These are regime-change signals for validation, not buy signals."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
