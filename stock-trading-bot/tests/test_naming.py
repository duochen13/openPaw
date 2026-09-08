import pytest

from stock_trading_bot.naming import safe_ticker_component


@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("nvda", "NVDA"),
    ("NOW", "NOW"),
    ("BRK.B", "BRK.B"),
    ("0700.HK", "0700.HK"),
    ("  aapl  ", "AAPL"),
])
def test_valid_tickers_are_normalized(raw, expected):
    assert safe_ticker_component(raw) == expected


@pytest.mark.unit
@pytest.mark.parametrize("hostile", [
    "../../etc/passwd",
    "..",
    "a/b",
    "a\\b",
    "NVDA;rm -rf /",
    "NVDA\x00",
    "",
    "   ",
    "A" * 13,
])
def test_hostile_tickers_are_rejected(hostile):
    with pytest.raises(ValueError):
        safe_ticker_component(hostile)
