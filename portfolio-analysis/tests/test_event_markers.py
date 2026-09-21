"""Event-driven chart annotations (Daniel feedback on PR #43).

Markers are the union of unusual-move days and verified dated-event days
(earnings, SEC filings, macro releases). Forum/news chatter alone never
seeds a marker. Event-only markers carry the day's return and abnormal
move; z/sigma/alpha stay None because they were never estimated for
those days.
"""

import json
import math
import random
from datetime import date, timedelta
from itertools import pairwise

import pytest

from portfolio_analysis.artifacts import Coverage, MovesArtifact
from portfolio_analysis.config import MoveParams
from portfolio_analysis.events.base import dated_fact_label
from portfolio_analysis.render import (
    _event_catalog,
    _merge_event_markers,
    _regime_points,
    chart_data,
    render_html,
)
from portfolio_analysis.signals import SLOPE_DISPLAY_SPAN, alpha_signal, smooth_display

PARAMS = MoveParams(beta_window=20, sigma_window=10, z_threshold=2.5)


def _prices(n, seed=3, drift=0.0005, vol=0.01):
    rng = random.Random(seed)
    rets = [rng.gauss(drift, vol) for _ in range(n)]
    start = date(2024, 1, 2)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(n + 1)]
    prices = {dates[0]: 100.0}
    for i, r in enumerate(rets, start=1):
        prices[dates[i]] = prices[dates[i - 1]] * (1 + r)
    return prices, dates


def _artifact(moves=()):
    return MovesArtifact("META", "QQQ", PARAMS, Coverage(None, None, 3, len(moves)), list(moves))


# ---------------------------------------------------------------------------
# dated_fact_label


@pytest.mark.unit
def test_dated_fact_label_kinds():
    assert dated_fact_label("filing", {"form": "10-K", "filed": "2024-02-01"}) == (
        "10-K filing",
        "2024-02-01",
    )
    assert dated_fact_label(
        "earnings_reported", {"reportedDate": "2024-04-24"}
    ) == ("Quarterly earnings reported", "2024-04-24")
    assert dated_fact_label("macro_release", {"release": "CPI", "date": "2024-03-12"}) == (
        "CPI release",
        "2024-03-12",
    )


@pytest.mark.unit
def test_dated_fact_label_ignores_chatter_and_malformed():
    # Document/headline keys (HN, news, Reddit) are not dated evidence and
    # must never pin an event to a day.
    assert dated_fact_label("document", {"title": "stock moons"}) is None
    assert dated_fact_label("headline", {"title": "stock moons"}) is None
    assert dated_fact_label("commentary", {"text": "to the moon"}) is None
    assert dated_fact_label("unknown_kind", {"date": "2024-01-01"}) is None
    # Malformed verified facts degrade to None, not a crash.
    assert dated_fact_label("filing", {"form": "10-K"}) is None
    assert dated_fact_label("filing", None) is None
    assert dated_fact_label("earnings_reported", {}) is None


# ---------------------------------------------------------------------------
# _event_catalog


def _write_catalog(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


@pytest.mark.unit
def test_event_catalog_missing_file(tmp_path):
    assert _event_catalog(tmp_path, "META") == {}


@pytest.mark.unit
def test_event_catalog_corrupt_file(tmp_path):
    target = tmp_path / "META" / "event_dates.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json")
    assert _event_catalog(tmp_path, "META") == {}


@pytest.mark.unit
def test_event_catalog_wrong_schema_or_ticker(tmp_path):
    target = tmp_path / "META" / "event_dates.json"
    _write_catalog(
        target,
        {"schema_version": 999, "ticker": "META", "dates": {"2024-01-01": []}},
    )
    assert _event_catalog(tmp_path, "META") == {}
    _write_catalog(
        target,
        {"schema_version": 1, "ticker": "NVDA", "dates": {"2024-01-01": []}},
    )
    assert _event_catalog(tmp_path, "META") == {}


@pytest.mark.unit
def test_event_catalog_parses_rows(tmp_path):
    target = tmp_path / "META" / "event_dates.json"
    _write_catalog(
        target,
        {
            "schema_version": 1,
            "ticker": "META",
            "dates": {
                "2024-04-24": [
                    {
                        "kind": "earnings",
                        "label": "Quarterly earnings reported",
                        "date": "2024-04-24",
                        "detail": "",
                        "url": "https://example.com/earnings",
                    }
                ],
                "2024-04-25": [{"label": "", "date": "2024-04-25"}],
            },
        },
    )
    catalog = _event_catalog(tmp_path, "META")
    assert set(catalog) == {"2024-04-24"}
    row = catalog["2024-04-24"][0]
    assert row["label"] == "Quarterly earnings reported"
    assert row["date"] == "2024-04-24"
    assert row["url"] == "https://example.com/earnings"


# ---------------------------------------------------------------------------
# _merge_event_markers


def _merge(moves, catalog, dates, asset, benchmark, beta_window=20):
    _merge_event_markers(
        moves,
        event_catalog=catalog,
        dates=dates,
        asset=asset,
        benchmark=benchmark,
        benchmark_name="QQQ",
        beta_window=beta_window,
    )
    return moves


@pytest.mark.unit
def test_merge_creates_event_only_marker_for_modest_move():
    asset, dates = _prices(60)
    benchmark, _ = _prices(60, seed=11)
    day = dates[50]
    catalog = {
        day: [
            {
                "label": "Quarterly earnings reported",
                "date": day,
                "detail": "",
                "url": "",
            }
        ]
    }
    moves = _merge([], catalog, dates, asset, benchmark)
    assert len(moves) == 1
    m = moves[0]
    assert m["kind"] == "event"
    assert m["date"] == day
    assert m["z"] is None
    assert m["sigma_60"] is None
    assert m["alpha_annualized"] is None
    assert m["coverage"] is None
    assert m["evidence_status"] == "event_only"
    # Return and abnormal move are still real numbers.
    assert math.isfinite(m["return"])
    assert math.isfinite(m["beta"])
    assert math.isfinite(m["idiosyncratic_component"])
    assert m["return"] == pytest.approx(asset[day] / asset[dates[49]] - 1)


@pytest.mark.unit
def test_merge_keeps_single_marker_for_move_and_event_day():
    asset, dates = _prices(60)
    benchmark, _ = _prices(60, seed=11)
    day = dates[50]
    existing = {
        "date": day,
        "kind": "move",
        "facts": [{"label": "10-K filing", "date": day}],
    }
    catalog = {
        day: [
            {"label": "10-K filing", "date": day, "detail": "", "url": ""},
            {
                "label": "Quarterly earnings reported",
                "date": day,
                "detail": "",
                "url": "",
            },
        ]
    }
    moves = _merge([existing], catalog, dates, asset, benchmark)
    assert len(moves) == 1
    m = moves[0]
    assert m["kind"] == "move"
    assert [f["label"] for f in m["facts"]] == [
        "10-K filing",
        "Quarterly earnings reported",
    ]


@pytest.mark.unit
def test_merge_skips_day_without_trailing_window():
    asset, dates = _prices(60)
    benchmark, _ = _prices(60, seed=11)
    day = dates[10]  # index <= beta_window: no full trailing window
    catalog = {day: [{"label": "CPI release", "date": day, "detail": "", "url": ""}]}
    assert _merge([], catalog, dates, asset, benchmark, beta_window=20) == []


@pytest.mark.unit
def test_merge_skips_day_outside_price_history():
    asset, dates = _prices(60)
    benchmark, _ = _prices(60, seed=11)
    catalog = {
        "1999-01-01": [{"label": "CPI release", "date": "1999-01-01", "detail": "", "url": ""}]
    }
    assert _merge([], catalog, dates, asset, benchmark) == []


@pytest.mark.unit
def test_merge_skips_degenerate_beta():
    asset, dates = _prices(60)
    # Flat benchmark: zero variance, beta undefined.
    benchmark = {d: 100.0 for d in dates}
    day = dates[50]
    catalog = {day: [{"label": "CPI release", "date": day, "detail": "", "url": ""}]}
    assert _merge([], catalog, dates, asset, benchmark) == []


# ---------------------------------------------------------------------------
# smooth_display


@pytest.mark.unit
def test_smooth_display_trailing_average():
    out = smooth_display([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], span=3)
    assert out == [None, None, 2.0, 3.0, 4.0, 5.0]


@pytest.mark.unit
def test_smooth_display_none_breaks_the_run():
    out = smooth_display([1.0, 2.0, None, 4.0, 5.0, 6.0], span=2)
    assert out == [None, 1.5, None, None, 4.5, 5.5]


@pytest.mark.unit
def test_smooth_display_is_causal():
    before = smooth_display([1.0, 2.0, 3.0, 4.0, 5.0], span=5)
    after = smooth_display([1.0, 2.0, 3.0, 4.0, 500.0], span=5)
    assert before[:4] == after[:4]


@pytest.mark.unit
def test_smooth_display_default_span():
    out = smooth_display([float(i) for i in range(SLOPE_DISPLAY_SPAN)])
    assert out[-1] == pytest.approx(sum(range(SLOPE_DISPLAY_SPAN)) / SLOPE_DISPLAY_SPAN)
    assert all(v is None for v in out[:-1])


# ---------------------------------------------------------------------------
# _regime_points: display smoothing must not touch signals


@pytest.mark.unit
def test_regime_points_display_series_leaves_signals_untouched():
    asset, _ = _prices(400, vol=0.02)
    benchmark, _ = _prices(400, seed=21, vol=0.012)
    pts = _regime_points(asset, benchmark, 60)
    assert len(pts["alpha_slope_display"]) == len(pts["alpha_slope"])
    # Signals still classify the raw slope.
    for alpha_ann, slope, signal in zip(
        pts["alpha_annualized"], pts["alpha_slope"], pts["signals"], strict=True
    ):
        assert signal == alpha_signal(alpha_ann, slope)
    # The display series is smoother than the raw slope where both exist.
    raw = [s for s in pts["alpha_slope"] if s is not None]
    disp = [s for s in pts["alpha_slope_display"] if s is not None]
    assert disp, "expected some display points"
    raw_jumps = [abs(b - a) for a, b in pairwise(raw)]
    disp_jumps = [abs(b - a) for a, b in pairwise(disp)]
    assert sum(disp_jumps) / len(disp_jumps) <= sum(raw_jumps) / len(raw_jumps)


# ---------------------------------------------------------------------------
# chart_data / render_html integration


@pytest.mark.unit
def test_chart_data_merges_event_markers_and_tldr_names_them(tmp_path):
    asset, dates = _prices(600)
    benchmark, _ = _prices(600, seed=31)
    day = dates[580]
    _write_catalog(
        tmp_path / "META" / "event_dates.json",
        {
            "schema_version": 1,
            "ticker": "META",
            "dates": {
                day: [
                    {
                        "kind": "earnings",
                        "label": "Quarterly earnings reported",
                        "date": day,
                        "detail": "",
                        "url": "",
                    }
                ]
            },
        },
    )
    data = chart_data(_artifact(), asset, benchmark, tmp_path, name="Meta Platforms")
    kinds = [m["kind"] for m in data["moves"]]
    assert "event" in kinds
    event_rows = [m for m in data["moves"] if m["kind"] == "event"]
    assert len(event_rows) == 1
    assert event_rows[0]["z"] is None
    assert "dated event" in data["tldr"]
    assert len(data["tldr"].split()) < 100
    # The slope sparkline gets a display series distinct from the raw slope.
    disp = data["regime"]["windows"]["250"]["alpha_slope_display"]
    raw = data["regime"]["windows"]["250"]["alpha_slope"]
    assert len(disp) == len(raw)
    assert any(d != r for d, r in zip(disp, raw, strict=True) if d is not None and r is not None)


@pytest.mark.unit
def test_render_html_event_only_marker_renders_without_crash(tmp_path):
    asset, dates = _prices(300)
    benchmark, _ = _prices(300, seed=31)
    day = dates[280]
    _write_catalog(
        tmp_path / "META" / "event_dates.json",
        {
            "schema_version": 1,
            "ticker": "META",
            "dates": {
                day: [
                    {
                        "kind": "macro",
                        "label": "CPI release",
                        "date": day,
                        "detail": "",
                        "url": "",
                    }
                ]
            },
        },
    )
    data = chart_data(_artifact(), asset, benchmark, tmp_path, name="Meta Platforms")
    html = render_html(data)
    assert "—" in html  # event-only z renders as an em dash, not "None"
    assert "None" not in html.split("<table")[1].split("</table>")[0]
