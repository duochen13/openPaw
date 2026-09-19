"""Industry benchmark line (issue #16): config, render data, and fallbacks."""

from datetime import date, timedelta

import pytest
import yaml

from portfolio_analysis import cli
from portfolio_analysis.artifacts import MovesArtifact
from portfolio_analysis.config import MoveParams, load_portfolio
from portfolio_analysis.moves import Coverage, annualize_alpha, correlation
from portfolio_analysis.render import chart_data
from tests import test_cli_collect

setup = test_cli_collect.setup


def _prices(start, returns, base=100.0):
    """Build a date -> adjusted close dict from a start date and returns."""
    out = {}
    price = base
    day = date.fromisoformat(start)
    for r in returns:
        out[day.isoformat()] = price
        price *= 1 + r
        day += timedelta(days=1)
    out[day.isoformat()] = price
    return out


#: The industry return series the synthetic asset is built from:
#: asset_return = 1.5 * industry_return + 0.002, so OLS vs the industry
#: recovers beta 1.5, daily alpha 0.002, correlation 1.0.
_FULL_RETURNS = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.005, 0.012,
                -0.008, 0.003, 0.017, -0.014, 0.009, 0.001]


def _industry_data(tmp_path, industry, industry_name="CLOU", window=10):
    """chart_data for a synthetic asset/industry pair with known beta 1.5."""
    asset_returns = [1.5 * r + 0.002 for r in _FULL_RETURNS]
    asset = _prices("2024-01-01", asset_returns, base=50.0)
    bench = _prices("2024-01-01", _FULL_RETURNS, base=300.0)
    art = MovesArtifact(
        "NOW", "QQQ", MoveParams(window, 5, 2.5),
        Coverage(None, ("2024-01-01", "2024-01-15"), 5, 0), [],
    )
    return chart_data(
        art, asset, bench, tmp_path, name="ServiceNow, Inc.",
        industry=industry, industry_name=industry_name,
    )

@pytest.mark.unit
def test_shipped_config_industry_mapping():
    portfolio = load_portfolio()
    assert portfolio.industry_benchmark("NOW") == "CLOU"
    assert portfolio.industry_benchmark("MSFT") == "CLOU"
    assert portfolio.industry_benchmark("GOOGL") == "MAGS"
    assert portfolio.industry_benchmark("META") == "MAGS"
    assert portfolio.industry_benchmark("NVDA") == "SOXX"
    assert portfolio.industry_benchmark("now") == "CLOU"
    assert portfolio.industry_benchmark("TSLA") is None
    assert portfolio.industry_benchmark("AMZN") is None
    assert portfolio.industry_benchmark("UNKNOWN") is None


@pytest.mark.unit
def test_industry_benchmarks_parsed_sanitized_and_optional(tmp_path):
    config = {
        "tickers": [],
        "benchmark": "QQQ",
        "price_years": 6,
        "moves": {"beta_window": 250, "sigma_window": 60, "z_threshold": 2.5},
        "news_coverage_start": "2022-03-01",
        "paths": {"db": "d", "moves": "m", "events": "e", "reasons": "r",
                  "cache": "c", "out": "o"},
        "industry_benchmarks": {"now": "clou", "META": "MAGS"},
    }
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(config))
    portfolio = load_portfolio(path)
    assert portfolio.industry_benchmark("NOW") == "CLOU"
    assert portfolio.industry_benchmark("META") == "MAGS"
    assert portfolio.industry_benchmark("TSLA") is None

    del config["industry_benchmarks"]
    path.write_text(yaml.safe_dump(config))
    assert load_portfolio(path).industry_benchmark("NOW") is None


@pytest.mark.unit
def test_chart_data_includes_industry_series_and_factor(tmp_path):
    ind_returns = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.005, 0.012,
                   -0.008, 0.003, 0.017, -0.014, 0.009, 0.001]
    industry = _prices("2024-01-01", ind_returns, base=30.0)
    result = _industry_data(tmp_path, industry)
    assert result["industry_benchmark"] == "CLOU"
    assert result["industry_prices"] == [industry[d] for d in result["dates"]]
    factor = result["industry_factor"]
    assert factor is not None
    assert factor["benchmark"] == "CLOU"
    assert factor["window"] == 10
    # By construction asset = 1.5 * industry + 0.002 daily drift.
    assert factor["beta"] == pytest.approx(1.5, rel=1e-9)
    assert factor["alpha_annualized"] == pytest.approx(annualize_alpha(0.002), rel=1e-9)
    assert factor["correlation"] == pytest.approx(1.0, abs=1e-9)
    assert factor["as_of"] == result["dates"][-1]


@pytest.mark.unit
def test_industry_factor_uses_overlap_only_for_short_history(tmp_path):
    # MAGS-style: industry starts well after the asset series. The industry
    # returns are the asset's own components over the overlap, so beta stays
    # 1.5: returns realized 2024-01-06..2024-01-15 are _FULL_RETURNS[4:14].
    industry = _prices("2024-01-05", _FULL_RETURNS[4:14], base=30.0)
    result = _industry_data(tmp_path, industry)
    leading = result["industry_prices"][:4]
    assert leading == [None] * 4
    assert all(p is not None for p in result["industry_prices"][4:])
    factor = result["industry_factor"]
    assert factor is not None
    # 11 overlap dates -> 10 returns == the 10-session window: stats exist,
    # but only over the overlap, as of the last overlapping date.
    assert factor["as_of"] == result["dates"][-1]
    assert factor["beta"] == pytest.approx(1.5, rel=1e-9)


@pytest.mark.unit
def test_short_industry_overlap_draws_line_without_stats(tmp_path):
    ind_returns = [0.01, -0.02, 0.015]
    industry = _prices("2024-01-12", ind_returns, base=30.0)
    result = _industry_data(tmp_path, industry)
    assert result["industry_benchmark"] == "CLOU"
    assert any(p is not None for p in result["industry_prices"])
    # Only 3 overlap returns < the 10-session window: no stats, no crash.
    assert result["industry_factor"] is None


@pytest.mark.unit
def test_missing_industry_falls_back_to_two_line_chart(tmp_path):
    result = _industry_data(tmp_path, None, industry_name=None)
    assert result["industry_benchmark"] is None
    assert result["industry_factor"] is None
    assert result["industry_prices"] == [None] * len(result["dates"])
    # The market factor is unaffected.
    assert result["factor"] is None or "beta" in result["factor"]


@pytest.mark.unit
def test_degenerate_industry_series_yields_no_factor(tmp_path):
    ind_returns = [0.01, -0.02, 0.015, 0.005, -0.01, 0.02, -0.005, 0.012,
                   -0.008, 0.003, 0.017, -0.014, 0.009, 0.001]
    industry = {d: 30.0 for d in _prices("2024-01-01", ind_returns)}
    result = _industry_data(tmp_path, industry)
    # Flat industry line: beta/correlation undefined -> no stats, no crash.
    assert result["industry_factor"] is None
    assert all(p == 30.0 for p in result["industry_prices"])


@pytest.mark.unit
def test_render_wires_industry_from_store(setup, tmp_path):
    from portfolio_analysis.store import Store
    from tests.test_cli_detect import _bars

    store = Store.open(setup.path("db"))
    store.upsert_price_bars(
        _bars(
            "META",
            {
                "2024-04-22": 100,
                "2024-04-23": 101,
                "2024-04-24": 90,
                "2024-04-25": 81,
                "2024-04-26": 82,
            },
        )
    )
    store.upsert_price_bars(
        _bars(
            "MAGS",
            {
                "2024-04-22": 40.0,
                "2024-04-23": 41.0,
                "2024-04-24": 40.5,
                "2024-04-25": 42.0,
                "2024-04-26": 41.5,
            },
        )
    )
    store.close()
    assert cli.main(["render", "META", "--out-dir", str(tmp_path / "out")]) == 0
    text = (tmp_path / "out/META.html").read_text()
    assert '"industry_benchmark": "MAGS"' in text
    assert '"industry_factor": null' in text  # too short for a 250-day window
    assert "industry-key" in text


@pytest.mark.unit
def test_correlation_known_values():
    assert correlation([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == pytest.approx(1.0)
    assert correlation([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]) == pytest.approx(-1.0)
    with pytest.raises(ValueError, match="zero variance"):
        correlation([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="same length"):
        correlation([1.0, 2.0], [1.0])
    with pytest.raises(ValueError, match="two observations"):
        correlation([1.0], [2.0])
