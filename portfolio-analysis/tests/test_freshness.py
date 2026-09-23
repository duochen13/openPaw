"""Tests for issue #56: freshness-aware chart/dashboard builds.

The trading-day calendar pins the tricky boundaries: weekends, US market
holidays (including observed days), and the 16:00 ET close cutoff.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from portfolio_analysis import cli
from portfolio_analysis.config import Portfolio, PortfolioEntry
from portfolio_analysis.freshness import (
    is_trading_day,
    last_completed_session,
    price_staleness,
)
from portfolio_analysis.moves import MoveParams
from portfolio_analysis.render import render_html
from portfolio_analysis.store import Store

NY = ZoneInfo("America/New_York")


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY)


# ---------------------------------------------------------------------------
# Trading-day calendar
# ---------------------------------------------------------------------------


def test_weekend_not_trading_day() -> None:
    assert not is_trading_day(date(2026, 9, 26))  # Saturday
    assert not is_trading_day(date(2026, 9, 27))  # Sunday


def test_holiday_not_trading_day() -> None:
    # Independence Day 2026 falls on Saturday; the market observes Friday.
    assert not is_trading_day(date(2026, 7, 3))
    assert not is_trading_day(date(2026, 12, 25))  # Christmas, Friday


def test_weekday_is_trading_day() -> None:
    assert is_trading_day(date(2026, 9, 25))  # Friday
    assert is_trading_day(date(2026, 7, 2))  # Thursday before the observed holiday


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # Friday after the close: the session is complete.
        (_at(date(2026, 9, 25), 17, 0), date(2026, 9, 25)),
        # Saturday: roll back to Friday.
        (_at(date(2026, 9, 26), 10, 0), date(2026, 9, 25)),
        # Sunday night: still Friday.
        (_at(date(2026, 9, 27), 23, 59), date(2026, 9, 25)),
        # Monday before the close: the session is not complete yet.
        (_at(date(2026, 9, 28), 10, 0), date(2026, 9, 25)),
        # Monday exactly at the close counts as complete.
        (_at(date(2026, 9, 28), 16, 0), date(2026, 9, 28)),
        # Monday after the close: today's session.
        (_at(date(2026, 9, 28), 16, 30), date(2026, 9, 28)),
        # Observed holiday (Friday): roll back to Thursday.
        (_at(date(2026, 7, 3), 12, 0), date(2026, 7, 2)),
        # Christmas Friday: roll back to Christmas Eve.
        (_at(date(2026, 12, 25), 18, 0), date(2026, 12, 24)),
        # Observed Monday holiday in 2027: roll back to the prior Friday.
        (_at(date(2027, 7, 5), 12, 0), date(2027, 7, 2)),
    ],
)
def test_last_completed_session(now: datetime, expected: date) -> None:
    assert last_completed_session(now) == expected


# ---------------------------------------------------------------------------
# Price staleness
# ---------------------------------------------------------------------------


def test_price_staleness_fresh() -> None:
    now = _at(date(2026, 9, 25), 17, 0)
    assert price_staleness(date(2026, 9, 25), now) == (False, 0)


def test_price_staleness_one_session_behind() -> None:
    now = _at(date(2026, 9, 25), 17, 0)
    assert price_staleness(date(2026, 9, 24), now) == (True, 1)


def test_price_staleness_no_bars() -> None:
    now = _at(date(2026, 9, 25), 17, 0)
    assert price_staleness(None, now) == (True, 0)


def test_price_staleness_weekend_does_not_count() -> None:
    # Monday morning: Friday's bar is still fresh; Thursday's is one behind.
    now = _at(date(2026, 9, 28), 10, 0)
    assert price_staleness(date(2026, 9, 25), now) == (False, 0)
    assert price_staleness(date(2026, 9, 24), now) == (True, 1)


def test_price_staleness_over_holiday_weekend() -> None:
    # Friday July 3 2026 is an observed holiday: a Thursday bar is fresh on
    # Monday morning, and the gap counts one session, not four days.
    now = _at(date(2026, 7, 6), 10, 0)
    assert price_staleness(date(2026, 7, 2), now) == (False, 0)
    assert price_staleness(date(2026, 7, 1), now) == (True, 1)


# ---------------------------------------------------------------------------
# Store-level helpers
# ---------------------------------------------------------------------------


def _portfolio(symbols: tuple[str, ...] = ("AAA",), benchmark: str = "QQQ") -> Portfolio:
    return Portfolio(
        entries=tuple(PortfolioEntry(s, 1000 + i, f"{s} Inc.", ()) for i, s in enumerate(symbols)),
        benchmark=benchmark,
        price_years=6,
        move_params=MoveParams(beta_window=250, sigma_window=20, z_threshold=2.5),
        news_coverage_start="2020-01-01",
        paths={},
    )


def _bars(symbol: str, days: list[date]) -> list[dict[str, object]]:
    return [
        {
            "ticker": symbol,
            "date": d.isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "adj_close": 100.0,
            "volume": 1000,
            "source": "test",
        }
        for d in days
    ]


def _seed(store: Store, last: date, symbols: tuple[str, ...] = ("AAA", "QQQ")) -> None:
    """Bars for the 10 calendar days ending on `last`, for every symbol."""
    days = [date.fromordinal(last.toordinal() - i) for i in range(9, -1, -1)]
    for symbol in symbols:
        store.upsert_price_bars(_bars(symbol, days))


def test_prices_need_refresh_fresh(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    last = last_completed_session(datetime.now(UTC))
    _seed(store, last)
    try:
        needed, behind = cli._prices_need_refresh(_portfolio(), store, ["AAA"], datetime.now(UTC))
    finally:
        store.close()
    assert needed is False
    assert behind == 0


def test_prices_need_refresh_stale(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    last = last_completed_session(datetime.now(UTC))
    _seed(store, date.fromordinal(last.toordinal() - 5))
    try:
        needed, behind = cli._prices_need_refresh(_portfolio(), store, ["AAA"], datetime.now(UTC))
    finally:
        store.close()
    assert needed is True
    assert behind >= 1


def test_prices_need_refresh_missing_symbol(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    last = last_completed_session(datetime.now(UTC))
    # Only the benchmark is seeded; AAA has no bars at all.
    _seed(store, last, symbols=("QQQ",))
    try:
        needed, _ = cli._prices_need_refresh(_portfolio(), store, ["AAA"], datetime.now(UTC))
    finally:
        store.close()
    assert needed is True


def test_prices_need_refresh_empty_store(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    try:
        needed, _ = cli._prices_need_refresh(_portfolio(), store, ["AAA"], datetime.now(UTC))
    finally:
        store.close()
    assert needed is True


def test_fundamentals_need_refresh_when_missing(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    try:
        assert cli._fundamentals_need_refresh(_portfolio(), store, ["AAA"]) is True
    finally:
        store.close()


def test_fundamentals_need_refresh_when_fresh(tmp_path: Path) -> None:
    store = Store.open(tmp_path / "t.sqlite")
    store.upsert_eps_quarters(
        [
            {
                "ticker": "AAA",
                "quarter": "2026-06-30",
                "filed": "2026-07-30",
                "eps": 1.0,
                "source": "test",
            }
        ]
    )
    try:
        # No KPI config for AAA, so EPS freshness alone decides.
        assert cli._fundamentals_need_refresh(_portfolio(), store, ["AAA"]) is False
    finally:
        store.close()


# ---------------------------------------------------------------------------
# Pre-flight behavior
# ---------------------------------------------------------------------------


def _args(db: Path, **flags: object) -> argparse.Namespace:
    return argparse.Namespace(db=str(db), **flags)


def _seed_fresh_db(path: Path) -> None:
    store = Store.open(path)
    last = last_completed_session(datetime.now(UTC))
    _seed(store, last)
    store.upsert_eps_quarters(
        [
            {
                "ticker": "AAA",
                "quarter": "2026-06-30",
                "filed": "2026-07-30",
                "eps": 1.0,
                "source": "test",
            }
        ]
    )
    store.close()


def test_preflight_offline_fetches_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "t.sqlite"
    _seed_fresh_db(db)
    calls: list[str] = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda a: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_fetch_fundamentals", lambda a: calls.append("fund") or 0)
    assert cli._refresh_if_stale(_args(db, offline=True, refresh=False), _portfolio(), ["AAA"]) == 0
    assert calls == []


def test_preflight_fresh_data_fetches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.sqlite"
    _seed_fresh_db(db)
    calls: list[str] = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda a: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_fetch_fundamentals", lambda a: calls.append("fund") or 0)
    assert (
        cli._refresh_if_stale(_args(db, offline=False, refresh=False), _portfolio(), ["AAA"]) == 0
    )
    assert calls == []


def test_preflight_stale_prices_only_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    last = last_completed_session(datetime.now(UTC))
    _seed(store, date.fromordinal(last.toordinal() - 5))
    store.upsert_eps_quarters(
        [
            {
                "ticker": "AAA",
                "quarter": "2026-06-30",
                "filed": "2026-07-30",
                "eps": 1.0,
                "source": "test",
            }
        ]
    )
    store.close()
    calls: list[str] = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda a: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_fetch_fundamentals", lambda a: calls.append("fund") or 0)
    assert (
        cli._refresh_if_stale(_args(db, offline=False, refresh=False), _portfolio(), ["AAA"]) == 0
    )
    assert calls == ["prices"]


def test_preflight_stale_fundamentals_only_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    last = last_completed_session(datetime.now(UTC))
    _seed(store, last)
    store.close()
    calls: list[str] = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda a: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_fetch_fundamentals", lambda a: calls.append("fund") or 0)
    assert (
        cli._refresh_if_stale(_args(db, offline=False, refresh=False), _portfolio(), ["AAA"]) == 0
    )
    assert calls == ["fund"]


def test_preflight_refresh_forces_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "t.sqlite"
    _seed_fresh_db(db)
    calls: list[str] = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda a: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_fetch_fundamentals", lambda a: calls.append("fund") or 0)
    args = _args(db, offline=False, refresh=True)
    assert cli._refresh_if_stale(args, _portfolio(), ["AAA"]) == 0
    assert calls == ["prices", "fund"]
    # --refresh also arms the underlying force flags.
    assert args.refresh_prices is True
    assert args.force is True


def test_warn_if_price_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "t.sqlite"
    store = Store.open(db)
    last = last_completed_session(datetime.now(UTC))
    _seed(store, date.fromordinal(last.toordinal() - 5))
    store.close()
    cli._warn_if_price_stale(_args(db), _portfolio(), ["AAA"])
    err = capsys.readouterr().err
    assert "warning" in err
    assert "trading sessions behind" in err


def test_no_warn_when_fresh(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "t.sqlite"
    _seed_fresh_db(db)
    cli._warn_if_price_stale(_args(db), _portfolio(), ["AAA"])
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Header line
# ---------------------------------------------------------------------------


def test_render_html_has_freshness_line() -> None:
    template = (
        Path(__file__).resolve().parent.parent / "src/portfolio_analysis/templates/chart.html"
    ).read_text()
    assert 'id="freshness-line"' in template
    assert "fundamentals_as_of" in template


def test_render_html_without_asof_fields(tmp_path: Path) -> None:
    """Older payloads (no price_as_of) must still render the template."""
    from tests.test_render import data as make_data

    text = render_html(make_data(tmp_path))
    assert 'id="freshness-line"' in text
