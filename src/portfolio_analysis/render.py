"""Self-contained evidence chart. Source headlines are not causal attribution."""

from __future__ import annotations

import html
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from portfolio_analysis.artifacts import MovesArtifact, read_moves
from portfolio_analysis.bundle import SCHEMA_VERSION, bundle_hash, move_payload
from portfolio_analysis.config import Portfolio
from portfolio_analysis.moves import aligned_returns, annualize_alpha, correlation, ols_regression
from portfolio_analysis.naming import safe_ticker_component
from portfolio_analysis.store import Store

#: Sample the rolling beta/alpha series this often (trading days). Sixty-odd
#: points keeps the embedded JSON small while still showing regime changes
#: like a beta collapsing from 1.0 to 0.27.
_REGIME_STEP = 21


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
) -> dict[str, list[object]]:
    """Rolling beta, annualized alpha, and R², sampled every `step` sessions.

    R² is computed over the identical return observations as beta and alpha.
    Empty when the series is shorter than one full window, for the same reason
    as _trailing_factor. The most recent session is always the last point. A
    degenerate window (zero variance, so beta/alpha/R² are all undefined) is
    skipped, never filled with a made-up number.
    """
    dates, asset_returns, benchmark_returns = aligned_returns(asset, benchmark)
    if len(asset_returns) < window:
        return {"dates": [], "beta": [], "r_squared": [], "alpha_annualized": []}
    ends = list(range(window, len(asset_returns) + 1, step))
    if ends[-1] != len(asset_returns):
        ends.append(len(asset_returns))
    out_dates: list[object] = []
    out_beta: list[object] = []
    out_r_squared: list[object] = []
    out_alpha: list[object] = []
    for end in ends:
        try:
            beta, alpha, r_squared = ols_regression(
                asset_returns[end - window : end],
                benchmark_returns[end - window : end],
                r_squared=True,
            )
        except ValueError:
            continue
        out_dates.append(dates[end - 1])
        out_beta.append(beta)
        out_r_squared.append(r_squared)
        out_alpha.append(annualize_alpha(alpha))
    return {
        "dates": out_dates,
        "beta": out_beta,
        "r_squared": out_r_squared,
        "alpha_annualized": out_alpha,
    }


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
    return {
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
        "regime": _regime_points(asset, benchmark, artifact.params.beta_window),
    }


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
    return (
        template.replace("__TITLE__", html.escape(f"{data['ticker']} · Price & events"))
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
        )
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{symbol}.html"
    target.write_text(render_html(data))
    return target
