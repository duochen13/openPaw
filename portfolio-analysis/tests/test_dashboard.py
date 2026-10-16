import pytest

from portfolio_analysis.config import load_portfolio
from portfolio_analysis.dashboard import render_dashboard


@pytest.mark.unit
def test_card_carries_history_badge_when_mapped(tmp_path):
    """Issue #152: a ticker whose history cannot fill the beta window is
    badged on its dashboard card so the card does not overclaim."""
    portfolio = load_portfolio()
    target = render_dashboard(
        portfolio, tmp_path / "out", history_badges={"SPCX": "history < 250d"}
    )
    page = target.read_text()
    assert '<span class="badge">history &lt; 250d</span>' in page
    # The badge belongs to the SPCX card, not sprinkled over every card.
    spcx_card = page.split('href="SPCX.html"', 1)[1].split("</a>", 1)[0]
    assert "history &lt; 250d" in spcx_card
    meta_card = page.split('href="META.html"', 1)[1].split("</a>", 1)[0]
    assert "badge" not in meta_card


@pytest.mark.unit
def test_no_badges_without_a_mapping(tmp_path):
    portfolio = load_portfolio()
    target = render_dashboard(portfolio, tmp_path / "out")
    assert 'class="badge"' not in target.read_text()
