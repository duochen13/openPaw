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
from portfolio_analysis.artifacts import MovesArtifact, read_moves
from portfolio_analysis.bundle import SCHEMA_VERSION, bundle_hash, move_payload
from portfolio_analysis.config import Portfolio
from portfolio_analysis.fundamentals import pe_series
from portfolio_analysis.moves import aligned_returns, annualize_alpha, correlation, ols_regression
from portfolio_analysis.naming import safe_ticker_component
from portfolio_analysis.signals import (
    REGIME_WINDOWS,
    SLOPE_SPAN,
    alpha_signal,
    rolling_alpha_daily,
    rolling_slope,
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
        kind = fact["key"]
        if kind == "filing":
            label, day = f"{value['form']} filing", value["filed"]
        elif kind == "earnings_reported":
            label, day = "Quarterly earnings reported", value["reportedDate"]
        elif kind == "macro_release":
            label, day = f"{value['release']} release", value["date"]
        else:
            continue
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
        beta, alpha = ols_regression(
            asset_returns[-window:], industry_returns[-window:]
        )
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


def _regime_points(
    asset: dict[str, float],
    benchmark: dict[str, float],
    window: int,
    step: int = _REGIME_STEP,
    tail: int | None = None,
) -> dict[str, list[object]]:
    """Rolling beta, annualized alpha, R², alpha slope and turnaround signals,
    sampled every `step` sessions.

    R² is computed over the identical return observations as beta and alpha.
    The slope is the change in *annualized* alpha per trading session over
    ``SLOPE_SPAN`` sessions (see ``signals`` for the unit convention),
    derived from the full daily alpha series and then sampled, so the "20
    trading days" definition is exact, not an artifact of the sampling grid.
    ``signals[i]`` classifies the sampled point ("turnaround" or ``None``);
    slope and signals are ``None`` during their warmup. Empty when the series
    is shorter than one full window, for the same reason as _trailing_factor.
    The most recent session is always the last point. A degenerate window
    (zero variance, so beta/alpha/R² are all undefined) is skipped, never
    filled with a made-up number.

    ``tail`` keeps only the most recent ``tail`` sessions before sampling
    (used for the daily fine series in issue #41), so the embedded payload
    stays bounded: zoomed-out views use the monthly sampling instead.
    """
    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)
    empty: dict[str, list[object]] = {
        "dates": [],
        "beta": [],
        "r_squared": [],
        "alpha_annualized": [],
        "alpha_slope": [],
        "signals": [],
    }
    if len(asset_returns) < window:
        return empty
    alpha_daily = rolling_alpha_daily(asset_returns, benchmark_returns, window)
    slope_daily = rolling_slope(alpha_daily, SLOPE_SPAN)
    n = len(asset_returns)
    ends = list(range(window, n + 1, step))
    if tail is not None:
        ends = [e for e in ends if e > n - tail]
    if not ends or ends[-1] != n:
        ends.append(n)
    out: dict[str, list[object]] = {key: [] for key in empty}
    for end in ends:
        i = end - 1  # return index whose date is dates[end - 1]
        alpha_ann = alpha_daily[i]
        if alpha_ann is None:
            continue  # degenerate window: beta/alpha/R² undefined, skip
        beta, _, r_squared = ols_regression(
            asset_returns[end - window : end],
            benchmark_returns[end - window : end],
            r_squared=True,
        )
        out["dates"].append(dates[i])
        out["beta"].append(beta)
        out["r_squared"].append(r_squared)
        out["alpha_annualized"].append(alpha_ann)
        out["alpha_slope"].append(slope_daily[i])
        out["signals"].append(alpha_signal(alpha_ann, slope_daily[i]))
    return out


def _pe_panel(
    asset: dict[str, float],
    quarters: list[tuple[str, str, float]],
) -> dict[str, object] | None:
    """Rolling TTM P/E panel data (issue #28).

    Daily adjusted close over the TTM EPS in effect that day. Returns None
    when no quarter is stored at all - the template hides the section, the
    same rule as the factor strips. Days before the fourth reported quarter
    (or with non-positive TTM EPS) carry None: gaps, never invented numbers.
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
    return {
        "dates": dates,
        "pe": pe,
        "ttm_eps": ttm,
        "current_pe": current[1],
        "current_ttm_eps": current_ttm,
        "as_of": current[0],
        "quarters_reported": len(quarters),
    }


def _kpi_data(store: Store, symbol: str) -> dict[str, Any] | None:
    """Business-KPI panels for the per-stock chart (issue #29).

    None when the ticker has no KPI config or no stored KPI data - the
    template hides the section, the same rule as the P/E and factor
    panels. A broken KPI config degrades to no section, never a crash.
    """
    try:
        metric_keys = kpis_module.load_kpi_config().get(symbol, [])
    except kpis_module.ConfigError:
        return None
    if not metric_keys:
        return None
    series = {key: store.kpi_quarters(symbol, key) for key in metric_keys}
    series = {key: rows for key, rows in series.items() if rows}
    if not series:
        return None
    return kpis_module.kpi_panels(series, metric_keys)


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
            f"\u03b1 is {alpha:+.2%} annualized (trailing 250 sessions){direction}."
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

    # 2. historical drivers from collected event windows.
    evidenced = [m for m in moves if m.get("evidence_status") == "available"]
    if not moves:
        parts.append("No unusual moves were flagged in this history.")
    elif not evidenced:
        parts.append(
            f"No event windows have been collected for the {len(moves)} unusual "
            "move days, so historical drivers are unidentified."
        )
    else:

        def has(label_test: Callable[[str], bool], move: dict[str, Any]) -> bool:
            return any(label_test(f.get("label", "")) for f in move.get("facts", []))

        buckets = [
            ("Earnings reports", lambda label: label == "Quarterly earnings reported"),
            (
                "SEC filings",
                lambda label: label.startswith("8-K")
                or "filing" in label.lower(),
            ),
            ("Macro releases", lambda label: "release" in label.lower()),
        ]
        counts = [
            (name, sum(1 for m in evidenced if has(test, m)))
            for name, test in buckets
        ]
        counts = [(name, c) for name, c in counts if c]
        counts.sort(key=lambda nc: -nc[1])
        if counts:
            top = "; ".join(
                f"{name.lower()} lined up with {c} of {len(moves)} unusual moves"
                for name, c in counts[:2]
            )
            parts.append(top[0].upper() + top[1:] + ".")
        else:
            parts.append(
                "Collected event windows show no dated earnings, filings, or "
                "macro releases lining up with the unusual moves."
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
                "Interpretation: \u03b1 is negative and deteriorating \u2014 "
                "no sign of repair yet."
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
            industry.get(d) is not None
            and (not math.isfinite(industry[d]) or industry[d] <= 0)
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
        "pe": _pe_panel(asset, eps_quarters or []),
        "kpis": kpis,
        "regime": {
            # The window switch (issue #19) offers 60/125/250-session OLS;
            # "250" is the default and matches artifact.params.beta_window.
            "default_window": "250",
            "windows": {
                str(window): _regime_points(asset, benchmark, window)
                for window in REGIME_WINDOWS
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
    rows = "".join(
        f"<tr><td>{html.escape(m['date'])}</td><td>{m['return']:+.2%}</td>"
        f"<td>{m['abnormal_return']:+.2%}</td><td>{m['z']:+.2f}</td></tr>"
        for m in data["moves"]
    )
    stocks = data.get("stocks", [{"symbol": data["ticker"], "name": data["ticker"]}])
    stock_links = "".join(
        '<a href="' + html.escape(safe_ticker_component(stock["symbol"]), quote=True)
        + '.html"' + (' aria-current="page"' if stock["symbol"] == data["ticker"] else '')
        + '><strong>' + html.escape(stock["symbol"]) + '</strong><span>'
        + html.escape(stock["name"]) + '</span></a>'
        for stock in stocks
    )
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
    if artifact.ticker != symbol or artifact.benchmark != portfolio.benchmark:
        raise ValueError("move artifact does not match configured ticker/benchmark")
    store = Store.open(db)
    try:
        # The industry benchmark is best-effort: a mapped ticker with no
        # stored prices renders the two-line chart, not an error.
        industry_ticker = portfolio.industry_benchmark(symbol)
        industry_series = (
            store.adjusted_series(industry_ticker) if industry_ticker else {}
        )
        data = chart_data(
            artifact,
            store.adjusted_series(symbol),
            store.adjusted_series(artifact.benchmark),
            events_dir,
            name=portfolio.entry(symbol).name,
            aliases=portfolio.entry(symbol).aliases,
            industry=industry_series or None,
            industry_name=industry_ticker if industry_series else None,
            eps_quarters=store.eps_quarters(symbol),
            kpis=_kpi_data(store, symbol),
        )
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{symbol}.html"
    data["stocks"] = [
        {"symbol": entry.symbol, "name": entry.name} for entry in portfolio.entries
    ]
    target.write_text(render_html(data))
    return target
