"""Index charts (issue #57): config, ingest mapping, benchmarks, rendering.

QQQ/NDX/SPY are first-class charts with their own benchmark (SPY by
default) so an index is never measured against itself. Indices have no
CIK: fundamentals sections render as n/a, never an exception.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from portfolio_analysis import cli
from portfolio_analysis.config import (
    IndexEntry,
    MoveParams,
    Portfolio,
    PortfolioEntry,
    load_portfolio,
)
from portfolio_analysis.dashboard import render_dashboard
from portfolio_analysis.factor_dashboard import factor_dashboard_data
from portfolio_analysis.render import render_html
from portfolio_analysis.store import Store

_BASE = {
    "tickers": [
        {
            "symbol": "META",
            "cik": 1326801,
            "name": "Meta Platforms, Inc.",
            "aliases": ["Meta"],
        },
    ],
    "benchmark": "QQQ",
    "price_years": 6,
    "moves": {"beta_window": 250, "sigma_window": 60, "z_threshold": 2.5},
    "news_coverage_start": "2022-03-01",
    "paths": {},
}

_INDICES = [
    {"symbol": "QQQ", "name": "Invesco QQQ Trust", "yahoo": "QQQ"},
    {"symbol": "NDX", "name": "Nasdaq-100 Index", "yahoo": "^NDX"},
    {
        "symbol": "SPY",
        "name": "SPDR S&P 500 ETF Trust",
        "yahoo": "SPY",
        "benchmark": "QQQ",
    },
]


def _write_config(tmp_path: Path, **overrides) -> Path:
    config = {**_BASE, "indices": _INDICES, **overrides}
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def _portfolio() -> Portfolio:
    return Portfolio(
        entries=(PortfolioEntry("META", 1326801, "Meta Platforms, Inc.", ("Meta",)),),
        benchmark="QQQ",
        price_years=6,
        move_params=MoveParams(beta_window=250, sigma_window=20, z_threshold=2.5),
        news_coverage_start="2020-01-01",
        paths={},
        indices=tuple(
            IndexEntry(
                symbol=idx["symbol"],
                name=idx["name"],
                yahoo=idx["yahoo"],
                benchmark=idx.get("benchmark", "SPY"),
            )
            for idx in _INDICES
        ),
    )


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------


def test_indices_parse_with_yahoo_and_benchmarks(tmp_path: Path) -> None:
    portfolio = load_portfolio(_write_config(tmp_path))
    assert [i.symbol for i in portfolio.indices] == ["QQQ", "NDX", "SPY"]
    ndx = portfolio.index_entry("ndx")
    assert ndx.yahoo == "^NDX"
    assert ndx.benchmark == "SPY"  # defaulted from index_benchmark
    assert portfolio.index_entry("SPY").benchmark == "QQQ"  # explicit override


def test_index_benchmark_defaults_to_spy(tmp_path: Path) -> None:
    config = {**_BASE, "indices": [{"symbol": "NDX", "name": "N", "yahoo": "^NDX"}]}
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(config))
    portfolio = load_portfolio(path)
    assert portfolio.index_benchmark == "SPY"
    assert portfolio.index_entry("NDX").benchmark == "SPY"


def test_yahoo_defaults_to_symbol(tmp_path: Path) -> None:
    config = {**_BASE, "indices": [{"symbol": "QQQ", "name": "Q"}]}
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(config))
    assert load_portfolio(path).index_entry("QQQ").yahoo == "QQQ"


def test_no_indices_key_means_no_index_charts(tmp_path: Path) -> None:
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(_BASE))
    portfolio = load_portfolio(path)
    assert portfolio.indices == ()
    assert portfolio.chart_symbols == ("META",)


def test_shipped_config_has_indices() -> None:
    portfolio = load_portfolio()
    assert [i.symbol for i in portfolio.indices] == ["QQQ", "NDX", "SPY"]
    assert portfolio.benchmark_for("NDX") == "SPY"
    assert portfolio.benchmark_for("QQQ") == "SPY"


# ---------------------------------------------------------------------------
# Benchmark resolution and the self-benchmark guard
# ---------------------------------------------------------------------------


def test_benchmark_for() -> None:
    portfolio = _portfolio()
    assert portfolio.benchmark_for("META") == "QQQ"  # stocks: portfolio benchmark
    assert portfolio.benchmark_for("QQQ") == "SPY"  # indices: own benchmark
    assert portfolio.benchmark_for("NDX") == "SPY"
    assert portfolio.benchmark_for("SPY") == "QQQ"  # explicit override


def test_self_benchmark_raises() -> None:
    portfolio = Portfolio(
        entries=(PortfolioEntry("AAA", 1, "AAA Inc.", ()),),
        benchmark="QQQ",
        price_years=6,
        move_params=MoveParams(250, 20, 2.5),
        news_coverage_start="2020-01-01",
        paths={},
        indices=(IndexEntry("QQQ", "Q", "QQQ", "QQQ"),),
    )
    with pytest.raises(ValueError, match="benchmarked against itself"):
        portfolio.benchmark_for("QQQ")
    assert cli._check_benchmarks(portfolio, ["QQQ"]) is not None
    assert "itself" in cli._check_benchmarks(portfolio, ["QQQ"])


def test_check_benchmarks_clean() -> None:
    assert cli._check_benchmarks(_portfolio(), ["META", "NDX", "QQQ", "SPY"]) is None


def test_yahoo_ticker_mapping() -> None:
    portfolio = _portfolio()
    assert portfolio.yahoo_ticker("NDX") == "^NDX"
    assert portfolio.yahoo_ticker("QQQ") == "QQQ"
    assert portfolio.yahoo_ticker("META") == "META"


def test_resolve_matches_index_name() -> None:
    portfolio = _portfolio()
    assert portfolio.resolve("NDX") == "NDX"
    assert portfolio.resolve("nasdaq-100 index") == "NDX"
    assert portfolio.resolve("Meta") == "META"
    assert portfolio.resolve("nope") is None


def test_chart_symbols_lists_indices_after_stocks() -> None:
    assert _portfolio().chart_symbols == ("META", "QQQ", "NDX", "SPY")


# ---------------------------------------------------------------------------
# Ingest: Yahoo mapping and benchmark coverage
# ---------------------------------------------------------------------------


def test_price_targets_cover_index_benchmarks() -> None:
    portfolio = _portfolio()
    targets = cli._price_targets(portfolio, ["NDX"])
    assert targets == ["NDX", "SPY"]  # NDX's own benchmark rides along


def test_price_targets_dedupe_and_order() -> None:
    portfolio = _portfolio()
    targets = cli._price_targets(portfolio, ["META", "NDX"])
    assert targets == ["META", "NDX", "QQQ", "SPY"]


def test_fetch_yahoo_uses_vendor_ticker_but_stamps_storage_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from portfolio_analysis import prices

    seen: dict[str, str] = {}

    def fake_get_json(url: str) -> dict:
        seen["url"] = url
        return {
            "chart": {
                "result": [
                    {
                        "timestamp": [1_700_000_000],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [100.0],
                                    "high": [101.0],
                                    "low": [99.0],
                                    "close": [100.5],
                                    "volume": [1000],
                                }
                            ],
                            "adjclose": [{"adjclose": [100.5]}],
                        },
                    }
                ]
            }
        }

    monkeypatch.setattr(prices, "_http_get_json", fake_get_json)
    bars = prices.fetch_yahoo("NDX", years=1, yahoo_ticker="^NDX")
    assert "^NDX" in seen["url"]
    assert bars and bars[0]["ticker"] == "NDX"


# ---------------------------------------------------------------------------
# Factor dashboard index rows
# ---------------------------------------------------------------------------


def _seed_index_store(tmp_path: Path) -> Store:
    """Synthetic bars where the indices genuinely track the market.

    NDX/QQQ are built from SPY's returns plus small noise, so NDX's beta
    vs SPY comes out near 1 - the relationship the real charts show.
    """
    store = Store.open(tmp_path / "t.sqlite")
    start = date(2021, 1, 4)
    n = 320
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n)]
    market_rng = random.Random(42)
    market = [market_rng.random() - 0.5 for _ in range(n)]
    specs = (("SPY", 1.0, 11), ("NDX", 1.05, 12), ("QQQ", 1.03, 13), ("META", 1.2, 14))
    for symbol, beta, seed in specs:
        rng = random.Random(seed)
        px = 100.0
        bars = []
        for d, m in zip(dates, market, strict=True):
            px *= 1 + (beta * m + (rng.random() - 0.5) * 0.004) * 0.02
            bars.append(
                {
                    "ticker": symbol,
                    "date": d,
                    "open": px,
                    "high": px,
                    "low": px,
                    "close": px,
                    "adj_close": px,
                    "volume": 1000,
                    "source": "test",
                }
            )
        store.upsert_price_bars(bars)
    return store


def test_factor_dashboard_includes_index_rows(tmp_path: Path) -> None:
    store = _seed_index_store(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
    finally:
        store.close()
    stocks = data["stocks"]
    assert set(stocks) == {"META", "QQQ", "NDX", "SPY"}
    assert stocks["META"]["benchmark"] == "QQQ"
    assert stocks["NDX"]["benchmark"] == "SPY"
    assert stocks["QQQ"]["benchmark"] == "SPY"
    assert stocks["SPY"]["benchmark"] == "QQQ"
    # Index betas are real numbers, not degenerate: NDX tracks its own
    # benchmark closely, so beta vs SPY should be near 1, not 0/None.
    ndx_beta = [b for b in stocks["NDX"]["beta"] if b is not None]
    assert ndx_beta, "NDX should have defined beta points"
    assert 0.5 < sum(ndx_beta) / len(ndx_beta) < 2.0


def test_factor_dashboard_self_benchmark_raises(tmp_path: Path) -> None:
    bad = Portfolio(
        entries=(PortfolioEntry("AAA", 1, "AAA Inc.", ()),),
        benchmark="QQQ",
        price_years=6,
        move_params=MoveParams(250, 20, 2.5),
        news_coverage_start="2020-01-01",
        paths={},
        indices=(IndexEntry("QQQ", "Q", "QQQ", "QQQ"),),
    )
    store = Store.open(tmp_path / "t.sqlite")
    try:
        with pytest.raises(ValueError, match="benchmarked against itself"):
            factor_dashboard_data(bad, store)
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Rendering: sidebar grouping and n/a fundamentals
# ---------------------------------------------------------------------------


def test_sidebar_groups_indices(tmp_path: Path) -> None:
    from tests.test_render import data as make_data

    payload = make_data(tmp_path)
    payload["stocks"] = [
        {"symbol": "META", "name": "Meta", "group": "Stocks"},
        {"symbol": "NDX", "name": "Nasdaq-100 Index", "group": "Indices"},
    ]
    text = render_html(payload)
    assert '<h3 class="nav-group">Stocks</h3>' in text
    assert '<h3 class="nav-group">Indices</h3>' in text
    assert "NDX.html" in text


def test_dashboard_page_lists_index_cards(tmp_path: Path) -> None:
    target = render_dashboard(_portfolio(), tmp_path / "out")
    text = target.read_text()
    assert '<h2 class="group">Indices</h2>' in text
    assert "NDX.html" in text
    assert "Nasdaq-100 Index" in text


def test_fundamentals_preflight_skips_indices(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    try:
        # No bars, no EPS: indices are simply skipped, never a KeyError.
        assert cli._fundamentals_need_refresh(_portfolio(), store, ["NDX"]) is False
    finally:
        store.close()


def test_kpi_data_is_none_for_indices(tmp_path: Path) -> None:
    from portfolio_analysis.render import _kpi_data

    store = Store.open(tmp_path / "t.sqlite")
    try:
        assert _kpi_data(store, "NDX") is None
    finally:
        store.close()
