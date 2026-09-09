from datetime import UTC, datetime
from unittest import mock

import pytest

from stock_trading_bot import cli
from stock_trading_bot.ingest import prices
from stock_trading_bot.store import Store

CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-09-04,101.0,105.0,100.5,104.0,1200000\n"
)
LATER = datetime(2026, 9, 30, tzinfo=UTC)


def _run(argv, csv=CSV):
    with mock.patch.object(prices, "_http_get", return_value=csv):
        return cli.main(argv)


@pytest.mark.unit
def test_ingest_writes_bars_that_are_visible_afterwards(tmp_path, capsys):
    db = tmp_path / "panel.sqlite"
    assert _run(["ingest", "NVDA", "--db", str(db)]) == 0
    assert "1 bar" in capsys.readouterr().out
    assert len(Store.open(db).as_of(LATER).price_bars("NVDA")) == 1


@pytest.mark.unit
def test_a_second_run_writes_nothing(tmp_path, capsys):
    """Append-only means re-running is a no-op, not a duplicate."""
    db = tmp_path / "panel.sqlite"
    _run(["ingest", "NVDA", "--db", str(db)])
    capsys.readouterr()
    _run(["ingest", "NVDA", "--db", str(db)])
    assert "0 bar(s) written, 1 unchanged" in capsys.readouterr().out


@pytest.mark.unit
def test_a_company_name_resolves_to_its_ticker(tmp_path, capsys):
    db = tmp_path / "panel.sqlite"
    _run(["ingest", "ServiceNow", "--db", str(db)])
    assert capsys.readouterr().out.startswith("NOW:")


@pytest.mark.unit
def test_ingest_rejects_an_unsafe_ticker(tmp_path):
    with pytest.raises(ValueError):
        _run(["ingest", "../etc", "--db", str(tmp_path / "p.sqlite")])


@pytest.mark.unit
def test_unknown_command_returns_nonzero():
    assert cli.main([]) == 2


@pytest.mark.unit
def test_a_changed_value_does_append_a_restatement(tmp_path):
    """Append-only means a new row records new information. A corrected close
    must be recorded; an identical re-fetch must not."""
    db = tmp_path / "panel.sqlite"
    _run(["ingest", "NVDA", "--db", str(db)])
    revised = CSV.replace("104.0", "104.5")
    _run(["ingest", "NVDA", "--db", str(db)], csv=revised)

    store = Store.open(db)
    assert store._conn.execute("SELECT COUNT(*) FROM price_bar").fetchone()[0] == 2
    # The reader still sees exactly one bar: the latest visible observation.
    bars = store.as_of(LATER).price_bars("NVDA")
    assert len(bars) == 1
    assert bars[0]["close"] == 104.5
