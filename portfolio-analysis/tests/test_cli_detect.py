import pytest

from portfolio_analysis import cli
from portfolio_analysis.artifacts import read_moves
from portfolio_analysis.store import Store
from tests.test_moves_compute import _series


def _bars(ticker, series):
    return [{
        "ticker": ticker, "date": d, "open": p, "high": p, "low": p,
        "close": p, "adj_close": p, "volume": 1.0, "source": "test",
    } for d, p in series.items()]


def _seed(db, n=252, spike_at=251, spike=0.20):
    """Seed the store from the SHARED fixture in test_moves_compute.

    This file used to carry its own copy, and the copy drifted back into the
    collinear-noise bug that fixture documents removing: noise keyed to the
    benchmark's parity loads onto beta, leaving sigma at ~1e-16 and z at
    ~2e15, so `assert z > 2.5` passed on floating-point dust. One fixture,
    imported, cannot drift twice.
    """
    asset, bench, dates = _series(n=n, spike_at=spike_at, spike=spike)
    store = Store.open(db)
    try:
        store.upsert_price_bars(_bars("META", asset))
        store.upsert_price_bars(_bars("QQQ", bench))
    finally:
        store.close()
    return dates


@pytest.mark.unit
def test_detect_writes_the_store_and_the_artifact(tmp_path):
    db = tmp_path / "t.sqlite"
    out = tmp_path / "moves"
    dates = _seed(db)

    assert cli.main([
        "detect-moves", "META", "--db", str(db), "--moves-dir", str(out)
    ]) == 0

    artifact = read_moves(out / "META.json")
    assert artifact.coverage.flagged_days == 1
    assert artifact.moves[0].date == dates[251]
    assert artifact.moves[0].z > 2.5

    store = Store.open(db)
    try:
        rows = store.moves("META")
        assert len(rows) == 1
        assert rows[0]["date"] == dates[251]
        assert rows[0]["benchmark"] == "QQQ"
    finally:
        store.close()


@pytest.mark.unit
def test_rerunning_detect_does_not_duplicate_moves(tmp_path):
    db = tmp_path / "t.sqlite"
    out = tmp_path / "moves"
    _seed(db)
    args = ["detect-moves", "META", "--db", str(db), "--moves-dir", str(out)]
    assert cli.main(args) == 0
    assert cli.main(args) == 0
    store = Store.open(db)
    try:
        assert len(store.moves("META")) == 1
    finally:
        store.close()


@pytest.mark.unit
def test_detect_fails_clearly_when_the_benchmark_was_never_ingested(tmp_path, capsys):
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    try:
        store.upsert_price_bars(_bars("META", {"2024-04-24": 1.0, "2024-04-25": 1.1}))
    finally:
        store.close()

    assert cli.main([
        "detect-moves", "META", "--db", str(db), "--moves-dir", str(tmp_path / "m")
    ]) == 1
    assert "QQQ" in capsys.readouterr().err
