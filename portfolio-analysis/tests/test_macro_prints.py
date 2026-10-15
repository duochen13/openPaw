"""CPI prints layer (issue #153): loader, surprise math, classification,
macro-source integration, bundle tagging, dashboard context, collector."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from portfolio_analysis.bundle import build_bundle
from portfolio_analysis.event_dashboard import _event_context
from portfolio_analysis.events.base import VerifiedFact, dated_fact_label
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.events.macro_prints import (
    CpiMetric,
    CpiPrint,
    CpiPrints,
    classify_print,
)
from portfolio_analysis.moves import Move

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CALENDAR = {
    "schema_version": 1,
    "as_of": "2026-10-14",
    "series": {
        "FOMC": {"coverage": [["2021-01-01", "2026-12-31"]], "events": []},
        "CPI": {
            "coverage": [["2021-01-01", "2026-12-31"]],
            "events": [
                {"date": "2026-09-11", "url": "https://www.bls.gov/schedule/2026/home.htm"},
                {"date": "2026-10-14", "url": "https://www.bls.gov/schedule/2026/home.htm"},
            ],
        },
        "PCE": {"coverage": [["2021-01-01", "2026-12-31"]], "events": []},
    },
}


def _metric(actual: Any, consensus: Any = None, prior: Any = None) -> dict[str, Any]:
    return {"actual": actual, "consensus": consensus, "prior": prior, "revision": None}


def _release(date: str, reference: str, *, consensus: bool) -> dict[str, Any]:
    return {
        "release_date": date,
        "reference_period": reference,
        "release_time_et": "08:30",
        "url": "https://www.bls.gov/news.release/archives/cpi_10142026.htm",
        "metrics": {
            "headline_mom": _metric(0.6, 0.5 if consensus else None, 0.4),
            "headline_yoy": _metric(3.7, 3.6 if consensus else None, 3.4),
            "core_mom": _metric(0.3, 0.2 if consensus else None, 0.3),
            "core_yoy": _metric(2.6, 2.5 if consensus else None, 2.4),
        },
    }


PRINTS = {
    "schema_version": 1,
    "series": "CPI",
    "as_of": "2026-10-14",
    "source": "U.S. Bureau of Labor Statistics (BLS)",
    "releases": [
        _release("2026-09-11", "2026-08", consensus=False),
        _release("2026-10-14", "2026-09", consensus=True),
    ],
}


def _write(tmp_path: Path, payload: Any, name: str = "cpi_prints.yaml") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


@pytest.mark.unit
def test_loader_round_trip_and_surprises(tmp_path: Path) -> None:
    prints = CpiPrints(_write(tmp_path, PRINTS))
    assert len(prints) == 2
    anchor = prints.on("2026-10-14")
    assert anchor is not None
    assert anchor.reference_period == "2026-09"
    assert anchor.metrics["headline_yoy"].surprise == pytest.approx(0.1)
    assert anchor.metrics["core_mom"].surprise == pytest.approx(0.1)
    assert anchor.max_abs_surprise() == pytest.approx(0.1)
    earlier = prints.on("2026-09-11")
    assert earlier is not None
    # No sourced consensus -> no measurable surprise, by design.
    assert earlier.surprises() == {}
    assert earlier.max_abs_surprise() is None
    assert prints.on("2026-10-15") is None
    assert [p.release_date for p in prints.between("2026-09-01", "2026-10-31")] == [
        "2026-09-11",
        "2026-10-14",
    ]


@pytest.mark.unit
def test_loader_rejects_bad_files(tmp_path: Path) -> None:
    bad_schema = {**PRINTS, "schema_version": 2}
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, bad_schema))
    missing_metric = json.loads(json.dumps(PRINTS))
    del missing_metric["releases"][0]["metrics"]["core_yoy"]
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, missing_metric))
    missing_yoy = json.loads(json.dumps(PRINTS))
    missing_yoy["releases"][0]["metrics"]["headline_yoy"]["actual"] = None
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, missing_yoy))
    unordered = json.loads(json.dumps(PRINTS))
    unordered["releases"] = list(reversed(unordered["releases"]))
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, unordered))
    bad_url = json.loads(json.dumps(PRINTS))
    bad_url["releases"][0]["url"] = "http://example.com/cpi"
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, bad_url))
    bad_type = json.loads(json.dumps(PRINTS))
    bad_type["releases"][0]["metrics"]["core_mom"]["actual"] = "0.3"
    with pytest.raises(ValueError):
        CpiPrints(_write(tmp_path, bad_type))


@pytest.mark.unit
def test_loader_allows_null_mom_for_shutdown_release(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(PRINTS))
    payload["releases"][0]["metrics"]["headline_mom"]["actual"] = None
    payload["releases"][0]["metrics"]["core_mom"]["actual"] = None
    prints = CpiPrints(_write(tmp_path, payload))
    release = prints.on("2026-09-11")
    assert release is not None
    assert release.metrics["headline_mom"].actual is None


def _print(consensus: bool = True) -> CpiPrint:
    release = _release("2026-10-14", "2026-09", consensus=consensus)
    return CpiPrint(
        release_date=release["release_date"],
        reference_period=release["reference_period"],
        release_time_et="08:30",
        url=release["url"],
        metrics={
            key: CpiMetric(
                actual=value["actual"],
                consensus=value["consensus"],
                prior=value["prior"],
                revision=None,
            )
            for key, value in release["metrics"].items()
        },
    )


@pytest.mark.unit
def test_classify_macro_driven_and_mixed() -> None:
    driven = classify_print(_print(), has_ticker_events=False)
    assert driven is not None
    assert driven["classification"] == "macro-driven"
    assert driven["surprises_pp"] == {
        "headline_mom": 0.1,
        "headline_yoy": 0.1,
        "core_mom": 0.1,
        "core_yoy": 0.1,
    }
    assert driven["max_abs_surprise_pp"] == pytest.approx(0.1)
    assert driven["ticker_events_same_day"] is False
    mixed = classify_print(_print(), has_ticker_events=True)
    assert mixed is not None
    assert mixed["classification"] == "mixed"


@pytest.mark.unit
def test_classify_needs_a_material_sourced_surprise() -> None:
    # No consensus anywhere -> nothing to measure -> no tag.
    assert classify_print(_print(consensus=False), has_ticker_events=False) is None
    # Consensus met exactly -> surprise 0.0 -> no tag.
    release = _release("2026-10-14", "2026-09", consensus=True)
    for value in release["metrics"].values():
        value["consensus"] = value["actual"]
    in_line = CpiPrint(
        release_date=release["release_date"],
        reference_period=release["reference_period"],
        release_time_et="08:30",
        url=release["url"],
        metrics={
            key: CpiMetric(value["actual"], value["consensus"], value["prior"], None)
            for key, value in release["metrics"].items()
        },
    )
    assert classify_print(in_line, has_ticker_events=False) is None


@pytest.mark.unit
def test_macro_source_emits_print_facts_and_catalog(tmp_path: Path) -> None:
    (tmp_path / "macro_calendar.yaml").write_text(json.dumps(CALENDAR))
    _write(tmp_path, PRINTS)
    source = MacroSource(tmp_path / "macro_calendar.yaml")
    _, facts = source.collect("NOW", "2026-10-01", "2026-10-31")
    by_key = {fact.key: fact for fact in facts}
    assert set(by_key) == {"macro_release", "macro_print"}
    print_fact = by_key["macro_print"]
    assert print_fact.value["reference_period"] == "2026-09"
    assert print_fact.value["metrics"]["headline_yoy"]["actual"] == 3.7
    assert print_fact.source.startswith("https://www.bls.gov/")
    label = dated_fact_label(print_fact.key, print_fact.value)
    assert label == ("CPI print: headline 3.7% y/y vs 3.6% consensus", "2026-10-14")
    row = source.catalog()["CPI"][-1]
    assert row["print"]["metrics"]["core_yoy"]["surprise"] == pytest.approx(0.1)


@pytest.mark.unit
def test_macro_source_without_prints_file_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "macro_calendar.yaml").write_text(json.dumps(CALENDAR))
    source = MacroSource(tmp_path / "macro_calendar.yaml")
    assert source.cpi_prints is None
    _, facts = source.collect("NOW", "2026-10-01", "2026-10-31")
    assert [fact.key for fact in facts] == ["macro_release"]
    assert "print" not in source.catalog()["CPI"][-1]


class _StaticSource:
    name = "static"

    def __init__(self, facts: list[VerifiedFact]) -> None:
        self._facts = facts

    def collect(self, ticker: str, start: str, end: str) -> tuple[list, list[VerifiedFact]]:
        return [], self._facts


def _move() -> Move:
    return Move(
        ticker="NOW",
        date="2026-10-14",
        ret=-0.03,
        benchmark="QQQ",
        benchmark_return=-0.02,
        beta=1.1,
        alpha=0.0,
        abnormal_return=-0.008,
        sigma_60=0.002,
        z=-4.0,
    )


def _print_fact() -> VerifiedFact:
    return VerifiedFact(
        key="macro_print",
        value=_print().fact_value(),
        source="https://www.bls.gov/news.release/archives/cpi_10142026.htm",
    )


def _bundle(facts: list[VerifiedFact]) -> dict[str, Any]:
    return build_bundle(
        _move(),
        window=("2026-10-12", "2026-10-15"),
        sources=[_StaticSource(facts)],
        news_coverage_start="2020-01-01",
        source_status={},
        macro_coverage={"CPI": True, "FOMC": True, "PCE": True},
        collection_key="test",
    )


@pytest.mark.unit
def test_bundle_tags_cpi_day_move_macro_driven() -> None:
    bundle = _bundle([_print_fact()])
    classification = bundle["macro_classification"]
    assert classification["classification"] == "macro-driven"
    assert classification["release_date"] == "2026-10-14"
    assert classification["surprises_pp"]["headline_yoy"] == pytest.approx(0.1)
    assert bundle["bundle_sha256"]  # hash computed over the tagged payload


@pytest.mark.unit
def test_bundle_mixed_when_ticker_event_shares_the_day() -> None:
    filing = VerifiedFact(
        key="filing",
        value={"form": "8-K", "filed": "2026-10-14"},
        source="https://www.sec.gov/",
    )
    bundle = _bundle([_print_fact(), filing])
    assert bundle["macro_classification"]["classification"] == "mixed"


@pytest.mark.unit
def test_bundle_macro_release_fact_same_day_is_not_a_ticker_event() -> None:
    release = VerifiedFact(
        key="macro_release",
        value={"release": "CPI", "date": "2026-10-14", "url": "https://www.bls.gov/"},
        source="https://www.bls.gov/",
    )
    bundle = _bundle([_print_fact(), release])
    assert bundle["macro_classification"]["classification"] == "macro-driven"


@pytest.mark.unit
def test_bundle_without_print_fact_has_no_classification() -> None:
    bundle = _bundle([])
    assert "macro_classification" not in bundle


@pytest.mark.unit
def test_dashboard_context_uses_print_when_present() -> None:
    row = {
        "date": "2026-10-14",
        "url": "https://www.bls.gov/schedule/2026/home.htm",
        "print": _print().as_dict(),
    }
    context = _event_context("CPI", row, "2026-10-14")
    assert context["surprise"] == {
        "headline_mom": 0.1,
        "headline_yoy": 0.1,
        "core_mom": 0.1,
        "core_yoy": 0.1,
    }
    assert "headline 3.7% y/y vs 3.6% consensus" in context["summary"]
    assert context["short_label"] == "CPI: headline 3.7% y/y"
    bare = _event_context("CPI", {"date": "2026-10-14", "url": row["url"]}, "2026-10-14")
    assert bare["surprise"] is None
    assert bare["short_label"] == "CPI release"


@pytest.mark.unit
def test_dashboard_context_handles_first_release_and_missing_mom() -> None:
    # The earliest backfilled release has prior=null throughout, and the
    # shutdown-affected release has no m/m prints: neither may crash the
    # summary formatting.
    release = _release("2024-11-13", "2024-10", consensus=False)
    for value in release["metrics"].values():
        value["prior"] = None
    release["metrics"]["headline_mom"]["actual"] = None
    release["metrics"]["core_mom"]["actual"] = None
    print_ = CpiPrint(
        release_date=release["release_date"],
        reference_period=release["reference_period"],
        release_time_et="08:30",
        url=release["url"],
        metrics={
            key: CpiMetric(value["actual"], value["consensus"], value["prior"], None)
            for key, value in release["metrics"].items()
        },
    )
    row = {"date": "2024-11-13", "url": release["url"], "print": print_.as_dict()}
    context = _event_context("CPI", row, "2026-10-14")
    assert "headline 3.7% y/y" in context["summary"]
    assert "core m/m not published" in context["summary"]
    assert context["surprise"] is None


@pytest.mark.unit
def test_checked_in_prints_file_is_valid_and_current() -> None:
    prints = CpiPrints(PROJECT_ROOT / "config" / "cpi_prints.yaml")
    assert len(prints) >= 23  # 24-month backfill, releases 2024-11-13 on
    first = prints.between("2024-01-01", "2024-12-31")
    assert first[0].release_date == "2024-11-13"
    anchor = prints.on("2026-10-14")
    assert anchor is not None
    # Task-verified values for the September 2026 release.
    assert anchor.metrics["headline_yoy"].actual == 3.7
    assert anchor.metrics["headline_yoy"].consensus == 3.6
    assert anchor.metrics["headline_yoy"].prior == 3.4
    assert anchor.metrics["headline_mom"].actual == 0.6
    assert anchor.metrics["core_mom"].actual == 0.3
    assert anchor.metrics["core_mom"].consensus == 0.2
    assert anchor.metrics["core_mom"].prior == 0.3
    assert anchor.metrics["core_yoy"].actual == 2.6
    assert anchor.metrics["core_yoy"].consensus == 2.5
    assert anchor.metrics["core_yoy"].prior == 2.4
    # Consensus discipline: the anchor release is the only one with a
    # hand-verified survey median in this backfill.
    for print_ in prints.between("2024-01-01", "2026-10-13"):
        assert print_.surprises() == {}


def _collector():
    spec = importlib.util.spec_from_file_location(
        "collect_cpi", PROJECT_ROOT / "scripts" / "collect_cpi.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TABLE_A_HTML = """
<html><body><h2>Table A. Percent changes in CPI for All Urban Consumers (CPI-U)</h2>
<table>
<tr><th></th><th>Jun.</th><th>Jul.</th><th>Aug.</th><th>Sep.</th><th>Oct.</th><th>Nov.</th><th>Dec.</th><th>12-mos.</th></tr>
<tr><td>All items</td><td>0.1</td><td>0.2</td><td>0.2</td><td>0.3</td><td>-</td><td>-</td><td>0.3</td><td>2.7</td></tr>
<tr><td>Food</td><td>0.3</td><td>0.0</td><td>0.5</td><td>0.2</td><td>-</td><td>-</td><td>0.7</td><td>3.1</td></tr>
<tr><td>All items less food and energy</td><td>0.2</td><td>0.3</td><td>0.3</td><td>0.2</td><td>-</td><td>-</td><td>0.2</td><td>2.6</td></tr>
</table></body></html>
"""


@pytest.mark.unit
def test_collector_parses_table_a() -> None:
    collector = _collector()
    actuals = collector.parse_table_a(TABLE_A_HTML)
    assert actuals == {
        "headline_mom": 0.3,
        "headline_yoy": 2.7,
        "core_mom": 0.2,
        "core_yoy": 2.6,
    }
    assert collector.reference_period(__import__("datetime").date(2025, 12, 18)) == "2025-11"


@pytest.mark.unit
def test_collector_payload_chains_priors_and_consensus() -> None:
    collector = _collector()
    payload = collector.build_payload(
        [
            ("2026-09-11", {"headline_mom": 0.4, "headline_yoy": 3.4, "core_mom": 0.3, "core_yoy": 2.4}),
            ("2026-10-14", {"headline_mom": 0.6, "headline_yoy": 3.7, "core_mom": 0.3, "core_yoy": 2.6}),
        ],
        as_of="2026-10-14",
    )
    first, second = payload["releases"]
    assert first["metrics"]["headline_yoy"]["prior"] is None
    assert second["metrics"]["headline_yoy"]["prior"] == 3.4
    assert second["metrics"]["headline_yoy"]["consensus"] == 3.6
    assert second["metrics"]["headline_mom"]["consensus"] is None
    assert second["reference_period"] == "2026-09"
