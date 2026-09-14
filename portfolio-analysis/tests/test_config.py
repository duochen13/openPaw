from datetime import date

import pytest
import yaml

from portfolio_analysis.config import (
    PROJECT_ROOT,
    MoveParams,
    load_portfolio,
    resolve_path,
)

#: A small two-ticker portfolio, independent of the shipped config. The shipped
#: config explicitly invites adding tickers, so behavioral tests dump this to a
#: tmp_path fixture instead - only the "shipped config is valid" test below
#: touches the real file.
_BASE_CONFIG = {
    "tickers": [
        {
            "symbol": "META",
            "cik": 1326801,
            "name": "Meta Platforms, Inc.",
            "aliases": ["Meta", "Facebook", "Meta Platforms"],
        },
        {
            # Deliberately messy: the I7 regression guard below asserts this
            # comes back sanitized rather than making entry() raise.
            "symbol": "brk.b",
            "cik": 1067983,
            "name": "Berkshire Hathaway Inc.",
            "aliases": ["Berkshire", "Berkshire Hathaway"],
        },
    ],
    "benchmark": "QQQ",
    "price_years": 6,
    "moves": {"beta_window": 250, "sigma_window": 60, "z_threshold": 2.5},
    "news_coverage_start": "2022-03-01",
    "paths": {
        "db": "data/prices.sqlite",
        "moves": "data/moves",
        "events": "data/events",
        "reasons": "data/reasons",
        "cache": "data/cache",
        "out": "out",
    },
}


def _write_portfolio(tmp_path, **overrides):
    """Dump a small two-ticker portfolio YAML to tmp_path and return its path."""
    config = {**_BASE_CONFIG, **overrides}
    path = tmp_path / "portfolio.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


@pytest.mark.unit
def test_the_shipped_config_loads_and_is_valid():
    portfolio = load_portfolio()
    assert portfolio.symbols == ("META",)
    assert portfolio.benchmark == "QQQ"
    assert portfolio.price_years == 6
    assert portfolio.move_params.beta_window == 250
    assert portfolio.move_params.sigma_window == 60
    assert portfolio.move_params.z_threshold == 2.5


@pytest.mark.unit
def test_entry_lookup_is_case_insensitive(tmp_path):
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    entry = portfolio.entry("meta")
    assert entry.cik == 1326801
    assert entry.name == "Meta Platforms, Inc."


@pytest.mark.unit
def test_entry_lookup_raises_on_unknown_symbol(tmp_path):
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    with pytest.raises(KeyError):
        portfolio.entry("TSLA")


@pytest.mark.unit
def test_resolve_maps_symbol_name_and_alias_to_symbol(tmp_path):
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    assert portfolio.resolve("META") == "META"
    assert portfolio.resolve("Facebook") == "META"
    assert portfolio.resolve("meta platforms, inc.") == "META"
    assert portfolio.resolve("TSLA") is None


@pytest.mark.unit
def test_path_resolves_against_the_project_root(tmp_path):
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    assert portfolio.path("db") == PROJECT_ROOT / "data" / "prices.sqlite"


@pytest.mark.unit
def test_path_on_an_unknown_key_raises_with_known_keys_listed(tmp_path):
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    with pytest.raises(KeyError) as excinfo:
        portfolio.path("nope")
    message = str(excinfo.value)
    assert "nope" in message
    for key in portfolio.paths:
        assert key in message


@pytest.mark.unit
def test_a_messy_symbol_is_sanitized_and_findable(tmp_path):
    """I7 regression guard: a lowercase symbol in the YAML must not make
    entry() raise or write a lowercase path - naming.py's promise is that
    every ticker crossing an I/O boundary is sanitized, and config loading
    is one such boundary."""
    portfolio = load_portfolio(_write_portfolio(tmp_path))
    assert "BRK.B" in portfolio.symbols
    assert portfolio.entry("BRK.B").name == "Berkshire Hathaway Inc."


@pytest.mark.unit
def test_an_unparseable_news_coverage_start_raises_at_load(tmp_path):
    path = _write_portfolio(tmp_path, news_coverage_start="not-a-date")
    with pytest.raises(ValueError):
        load_portfolio(path)


@pytest.mark.unit
def test_news_coverage_start_round_trips_to_an_iso_string(tmp_path):
    """PyYAML parses an unquoted date-looking scalar into a datetime.date;
    this pins the coercion back to the str the rest of the codebase expects."""
    path = _write_portfolio(tmp_path, news_coverage_start=date(2022, 3, 1))
    portfolio = load_portfolio(path)
    assert portfolio.news_coverage_start == "2022-03-01"


@pytest.mark.unit
def test_config_paths_resolve_against_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    """The CLI must write to the same database regardless of invocation dir."""
    config_path = _write_portfolio(tmp_path)
    monkeypatch.chdir(tmp_path)
    portfolio = load_portfolio(config_path)
    resolved = resolve_path(portfolio.paths["db"])
    assert resolved.is_absolute()
    assert resolved == PROJECT_ROOT / "data" / "prices.sqlite"


@pytest.mark.unit
def test_sigma_window_must_be_smaller_than_beta_window():
    """compute_moves derives sigma inside the beta window, so a sigma window
    at least as large as the beta window would index before the series start."""
    with pytest.raises(ValueError):
        MoveParams(beta_window=60, sigma_window=60, z_threshold=2.5)


@pytest.mark.unit
def test_a_window_below_two_raises():
    with pytest.raises(ValueError):
        MoveParams(beta_window=1, sigma_window=1, z_threshold=2.5)


@pytest.mark.unit
@pytest.mark.parametrize("threshold", [0, -2.5])
def test_a_non_positive_z_threshold_raises(threshold):
    with pytest.raises(ValueError):
        MoveParams(beta_window=250, sigma_window=60, z_threshold=threshold)


@pytest.mark.unit
def test_a_nan_z_threshold_raises():
    """Without the isfinite guard this constructs cleanly: abs(z) >= nan is
    False for every z, so a NaN threshold would silently suppress every move
    rather than raising - indistinguishable from a quiet market."""
    with pytest.raises(ValueError):
        MoveParams(beta_window=250, sigma_window=60, z_threshold=float("nan"))
