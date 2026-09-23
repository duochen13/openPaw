import json
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path

import pytest

from portfolio_analysis import cli
from portfolio_analysis.artifacts import MovesArtifact
from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import Coverage
from portfolio_analysis.render import chart_data, render_html, safe_url
from tests import test_cli_collect
from tests.test_bundle import MOVE, bundle

setup = test_cli_collect.setup


def artifact(moves=None):
    return MovesArtifact(
        "META",
        "QQQ",
        MoveParams(250, 60, 2.5),
        Coverage(None, ("2024-04-24", "2024-04-26"), 3, 1),
        [MOVE] if moves is None else moves,
    )


def data(tmp_path, art=None):
    return chart_data(
        art or artifact(),
        {"2024-04-23": 50, "2024-04-24": 100, "2024-04-25": 90, "2024-04-26": 95},
        {"2024-04-23": 90, "2024-04-24": 100, "2024-04-25": 99.5, "2024-04-26": 101},
        tmp_path,
        name="Meta Platforms",
    )


def test_chart_excludes_warmup_and_preserves_signed_price_return(tmp_path):
    result = data(tmp_path)
    assert result["dates"][0] == "2024-04-24"
    assert result["prices"] == [100, 90, 95]
    assert result["moves"][0]["return"] == -0.1
    assert result["moves"][0]["evidence_status"] == "missing"


def test_valid_evidence_attached_but_stale_or_corrupt_evidence_rejected(tmp_path):
    path = tmp_path / "META/2024-04-25.json"
    path.parent.mkdir()
    path.write_text(json.dumps(bundle()))
    assert data(tmp_path)["moves"][0]["evidence_status"] == "available"
    stale = data(tmp_path, artifact([replace(MOVE, ret=-0.12, abnormal_return=-0.113)]))["moves"][0]
    assert stale["evidence_status"] == "stale"
    assert stale["documents"] == []
    path.write_text(path.read_text().replace("example.com", "evil.com"))
    assert data(tmp_path)["moves"][0]["evidence_status"] == "invalid"


def test_empty_move_set_still_renders_price_history(tmp_path):
    result = data(tmp_path, artifact([]))
    assert result["moves"] == []
    assert '<svg id="chart"' in render_html(result)


def test_timeframe_slider_markup_present_and_period_select_kept(tmp_path):
    text = render_html(data(tmp_path))
    for frag in (
        'id="timeframe-bar"',
        'id="tf-presets"',
        'data-tf="all"',
        'data-tf="3"',
        'data-tf="1"',
        'data-tf="0.5"',
        'data-tf="3m"',
        'data-tf="1m"',
        'data-tf="1w"',
        'id="tf-slider"',
        'id="tf-h0"',
        'id="tf-h1"',
        'role="slider"',
        'id="tf-d0"',
        'id="tf-d1"',
        'id="range"',
        'syncSliderFromState',
        'commitTF',
    ):
        assert frag in text, frag


def test_script_escape_and_dangerous_source_urls(tmp_path):
    result = data(tmp_path)
    result["name"] = "</script><img src=x onerror=alert(1)>"
    text = render_html(result)
    assert "</script><img" not in text
    assert "\\u003c/script\\u003e" in text
    assert safe_url("javascript:alert(1)") == ""
    assert safe_url("data:text/html,evil") == ""
    assert safe_url("https://www.sec.gov/Archives/a.htm").startswith("https://")


def test_self_contained_html_has_no_external_dependencies(tmp_path):
    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            assert not attrs.get("src"), (tag, attrs)
            assert not (tag == "link" and attrs.get("rel") == "stylesheet")

    text = render_html(data(tmp_path))
    Parser().feed(text)
    assert "__DATA__" not in text
    assert "<noscript>" in text


def test_invalid_prices_fail_instead_of_drawing_nan(tmp_path):
    with pytest.raises(ValueError, match="finite"):
        chart_data(
            artifact(),
            {"2024-04-24": 100, "2024-04-25": float("nan")},
            {"2024-04-24": 100, "2024-04-25": 100},
            tmp_path,
            name="Meta",
        )


def test_render_command_produces_html_without_network(setup, tmp_path):
    from portfolio_analysis.store import Store
    from tests.test_cli_detect import _bars

    store = Store.open(setup.path("db"))
    store.upsert_price_bars(
        _bars(
            "META",
            {
                "2024-04-22": 100,
                "2024-04-23": 101,
                "2024-04-24": 90,
                "2024-04-25": 81,
                "2024-04-26": 82,
            },
        )
    )
    store.close()
    assert cli.main(["render", "META", "--out-dir", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out/META.html").exists()


def test_chart_runs_stages_and_still_renders_after_collection_error(monkeypatch, setup):
    calls = []
    monkeypatch.setattr(cli, "_ingest_prices", lambda _: calls.append("prices") or 0)
    monkeypatch.setattr(cli, "_detect_moves", lambda _: calls.append("moves") or 0)
    monkeypatch.setattr(cli, "_collect_events", lambda _: calls.append("events") or 1)
    monkeypatch.setattr(cli, "_render", lambda _: calls.append("render") or 0)
    assert cli.main(["chart", "META", "--refresh-prices"]) == 1
    assert calls == ["prices", "moves", "events", "render"]


def test_chart_offline_mode_does_not_collect(monkeypatch, setup):
    monkeypatch.setattr(cli, "_ingest_prices", lambda _: 0)
    monkeypatch.setattr(cli, "_detect_moves", lambda _: 0)
    monkeypatch.setattr(cli, "_collect_events", lambda _: pytest.fail("unexpected collection"))
    monkeypatch.setattr(cli, "_render", lambda _: 0)
    assert cli.main(["chart", "META", "--skip-events"]) == 0


def test_chart_data_defaults_kpis_to_none(tmp_path):
    # Existing callers are unaffected: no KPIs means the template hides
    # the business-metrics section, the same rule as the P/E panel.
    assert data(tmp_path)["kpis"] is None


def test_chart_data_carries_kpi_payload(tmp_path):
    payload = {"metrics": [{"key": "revenue", "label": "Revenue"}]}
    result = chart_data(
        artifact(),
        {"2024-04-24": 100, "2024-04-25": 90},
        {"2024-04-24": 100, "2024-04-25": 99.5},
        tmp_path,
        name="Meta Platforms",
        kpis=payload,
    )
    assert result["kpis"] is payload


def test_render_html_embeds_kpi_section_and_payload(tmp_path):
    payload = {
        "metrics": [{
            "key": "revenue", "label": "Revenue", "format": "currency",
            "yoy_unit": "pct", "quarters": ["2024-03-31"], "values": [100.0],
            "yoy": [None], "current": 100.0, "current_yoy": None,
            "as_of": "2024-03-31", "quarters_reported": 1,
            "blurb": "Quarterly revenue (SEC EDGAR).",
        }]
    }
    result = chart_data(
        artifact(),
        {"2024-04-24": 100, "2024-04-25": 90},
        {"2024-04-24": 100, "2024-04-25": 99.5},
        tmp_path,
        name="Meta Platforms",
        kpis=payload,
    )
    html = render_html(result)
    assert 'id="kpi-box"' in html
    assert "renderKPIs();" in html
    assert '"kpis": {"metrics": [{"key": "revenue"' in html


def test_issue52_dashboard_defaults():
    """Issue #52: the alpha-slope tab loads by default with slope half-life 120."""
    html = (
        Path(__file__).resolve().parent.parent
        / "src" / "portfolio_analysis" / "templates" / "chart.html"
    ).read_text()
    assert "regimeMode:'wls-slope'" in html  # fresh-load state default
    assert "?rm:'wls-slope'" in html  # URL-hash fallback default
    assert "wlsSlopeHalfLife:'120'" in html
    assert 'id="regime-tab-wls-slope" role="tab" aria-selected="true"' in html
    assert '<option value="120" selected>120 sessions</option>' in html


def test_issue52_hash_regime_mode_override():
    """Issue #52: an explicit #regimeMode in the URL hash must override the default.

    All three valid values ('fixed', 'wls', 'wls-slope') are preserved; only a
    missing/invalid value falls back to the 'wls-slope' default.
    """
    html = (
        Path(__file__).resolve().parent.parent
        / "src" / "portfolio_analysis" / "templates" / "chart.html"
    ).read_text()
    assert (
        "state.regimeMode=(['fixed','wls','wls-slope'].includes(rm))?rm:'wls-slope';"
        in html
    )


def test_issue58_sticky_timeframe_bar():
    """Issue #58: the timeframe bar sticks to the viewport top while scrolling."""
    html = (
        Path(__file__).resolve().parent.parent
        / "src" / "portfolio_analysis" / "templates" / "chart.html"
    ).read_text()
    assert "#timeframe-bar{margin:2px 0 14px;position:sticky;top:0;" in html
    assert "background:var(--paper)" in html  # no bleed-through when stuck
    assert "#timeframe-bar.stuck{" in html  # stuck-state styling hook
    assert "IntersectionObserver" in html  # toggles .stuck while pinned
