"""Self-contained evidence chart. Source headlines are not causal attribution."""

from __future__ import annotations

import html
import json
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from portfolio_analysis import kpis as kpis_module
from portfolio_analysis import manual_kpis as manual_kpis_module
from portfolio_analysis import positions as positions_module
from portfolio_analysis.artifacts import MovesArtifact, read_moves
from portfolio_analysis.bundle import SCHEMA_VERSION, bundle_hash, move_payload
from portfolio_analysis.config import Portfolio
from portfolio_analysis.events.base import dated_fact_label
from portfolio_analysis.fundamentals import pe_series
from portfolio_analysis.moves import (
    aligned_returns,
    annualize_alpha,
    correlation,
    decay_weights,
    ols_beta,
    ols_regression,
    wls_regression,
)
from portfolio_analysis.naming import safe_ticker_component
from portfolio_analysis.signals import (
    DEFAULT_WLS_HALF_LIFE,
    REGIME_WINDOWS,
    SLOPE_SPAN,
    SLOPE_SPANS,
    WLS_HALF_LIVES,
    alpha_signal,
    rolling_alpha_daily,
    rolling_slope,
    smooth_display,
)
from portfolio_analysis.store import Store

#: Sample the rolling beta/alpha series this often (trading days). Sixty-odd
#: points keeps the embedded JSON small while still showing regime changes
#: like a beta collapsing from 1.0 to 0.27.
_REGIME_STEP = 21

#: Recent sessions kept at daily resolution for zoomed-in views (issue #41).
#: 400 sessions (~19 months) bounds the embedded payload: the fine series is
#: only embedded for this tail, and the chart falls back to the monthly
#: sampling for earlier history.
_FINE_TAIL_SESSIONS = 400

#: Hard cap on TLDR words (issue #42).
_TLDR_MAX_WORDS = 100


def safe_url(value: object) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
        return text if parsed.scheme in {"https", "http"} and parsed.netloc else ""
    except ValueError:
        return ""


def _plain(value: object) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))


def _facts(bundle: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for fact in bundle["verified"]:
        value = fact.get("value")
        if not isinstance(value, dict):
            continue
        labeled = dated_fact_label(fact["key"], value)
        if labeled is None:
            continue
        label, day = labeled
        rows.append(
            {
                "label": label,
                "date": day,
                "detail": str(fact.get("detail", "")),
                "url": safe_url(value.get("url") or fact.get("source")),
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["label"]))


def _documents(bundle: dict[str, Any], aliases: tuple[str, ...]) -> list[dict[str, Any]]:
    docs = [
        {
            "id": doc["doc_id"],
            "title": _plain(doc["title"]),
            "summary": _plain(doc.get("summary", "")),
            "url": safe_url(doc["url"]),
            "source": doc["source"],
            "published_at": doc["published_at"],
            "relevance": doc.get("relevance"),
        }
        for doc in bundle["documents"]
    ]
    # Editorial ordering only, never a causal score or support count.
    words = re.compile(
        r"\b(stock|shares|earnings|revenue|profit|capex|guidance|antitrust|lawsuit)\b", re.I
    )
    company = re.compile(
        r"\b(?:" + "|".join(re.escape(a) for a in (bundle["ticker"], *aliases)) + r")\b", re.I
    )
    return sorted(
        docs,
        key=lambda doc: (
            -int(doc["source"] == "alphavantage_news"),
            -int(bool(company.search(doc["title"]))),
            -len(words.findall(doc["title"])),
            -float(doc["relevance"] or 0),
            doc["published_at"],
            doc["id"],
        ),
    )


def _trailing_factor(
    asset: dict[str, float],
    benchmark: dict[str, float],
    window: int,
    benchmark_name: str,
) -> dict[str, object] | None:
    """Trailing-window beta, annualized alpha, and R² vs the benchmark.

    Returns None when the series is shorter than one full window or the
    trailing window is degenerate: a beta over a partial window is not
    comparable to the detection beta, and a made-up number here would be
    worse than no number. The template hides the strip when this is None.
    """
    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)
    if len(asset_returns) < window:
        return None
    try:
        beta, alpha, r_squared = ols_regression(
            asset_returns[-window:], benchmark_returns[-window:], r_squared=True
        )
    except ValueError:
        return None
    return {
        "beta": beta,
        "r_squared": r_squared,
        "alpha_annualized": annualize_alpha(alpha),
        "window": window,
        "as_of": dates[-1],
        "benchmark": benchmark_name,
        "note": (
            "Trailing OLS intercept vs the benchmark: the drift the market "
            "does not explain. A historical residual, not a forecast."
        ),
    }


def _industry_factor(
    asset: dict[str, float],
    industry: dict[str, float],
    window: int,
    industry_name: str,
) -> dict[str, object] | None:
    """Trailing-window beta, annualized alpha, and correlation vs the industry.

    Computed over the overlapping window only: a short industry history (e.g.
    MAGS, listed April 2023) contributes only its overlap with the asset.
    Returns None when the overlap is shorter than one full window or the
    regression is degenerate - no made-up numbers, the same rule as
    _trailing_factor. The template hides the strip when this is None.
    """
    try:
        dates, asset_returns, industry_returns = aligned_returns(asset, industry)
    except ValueError:
        return None
    if len(asset_returns) < window:
        return None
    try:
        beta, alpha = ols_regression(asset_returns[-window:], industry_returns[-window:])
        rho = correlation(asset_returns[-window:], industry_returns[-window:])
    except ValueError:
        return None
    return {
        "beta": beta,
        "alpha_annualized": annualize_alpha(alpha),
        "correlation": rho,
        "window": window,
        "as_of": dates[-1],
        "benchmark": industry_name,
        "note": (
            "Trailing OLS intercept vs the industry benchmark: the drift the "
            "industry does not explain. A historical residual, not a forecast."
        ),
    }


def _regime_ends(n: int, warmup_end: int, step: int, tail: int | None) -> list[int]:
    """Sampling grid for the regime series (issue #50: shared helper).

    Sessions ``warmup_end .. n`` sampled every ``step``; ``tail`` keeps only
    the most recent ``tail`` sessions (daily fine series); the most recent
    session is always included. ``_regime_points`` and the WLS-slope series
    share this grid so their ``dates`` arrays line up exactly.
    """
    ends = list(range(warmup_end, n + 1, step))
    if tail is not None:
        ends = [e for e in ends if e > n - tail]
    if not ends or ends[-1] != n:
        ends.append(n)
    return ends


def _regime_points(
    asset: dict[str, float],
    benchmark: dict[str, float],
    window: int | None = None,
    step: int = _REGIME_STEP,
    tail: int | None = None,
    *,
    half_life: float | None = None,
    slope_span: int = SLOPE_SPAN,
) -> dict[str, list[object]]:
    """Rolling beta, annualized alpha, R², alpha slope and turnaround signals,
    sampled every `step` sessions.

    Exactly one of ``window`` (hard-window OLS, "fixed time weight") or
    ``half_life`` (exponentially-decayed WLS over the growing history,
    "enable time weight", issue #47) must be set.

    R² is computed over the identical return observations as beta and alpha.
    The slope is the change in *annualized* alpha per trading session over
    ``slope_span`` sessions (see ``signals`` for the unit convention),
    derived from the full daily alpha series and then sampled, so the "N
    trading days" definition is exact, not an artifact of the sampling grid.
    ``signals[i]`` classifies the sampled point ("turnaround" or ``None``);
    slope and signals are ``None`` during their warmup. Empty when the series
    is shorter than one full window (OLS) or one half-life (WLS), for the
    same reason as _trailing_factor. The most recent session is always the
    last point. A degenerate window (zero variance, so beta/alpha/R² are all
    undefined) is skipped, never filled with a made-up number.

    ``tail`` keeps only the most recent ``tail`` sessions before sampling
    (used for the daily fine series in issue #41), so the embedded payload
    stays bounded: zoomed-out views use the monthly sampling instead.
    """
    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)
    empty: dict[str, list[Any]] = {
        "dates": [],
        "beta": [],
        "r_squared": [],
        "alpha_annualized": [],
        "alpha_slope": [],
        # Display-only smoothing of the slope (trailing average over the
        # sampled points). Signals and the TLDR keep the raw alpha_slope.
        "alpha_slope_display": [],
        "signals": [],
    }
    if (window is None) == (half_life is None):
        raise ValueError("exactly one of window and half_life must be set")
    use_wls = half_life is not None
    if use_wls:
        assert half_life is not None
        min_history = max(2, int(half_life))
    else:
        assert window is not None
        min_history = window
    if len(asset_returns) < min_history:
        return empty
    if half_life is None:
        assert window is not None
        alpha_daily = rolling_alpha_daily(asset_returns, benchmark_returns, window)
        slope_daily = rolling_slope(alpha_daily, slope_span)
        warmup_end = window
    else:
        alpha_daily = rolling_alpha_daily(
            asset_returns, benchmark_returns, None, half_life=half_life
        )
        # Issue #50: the "enable time weight" tab keeps the legacy two-point
        # slope; the WLS-regression slope lives only in the third tab's
        # separate payload (_wls_slope_payload).
        slope_daily = rolling_slope(alpha_daily, slope_span)
        warmup_end = max(2, int(half_life))
    n = len(asset_returns)
    ends = _regime_ends(n, warmup_end, step, tail)
    out: dict[str, list[Any]] = {key: [] for key in empty}
    for end in ends:
        i = end - 1  # return index whose date is dates[end - 1]
        alpha_ann = alpha_daily[i]
        if alpha_ann is None:
            continue  # degenerate window: beta/alpha/R² undefined, skip
        if half_life is None:
            assert window is not None
            beta, _, r_squared = ols_regression(
                asset_returns[end - window : end],
                benchmark_returns[end - window : end],
                r_squared=True,
            )
        else:
            weights = decay_weights(end, half_life)
            beta, _, r_squared = wls_regression(
                asset_returns[:end],
                benchmark_returns[:end],
                weights,
                r_squared=True,
            )
        out["dates"].append(dates[i])
        out["beta"].append(beta)
        out["r_squared"].append(r_squared)
        out["alpha_annualized"].append(alpha_ann)
        out["alpha_slope"].append(slope_daily[i])
        out["signals"].append(alpha_signal(alpha_ann, slope_daily[i]))
    out["alpha_slope_display"] = smooth_display(
        [s if isinstance(s, float) else None for s in out["alpha_slope"]]
    )
    return out


def _wls_slope_series(
    dates: list[str],
    alpha_daily: list[float | None],
    half_life: float,
    slope_span: int,
    step: int = _REGIME_STEP,
    tail: int | None = None,
) -> dict[str, list[object]]:
    """Sampled WLS-regression slope + turnaround signals for one
    ``(half_life, slope_span)`` combo (issue #50).

    Powers the "enable time weight (alpha slope)" tab: the beta/R²/alpha
    panels keep reading the ``wls`` payload for this half-life, while the
    slope sparkline and signal markers read this series. ``alpha_daily`` is
    the full daily WLS alpha series for ``half_life`` (computed once by the
    caller and shared across spans); the slope is the WLS regression of the
    trailing ``slope_span`` alphas with the same half-life decay, so recent
    sessions dominate the fit. The sampling grid matches
    ``_regime_points(half_life=half_life, step=step, tail=tail)`` exactly,
    so the ``dates`` arrays line up.

    Signals classify each sampled point with this combo's slope
    (``alpha < 0 and slope > 0``); warmup and ``None``-poisoning follow
    ``rolling_slope``, never fabricated.
    """
    n = len(alpha_daily)
    warmup_end = max(2, int(half_life))
    if n < warmup_end:
        return {"dates": [], "alpha_slope": [], "alpha_slope_display": [], "signals": []}
    slope_daily = rolling_slope(alpha_daily, slope_span, half_life=half_life)
    out: dict[str, list[Any]] = {
        "dates": [],
        "alpha_slope": [],
        "alpha_slope_display": [],
        "signals": [],
    }
    for end in _regime_ends(n, warmup_end, step, tail):
        i = end - 1
        alpha_ann = alpha_daily[i]
        if alpha_ann is None:
            continue  # degenerate alpha: same skip rule as _regime_points
        out["dates"].append(dates[i])
        out["alpha_slope"].append(slope_daily[i])
        out["signals"].append(alpha_signal(alpha_ann, slope_daily[i]))
    out["alpha_slope_display"] = smooth_display(
        [s if isinstance(s, float) else None for s in out["alpha_slope"]]
    )
    return out


def _wls_slope_payload(
    asset: dict[str, float], benchmark: dict[str, float], *, fine: bool
) -> dict[str, dict[str, dict[str, list[object]]]]:
    """Nested ``{half_life: {slope_span: series}}`` payload for the
    "enable time weight (alpha slope)" tab (issue #50).

    The daily WLS alpha series is computed once per half-life and shared
    across spans; ``fine`` selects the daily-tail sampling for zoomed views
    (mirroring ``wls_fine``) versus the monthly sampling (mirroring ``wls``).
    """
    step = 1 if fine else _REGIME_STEP
    tail = _FINE_TAIL_SESSIONS if fine else None
    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)
    payload: dict[str, dict[str, dict[str, list[object]]]] = {}
    for half_life in WLS_HALF_LIVES:
        h = float(half_life)
        if len(asset_returns) < max(2, int(h)):
            continue
        alpha_daily = rolling_alpha_daily(asset_returns, benchmark_returns, None, half_life=h)
        payload[str(half_life)] = {
            str(span): _wls_slope_series(dates, alpha_daily, h, span, step=step, tail=tail)
            for span in SLOPE_SPANS
        }
    return payload


def _operating_differs(
    quarters: list[tuple[str, str, float]],
    operating_quarters: list[tuple[str, str, float | None]],
) -> bool:
    """True when the operating series actually adjusts GAAP anywhere.

    A quarter counts as differing when its operating EPS is a gap (None) or
    numerically different from GAAP. Fallback quarters copy the GAAP float
    exactly, so plain inequality is safe.
    """
    gaap = {q: eps for q, _, eps in quarters}
    for q, _, op_eps in operating_quarters:
        if q not in gaap:
            continue
        if op_eps is None or op_eps != gaap[q]:
            return True
    return False


def _pe_panel(
    asset: dict[str, float],
    quarters: list[tuple[str, str, float]],
    operating_quarters: list[tuple[str, str, float | None]] | None = None,
) -> dict[str, object] | None:
    """Rolling TTM P/E panel data (issue #28), plus operating P/E (#70).

    Daily adjusted close over the TTM EPS in effect that day. Returns None
    when no quarter is stored at all - the template hides the section, the
    same rule as the factor strips. Days before the fourth reported quarter
    (or with non-positive TTM EPS) carry None: gaps, never invented numbers.

    ``operating_quarters`` carries the derived operating EPS series
    (ex-investment gains). The ``"operating"`` sub-panel is populated only
    when it actually differs from GAAP; otherwise ``"operating"`` is None
    and the template shows a "no adjustment available" note instead of a
    meaningless toggle.
    """
    if not quarters:
        return None
    series = pe_series(asset, quarters)
    dates = sorted(series)
    pe = [series[d]["pe"] for d in dates]
    ttm = [series[d]["ttm_eps"] for d in dates]
    defined = [(d, v) for d, v in zip(dates, pe, strict=True) if v is not None]
    current = defined[-1] if defined else (None, None)
    current_ttm = ttm[dates.index(current[0])] if current[0] else None
    panel: dict[str, object] = {
        "dates": dates,
        "pe": pe,
        "ttm_eps": ttm,
        "current_pe": current[1],
        "current_ttm_eps": current_ttm,
        "as_of": current[0],
        "quarters_reported": len(quarters),
        "operating": None,
        "has_operating_adjustment": False,
        "methodology": (
            "Operating EPS excludes realized/unrealized gains (losses) on "
            "equity securities, tax-adjusted at the quarter's effective tax "
            "rate - an approximation, not the company's reported non-GAAP EPS."
        ),
    }
    if operating_quarters and _operating_differs(quarters, operating_quarters):
        op_series = pe_series(asset, operating_quarters, eps_source="operating")
        op_dates = sorted(op_series)
        op_pe = [op_series[d]["pe"] for d in op_dates]
        op_ttm = [op_series[d]["ttm_eps"] for d in op_dates]
        op_defined = [(d, v) for d, v in zip(op_dates, op_pe, strict=True) if v is not None]
        op_current = op_defined[-1] if op_defined else (None, None)
        op_current_ttm = op_ttm[op_dates.index(op_current[0])] if op_current[0] else None
        panel["operating"] = {
            "dates": op_dates,
            "pe": op_pe,
            "ttm_eps": op_ttm,
            "current_pe": op_current[1],
            "current_ttm_eps": op_current_ttm,
            "as_of": op_current[0],
            "quarters_reported": len(operating_quarters),
        }
        panel["has_operating_adjustment"] = True
    return panel


def _kpi_data(store: Store, symbol: str) -> dict[str, Any] | None:
    """Business-KPI panels for the per-stock chart (issues #29 + #59 + #67).

    EDGAR panels (#29) come first, then hand-entered manual panels (#59),
    each carrying ``"source": "manual"`` so the template can label them.
    Panels are then stably sorted into groups (issue #67) - "revenue"
    (revenue & demand) before "cost" (cost control) - so related metrics
    sit together regardless of config order. None when the ticker has
    neither EDGAR nor manual data - the template hides the section, the
    same rule as the P/E and factor panels. A broken KPI config degrades
    to a smaller section, never a crash.
    """
    try:
        metric_keys = kpis_module.load_kpi_config().get(symbol, [])
    except kpis_module.ConfigError:
        metric_keys = []
    series = {key: store.kpi_quarters(symbol, key) for key in metric_keys}
    series = {key: rows for key, rows in series.items() if rows}
    # Derived metrics (kind "spread") are computed at render time from the
    # stored component series - they are never fetched or stored.
    for key in metric_keys:
        spec = kpis_module.METRIC_DEFS.get(key)
        if not spec or spec.get("kind") != "spread" or key in series:
            continue
        num_key, den_key = spec["components"]
        if num_key in series and den_key in series:
            spread = kpis_module.spread_from_series(series[num_key], series[den_key])
            if spread:
                series[key] = spread
    panels = kpis_module.kpi_panels(series, metric_keys)
    metrics: list[dict[str, Any]] = list(panels["metrics"]) if panels else []
    try:
        manual_cfg = manual_kpis_module.load_manual_kpis()
    except manual_kpis_module.ManualKpiError:
        manual_cfg = None
    if manual_cfg is not None:
        metrics.extend(manual_kpis_module.manual_kpi_panels(manual_cfg.metrics.get(symbol, {})))
    if not metrics:
        return None
    return {"metrics": order_panels_by_group(metrics)}


#: Render order for KPI groups (issue #67): revenue & demand first, then
#: cost control, then anything ungrouped. Stable sort keeps config order
#: within a group.
_GROUP_RANK = {"revenue": 0, "cost": 1, "other": 2}


def order_panels_by_group(
    panels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Stable group sort for KPI panels (issue #67)."""
    return sorted(panels, key=lambda p: _GROUP_RANK.get(p.get("group", "other"), 2))


def _tldr_text(
    *,
    factor: dict[str, Any] | None,
    regime: dict[str, Any],
    moves: list[dict[str, Any]],
    benchmark: str,
) -> str:
    """Sub-100-word TLDR for the top of a stock page (issue #42).

    Generated from already-computed data at render time, so it refreshes
    with the data. Covers: alpha/beta trend + direction, 1-2 historical
    drivers from collected event windows, incoming catalysts, and a
    forward-looking read explicitly labeled as interpretation. When event
    windows are uncollected the text says so plainly instead of inventing
    drivers; when no upcoming catalyst dates exist it says that too. The
    hard word cap is enforced here, not trusted to phrasing.
    """
    parts: list[str] = []

    # 1. alpha/beta trend + direction, from the default (250-session) window.
    windows = regime.get("windows") or {}
    reg = windows.get("250") or {}
    alphas = [a for a in reg.get("alpha_annualized", []) if a is not None]
    slopes = [s for s in reg.get("alpha_slope", []) if s is not None]
    if alphas:
        alpha = alphas[-1]
        direction = ""
        if slopes:
            direction = (
                " and improving"
                if slopes[-1] > 0
                else " and still falling"
                if slopes[-1] < 0
                else " and flat"
            )
        parts.append(
            "\u03b1 is "
            f"{alpha:+.2%} annualized (trailing 250 sessions, fixed time weight)"
            f"{direction}."
        )
    else:
        parts.append("\u03b1 is unavailable \u2014 history is shorter than one window.")
    beta = (factor or {}).get("beta")
    if isinstance(beta, (int, float)):
        if beta < 0.5:
            relation = "the stock barely tracks the benchmark"
        elif beta < 0.8:
            relation = "the stock moves less than the market"
        elif beta <= 1.2:
            relation = "the stock moves roughly with the market"
        else:
            relation = "the stock amplifies market moves"
        # Beta trend from the 250-session regime series (issue #42 asks for
        # the trend, not just the level).
        betas = [b for b in reg.get("beta", []) if b is not None]
        trend = ""
        if len(betas) >= 2:
            delta = betas[-1] - betas[0]
            if abs(delta) < 0.05:
                trend = ", roughly steady over the window"
            elif delta < 0:
                trend = f", down from {betas[0]:.2f} at the start of the window"
            else:
                trend = f", up from {betas[0]:.2f} at the start of the window"
        parts.append(f"\u03b2 {beta:.2f} vs {benchmark}{trend} \u2014 {relation}.")

    # 2. historical drivers from collected dated events. Markers are unusual
    # moves ("move") plus dated events whose day moved modestly ("event");
    # driver buckets count only unusual-move days, and dated-event markers
    # get their own sentence so the counts stay honest.
    move_days = [m for m in moves if m.get("kind", "move") == "move"]
    event_days = [m for m in moves if m.get("kind") == "event"]
    flagged = [m for m in move_days if m.get("facts")]
    if not move_days:
        parts.append("No unusual moves were flagged in this history.")
    elif not flagged:
        parts.append(
            f"No dated events were collected for the {len(move_days)} unusual "
            "move days, so historical drivers are unidentified."
        )
    else:

        def has(label_test: Callable[[str], bool], move: dict[str, Any]) -> bool:
            return any(label_test(f.get("label", "")) for f in move.get("facts", []))

        buckets = [
            ("Earnings reports", lambda label: label == "Quarterly earnings reported"),
            (
                "SEC filings",
                lambda label: label.startswith("8-K") or "filing" in label.lower(),
            ),
            ("Macro releases", lambda label: "release" in label.lower()),
        ]
        counts = [(name, sum(1 for m in flagged if has(test, m))) for name, test in buckets]
        counts = [(name, c) for name, c in counts if c]
        counts.sort(key=lambda nc: -nc[1])
        if counts:
            top = "; ".join(
                f"{name.lower()} lined up with {c} of {len(move_days)} unusual moves"
                for name, c in counts[:2]
            )
            parts.append(top[0].upper() + top[1:] + ".")
        else:
            parts.append(
                "Collected dated events show no earnings, filings, or "
                "macro releases lining up with the unusual moves."
            )
    if event_days:
        parts.append(
            f"{len(event_days)} dated event{'s' if len(event_days) != 1 else ''} "
            "also annotate the chart without large moves."
        )

    # 3. incoming catalysts. There is no upcoming-catalyst feed in the
    # collected data, so this states the gap plainly instead of inventing
    # a date.
    parts.append("No upcoming catalyst dates are available in the collected data.")

    # 4. forward-looking read, labeled as interpretation, grounded in (1).
    if alphas:
        alpha, slope = alphas[-1], slopes[-1] if slopes else None
        if alpha < 0 and slope is not None and slope > 0:
            read = (
                "Interpretation: \u03b1 is still negative but improving \u2014 "
                "early repair, not a recovery."
            )
        elif alpha < 0:
            read = (
                "Interpretation: \u03b1 is negative and deteriorating \u2014 no sign of repair yet."
            )
        else:
            read = (
                "Interpretation: \u03b1 is positive \u2014 the stock has recently "
                f"earned its drift vs {benchmark}."
            )
        parts.append(read)

    text = " ".join(parts)
    words = text.split()
    if len(words) > _TLDR_MAX_WORDS:
        text = " ".join(words[: _TLDR_MAX_WORDS - 1]) + "\u2026"
    return text


def _event_catalog(events_dir: Path, symbol: str) -> dict[str, list[dict[str, str]]]:
    """Dated events collected independently of the move filter.

    Reads ``events_dir/<symbol>/event_dates.json`` (written by the event
    collection step from verified facts: earnings, SEC filings, macro
    releases - never forum chatter). Missing, corrupt, or wrong-schema files
    degrade to no event markers, never a crash.
    """
    try:
        payload = json.loads((events_dir / symbol / "event_dates.json").read_text())
    except (OSError, ValueError):
        return {}
    if payload.get("schema_version") != 1 or payload.get("ticker") != symbol:
        return {}
    raw = payload.get("dates")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict[str, str]]] = {}
    for day, entries in raw.items():
        if not isinstance(entries, list):
            continue
        rows = [
            {
                "label": str(entry["label"]),
                "date": str(entry.get("date") or day),
                "detail": str(entry.get("detail", "")),
                "url": safe_url(entry.get("url")),
            }
            for entry in entries
            if isinstance(entry, dict) and entry.get("label")
        ]
        if rows:
            out[str(day)] = sorted(rows, key=lambda row: row["label"])
    return out


def _merge_event_markers(
    moves: list[dict[str, Any]],
    *,
    event_catalog: dict[str, list[dict[str, str]]],
    dates: list[str],
    asset: dict[str, float],
    benchmark: dict[str, float],
    benchmark_name: str,
    beta_window: int,
) -> None:
    """Union of unusual-move days and dated-event days, in place.

    A date with a collected dated event earns a chart annotation even when
    its abnormal move was modest (the event, not the move size, earns the
    annotation). A date that is both a move and an event day keeps a single
    "move" marker with the catalog facts merged in. Event markers carry the
    day's return and abnormal move via the trailing beta_window-session OLS
    beta; z/sigma/alpha are None because they were never estimated for
    these days. Days without a full trailing window are skipped rather than
    shown with a made-up abnormal move.
    """
    if not event_catalog:
        return
    by_date = {m["date"]: m for m in moves}
    index = {day: i for i, day in enumerate(dates)}
    for day in sorted(event_catalog):
        facts = event_catalog[day]
        row = by_date.get(day)
        if row is not None:
            seen = {(fact["label"], fact["date"]) for fact in row["facts"]}
            for fact in facts:
                if (fact["label"], fact["date"]) not in seen:
                    row["facts"].append(fact)
                    seen.add((fact["label"], fact["date"]))
            row["facts"].sort(key=lambda fact: (fact["date"], fact["label"]))
            continue
        i = index.get(day)
        if i is None or i <= beta_window:
            continue
        ret = asset[day] / asset[dates[i - 1]] - 1
        bench_ret = benchmark[day] / benchmark[dates[i - 1]] - 1
        asset_rets = [asset[dates[j]] / asset[dates[j - 1]] - 1 for j in range(i - beta_window, i)]
        bench_rets = [
            benchmark[dates[j]] / benchmark[dates[j - 1]] - 1 for j in range(i - beta_window, i)
        ]
        try:
            beta = ols_beta(asset_rets, bench_rets)
        except ValueError:
            continue
        abnormal = ret - beta * bench_ret
        by_date[day] = {
            "date": day,
            "kind": "event",
            "benchmark": benchmark_name,
            "return": ret,
            "benchmark_return": bench_ret,
            "beta": beta,
            "alpha": None,
            "abnormal_return": abnormal,
            "sigma_60": None,
            "z": None,
            "market_component": beta * bench_ret,
            "idiosyncratic_component": abnormal,
            "alpha_annualized": None,
            "facts": facts,
            "documents": [],
            "coverage": None,
            "evidence_status": "event_only",
        }
        moves.append(by_date[day])


def chart_data(
    artifact: MovesArtifact,
    asset: dict[str, float],
    benchmark: dict[str, float],
    events_dir: Path,
    *,
    name: str,
    aliases: tuple[str, ...] = (),
    industry: dict[str, float] | None = None,
    industry_name: str | None = None,
    eps_quarters: list[tuple[str, str, float]] | None = None,
    operating_eps_quarters: list[tuple[str, str, float | None]] | None = None,
    kpis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dates = sorted(set(asset) & set(benchmark))
    if artifact.coverage.evaluated:
        lo, hi = artifact.coverage.evaluated
        dates = [day for day in dates if lo <= day <= hi]
    if len(dates) < 2:
        raise ValueError("need at least two price dates to render; run ingest-prices first")
    if any(
        not math.isfinite(series[d]) or series[d] <= 0
        for series in (asset, benchmark)
        for d in dates
    ):
        raise ValueError("chart prices must be finite and positive")
    symbol = safe_ticker_component(artifact.ticker)
    # The industry line is optional: unmapped symbols, or a mapped ticker
    # with no stored prices, render the two-line chart exactly as before.
    # industry_prices stays aligned with `dates`; None marks days before the
    # industry series starts (e.g. MAGS, listed April 2023).
    industry_prices: list[float | None] = [None] * len(dates)
    industry_factor: dict[str, object] | None = None
    if industry and industry_name:
        if any(
            industry.get(d) is not None and (not math.isfinite(industry[d]) or industry[d] <= 0)
            for d in dates
        ):
            raise ValueError("industry chart prices must be finite and positive")
        industry_prices = [industry.get(d) for d in dates]
        industry_factor = _industry_factor(
            asset, industry, artifact.params.beta_window, industry_name
        )
    moves = []
    for move in artifact.moves:
        if move.date not in dates:
            raise ValueError(f"move {move.date} is outside the rendered price series")
        market_component = move.beta * move.benchmark_return
        # By construction in compute_moves, ret == beta*benchmark_return +
        # abnormal_return. Verify rather than assume: a hand-built artifact
        # with an inconsistent decomposition must fail loudly here, not render
        # a tooltip whose parts do not add up.
        if not math.isclose(
            move.ret,
            market_component + move.abnormal_return,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"move {move.date}: ret {move.ret} != beta*benchmark_return "
                f"({market_component}) + abnormal_return ({move.abnormal_return})"
            )
        row: dict[str, Any] = {
            "date": move.date,
            "kind": "move",
            **move_payload(move),
            "market_component": market_component,
            "idiosyncratic_component": move.abnormal_return,
            "alpha_annualized": annualize_alpha(move.alpha),
            "facts": [],
            "documents": [],
            "coverage": None,
            "evidence_status": "missing",
        }
        path = events_dir / symbol / f"{move.date}.json"
        if path.exists():
            try:
                bundle = json.loads(path.read_text())
                if (
                    bundle["schema_version"] != SCHEMA_VERSION
                    or bundle["bundle_sha256"] != bundle_hash(bundle)
                    or bundle["ticker"] != symbol
                    or bundle["date"] != move.date
                ):
                    raise ValueError("invalid evidence bundle")
                if bundle["move"] != move_payload(move):
                    row["evidence_status"] = "stale"
                else:
                    facts, documents = _facts(bundle), _documents(bundle, aliases)
                    row.update(
                        facts=facts,
                        documents=documents,
                        coverage=bundle["coverage"],
                        evidence_status="available",
                    )
            except (ValueError, KeyError, TypeError):
                row["evidence_status"] = "invalid"
        moves.append(row)
    _merge_event_markers(
        moves,
        event_catalog=_event_catalog(events_dir, symbol),
        dates=dates,
        asset=asset,
        benchmark=benchmark,
        benchmark_name=artifact.benchmark,
        beta_window=artifact.params.beta_window,
    )
    moves.sort(key=lambda m: m["date"])
    data: dict[str, Any] = {
        "ticker": symbol,
        "name": name,
        "benchmark": artifact.benchmark,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dates": dates,
        "prices": [asset[d] for d in dates],
        "benchmark_prices": [benchmark[d] for d in dates],
        "industry_benchmark": industry_name,
        "industry_prices": industry_prices,
        "industry_factor": industry_factor,
        "moves": moves,
        "threshold": artifact.params.z_threshold,
        "beta_window": artifact.params.beta_window,
        "sigma_window": artifact.params.sigma_window,
        "factor": _trailing_factor(
            asset, benchmark, artifact.params.beta_window, artifact.benchmark
        ),
        "pe": _pe_panel(asset, eps_quarters or [], operating_eps_quarters or []),
        "kpis": kpis,
        "regime": {
            # The window switch (issue #19) offers 60/125/250-session OLS;
            # "250" is the default and matches artifact.params.beta_window.
            "default_window": "250",
            "windows": {
                str(window): _regime_points(asset, benchmark, window) for window in REGIME_WINDOWS
            },
            # Daily-resolution tail for zoomed-in views (issue #41). The
            # template picks daily/weekly/monthly by visible range and falls
            # back to "windows" where the fine tail does not reach.
            "fine_tail_sessions": _FINE_TAIL_SESSIONS,
            "fine": {
                str(window): _regime_points(
                    asset, benchmark, window, step=1, tail=_FINE_TAIL_SESSIONS
                )
                for window in REGIME_WINDOWS
            },
            # Time-weighted (WLS) twins of the above (issue #47): growing
            # history with exponential decay instead of a hard OLS window.
            # The "enable time weight" tab reads these; the half-life -
            # not a window - controls how much history matters.
            "wls_half_lives": [str(h) for h in WLS_HALF_LIVES],
            "wls_default": str(DEFAULT_WLS_HALF_LIFE),
            "wls": {
                str(half_life): _regime_points(asset, benchmark, half_life=float(half_life))
                for half_life in WLS_HALF_LIVES
            },
            "wls_fine": {
                str(half_life): _regime_points(
                    asset,
                    benchmark,
                    step=1,
                    tail=_FINE_TAIL_SESSIONS,
                    half_life=float(half_life),
                )
                for half_life in WLS_HALF_LIVES
            },
            # WLS-regression slope series per (half-life, slope-span) combo
            # (issue #50): the "enable time weight (alpha slope)" tab reads
            # beta/R²/alpha from "wls"/"wls_fine" and the slope + signals
            # from here. The span selector (10/20/30) is the responsiveness
            # knob for the slope fit.
            "slope_spans": [str(s) for s in SLOPE_SPANS],
            "slope_default": str(SLOPE_SPAN),
            "wls_slope": _wls_slope_payload(asset, benchmark, fine=False),
            "wls_slope_fine": _wls_slope_payload(asset, benchmark, fine=True),
        },
    }
    data["tldr"] = _tldr_text(
        factor=data["factor"],
        regime=data["regime"],
        moves=data["moves"],
        benchmark=artifact.benchmark,
    )
    return data


def render_html(data: dict[str, Any]) -> str:
    template = Path(__file__).with_name("templates").joinpath("chart.html").read_text()
    # JSON is inert text. Escape HTML delimiters so hostile article text cannot
    # end the script element, even though the UI only uses textContent.
    payload = json.dumps(data, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c")
    payload = (
        payload.replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )

    def fallback_row(m: dict[str, Any]) -> str:
        # Event-driven markers have no z (it was never estimated for them).
        z = "—" if m["z"] is None else f"{m['z']:+.2f}"
        return (
            f"<tr><td>{html.escape(m['date'])}</td><td>{m['return']:+.2%}</td>"
            f"<td>{m['abnormal_return']:+.2%}</td><td>{z}</td></tr>"
        )

    rows = "".join(fallback_row(m) for m in data["moves"])
    stocks = data.get("stocks", [{"symbol": data["ticker"], "name": data["ticker"]}])
    links: list[str] = []
    seen_group: str | None = None
    for stock in stocks:
        group = stock.get("group")
        if group and group != seen_group:
            links.append(f'<h3 class="nav-group">{html.escape(group)}</h3>')
            seen_group = group
        links.append(
            '<a href="'
            + html.escape(safe_ticker_component(stock["symbol"]), quote=True)
            + '.html"'
            + (' aria-current="page"' if stock["symbol"] == data["ticker"] else "")
            + "><strong>"
            + html.escape(stock["symbol"])
            + "</strong><span>"
            + html.escape(stock["name"])
            + "</span></a>"
        )
    stock_links = "".join(links)
    return (
        template.replace("__TITLE__", html.escape(f"{data['ticker']} · Price & events"))
        .replace("__STOCK_LINKS__", stock_links)
        .replace("__FALLBACK_ROWS__", rows)
        .replace("__DATA__", payload)
    )


def render_chart(
    portfolio: Portfolio,
    symbol: str,
    *,
    db: Path,
    moves_dir: Path,
    events_dir: Path,
    out_dir: Path,
) -> Path:
    symbol = safe_ticker_component(symbol)
    artifact = read_moves(moves_dir / f"{symbol}.json")
    benchmark = portfolio.benchmark_for(symbol)
    if artifact.ticker != symbol or artifact.benchmark != benchmark:
        raise ValueError("move artifact does not match configured ticker/benchmark")
    store = Store.open(db)
    try:
        # The industry benchmark is best-effort: a mapped ticker with no
        # stored prices renders the two-line chart, not an error.
        industry_ticker = portfolio.industry_benchmark(symbol)
        industry_series = store.adjusted_series(industry_ticker) if industry_ticker else {}
        if portfolio.is_index(symbol):
            display_name = portfolio.index_entry(symbol).name
            aliases: tuple[str, ...] = ()
        else:
            display_name = portfolio.entry(symbol).name
            aliases = portfolio.entry(symbol).aliases
        data = chart_data(
            artifact,
            store.adjusted_series(symbol),
            store.adjusted_series(artifact.benchmark),
            events_dir,
            name=display_name,
            aliases=aliases,
            industry=industry_series or None,
            industry_name=industry_ticker if industry_series else None,
            eps_quarters=store.eps_quarters(symbol),
            operating_eps_quarters=store.operating_eps_quarters(symbol),
            kpis=_kpi_data(store, symbol),
        )
        # Prominent as-of dates (#56): price coverage and fundamentals
        # currency, display-only from already-stored data — render stays
        # offline.
        data["price_as_of"] = data["dates"][-1] if data["dates"] else None
        fund_at = max(
            (ts for ts in (store.eps_fetched_at(symbol), store.kpi_fetched_at(symbol)) if ts),
            default=None,
        )
        data["fundamentals_as_of"] = fund_at[:10] if fund_at else None
        # Trade markers (issue #65): this ticker's buy/sell history for the
        # vertical markers on the price chart and the regime sparklines. A
        # missing trades file renders exactly as before; a corrupt one fails
        # loud instead of silently dropping markers.
        try:
            all_trades = positions_module.load_trades()
        except ValueError as exc:
            raise ValueError(f"trade history: {exc}") from exc
        data["trades"] = [
            {"date": t.date, "side": t.side, "qty": t.qty, "price": t.price}
            for t in positions_module.trades_for_symbol(all_trades, symbol)
        ]
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{symbol}.html"
    data["stocks"] = [
        {"symbol": entry.symbol, "name": entry.name, "group": "Stocks"}
        for entry in portfolio.entries
    ] + [
        {"symbol": index.symbol, "name": index.name, "group": "Indices"}
        for index in portfolio.indices
    ]
    target.write_text(render_html(data))
    return target
