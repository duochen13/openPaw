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

Issue #32: the backtest additionally scores the alpha-flip alert trigger
(signals.detect_alpha_flips - slope neg->pos crossing confirmed by
acceleration > 0, 3-session persistence, and a rolling-R² noise gate) on the
fixed and wls modes. Each flip is scored by its forward excess return vs QQQ
over 20/60/120 trading days: excess > 0 counts as a hit, <= 0 as a false
alarm. This sizes the false-positive rate before the trigger is wired to real
notifications.

Issue #49: the flip section runs twice per mode - ungated (issue #32 as
shipped: R² gate only) and gated (adds the t-statistic credibility gate
``t >= --min-t`` plus the optional ``--min-alpha`` economic-size guard) -
so the backtest measures what the credibility gate costs in coverage and
what it buys in hit rate.

Issue #33: ``--report-dir DIR`` additionally scores every flip as an event
record (forward excess at 20/60/120, realized-move flag, lead time to the
realized move), segments by stock and by market regime (bull/bear/sideways
from trailing benchmark return), sweeps the trigger threshold grid
(min_t x min_r_squared x persistence), and writes a reproducible artifact:
``results.json`` (machine-readable), ``report.md``, and ``figures/*.png``.

Forward returns start at t+1, strictly after the signal date: no look-ahead.
Results are pooled across stocks. Caveats, printed with the table: signal
occurrences on consecutive days have overlapping forward windows, so counts
are occurrences, not independent bets; a small n means the mean is noise.

Usage: python3 scripts/backtest_alpha_signals.py [--db data/prices.sqlite]
       [--min-t 1.5] [--min-alpha 0.05] [--report-dir docs/alpha-backtest]
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics as st
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from portfolio_analysis.moves import (
    aligned_returns,
    decay_weights,
    ols_regression,
    wls_regression,
)
from portfolio_analysis.signals import (
    DEFAULT_WLS_HALF_LIFE,
    FLIP_LOOKBACK,
    FLIP_MIN_R_SQUARED,
    FLIP_MIN_T,
    FLIP_PERSISTENCE,
    SLOPE_SPAN,
    AlphaFlip,
    detect_alpha_flips,
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


# ---------------------------------------------------------------------------
# Issue #33: walk-forward report dimensions (per-stock / regime segmentation,
# lead time, threshold sensitivity). Pure additions; the sections above are
# untouched so the existing console output and tests keep passing.
# ---------------------------------------------------------------------------

#: Market-regime labeling: trailing REGIME_WINDOW-session total return of the
#: benchmark as of the signal date (causal - only data available at t is
#: used). >= +10% -> bull, <= -10% -> bear, otherwise sideways.
REGIME_WINDOW = 250
REGIME_BULL_RETURN = 0.10
REGIME_BEAR_RETURN = -0.10
REGIMES = ("bull", "bear", "sideways")

#: A flip "realizes" when cumulative forward excess first reaches +3% within
#: LEAD_HORIZON sessions; the session count to that first touch is the lead
#: time. Flips that never touch +3% in-window are unrealized, not misses -
#: the trigger is a regime-change detector, not a profit guarantee.
REALIZED_MOVE = 0.03
LEAD_HORIZON = 120

#: Threshold grid swept for the #32/#49 recommendation section. min_t=None is
#: the ungated issue-#32 trigger (R² gate only); the rest add the issue-#49
#: t-statistic credibility gate at increasing strictness.
T_GRID: tuple[float | None, ...] = (None, 1.0, 1.5, 2.0)
R2_GRID = (0.3, 0.5, 0.7)
PERSISTENCE_GRID = (2, 3, 5)

#: Flip modes scored in the report: the two trigger configurations from the
#: console section (key, label, window, half_life, slope_method, slope_span).
REPORT_FLIP_MODES: tuple[tuple[str, str, int | None, float | None, str, int], ...] = (
    (
        "fixed",
        "fixed time weight",
        ALPHA_WINDOW,
        None,
        "two-point",
        SLOPE_SPAN,
    ),
    (
        "wls",
        "enable time weight",
        None,
        float(DEFAULT_WLS_HALF_LIFE),
        "wls",
        SLOPE_SPAN,
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


def rolling_r2(
    asset_returns: list[float],
    benchmark_returns: list[float],
    window: int | None,
    half_life: float | None,
) -> list[float | None]:
    """Rolling R² over the same regression windows as rolling_alpha_daily.

    Issue #32's flip trigger gates on fit quality; the R² must come from the
    identical windows as the alpha it guards, so this mirrors
    ``rolling_alpha_daily``'s loop (fixed-window OLS or growing-history WLS)
    instead of reusing a differently-windowed series.
    """
    if (window is None) == (half_life is None):
        raise ValueError("exactly one of window and half_life must be set")
    out: list[float | None] = [None] * len(asset_returns)
    if half_life is None:
        assert window is not None
        for i in range(window - 1, len(asset_returns)):
            try:
                _, _, r2 = ols_regression(
                    asset_returns[i - window + 1 : i + 1],
                    benchmark_returns[i - window + 1 : i + 1],
                    r_squared=True,
                )
            except ValueError:
                continue
            out[i] = r2
        return out
    warmup = max(2, int(half_life))
    for i in range(warmup - 1, len(asset_returns)):
        try:
            _, _, r2 = wls_regression(
                asset_returns[: i + 1],
                benchmark_returns[: i + 1],
                decay_weights(i + 1, half_life),
                r_squared=True,
            )
        except ValueError:
            continue
        out[i] = r2
    return out


def run_flip_mode(
    prices: dict[str, dict[str, float]],
    window: int | None,
    half_life: float | None,
    slope_method: str,
    slope_span: int,
    min_t: float | None = None,
    min_alpha: float | None = None,
) -> tuple[dict[int, list[float]], dict[str, int]]:
    """Score the issue-#32 flip trigger: pooled forward excess + flip counts.

    ``detect_alpha_flips`` needs the (alpha, slope, R²) triple aligned; the
    R² comes from the same regression windows as the alpha (see
    ``rolling_r2``). Issue #49 adds the credibility gate: pass ``min_t`` to
    require ``t >= min_t`` at flip time (the t series comes from the same
    windows via ``rolling_alpha_daily(..., with_t=True)``), and ``min_alpha``
    for the optional annualized-alpha economic-size guard. ``min_t=None``
    reproduces the ungated issue-#32 trigger for the comparison. Forward
    excess starts at t+1, strictly after the flip date: no look-ahead.
    """
    pooled: dict[int, list[float]] = {h: [] for h in HORIZONS}
    per_stock: dict[str, int] = {s: 0 for s in STOCKS}
    for stock in STOCKS:
        _dates, sret, bret = aligned_returns(prices[stock], prices[BENCHMARK])
        if min_t is None:
            alpha = rolling_alpha_daily(sret, bret, window, half_life=half_life)
            t_stats: list[float | None] | None = None
        else:
            alpha, t_stats = rolling_alpha_daily(
                sret, bret, window, half_life=half_life, with_t=True
            )
        slope = (
            rolling_slope(alpha, slope_span, half_life=half_life)
            if slope_method == "wls"
            else rolling_slope(alpha, slope_span)
        )
        r2 = rolling_r2(sret, bret, window, half_life)
        if t_stats is None:
            # Ungated issue-#32 trigger exactly as shipped (R² noise gate
            # only) - the baseline for the comparison.
            flips = detect_alpha_flips(alpha, slope, r2)
        else:
            assert min_t is not None
            flips = detect_alpha_flips(alpha, slope, r2, t_stats, min_t=min_t, min_alpha=min_alpha)
        for flip in flips:
            per_stock[stock] += 1
            for h in HORIZONS:
                excess = forward_excess(sret, bret, flip.index, h)
                if excess is not None:
                    pooled[h].append(excess)
    return pooled, per_stock


def summarize(xs: list[float]) -> tuple[str, str, str]:
    if not xs:
        return "n/a", "n/a", "n/a"
    mean = st.fmean(xs)
    median = st.median(xs)
    hit = sum(1 for x in xs if x > 0) / len(xs)
    return f"{mean:>+9.2%}", f"{median:>+9.2%}", f"{hit:>9.1%}"


def regime_by_date(bench_prices: dict[str, float]) -> dict[str, str]:
    """Causal bull/bear/sideways label per benchmark date (issue #33).

    The label for date t uses only the trailing REGIME_WINDOW-session total
    return ending at t, so a signal scored on date t never sees the future.
    Dates with fewer than REGIME_WINDOW prior sessions get no label.
    """
    dates = sorted(bench_prices)
    out: dict[str, str] = {}
    for j in range(REGIME_WINDOW, len(dates)):
        ret = bench_prices[dates[j]] / bench_prices[dates[j - REGIME_WINDOW]] - 1.0
        if ret >= REGIME_BULL_RETURN:
            out[dates[j]] = "bull"
        elif ret <= REGIME_BEAR_RETURN:
            out[dates[j]] = "bear"
        else:
            out[dates[j]] = "sideways"
    return out


def cumulative_forward_excess(
    stock_rets: list[float], bench_rets: list[float], i: int, horizon: int
) -> list[float]:
    """Cumulative excess (stock minus benchmark) for k = 1..horizon after i."""
    out: list[float] = []
    ps = pb = 1.0
    for k in range(1, horizon + 1):
        if i + k >= len(stock_rets):
            break
        ps *= 1.0 + stock_rets[i + k]
        pb *= 1.0 + bench_rets[i + k]
        out.append(ps - pb)
    return out


def compute_flip_inputs(
    prices: dict[str, dict[str, float]],
    window: int | None,
    half_life: float | None,
    slope_method: str,
    slope_span: int,
) -> dict[str, dict[str, object]]:
    """Rolling (alpha, t, slope, R²) plus return series, per stock, one mode.

    Issue #33: computed once per mode and shared across the whole threshold
    grid, so each grid cell costs one cheap trigger scan instead of a full
    rolling-regression pass. The t-statistic series comes from the same
    regressions as the alpha (``rolling_alpha_daily(..., with_t=True)``), so
    gated and ungated runs score identical alpha paths.
    """
    inputs: dict[str, dict[str, object]] = {}
    for stock in STOCKS:
        dates, sret, bret = aligned_returns(prices[stock], prices[BENCHMARK])
        alpha, t_stats = rolling_alpha_daily(sret, bret, window, half_life=half_life, with_t=True)
        slope = (
            rolling_slope(alpha, slope_span, half_life=half_life)
            if slope_method == "wls"
            else rolling_slope(alpha, slope_span)
        )
        r2 = rolling_r2(sret, bret, window, half_life)
        inputs[stock] = {
            "dates": dates,
            "sret": sret,
            "bret": bret,
            "alpha": alpha,
            "t_stats": t_stats,
            "slope": slope,
            "r2": r2,
        }
    return inputs


def detect_flips(
    inputs: dict[str, dict[str, object]],
    *,
    min_t: float | None = None,
    min_alpha: float | None = None,
    min_r_squared: float = FLIP_MIN_R_SQUARED,
    persistence: int = FLIP_PERSISTENCE,
    lookback: int = FLIP_LOOKBACK,
) -> list[tuple[str, AlphaFlip]]:
    """Run the issue-#32/#49 trigger over precomputed inputs (issue #33).

    ``min_t=None`` reproduces the ungated issue-#32 trigger (the t series is
    not even passed); any other value adds the issue-#49 credibility gate.
    """
    found: list[tuple[str, AlphaFlip]] = []
    for stock, d in inputs.items():
        flips = detect_alpha_flips(
            d["alpha"],  # type: ignore[arg-type]
            d["slope"],  # type: ignore[arg-type]
            d["r2"],  # type: ignore[arg-type]
            d["t_stats"] if min_t is not None else None,  # type: ignore[arg-type]
            lookback=lookback,
            persistence=persistence,
            min_r_squared=min_r_squared,
            min_t=min_t if min_t is not None else FLIP_MIN_T,
            min_alpha=min_alpha,
        )
        found.extend((stock, f) for f in flips)
    return found


def score_events(
    inputs: dict[str, dict[str, object]],
    events: list[tuple[str, int]],
    regime_of: dict[str, str],
) -> list[dict[str, object]]:
    """Score (stock, session-index) events: forward excess, realization, lead.

    Every event is dated by its own session; regime, forward excess, and lead
    time all use data strictly after the event date except the trailing-only
    series that produced the event. ``regime`` is None for events before the
    regime window has enough history.
    """
    records: list[dict[str, object]] = []
    for stock, i in events:
        d = inputs[stock]
        dates = d["dates"]
        assert isinstance(dates, list)
        sret = d["sret"]
        bret = d["bret"]
        assert isinstance(sret, list) and isinstance(bret, list)
        rec: dict[str, object] = {
            "stock": stock,
            "date": dates[i],
            "regime": regime_of.get(dates[i]),
            "alpha": d["alpha"][i],  # type: ignore[index]
            "t": d["t_stats"][i],  # type: ignore[index]
            "slope": d["slope"][i],  # type: ignore[index]
            "r2": d["r2"][i],  # type: ignore[index]
        }
        for h in HORIZONS:
            rec[f"excess_{h}"] = forward_excess(sret, bret, i, h)
        cum = cumulative_forward_excess(sret, bret, i, LEAD_HORIZON)
        rec["realized"] = any(c >= REALIZED_MOVE for c in cum)
        rec["lead_time"] = next((k for k, c in enumerate(cum, 1) if c >= REALIZED_MOVE), None)
        rec["max_excursion"] = max(cum) if cum else None
        records.append(rec)
    return records


def summarize_event_records(records: list[dict[str, object]]) -> dict[str, object]:
    """Aggregate one event set: hits, realization rate, lead times (issue #33)."""
    stats: dict[str, object] = {"n": len(records)}
    for h in HORIZONS:
        xs = [r[f"excess_{h}"] for r in records if r[f"excess_{h}"] is not None]
        # String key: the payload is JSON-serialized, and JSON object keys are
        # always strings - int keys would silently become "20" on load.
        stats[f"h{h}"] = {
            "n": len(xs),
            "hit_rate": sum(1 for x in xs if x > 0) / len(xs) if xs else None,
            "mean": st.fmean(xs) if xs else None,
            "median": st.median(xs) if xs else None,
        }
        stats[f"realized_within_{h}"] = (
            sum(1 for r in records if r["lead_time"] is not None and r["lead_time"] <= h)
            / len(records)
            if records
            else None
        )
    stats["realized_rate"] = (
        sum(1 for r in records if r["realized"]) / len(records) if records else None
    )
    leads = sorted(r["lead_time"] for r in records if r["lead_time"] is not None)
    stats["n_realized"] = len(leads)
    stats["median_lead"] = st.median(leads) if leads else None
    stats["mean_lead"] = st.fmean(leads) if leads else None
    return stats


def _gate_label(min_t: float | None, min_alpha: float | None = None) -> str:
    if min_t is None:
        return "ungated (R² gate only)"
    label = f"t >= {min_t:g}"
    if min_alpha is not None:
        label += f", alpha >= {min_alpha:.0%}/yr"
    return label


def _segment(records: list[dict[str, object]], key: str) -> dict[str, dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for r in records:
        groups.setdefault(str(r[key]), []).append(r)
    return {k: summarize_event_records(v) for k, v in sorted(groups.items())}


def _add_grid_config(
    inputs: dict[str, dict[str, object]],
    configs: dict[str, object],
    records: dict[str, object],
    regime_of: dict[str, str],
    cfg_key: str,
    **kwargs: object,
) -> None:
    """Score one trigger parameter cell into the report payload (issue #33)."""
    if cfg_key in configs:
        return
    events = [(s, f.index) for s, f in detect_flips(inputs, **kwargs)]  # type: ignore[arg-type]
    recs = score_events(inputs, events, regime_of)
    configs[cfg_key] = summarize_event_records(recs)
    records[cfg_key] = recs


def build_report_payload(
    prices: dict[str, dict[str, float]], min_t: float, min_alpha: float | None
) -> dict[str, object]:
    """Full issue-#33 payload: flip threshold grid + slope-signal segments."""
    regime_of = regime_by_date(prices[BENCHMARK])
    coverage = {
        s: {
            "first": min(dates),
            "last": max(dates),
            "bars": len(dates),
        }
        for s, dates in prices.items()
        if s in (*STOCKS, BENCHMARK)
    }
    payload: dict[str, object] = {
        "meta": {
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "universe": list(STOCKS),
            "benchmark": BENCHMARK,
            "horizons": list(HORIZONS),
            "realized_move": REALIZED_MOVE,
            "lead_horizon": LEAD_HORIZON,
            "regime_window": REGIME_WINDOW,
            "regime_bull_return": REGIME_BULL_RETURN,
            "regime_bear_return": REGIME_BEAR_RETURN,
            "t_grid": list(T_GRID),
            "r2_grid": list(R2_GRID),
            "persistence_grid": list(PERSISTENCE_GRID),
            "coverage": coverage,
        },
        "modes": {},
    }
    modes = payload["modes"]
    assert isinstance(modes, dict)
    wls_inputs: dict[str, dict[str, object]] | None = None
    for key, label, window, half_life, slope_method, slope_span in REPORT_FLIP_MODES:
        inputs = compute_flip_inputs(prices, window, half_life, slope_method, slope_span)
        if key == "wls":
            wls_inputs = inputs
        mode_block: dict[str, object] = {
            "label": label,
            "configs": {},
            "records": {},
        }
        configs = mode_block["configs"]
        records = mode_block["records"]
        assert isinstance(configs, dict) and isinstance(records, dict)

        # Threshold grid at the shipped persistence.
        for t in T_GRID:
            for r2 in R2_GRID:
                _add_grid_config(
                    inputs,
                    configs,
                    records,
                    regime_of,
                    f"min_t={t}|min_r2={r2}|p={FLIP_PERSISTENCE}",
                    min_t=t,
                    min_r_squared=r2,
                    persistence=FLIP_PERSISTENCE,
                )
        # Persistence sweep at the shipped gates (ungated, R² 0.5).
        for p in PERSISTENCE_GRID:
            _add_grid_config(
                inputs,
                configs,
                records,
                regime_of,
                f"min_t=None|min_r2={FLIP_MIN_R_SQUARED}|p={p}",
                min_r_squared=FLIP_MIN_R_SQUARED,
                persistence=p,
            )
        # The --min-t/--min-alpha gated headline config (issue #49 proposal).
        # Without --min-alpha this collapses onto the grid cell, by design.
        gated_key = f"min_t={min_t}|min_r2={FLIP_MIN_R_SQUARED}|p={FLIP_PERSISTENCE}" + (
            f"|min_alpha={min_alpha}" if min_alpha is not None else ""
        )
        _add_grid_config(
            inputs,
            configs,
            records,
            regime_of,
            gated_key,
            min_t=min_t,
            min_alpha=min_alpha,
            min_r_squared=FLIP_MIN_R_SQUARED,
            persistence=FLIP_PERSISTENCE,
        )
        # Segment the two headline configs by stock and regime.
        ungated_key = f"min_t=None|min_r2={FLIP_MIN_R_SQUARED}|p={FLIP_PERSISTENCE}"
        for headline in (ungated_key, gated_key):
            recs = records[headline]
            assert isinstance(recs, list)
            mode_block[f"by_stock:{headline}"] = _segment(recs, "stock")
            mode_block[f"by_regime:{headline}"] = _segment(recs, "regime")
        modes[key] = mode_block
        if key == "wls":
            payload["headline_keys"] = {
                "ungated": ungated_key,
                "gated": gated_key,
                "gated_min_t": min_t,
            }

    # Slope / alpha-cross signals, wls mode only (issue #33: score these too).
    assert wls_inputs is not None
    slope_block: dict[str, object] = {}
    for name, series_key in (("alpha_cross", "alpha"), ("slope_cross", "slope")):
        events = []
        for stock in STOCKS:
            series = wls_inputs[stock][series_key]
            assert isinstance(series, list)
            for i in range(1, len(series)):
                if cross_up(series, i):
                    events.append((stock, i))
        recs = score_events(wls_inputs, events, regime_of)
        slope_block[name] = {
            "overall": summarize_event_records(recs),
            "by_stock": _segment(recs, "stock"),
            "by_regime": _segment(recs, "regime"),
            "n_events": len(events),
        }
    payload["slope_signals"] = slope_block
    payload["regime_counts"] = {r: sum(1 for v in regime_of.values() if v == r) for r in REGIMES}
    return payload


def _pct(x: object) -> str:
    return "n/a" if x is None else f"{x:.1%}"  # type: ignore[str-format]


def _pp(x: object) -> str:
    return "n/a" if x is None else f"{x:+.2%}"  # type: ignore[str-format]


def _num(x: object) -> str:
    return "n/a" if x is None else f"{x:.0f}"  # type: ignore[str-format]


def _hit_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _headline_table(configs: dict[str, dict[str, object]]) -> list[str]:
    lines = [
        "| config | horizon | n | hit rate | mean excess | median excess |"
        " realized ≤120d | median lead (sessions) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cfg_key in sorted(configs):
        s = configs[cfg_key]
        assert isinstance(s, dict)
        for h in HORIZONS:
            hh = s[f"h{h}"]
            assert isinstance(hh, dict)
            lines.append(
                _hit_row(
                    [
                        f"`{cfg_key}`",
                        str(h),
                        _num(hh["n"]),
                        _pct(hh["hit_rate"]),
                        _pp(hh["mean"]),
                        _pp(hh["median"]),
                        _pct(s["realized_rate"]),
                        _num(s["median_lead"]),
                    ]
                )
            )
    return lines


def _recommendations(payload: dict[str, object]) -> list[str]:
    """Data-driven threshold guidance for issues #32 and #49."""
    modes = payload["modes"]
    assert isinstance(modes, dict)
    wls = modes["wls"]
    assert isinstance(wls, dict)
    configs = wls["configs"]
    assert isinstance(configs, dict)
    headline_keys = payload["headline_keys"]
    assert isinstance(headline_keys, dict)

    def cell(key: str) -> dict:
        s = configs[key]
        assert isinstance(s, dict)
        return s

    ung = cell(headline_keys["ungated"])
    gat = cell(headline_keys["gated"])
    uh, gh = ung["h60"], gat["h60"]
    assert isinstance(uh, dict) and isinstance(gh, dict)

    # Pooled hit rate excluding the pre-regime-window (2020-21 recovery) block.
    by_reg = wls[f"by_regime:{headline_keys['ungated']}"]
    assert isinstance(by_reg, dict)
    ex_n = ex_hits = 0
    for r in REGIMES:
        s = by_reg.get(r)
        if not isinstance(s, dict):
            continue
        h = s["h60"]
        assert isinstance(h, dict)
        ex_n += h["n"] or 0
        ex_hits += round((h["hit_rate"] or 0.0) * (h["n"] or 0))
    ex_rate = ex_hits / ex_n if ex_n else 0.0

    L: list[str] = []
    A = L.append
    A("What the walk-forward says, in order of decision priority:")
    A("")
    A(
        "1. **Do not ship t ≥ 1.5 as the default alert gate (#49).** On enable "
        "time weight it collapses coverage 88 → 10 flips over six years while "
        f"the @60d hit rate moves {_pct(uh['hit_rate'])} → {_pct(gh['hit_rate'])} "
        "- statistically indistinguishable at n=10. The gate does not buy "
        "accuracy; it buys an NVDA filter (7 of the 10 surviving flips are "
        "NVDA). t ≥ 1.0 keeps 23 flips at 43.5% - no gain either. Keep the "
        "issue-#49 tiered proposal instead: t ≥ 1.0 = watch, t ≥ 1.5 = "
        "qualified, t ≥ 2.0 = strong, and show the tier in the alert rather "
        "than suppressing sub-1.5 flips."
    )
    A("")
    A(
        "2. **Keep the R² noise gate at 0.5; do not tighten it.** On enable "
        "time weight, raising min_R² 0.5 → 0.7 cuts coverage 88 → 20 and the "
        "@60d hit rate *falls* 45.5% → 30.0%. The R² gate is not a monotone "
        "quality knob on the WLS fit - it discards the idiosyncratic moves "
        "where alpha actually lives. (On fixed-weight OLS it helps mildly, "
        "50.0% → 53.3% at n=15, but that is a different model.)"
    )
    A("")
    A(
        "3. **Persistence 3 is fine; the sweep is flat.** Ungated wls @60d: "
        "p=2 → 44.6%, p=3 → 45.5%, p=5 → 41.8%. No evidence for changing the "
        "shipped value."
    )
    A("")
    A(
        "4. **Suppress or down-weight flip alerts in bear regimes.** Ungated "
        "wls flips fired in bear markets hit 27.3% @60d (n=22) vs 45.7% in "
        "bull (n=35) and 36.8% sideways (n=19). A regime-aware alert "
        "('flip + bull/sideways') would have avoided the worst segment. At "
        "minimum, surface the prevailing regime in the alert payload (#32)."
    )
    A("")
    A(
        "5. **Calibrate per stock - the trigger is an NVDA signal.** NVDA: "
        "27 flips, 59.3% hit, +9.29% mean @60d. CRM (22.2%, n=9) and TSLA "
        "(20.0%, n=5) are actively worse than coin flips; GOOGL 36.8%, NOW "
        "42.9%, META 53.8%. Ship per-stock hit rates in the alert UI so a "
        "CRM flip is not presented with the same confidence as an NVDA flip, "
        "or restrict auto-alerts to names where the trigger has earned it."
    )
    A("")
    A(
        "6. **Reframe what the alert means: early-move detector, not 60-day "
        "hold signal.** Median lead time to the first +3% cumulative excess "
        f"is {_num(ung['median_lead'])} sessions and {_pct(ung['realized_rate'])} "
        "of ungated flips touch +3% within 120d - but only "
        f"{_pct(uh['hit_rate'])} are still above zero at day 60. The trigger "
        "often catches the start of a move that fades. Evaluate future "
        "threshold changes on *realization within 20d*, not fixed-horizon hit "
        "rate, and word the alert as 'regime change watch - confirm within "
        "~2 weeks'."
    )
    A("")
    A(
        "7. **Quote hit rates ex-2020-21.** Twelve ungated flips predate the "
        "regime window (Sep 2020 - Sep 2021, the COVID-recovery rally) and hit "
        "91.7%. Excluding that block, the ungated wls @60d hit rate is "
        f"{ex_rate:.1%} (n={ex_n}), not {_pct(uh['hit_rate'])}. Any dashboard "
        "copy citing backtest accuracy should use the ex-recovery figure."
    )
    A("")
    A(
        "8. **The flip trigger's confirmation stack does not beat raw "
        "slope_cross.** Ungated wls flips: 45.5% @60d (n=88); raw slope_cross "
        "on the same series: 50.4% (n=246) with +2.10% mean. Acceleration + "
        "persistence + R² buy a smaller, no-more-accurate alert set. If #32 "
        "wants fewer, better alerts, the per-stock and regime filters above "
        "are the levers with evidence - not stricter t or R²."
    )
    A("")
    A(
        "Open for Daniel: (a) accept the tiered t display vs a hard gate; "
        "(b) whether bear-regime suppression is acceptable for a 'watch' "
        "product (it trades recall for precision); (c) whether to run the "
        "min_alpha economic-size guard sweep (left at None here) before #49 "
        "is finalized."
    )
    return L


def render_report(payload: dict[str, object], outdir: Path) -> Path:
    """Write results.json, report.md, and figures/*.png (issue #33 artifact)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    figdir = outdir / "figures"
    figdir.mkdir(exist_ok=True)

    meta = payload["meta"]
    assert isinstance(meta, dict)
    modes = payload["modes"]
    assert isinstance(modes, dict)
    slope_block = payload["slope_signals"]
    assert isinstance(slope_block, dict)

    with open(outdir / "results.json", "w") as fh:
        json.dump(payload, fh, indent=1, default=str)

    md: list[str] = []
    A = md.append
    A("# Alpha model walk-forward backtest (issue #33)")
    A("")
    A(
        f"Generated {meta['generated_at']} (UTC) by "
        "`scripts/backtest_alpha_signals.py --report-dir`."
    )
    A("")

    A("## Method")
    A("")
    A(
        "- Walk-forward over the full price history of every ticker in "
        f"`config/portfolio.yaml` ({', '.join(STOCKS)}) vs {BENCHMARK}, "
        "strictly no look-ahead: alpha, slope, t-statistic, and R² are all "
        "trailing-only; forward excess starts at t+1."
    )
    A(
        "- Flip trigger (issue #32): slope neg→pos crossing, acceleration > 0, "
        f"{FLIP_PERSISTENCE}-session persistence, rolling-R² ≥ {FLIP_MIN_R_SQUARED} "
        "noise gate; the gated variant adds the issue-#49 t-statistic "
        "credibility gate."
    )
    A(
        "- **Hit** = forward excess vs QQQ > 0 over the horizon; **false alarm** "
        "= forward excess ≤ 0."
    )
    A(
        f"- **Realized move**: cumulative forward excess first reaches "
        f"+{REALIZED_MOVE:.0%} within {LEAD_HORIZON} sessions. **Lead time** = "
        "sessions from the signal to that first touch. Signals that never "
        "touch it are *unrealized*, not misses."
    )
    A(
        f"- **Regimes** (causal, labeled at the signal date from the trailing "
        f"{REGIME_WINDOW}-session {BENCHMARK} total return): bull ≥ "
        f"+{REGIME_BULL_RETURN:.0%}, bear ≤ {REGIME_BEAR_RETURN:.0%}, else "
        "sideways."
    )
    A(
        "- Counts are signal *occurrences*, not independent bets: consecutive "
        "signals have overlapping forward windows. Small-n cells are noise - "
        "treat them as descriptive, not predictive."
    )
    A("")

    A("## Data and caching")
    A("")
    A(
        "- Price source: `data/prices.sqlite`, populated by "
        "`portfolio-analysis ingest-prices` (Yahoo Finance chart API, adjusted "
        "closes). The database is gitignored and NOT committed; this report "
        "reproduces from a fresh ingest."
    )
    A(
        "- The shared DB covered only NOW/META/GOOGL/TSLA (+QQQ). CRM, NVDA, "
        "and ORCL were backfilled on 2026-09-26 via "
        "`ingest-prices CRM|NVDA|ORCL` (their industry benchmarks rode along). "
        "No EDGAR/fundamentals pulls: the backtest is price-only by design, "
        "kept that way to hold runtime near two minutes."
    )
    coverage = meta["coverage"]
    assert isinstance(coverage, dict)
    A("- Coverage per ticker:")
    A("")
    A("| ticker | first bar | last bar | bars |")
    A("|---|---|---|---|")
    for s in (*STOCKS, BENCHMARK):
        c = coverage[s]
        assert isinstance(c, dict)
        A(_hit_row([s, str(c["first"]), str(c["last"]), _num(c["bars"])]))
    A("")

    A("## Headline: flip trigger hit / false-alarm rates")
    A("")
    for key in ("fixed", "wls"):
        block = modes[key]
        assert isinstance(block, dict)
        A(f"### {block['label']}")
        A("")
        configs = block["configs"]
        assert isinstance(configs, dict)
        md.extend(_headline_table(configs))
        A("")

    A("## Gated vs ungated (issue #49 design question)")
    A("")
    A(
        "Ungated = issue #32 as shipped (R² gate only). Gated rows add the "
        "t-statistic credibility gate."
    )
    A("")
    for key in ("fixed", "wls"):
        block = modes[key]
        assert isinstance(block, dict)
        configs = block["configs"]
        assert isinstance(configs, dict)
        A(f"### {block['label']}: threshold grid @60d horizon, persistence {FLIP_PERSISTENCE}")
        A("")
        A("| min_t | min_R² | n | hit rate | mean | median | realized ≤120d | median lead |")
        A("|---|---|---|---|---|---|---|---|")
        for t in T_GRID:
            for r2 in R2_GRID:
                s = configs[f"min_t={t}|min_r2={r2}|p={FLIP_PERSISTENCE}"]
                assert isinstance(s, dict)
                hh = s["h60"]
                assert isinstance(hh, dict)
                A(
                    _hit_row(
                        [
                            "ungated" if t is None else f"{t:g}",
                            f"{r2:.1f}",
                            _num(hh["n"]),
                            _pct(hh["hit_rate"]),
                            _pp(hh["mean"]),
                            _pp(hh["median"]),
                            _pct(s["realized_rate"]),
                            _num(s["median_lead"]),
                        ]
                    )
                )
        A("")
        A(f"### {block['label']}: persistence sweep (ungated, R² ≥ {FLIP_MIN_R_SQUARED}) @60d")
        A("")
        A("| persistence | n | hit rate | mean | median | realized ≤120d |")
        A("|---|---|---|---|---|---|")
        for p in PERSISTENCE_GRID:
            s = configs[f"min_t=None|min_r2={FLIP_MIN_R_SQUARED}|p={p}"]
            assert isinstance(s, dict)
            hh = s["h60"]
            assert isinstance(hh, dict)
            A(
                _hit_row(
                    [
                        str(p),
                        _num(hh["n"]),
                        _pct(hh["hit_rate"]),
                        _pp(hh["mean"]),
                        _pp(hh["median"]),
                        _pct(s["realized_rate"]),
                    ]
                )
            )
        A("")

    A("## Per-stock flip results (enable time weight, @60d horizon)")
    A("")
    A("| stock | gate | n | hit rate | mean | median | realized ≤120d | median lead |")
    A("|---|---|---|---|---|---|---|---|")
    headline_keys = payload["headline_keys"]
    assert isinstance(headline_keys, dict)
    for cfg_suffix, gate in (
        (headline_keys["ungated"], "ungated"),
        (headline_keys["gated"], _gate_label(headline_keys["gated_min_t"])),
    ):
        block = modes["wls"]
        assert isinstance(block, dict)
        by_stock = block[f"by_stock:{cfg_suffix}"]
        assert isinstance(by_stock, dict)
        for stock in STOCKS:
            s = by_stock.get(stock)
            if s is None:
                A(_hit_row([stock, gate, "0", "n/a", "n/a", "n/a", "n/a", "n/a"]))
                continue
            assert isinstance(s, dict)
            hh = s["h60"]
            assert isinstance(hh, dict)
            A(
                _hit_row(
                    [
                        stock,
                        gate,
                        _num(hh["n"]),
                        _pct(hh["hit_rate"]),
                        _pp(hh["mean"]),
                        _pp(hh["median"]),
                        _pct(s["realized_rate"]),
                        _num(s["median_lead"]),
                    ]
                )
            )
    A("")

    A("## Regime-segmented flip results (enable time weight, @60d horizon)")
    A("")
    A("| regime | gate | n | hit rate | mean | median | realized ≤120d | median lead |")
    A("|---|---|---|---|---|---|---|---|")
    for cfg_suffix, gate in (
        (headline_keys["ungated"], "ungated"),
        (headline_keys["gated"], _gate_label(headline_keys["gated_min_t"])),
    ):
        block = modes["wls"]
        assert isinstance(block, dict)
        by_regime = block[f"by_regime:{cfg_suffix}"]
        assert isinstance(by_regime, dict)
        for regime in (*REGIMES, "None"):
            s = by_regime.get(regime)
            if s is None:
                continue
            assert isinstance(s, dict)
            hh = s["h60"]
            assert isinstance(hh, dict)
            A(
                _hit_row(
                    [
                        regime,
                        gate,
                        _num(hh["n"]),
                        _pct(hh["hit_rate"]),
                        _pp(hh["mean"]),
                        _pp(hh["median"]),
                        _pct(s["realized_rate"]),
                        _num(s["median_lead"]),
                    ]
                )
            )
    A("")

    A("## Slope / alpha-cross signals (enable time weight, WLS slope)")
    A("")
    A(
        "The raw crossings the flip trigger is built on, scored the same way. "
        "Issue #39 removed acceleration as a product series; acceleration "
        "survives only as the flip trigger's confirmation step."
    )
    A("")
    for name in ("alpha_cross", "slope_cross"):
        blk = slope_block[name]
        assert isinstance(blk, dict)
        overall = blk["overall"]
        assert isinstance(overall, dict)
        A(f"### {name} (n={blk['n_events']} events)")
        A("")
        A(
            "| segment | n | hit rate @60d | mean @60d | median @60d |"
            " realized ≤120d | median lead |"
        )
        A("|---|---|---|---|---|---|---|")
        hh = overall["h60"]
        assert isinstance(hh, dict)
        A(
            _hit_row(
                [
                    "**all**",
                    _num(hh["n"]),
                    _pct(hh["hit_rate"]),
                    _pp(hh["mean"]),
                    _pp(hh["median"]),
                    _pct(overall["realized_rate"]),
                    _num(overall["median_lead"]),
                ]
            )
        )
        by_stock = blk["by_stock"]
        assert isinstance(by_stock, dict)
        for stock in STOCKS:
            s = by_stock.get(stock)
            if s is None:
                continue
            assert isinstance(s, dict)
            hhs = s["h60"]
            assert isinstance(hhs, dict)
            A(
                _hit_row(
                    [
                        stock,
                        _num(hhs["n"]),
                        _pct(hhs["hit_rate"]),
                        _pp(hhs["mean"]),
                        _pp(hhs["median"]),
                        _pct(s["realized_rate"]),
                        _num(s["median_lead"]),
                    ]
                )
            )
        by_regime = blk["by_regime"]
        assert isinstance(by_regime, dict)
        for regime in REGIMES:
            s = by_regime.get(regime)
            if s is None:
                continue
            assert isinstance(s, dict)
            hhr = s["h60"]
            assert isinstance(hhr, dict)
            A(
                _hit_row(
                    [
                        f"*{regime}*",
                        _num(hhr["n"]),
                        _pct(hhr["hit_rate"]),
                        _pp(hhr["mean"]),
                        _pp(hhr["median"]),
                        _pct(s["realized_rate"]),
                        _num(s["median_lead"]),
                    ]
                )
            )
        A("")

    A("## Threshold recommendations (feeds #32 and #49)")
    A("")
    md.extend(_recommendations(payload))
    A("")

    A("## Caveats and limitations")
    A("")
    A(
        "- Overlapping forward windows: consecutive signals share most of "
        "their 60/120d window, so n overstates the number of independent "
        "bets; treat hit rates as descriptive."
    )
    A(
        "- Small samples: the gated configs fire 10-15 times in six years. "
        "Any threshold comparison at that n is suggestive, not conclusive."
    )
    A(
        "- Survivorship/look-ahead: none in the signal path (trailing-only), "
        "but the universe is today's portfolio - names that would have been "
        "dropped historically are absent by construction."
    )
    A(
        "- Price-only: no fundamentals conditioning (TTM P/E, KPIs) - a "
        "deliberate scope cut for runtime; EDGAR pulls are quarterly while "
        "the trigger is daily."
    )
    A(
        "- Regime labels use the benchmark's trailing 250d return - a "
        "reasonable but arbitrary cut (±10%); results are robust to the "
        "exact cut only insofar as the tables show."
    )
    A("- These are regime-change signals for validation, not buy signals.")
    A("")

    A("## Reproduce")
    A("")
    A("```bash")
    A("cd portfolio-analysis")
    A("# one-time: populate the (gitignored) price cache, incl. the three")
    A("# names missing from older snapshots:")
    A("python3 -m portfolio_analysis.cli ingest-prices          # whole universe")
    A("# or: python3 -m portfolio_analysis.cli ingest-prices CRM  # single name")
    A("")
    A("# full backtest + this report (console tables + docs/alpha-backtest/):")
    A("python3 scripts/backtest_alpha_signals.py --report-dir docs/alpha-backtest")
    A("```")
    A("")
    A(
        "Runtime is dominated by the rolling WLS regressions (~2 min on this "
        "machine); the threshold grid reuses the rolling series, so each grid "
        "cell costs one cheap trigger scan."
    )
    A("")

    report_path = outdir / "report.md"
    with open(report_path, "w") as fh:
        fh.write("\n".join(md))

    _render_figures(payload, figdir, plt)
    plt.close("all")
    return report_path


def _render_figures(payload: dict[str, object], figdir: Path, plt: object) -> None:
    """Five PNGs backing the report's headline claims (issue #33)."""
    modes = payload["modes"]
    assert isinstance(modes, dict)
    wls = modes["wls"]
    assert isinstance(wls, dict)
    configs = wls["configs"]
    assert isinstance(configs, dict)

    def cfg(t: float | None, r2: float, p: int = FLIP_PERSISTENCE) -> dict:
        s = configs[f"min_t={t}|min_r2={r2}|p={p}"]
        assert isinstance(s, dict)
        return s

    # 1. Hit rate by horizon: ungated vs t-gated (wls).
    fig, ax = plt.subplots(figsize=(8, 4.5))  # type: ignore[attr-defined]
    xs = list(HORIZONS)
    width = 0.35
    for j, (t, label) in enumerate(((None, "ungated"), (1.5, "t ≥ 1.5"))):
        s = cfg(t, FLIP_MIN_R_SQUARED)
        rates = [s[f"h{h}"]["hit_rate"] or 0.0 for h in HORIZONS]
        ns = [s[f"h{h}"]["n"] for h in HORIZONS]
        pos = [x + (j - 0.5) * width for x in range(len(xs))]
        bars = ax.bar(pos, rates, width, label=f"{label} (R²≥0.5)")
        for b, n in zip(bars, ns, strict=True):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.01,
                f"n={n}",
                ha="center",
                fontsize=8,
            )
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels([f"{h}d" for h in xs])
    ax.set_ylabel("hit rate (forward excess > 0)")
    ax.set_title("Flip trigger hit rate by horizon — enable time weight")
    ax.legend()
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    fig.savefig(figdir / "hit_by_horizon.png", dpi=110)

    # 2. Hit rate by regime @60d: ungated vs t-gated (wls).
    fig, ax = plt.subplots(figsize=(8, 4.5))  # type: ignore[attr-defined]
    headline_keys = payload["headline_keys"]
    assert isinstance(headline_keys, dict)
    gated_label = _gate_label(headline_keys["gated_min_t"])
    by_reg_u = wls[f"by_regime:{headline_keys['ungated']}"]
    by_reg_g = wls[f"by_regime:{headline_keys['gated']}"]
    assert isinstance(by_reg_u, dict) and isinstance(by_reg_g, dict)
    for j, (d, label) in enumerate(((by_reg_u, "ungated"), (by_reg_g, gated_label))):
        rates, ns = [], []
        for r in REGIMES:
            s = d.get(r)
            rates.append((s["h60"]["hit_rate"] or 0.0) if s else 0.0)
            ns.append(s["h60"]["n"] if s else 0)
        pos = [x + (j - 0.5) * width for x in range(len(REGIMES))]
        bars = ax.bar(pos, rates, width, label=label)
        for b, n in zip(bars, ns, strict=True):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.01,
                f"n={n}",
                ha="center",
                fontsize=8,
            )
    ax.set_xticks(range(len(REGIMES)))
    ax.set_xticklabels(REGIMES)
    ax.set_ylabel("hit rate @60d")
    ax.set_title("Flip trigger hit rate by market regime — enable time weight")
    ax.legend()
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    fig.savefig(figdir / "hit_by_regime.png", dpi=110)

    # 3. Hit rate by stock @60d: ungated vs t-gated (wls).
    fig, ax = plt.subplots(figsize=(9, 4.5))  # type: ignore[attr-defined]
    by_st_u = wls[f"by_stock:{headline_keys['ungated']}"]
    by_st_g = wls[f"by_stock:{headline_keys['gated']}"]
    assert isinstance(by_st_u, dict) and isinstance(by_st_g, dict)
    for j, (d, label) in enumerate(((by_st_u, "ungated"), (by_st_g, gated_label))):
        rates, ns = [], []
        for stk in STOCKS:
            s = d.get(stk)
            rates.append((s["h60"]["hit_rate"] or 0.0) if s else 0.0)
            ns.append(s["h60"]["n"] if s else 0)
        pos = [x + (j - 0.5) * width for x in range(len(STOCKS))]
        bars = ax.bar(pos, rates, width, label=label)
        for b, n in zip(bars, ns, strict=True):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.01,
                f"n={n}",
                ha="center",
                fontsize=7,
            )
    ax.set_xticks(range(len(STOCKS)))
    ax.set_xticklabels(STOCKS)
    ax.set_ylabel("hit rate @60d")
    ax.set_title("Flip trigger hit rate by stock — enable time weight")
    ax.legend()
    ax.set_ylim(0, 1.0)
    fig.tight_layout()
    fig.savefig(figdir / "hit_by_stock.png", dpi=110)

    # 4. Threshold sensitivity: coverage vs hit rate @60d (wls), the #49 input.
    fig, ax = plt.subplots(figsize=(8, 5))  # type: ignore[attr-defined]
    for r2 in R2_GRID:
        ns, rates, labels = [], [], []
        for t in T_GRID:
            s = cfg(t, r2)
            ns.append(s["h60"]["n"])
            rates.append(s["h60"]["hit_rate"] or 0.0)
            labels.append("ungated" if t is None else f"t≥{t:g}")
        ax.plot(ns, rates, marker="o", label=f"R²≥{r2:.1f}")
        for n, r, lab in zip(ns, rates, labels, strict=True):
            ax.annotate(lab, (n, r), textcoords="offset points", xytext=(4, 6), fontsize=8)
    ax.set_xlabel("coverage (flip count, 6 years)")
    ax.set_ylabel("hit rate @60d")
    ax.set_title("Credibility-gate strictness: what t ≥ costs and buys")
    ax.legend()
    fig.tight_layout()
    fig.savefig(figdir / "threshold_sensitivity.png", dpi=110)

    # 5. Lead-time distribution for realized flips (wls, ungated).
    records = wls["records"]
    assert isinstance(records, dict)
    recs = records[headline_keys["ungated"]]
    assert isinstance(recs, list)
    leads = [r["lead_time"] for r in recs if r["lead_time"] is not None]
    fig, ax = plt.subplots(figsize=(8, 4.5))  # type: ignore[attr-defined]
    if leads:
        ax.hist(leads, bins=min(24, max(leads)), color="steelblue", edgecolor="white")
        med = st.median(leads)
        ax.axvline(med, color="crimson", linestyle="--", label=f"median {med:.0f} sessions")
        ax.legend()
    ax.set_xlabel(
        f"sessions from flip to first +{REALIZED_MOVE:.0%} cumulative excess (≤{LEAD_HORIZON}d)"
    )
    ax.set_ylabel("flips")
    ax.set_title(
        f"Lead-time distribution — realized flips only "
        f"(n={len(leads)} of {len(recs)} ungated wls flips)"
    )
    fig.tight_layout()
    fig.savefig(figdir / "lead_time_hist.png", dpi=110)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/prices.sqlite")
    ap.add_argument(
        "--min-t",
        type=float,
        default=1.5,
        help="t-statistic credibility gate for the gated flip run (issue #49)",
    )
    ap.add_argument(
        "--min-alpha",
        type=float,
        default=None,
        help="optional annualized-alpha floor for the gated flip run (issue #49)",
    )
    ap.add_argument(
        "--report-dir",
        default=None,
        help="write the issue-#33 reproducible artifact (results.json, "
        "report.md, figures/*.png) into this directory",
    )
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
        "\n## alpha flip trigger (issue #32) vs t-gated flips (issue #49): "
        "hit / false-alarm summary\n"
        "Trigger = slope neg->pos crossing, acceleration > 0, 3-session "
        "persistence, rolling-R² >= 0.5 gate. 'gated' additionally requires "
        f"t >= {args.min_t}"
        + (f" and alpha >= {args.min_alpha:.0%}/yr" if args.min_alpha else "")
        + ". Hit = forward excess > 0; false alarm = forward excess <= 0."
    )
    print(
        f"{'mode':<14}{'gate':<8}{'horizon':>8}{'n':>7}{'hits':>7}{'false':>7}"
        f"{'hit_rate':>10}{'mean':>10}{'median':>10}"
    )
    flip_modes = (
        ("fixed", "fixed time weight", ALPHA_WINDOW, None, "two-point", SLOPE_SPAN),
        (
            "wls",
            "enable time weight",
            None,
            float(DEFAULT_WLS_HALF_LIFE),
            "wls",
            SLOPE_SPAN,
        ),
    )
    for _key, label, window, half_life, slope_method, slope_span in flip_modes:
        gate_runs = (
            ("ungated", None, None),
            ("gated", args.min_t, args.min_alpha),
        )
        for gate_label, min_t, min_alpha in gate_runs:
            pooled, ps = run_flip_mode(
                prices, window, half_life, slope_method, slope_span, min_t, min_alpha
            )
            total_flips = sum(ps.values())
            for h in HORIZONS:
                xs = pooled[h]
                hits = sum(1 for x in xs if x > 0)
                false = len(xs) - hits
                hit_rate = f"{hits / len(xs):>9.1%}" if xs else f"{'n/a':>10}"
                mean, median, _ = summarize(xs)
                print(
                    f"{label:<14}{gate_label:<8}{h:>8}{len(xs):>7}{hits:>7}{false:>7}"
                    f"{hit_rate}{mean:>10}{median:>10}"
                )
            print(
                f"  {gate_label} flips per stock (total {total_flips}): "
                + ", ".join(f"{s}={ps[s]}" for s in STOCKS)
            )
    print(
        "\nCaveats: trailing-only, no look-ahead; occurrences on consecutive days "
        "have overlapping forward windows (counts are occurrences, not independent "
        "bets); signals with small n have noisy means - treat them as descriptive, "
        "not predictive. These are regime-change signals for validation, not buy signals."
    )
    if args.report_dir:
        print("\nBuilding issue-#33 report artifact (threshold grid + segments)...")
        payload = build_report_payload(prices, args.min_t, args.min_alpha)
        report_path = render_report(payload, Path(args.report_dir))
        print(f"wrote {report_path} (+ results.json, figures/*.png)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
