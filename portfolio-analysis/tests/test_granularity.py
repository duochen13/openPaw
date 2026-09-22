"""Issue #41: adaptive zoom granularity for the alpha/beta regime series.

The template switches daily/weekly/monthly by visible range (issue #41);
these tests pin the Python-side contract: the embedded ``fine`` series is
daily-step and tail-limited, every series stays aligned, and the template's
zoom->granularity mapping plus its monthly fallback still exist.
"""

from pathlib import Path

from portfolio_analysis.render import _FINE_TAIL_SESSIONS, _regime_points

TEMPLATE = Path(__file__).resolve().parent.parent / "src/portfolio_analysis/templates/chart.html"


def _prices(n, base=100.0, drift=0.001):
    days = [f"2024-{(m // 28) + 1:02d}-{(m % 28) + 1:02d}" for m in range(n)]
    # Unique, sortable day labels; values drift upward with noise.
    return {d: base * (1 + drift) ** i for i, d in enumerate(days)}


def test_fine_series_is_daily_step_and_tail_limited():
    prices = _prices(800)
    bench = _prices(800, base=200.0, drift=0.0005)
    fine = _regime_points(prices, bench, 250, step=1, tail=_FINE_TAIL_SESSIONS)
    dates = fine["dates"]
    assert len(dates) == _FINE_TAIL_SESSIONS, (
        f"fine tail should cover the last {_FINE_TAIL_SESSIONS} sessions"
    )
    # step=1: one point per session, no gaps.
    assert dates == sorted(dates)
    assert len(set(dates)) == len(dates)
    for key in ("beta", "r_squared", "alpha_annualized", "alpha_slope",
                "alpha_slope_display", "signals"):
        assert len(fine[key]) == len(dates), f"{key} misaligned with fine dates"
    # The fine tail really is the tail: its last date is the series end.
    assert dates[-1] == max(prices)


def test_coarse_series_stays_monthly_step():
    prices = _prices(800)
    bench = _prices(800, base=200.0, drift=0.0005)
    coarse = _regime_points(prices, bench, 250)
    fine = _regime_points(prices, bench, 250, step=1, tail=_FINE_TAIL_SESSIONS)
    assert len(coarse["dates"]) < len(fine["dates"]), (
        "default series must stay coarser than the daily fine tail"
    )


def test_template_zoom_to_granularity_mapping():
    html = TEMPLATE.read_text()
    # >1yr monthly, 1-12mo weekly, <1mo daily (the mapping issue #41 proposed).
    assert "function granularityForDays(days)" in html
    assert "days<=31?'daily'" in html.replace(" ", "")
    assert "days<=365?'weekly'" in html.replace(" ", "")
    # The active resolution is surfaced next to the sparklines (#41 checklist).
    assert "regime-gran" in html
    assert "resolution" in html
    # Fine tail is only the recent tail: zooming outside it falls back to monthly.
    assert "start<fineStart" in html.replace(" ", "")
    # Weekly is every 5th daily point, always keeping the latest point.
    assert "k%5===0" in html.replace(" ", "")
