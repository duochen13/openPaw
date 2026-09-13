import pytest

from portfolio_analysis.moves import aligned_returns


@pytest.mark.unit
def test_returns_are_computed_between_consecutive_common_dates():
    asset = {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 99.0}
    bench = {"2024-01-02": 50.0, "2024-01-03": 51.0, "2024-01-04": 51.0}
    dates, ar, br = aligned_returns(asset, bench)
    assert dates == ["2024-01-03", "2024-01-04"]
    assert ar == pytest.approx([0.10, -0.10])
    assert br == pytest.approx([0.02, 0.0])


@pytest.mark.unit
def test_dates_absent_from_one_series_are_dropped():
    asset = {"2024-01-02": 100.0, "2024-01-03": 110.0, "2024-01-04": 121.0}
    bench = {"2024-01-02": 50.0, "2024-01-04": 51.0}
    dates, ar, _ = aligned_returns(asset, bench)
    assert dates == ["2024-01-04"]
    # 100 -> 121 across the dropped date, not 110 -> 121.
    assert ar == pytest.approx([0.21])


@pytest.mark.unit
def test_more_than_five_dropped_dates_raises():
    """Beyond a handful of halts, the two series disagree about the trading
    calendar, and every return spanning a gap is fabricated."""
    asset = {f"2024-01-{d:02d}": 100.0 for d in range(1, 21)}
    bench = {f"2024-01-{d:02d}": 50.0 for d in range(1, 21) if d % 3}
    with pytest.raises(ValueError, match="trading calendar"):
        aligned_returns(asset, bench)


@pytest.mark.unit
def test_fewer_than_two_common_dates_raises():
    with pytest.raises(ValueError, match="at least two"):
        aligned_returns({"2024-01-02": 1.0}, {"2024-01-02": 1.0})


@pytest.mark.unit
def test_a_zero_prior_close_raises_rather_than_dividing():
    asset = {"2024-01-02": 0.0, "2024-01-03": 10.0}
    bench = {"2024-01-02": 50.0, "2024-01-03": 51.0}
    with pytest.raises(ValueError, match="non-positive"):
        aligned_returns(asset, bench)
