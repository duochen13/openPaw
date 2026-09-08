import pytest


@pytest.mark.unit
def test_package_imports():
    import stock_trading_bot

    assert stock_trading_bot is not None
