import pytest

from portfolio_analysis.store import Store

BAR = {
    "ticker": "META",
    "date": "2024-04-25",
    "open": 493.29,
    "high": 447.9,
    "low": 439.71,
    "close": 441.38,
    "adj_close": 441.38,
    "volume": 100_000_000.0,
    "source": "yahoo",
}


@pytest.fixture
def store(tmp_path):
    s = Store.open(tmp_path / "t.sqlite")
    yield s
    s.close()


@pytest.mark.unit
def test_insert_then_read_a_bar(store):
    store.upsert_price_bars([BAR])
    series = store.adjusted_series("META")
    assert series == {"2024-04-25": 441.38}


@pytest.mark.unit
def test_reinserting_the_same_date_upserts_rather_than_raising(store):
    """An adjusted close is legitimately rewritten by a later split, so a
    second observation must replace the first, not collide with it."""
    store.upsert_price_bars([BAR])
    store.upsert_price_bars([{**BAR, "adj_close": 220.69}])
    assert store.adjusted_series("META") == {"2024-04-25": 220.69}
    assert store.price_bar_count("META") == 1


@pytest.mark.unit
def test_adjusted_series_is_ordered_by_date(store):
    store.upsert_price_bars([
        {**BAR, "date": "2024-04-26", "adj_close": 443.29},
        {**BAR, "date": "2024-04-24", "adj_close": 493.5},
        BAR,
    ])
    assert list(store.adjusted_series("META")) == [
        "2024-04-24", "2024-04-25", "2024-04-26"
    ]


@pytest.mark.unit
def test_adjusted_series_is_empty_for_an_unknown_ticker(store):
    assert store.adjusted_series("TSLA") == {}


@pytest.mark.unit
def test_a_malformed_date_is_refused_at_the_write_boundary(store):
    """Lexicographic ordering must equal chronological ordering, which holds
    only if every date is fixed-width ISO. Enforced on the COLUMN so a
    fixture or a notebook INSERT cannot break it either."""
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_price_bars([{**BAR, "date": "2024-4-25"}])


@pytest.mark.unit
def test_upsert_and_read_moves(store):
    move = {
        "ticker": "META",
        "date": "2024-04-25",
        "ret": -0.105613,
        "benchmark": "QQQ",
        "benchmark_return": -0.004830,
        "beta": 1.490,
        "alpha": 0.000312,
        "abnormal_return": -0.098419,
        "sigma_60": 0.026083,
        "z": -3.77,
    }
    store.upsert_moves([move])
    rows = store.moves("META")
    assert len(rows) == 1
    assert rows[0]["z"] == pytest.approx(-3.77)
    assert rows[0]["benchmark"] == "QQQ"


@pytest.mark.unit
def test_recomputing_moves_replaces_rather_than_duplicates(store):
    move = {
        "ticker": "META", "date": "2024-04-25", "ret": -0.105613,
        "benchmark": "QQQ", "benchmark_return": -0.004830, "beta": 1.490,
        "alpha": 0.000312, "abnormal_return": -0.098419,
        "sigma_60": 0.026083, "z": -3.77,
    }
    store.upsert_moves([move])
    store.upsert_moves([{**move, "z": -3.80}])
    rows = store.moves("META")
    assert len(rows) == 1
    assert rows[0]["z"] == pytest.approx(-3.80)
