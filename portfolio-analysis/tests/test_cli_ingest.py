from unittest import mock

import pytest

from portfolio_analysis import cli
from portfolio_analysis.store import Store


def _bars(ticker, dates):
    return [{
        "ticker": ticker, "date": d, "open": 1.0, "high": 1.0, "low": 1.0,
        "close": 1.0, "adj_close": 1.0 + i, "volume": 1.0, "source": "yahoo",
    } for i, d in enumerate(dates)]


@pytest.mark.unit
def test_ingest_fetches_the_universe_and_the_benchmark(tmp_path):
    db = tmp_path / "t.sqlite"
    calls = []

    def fake_fetch(ticker, *, years, now=None):
        calls.append((ticker, years))
        return _bars(ticker, ["2024-04-24", "2024-04-25"])

    with mock.patch.object(cli.prices, "fetch_yahoo", side_effect=fake_fetch):
        assert cli.main(["ingest-prices", "--db", str(db)]) == 0

    assert calls == [("META", 6), ("QQQ", 6)]
    store = Store.open(db)
    try:
        assert store.price_bar_count("META") == 2
        assert store.price_bar_count("QQQ") == 2
    finally:
        store.close()


@pytest.mark.unit
def test_ingest_accepts_a_single_ticker_by_alias(tmp_path):
    db = tmp_path / "t.sqlite"
    calls = []

    def fake_fetch(ticker, *, years, now=None):
        calls.append(ticker)
        return _bars(ticker, ["2024-04-25"])

    with mock.patch.object(cli.prices, "fetch_yahoo", side_effect=fake_fetch):
        assert cli.main(["ingest-prices", "Facebook", "--db", str(db)]) == 0

    assert calls == ["META", "QQQ"]


@pytest.mark.unit
def test_ingest_rejects_a_ticker_outside_the_portfolio(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    with mock.patch.object(cli.prices, "fetch_yahoo") as fake:
        assert cli.main(["ingest-prices", "TSLA", "--db", str(db)]) == 2
    fake.assert_not_called()
    assert "not in the portfolio" in capsys.readouterr().err


@pytest.mark.unit
def test_no_subcommand_prints_usage_and_returns_two(capsys):
    assert cli.main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()
