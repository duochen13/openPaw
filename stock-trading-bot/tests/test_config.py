import pytest

from stock_trading_bot.config import (
    PROJECT_ROOT,
    load_run_config,
    load_watchlist,
    resolve_path,
)
from stock_trading_bot.naming import safe_ticker_component


@pytest.mark.unit
def test_watchlist_loads_the_shipped_default():
    wl = load_watchlist()
    assert wl.benchmark == "QQQ"
    assert "NOW" in wl.symbols
    assert 5 <= len(wl.symbols) <= 15      # spec §3.2 keeps this narrow


@pytest.mark.unit
def test_ambiguous_symbols_require_a_cashtag():
    wl = load_watchlist()
    assert wl.entry("NOW").require_cashtag is True
    assert wl.entry("NVDA").require_cashtag is False


@pytest.mark.unit
@pytest.mark.parametrize("text,expected", [
    ("servicenow", "NOW"),
    ("NOW", "NOW"),
    ("now", "NOW"),
    ("Service Now", "NOW"),
    ("ServiceNow, Inc.", "NOW"),
    ("  nvidia  ", "NVDA"),
    ("not a company", None),
    ("", None),
])
def test_resolution_handles_tickers_names_and_aliases(text, expected):
    assert load_watchlist().resolve(text) == expected


@pytest.mark.unit
def test_entry_raises_for_an_unknown_symbol():
    with pytest.raises(KeyError):
        load_watchlist().entry("ZZZZ")


@pytest.mark.unit
def test_run_config_exposes_latency_budgets():
    assert load_run_config()["latency_budget_seconds"]["stooq"] == 900


@pytest.mark.unit
def test_every_latency_budget_is_a_non_negative_int():
    """A negative budget would make known_at precede observed_at; a missing
    one would be treated as instant availability. Both are refused at use
    site, but the shipped config should never contain either."""
    for source, seconds in load_run_config()["latency_budget_seconds"].items():
        assert isinstance(seconds, int), source
        assert seconds >= 0, source


@pytest.mark.unit
def test_config_paths_resolve_against_the_project_root_not_the_cwd(tmp_path, monkeypatch):
    """Otherwise the database lands somewhere different depending on where the
    CLI happened to be invoked from."""
    monkeypatch.chdir(tmp_path)
    resolved = resolve_path(load_run_config()["paths"]["db"])
    assert resolved.is_absolute()
    assert resolved == PROJECT_ROOT / "data/db/panel.sqlite"


@pytest.mark.unit
def test_every_watchlist_symbol_is_path_safe():
    for symbol in load_watchlist().symbols:
        assert safe_ticker_component(symbol) == symbol
