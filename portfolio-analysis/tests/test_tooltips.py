"""Issue #40: hover tooltips on chart dots/markers - data contract tests.

The tooltip DOM/JS lives in templates/chart.html; these tests pin the
Python-side contract the tooltips read, so a missing key surfaces here
instead of as a blank tooltip. A static wiring check keeps the tooltip
functions themselves from being silently deleted.
"""

from pathlib import Path

from portfolio_analysis.render import _regime_points
from tests.test_render import data as make_data

TEMPLATE = Path(__file__).resolve().parent.parent / "src/portfolio_analysis/templates/chart.html"


def test_move_markers_carry_every_tooltip_field(tmp_path):
    moves = make_data(tmp_path)["moves"]
    assert moves, "fixture must include at least one marker"
    for m in moves:
        for key in ("date", "return", "z", "beta", "idiosyncratic_component",
                    "facts", "kind", "evidence_status"):
            assert key in m, f"marker missing tooltip field {key!r}"
        assert isinstance(m["facts"], list)
        for f in m["facts"]:
            assert "label" in f and "date" in f


def test_dated_event_markers_have_null_z_not_fake_z(tmp_path):
    moves = make_data(tmp_path)["moves"]
    for m in moves:
        if m.get("kind") == "event":
            assert m["z"] is None, "event markers must not invent a z-score"


def test_regime_signals_align_with_alpha_slope_points():
    prices = {f"2023-01-{d:02d}": 100 + d for d in range(1, 32)}
    bench = {f"2023-01-{d:02d}": 100 + d * 0.5 for d in range(1, 32)}
    out = _regime_points(prices, bench, window=20, step=5)
    n = len(out["dates"])
    assert n > 0
    for key in ("beta", "alpha_annualized", "alpha_slope", "signals"):
        assert len(out[key]) == n, f"{key} misaligned with dates"
    # Signals are classified kinds or None - never invented text.
    assert {s for s in out["signals"] if s} <= {"turnaround"}


def test_template_has_marker_and_signal_tooltip_wiring():
    html = TEMPLATE.read_text()
    # Price-chart move markers (#40): tooltip builder + edge-clamped placement.
    assert "function moveTipLines" in html
    assert "function placeTip" in html
    assert "pointerenter" in html
    # Alpha-chart signal dots: tooltip builder with date/kind/alpha/slope.
    assert "function showSigTip" in html
    assert "SIGNAL_TEXT" in html
    # Keyboard parity: tooltips also fire on focus.
    assert "focus" in html
    # TLDR section (#42) present in markup.
    assert 'id="tldr-box"' in html
    # Marker variant legend documents triangle vs diamond (#40 checklist).
    assert "Dated event" in html
