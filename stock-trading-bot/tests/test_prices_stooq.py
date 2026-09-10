from datetime import UTC, datetime
from unittest import mock

import pytest

from stock_trading_bot.ingest import prices

CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2026-09-03,100.0,102.0,99.5,101.0,1000000\n"
    "2026-09-04,101.0,105.0,100.5,104.0,1200000\n"
)
OBSERVED = datetime(2026, 9, 4, 21, 0, 0, tzinfo=UTC)
BUDGET = {"stooq": 900}


def _fetch(text=CSV):
    return mock.patch.object(prices, "_http_get", return_value=text)


@pytest.mark.unit
def test_parses_bars_into_the_four_timestamp_shape():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert len(bars) == 2
    first = bars[0]
    assert first["ticker"] == "NVDA"
    assert first["session_date"] == "2026-09-03"
    assert first["close"] == 101.0
    assert first["source"] == "stooq"


@pytest.mark.unit
def test_known_at_is_observed_at_plus_the_budget():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["known_at"] == "2026-09-04T21:15:00.000000+00:00"


@pytest.mark.unit
def test_event_time_is_the_session_close_not_the_fetch_time():
    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert bars[0]["event_time"] == "2026-09-03T20:00:00.000000+00:00"


@pytest.mark.unit
def test_ticker_is_sanitized_before_reaching_the_url():
    with pytest.raises(ValueError):
        prices.fetch_stooq("../etc", observed_at=OBSERVED, latency_budget=BUDGET)


@pytest.mark.unit
def test_no_rows_returns_empty_rather_than_raising():
    with _fetch("Date,Open,High,Low,Close,Volume\n"):
        assert prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET) == []


@pytest.mark.unit
def test_adapter_never_returns_a_live_profile_field():
    """Enforces the §5.5 guard at the adapter boundary."""
    from stock_trading_bot.ingest.live_profile_guard import LIVE_ONLY_FIELDS

    with _fetch():
        bars = prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)
    assert set(bars[0]) & LIVE_ONLY_FIELDS == set()


# --- stooq must fail loudly, not silently ------------------------------------

CHALLENGE = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>'
    "<noscript>This site requires JavaScript to verify your browser.</noscript>"
    "</body></html>"
)


@pytest.mark.unit
def test_an_html_anti_bot_challenge_raises_rather_than_yielding_no_bars():
    """stooq answers its challenge with HTTP 200. Parsed as CSV that is zero
    rows, which reads as 'this ticker has no history' instead of 'the vendor
    did not answer'."""
    with (
        mock.patch.object(prices, "_http_get", return_value=CHALLENGE),
        pytest.raises(prices.VendorResponseError, match="did not return CSV"),
    ):
        prices.fetch_stooq("NVDA", observed_at=OBSERVED, latency_budget=BUDGET)


# --- yahoo fallback ----------------------------------------------------------

YAHOO = {
    "chart": {
        "result": [{
            "meta": {"gmtoffset": -14400},
            # 09:30 EDT on 2026-09-03 and 2026-09-04, then a null-padded day.
            "timestamp": [1788442200, 1788528600, 1788615000],
            "indicators": {
                "quote": [{
                    "open": [100.0, 101.0, None],
                    "high": [102.0, 105.0, None],
                    "low": [99.5, 100.5, None],
                    "close": [101.0, 104.0, None],
                    "volume": [1000000, 1200000, None],
                }],
                "adjclose": [{"adjclose": [20.2, 20.8, None]}],
            },
        }]
    }
}
YBUDGET = {"stooq": 900, "yahoo": 900}


@pytest.mark.unit
def test_yahoo_returns_the_same_row_shape_as_stooq():
    with mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert {b["source"] for b in bars} == {"yahoo"}
    assert set(bars[0]) == {
        "ticker", "session_date", "event_time", "observed_at", "known_at",
        "open", "high", "low", "close", "volume", "source",
    }


@pytest.mark.unit
def test_yahoo_uses_raw_quote_not_adjusted_close():
    """adjclose is retroactively revised; consuming it bakes a future split
    into past prices."""
    with mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert bars[0]["close"] == 101.0        # raw
    assert bars[0]["close"] != 20.2         # not the adjusted value


@pytest.mark.unit
def test_yahoo_skips_bars_padded_with_nulls():
    """Yahoo pads holidays and halts with nulls. A partial bar is not a bar."""
    with mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert len(bars) == 2


@pytest.mark.unit
def test_yahoo_timestamps_map_to_the_local_trading_date():
    with mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert [b["session_date"] for b in bars] == ["2026-09-03", "2026-09-04"]


@pytest.mark.unit
def test_yahoo_event_time_is_canonical():
    with mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert bars[0]["event_time"] == "2026-09-03T20:00:00.000000+00:00"


@pytest.mark.unit
def test_an_empty_yahoo_result_raises():
    empty = {"chart": {"result": None, "error": "nope"}}
    with (
        mock.patch.object(prices, "_http_get_json", return_value=empty),
        pytest.raises(prices.VendorResponseError, match="no result"),
    ):
        prices.fetch_yahoo("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)


@pytest.mark.unit
def test_fetch_bars_prefers_stooq_when_it_answers():
    with mock.patch.object(prices, "_http_get", return_value=CSV), \
         mock.patch.object(prices, "_http_get_json") as yahoo:
        bars = prices.fetch_bars("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert {b["source"] for b in bars} == {"stooq"}
    yahoo.assert_not_called()


@pytest.mark.unit
def test_fetch_bars_falls_back_to_yahoo_when_stooq_challenges():
    with mock.patch.object(prices, "_http_get", return_value=CHALLENGE), \
         mock.patch.object(prices, "_http_get_json", return_value=YAHOO):
        bars = prices.fetch_bars("NVDA", observed_at=OBSERVED, latency_budget=YBUDGET)
    assert {b["source"] for b in bars} == {"yahoo"}
