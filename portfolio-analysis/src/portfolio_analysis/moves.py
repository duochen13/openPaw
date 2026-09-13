"""Move detection (spec §5). Pure statistics - no I/O, no network, no database.

    r_t      = adj_close_t / adj_close_{t-1} - 1
    beta     = OLS slope of r on r_benchmark over [t-250, t-1]
    AR_t     = r_t - beta * r_benchmark_t
    sigma_60 = stdev(AR) over [t-60, t-1]
    z_t      = AR_t / sigma_60

A day is flagged when |z_t| >= 2.5.

Both estimation windows end at t-1. This is a statistical requirement, not a
point-in-time one: including day t in the volatility estimate that day t must
clear makes the threshold move with the thing it is measuring.

The historical abnormal returns used for sigma are computed with the SAME beta
estimated at t, rather than each with its own contemporaneous beta. This is the
constant-beta convention of a standard event study, and it avoids a recursive
estimation whose result would depend on where the series happened to start.
"""
from __future__ import annotations

import statistics as st
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from portfolio_analysis.config import MoveParams
from portfolio_analysis.naming import safe_ticker_component

#: Halts and one-off listing gaps are tolerated; a systematic calendar
#: disagreement is not, because every return spanning a gap is fabricated.
_MAX_DROPPED_DATES = 5


def aligned_returns(
    asset: Mapping[str, float], benchmark: Mapping[str, float]
) -> tuple[list[str], list[float], list[float]]:
    """Simple returns over consecutive dates present in both series.

    Returns (dates, asset_returns, benchmark_returns), all the same length and
    one shorter than the common date set. `dates[i]` is the date the return
    was realized on.
    """
    common = sorted(set(asset) & set(benchmark))
    dropped = (len(asset) - len(common)) + (len(benchmark) - len(common))
    if dropped > _MAX_DROPPED_DATES:
        raise ValueError(
            f"{dropped} dates are missing from one series or the other; the two "
            "series disagree about the trading calendar, so every return "
            "spanning a gap would be fabricated"
        )
    if len(common) < 2:
        raise ValueError(f"need at least two common dates, got {len(common)}")

    dates: list[str] = []
    asset_returns: list[float] = []
    benchmark_returns: list[float] = []
    # pairwise, not zip(common, common[1:]): the two arms are deliberately
    # different lengths, so strict=True rejects it and a bare zip trips B905.
    for previous, current in pairwise(common):
        for series, name in ((asset, "asset"), (benchmark, "benchmark")):
            if series[previous] <= 0:
                raise ValueError(
                    f"non-positive {name} price {series[previous]!r} on {previous}"
                )
        dates.append(current)
        asset_returns.append(asset[current] / asset[previous] - 1)
        benchmark_returns.append(benchmark[current] / benchmark[previous] - 1)
    return dates, asset_returns, benchmark_returns


def ols_beta(asset: Sequence[float], benchmark: Sequence[float]) -> float:
    """Slope of the OLS regression of asset returns on benchmark returns.

    cov / var, which is the slope of the least-squares line. The intercept is
    alpha and is deliberately not returned: this project measures how much of a
    move the market explains, not whether the name outperforms.
    """
    if len(asset) != len(benchmark):
        raise ValueError(
            f"series must be the same length, got {len(asset)} and {len(benchmark)}"
        )
    if len(asset) < 2:
        raise ValueError(f"need at least two observations, got {len(asset)}")

    mean_asset = st.fmean(asset)
    mean_benchmark = st.fmean(benchmark)
    covariance = st.fmean(
        (a - mean_asset) * (b - mean_benchmark)
        for a, b in zip(asset, benchmark, strict=True)
    )
    variance = st.fmean((b - mean_benchmark) ** 2 for b in benchmark)
    if variance == 0:
        raise ValueError("benchmark has zero variance over the window; beta is undefined")
    return covariance / variance


@dataclass(frozen=True)
class Move:
    """One flagged day, fully decomposed (spec §7 `move` block)."""

    ticker: str
    date: str
    ret: float
    benchmark: str
    benchmark_return: float
    beta: float
    abnormal_return: float
    sigma_60: float
    z: float

    def as_row(self) -> dict[str, object]:
        """The shape Store.upsert_moves expects."""
        return {
            "ticker": self.ticker,
            "date": self.date,
            "ret": self.ret,
            "benchmark": self.benchmark,
            "benchmark_return": self.benchmark_return,
            "beta": self.beta,
            "abnormal_return": self.abnormal_return,
            "sigma_60": self.sigma_60,
            "z": self.z,
        }


@dataclass(frozen=True)
class Coverage:
    """What was and was not evaluated (spec §5, §7)."""

    price_series: tuple[str, str] | None
    evaluated: tuple[str, str] | None
    evaluated_days: int
    flagged_days: int


def compute_moves(
    ticker: str,
    benchmark_name: str,
    asset: Mapping[str, float],
    benchmark: Mapping[str, float],
    params: MoveParams,
) -> tuple[list[Move], Coverage]:
    """Flagged days and the coverage of the evaluation.

    A series too short to fill the beta window yields no moves and a coverage
    report saying so. A newly listed ticker is a coverage fact, not an error.
    """
    symbol = safe_ticker_component(ticker)
    common = sorted(set(asset) & set(benchmark))
    price_series = (common[0], common[-1]) if common else None

    if len(common) < 2:
        return [], Coverage(price_series, None, 0, 0)

    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)

    first = params.beta_window
    if first >= len(dates):
        return [], Coverage(price_series, None, 0, 0)

    moves: list[Move] = []
    for index in range(first, len(dates)):
        window = slice(index - params.beta_window, index)
        beta = ols_beta(asset_returns[window], benchmark_returns[window])

        # Constant beta across the sigma window, per the module docstring.
        abnormal = [
            asset_returns[j] - beta * benchmark_returns[j]
            for j in range(index - params.sigma_window, index + 1)
        ]
        sigma = st.stdev(abnormal[:-1])
        if sigma == 0:
            raise ValueError(
                f"{symbol}: zero abnormal-return volatility ending {dates[index - 1]}; "
                "z is undefined"
            )
        z = abnormal[-1] / sigma
        if abs(z) >= params.z_threshold:
            moves.append(Move(
                ticker=symbol,
                date=dates[index],
                ret=asset_returns[index],
                benchmark=benchmark_name,
                benchmark_return=benchmark_returns[index],
                beta=beta,
                abnormal_return=abnormal[-1],
                sigma_60=sigma,
                z=z,
            ))

    return moves, Coverage(
        price_series=price_series,
        evaluated=(dates[first], dates[-1]),
        evaluated_days=len(dates) - first,
        flagged_days=len(moves),
    )
