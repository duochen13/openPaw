"""PPI prints layer (issue #155): the CPI prints design generalized to a
second series — loader, surprise math, classification, macro-source
integration, bundle tagging, dashboard context, collector."""

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
    PpiPrint,
    PpiPrints,
    ReleaseMetric,
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
        "url": "https://www.bls.gov/news.release/archives/ppi_09102026.htm",
        "metrics": {
            "final_demand_mom": _metric(0.4, 0.2 if consensus else None, 0.0),
            "final_demand_yoy": _metric(5.4, 5.2 if consensus else None, 4.7),
            "core_mom": _metric(0.2, 0.2 if consensus else None, 0.2),
            "core_yoy": _metric(4.6, 4.5 if consensus else None, 4.2),
        },
    }


PRINTS = {
    "schema_version": 1,
    "series": "PPI",
    "as_of": "2026-09-10",
    "source": "U.S. Bureau of Labor Statistics (BLS)",
    "releases": [
        _release("2026-08-13", "2026-07", consensus=False),
        _release("2026-09-10", "2026-08", consensus=True),
    ],
}


def _write(tmp_path: Path, payload: Any, name: str = "ppi_prints.yaml") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def _print(consensus: bool = True, date: str = "2026-09-10") -> PpiPrint:
    release = _release(date, "2026-08", consensus=consensus)
    return PpiPrint(
        release_date=release["release_date"],
        reference_period=release["reference_period"],
        release_time_et="08:30",
        url=release["url"],
        metrics={
            key: ReleaseMetric(
                actual=value["actual"],
                consensus=value["consensus"],
                prior=value["prior"],
                revision=None,
            )
            for key, value in release["metrics"].items()
        },
    )


@pytest.mark.unit
def test_loader_round_trip_and_surprises(tmp_path: Path) -> None:
    prints = PpiPrints(_write(tmp_path, PRINTS))
    assert len(prints) == 2
    anchor = prints.on("2026-09-10")
    assert anchor is not None
    assert isinstance(anchor, PpiPrint)
    assert anchor.series == "PPI"
    assert anchor.reference_period == "2026-08"
    assert anchor.metrics["final_demand_mom"].surprise == pytest.approx(0.2)
    assert anchor.metrics["core_yoy"].surprise == pytest.approx(0.1)
    assert anchor.max_abs_surprise() == pytest.approx(0.2)
    earlier = prints.on("2026-08-13")
    assert earlier is not None
    # No sourced consensus -> no measurable surprise, by design.
    assert earlier.surprises() == {}
    assert earlier.max_abs_surprise() is None
    assert prints.on("2026-10-15") is None
    assert [p.release_date for p in prints.between("2026-08-01", "2026-09-30")] == [
        "2026-08-13",
        "2026-09-10",
    ]


@pytest.mark.unit
def test_loader_rejects_bad_files(tmp_path: Path) -> None:
    bad_schema = {**PRINTS, "schema_version": 2}
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, bad_schema))
    wrong_series = {**PRINTS, "series": "CPI"}
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, wrong_series))
    missing_metric = json.loads(json.dumps(PRINTS))
    del missing_metric["releases"][0]["metrics"]["core_yoy"]
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, missing_metric))
    cpi_metric = json.loads(json.dumps(PRINTS))
    cpi_metric["releases"][0]["metrics"]["headline_yoy"] = _metric(3.0)
    del cpi_metric["releases"][0]["metrics"]["final_demand_yoy"]
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, cpi_metric))
    missing_yoy = json.loads(json.dumps(PRINTS))
    missing_yoy["releases"][0]["metrics"]["final_demand_yoy"]["actual"] = None
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, missing_yoy))
    unordered = json.loads(json.dumps(PRINTS))
    unordered["releases"] = list(reversed(unordered["releases"]))
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, unordered))
    bad_url = json.loads(json.dumps(PRINTS))
    bad_url["releases"][0]["url"] = "http://example.com/ppi"
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, bad_url))
    bad_type = json.loads(json.dumps(PRINTS))
    bad_type["releases"][0]["metrics"]["core_mom"]["actual"] = "0.2"
    with pytest.raises(ValueError):
        PpiPrints(_write(tmp_path, bad_type))


@pytest.mark.unit
def test_loader_allows_null_mom(tmp_path: Path) -> None:
    payload = json.loads(json.dumps(PRINTS))
    payload["releases"][0]["metrics"]["final_demand_mom"]["actual"] = None
    payload["releases"][0]["metrics"]["core_mom"]["actual"] = None
    prints = PpiPrints(_write(tmp_path, payload))
    release = prints.on("2026-08-13")
    assert release is not None
    assert release.metrics["final_demand_mom"].actual is None


@pytest.mark.unit
def test_classify_macro_driven_and_mixed() -> None:
    driven = classify_print(_print(), has_ticker_events=False)
    assert driven is not None
    assert driven["classification"] == "macro-driven"
    assert driven["release"] == "PPI"
    assert driven["surprises_pp"] == {
        "final_demand_mom": 0.2,
        "final_demand_yoy": 0.2,
        "core_mom": 0.0,
        "core_yoy": 0.1,
    }
    assert driven["max_abs_surprise_pp"] == pytest.approx(0.2)
    mixed = classify_print(_print(), has_ticker_events=True)
    assert mixed is not None
    assert mixed["classification"] == "mixed"


@pytest.mark.unit
def test_classify_needs_a_material_sourced_surprise() -> None:
    assert classify_print(_print(consensus=False), has_ticker_events=False) is None


@pytest.mark.unit
def test_macro_source_emits_ppi_facts_and_catalog(tmp_path: Path) -> None:
    (tmp_path / "macro_calendar.yaml").write_text(json.dumps(CALENDAR))
    _write(tmp_path, PRINTS)
    source = MacroSource(tmp_path / "macro_calendar.yaml")
    assert source.ppi_prints is not None
    _, facts = source.collect("NOW", "2026-09-01", "2026-09-30")
    ppi_facts = [
        fact for fact in facts
        if fact.key == "macro_print" and fact.value["release"] == "PPI"
    ]
    assert len(ppi_facts) == 1
    fact = ppi_facts[0]
    assert fact.value["reference_period"] == "2026-08"
    assert fact.value["metrics"]["final_demand_yoy"]["actual"] == 5.4
    assert fact.source.startswith("https://www.bls.gov/")
    assert "final demand 5.4% y/y" in fact.detail
    label = dated_fact_label(fact.key, fact.value)
    assert label == ("PPI print: final demand 5.4% y/y vs 5.2% consensus", "2026-09-10")
    rows = source.catalog()["PPI"]
    assert [row["date"] for row in rows] == ["2026-08-13", "2026-09-10"]
    assert rows[-1]["print"]["metrics"]["core_yoy"]["surprise"] == pytest.approx(0.1)


@pytest.mark.unit
def test_macro_source_without_ppi_file_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "macro_calendar.yaml").write_text(json.dumps(CALENDAR))
    source = MacroSource(tmp_path / "macro_calendar.yaml")
    assert source.ppi_prints is None
    assert "PPI" not in source.catalog()
    _, facts = source.collect("NOW", "2026-09-01", "2026-09-30")
    assert all(fact.value.get("release") != "PPI" for fact in facts)


class _StaticSource:
    name = "static"

    def __init__(self, facts: list[VerifiedFact]) -> None:
        self._facts = facts

    def collect(self, ticker: str, start: str, end: str) -> tuple[list, list[VerifiedFact]]:
        return [], self._facts


def _move(date: str = "2026-09-10") -> Move:
    return Move(
        ticker="NOW",
        date=date,
        ret=-0.03,
        benchmark="QQQ",
        benchmark_return=-0.02,
        beta=1.1,
        alpha=0.0,
        abnormal_return=-0.008,
        sigma_60=0.002,
        z=-4.0,
    )


def _bundle(facts: list[VerifiedFact], date: str = "2026-09-10") -> dict[str, Any]:
    return build_bundle(
        _move(date),
        window=("2026-09-08", "2026-09-11"),
        sources=[_StaticSource(facts)],
        news_coverage_start="2020-01-01",
        source_status={},
        macro_coverage={"CPI": True, "FOMC": True, "PCE": True},
        collection_key="test",
    )


@pytest.mark.unit
def test_bundle_tags_ppi_day_move_macro_driven() -> None:
    fact = VerifiedFact(
        key="macro_print",
        value=_print().fact_value(),
        source="https://www.bls.gov/news.release/archives/ppi_09102026.htm",
    )
    bundle = _bundle([fact])
    classification = bundle["macro_classification"]
    assert classification["classification"] == "macro-driven"
    assert classification["release"] == "PPI"
    assert classification["release_date"] == "2026-09-10"
    assert classification["surprises_pp"]["final_demand_yoy"] == pytest.approx(0.2)


@pytest.mark.unit
def test_bundle_ppi_without_consensus_has_no_classification() -> None:
    fact = VerifiedFact(
        key="macro_print",
        value=_print(consensus=False).fact_value(),
        source="https://www.bls.gov/news.release/archives/ppi_09102026.htm",
    )
    bundle = _bundle([fact])
    assert "macro_classification" not in bundle


@pytest.mark.unit
def test_bundle_same_day_cpi_and_ppi_picks_larger_surprise() -> None:
    # CPI print with a 0.1pp surprise and a PPI print with a 0.2pp surprise
    # dated the same day: the bundle tags the PPI classification.
    cpi = CpiPrint(
        release_date="2026-09-10",
        reference_period="2026-08",
        release_time_et="08:30",
        url="https://www.bls.gov/news.release/archives/cpi_09102026.htm",
        metrics={
            "headline_mom": CpiMetric(0.4, 0.4, 0.1, None),
            "headline_yoy": CpiMetric(3.4, 3.3, 3.4, None),
            "core_mom": CpiMetric(0.3, 0.3, 0.2, None),
            "core_yoy": CpiMetric(2.4, 2.4, 2.5, None),
        },
    )
    facts = [
        VerifiedFact(key="macro_print", value=cpi.fact_value(), source=cpi.url),
        VerifiedFact(
            key="macro_print",
            value=_print().fact_value(),
            source="https://www.bls.gov/news.release/archives/ppi_09102026.htm",
        ),
    ]
    bundle = _bundle(facts)
    assert bundle["macro_classification"]["release"] == "PPI"
    assert bundle["macro_classification"]["max_abs_surprise_pp"] == pytest.approx(0.2)


@pytest.mark.unit
def test_dashboard_context_uses_ppi_print_when_present() -> None:
    row = {
        "date": "2026-09-10",
        "url": "https://www.bls.gov/news.release/archives/ppi_09102026.htm",
        "print": _print().as_dict(),
    }
    context = _event_context("PPI", row, "2026-10-14")
    assert context["surprise"] == {
        "final_demand_mom": 0.2,
        "final_demand_yoy": 0.2,
        "core_mom": 0.0,
        "core_yoy": 0.1,
    }
    assert "final demand 5.4% y/y vs 5.2% consensus" in context["summary"]
    assert context["short_label"] == "PPI: final demand 5.4% y/y"
    assert "Producer Price Index" in context["affected_variable"]
    bare = _event_context("PPI", {"date": "2026-09-10", "url": row["url"]}, "2026-10-14")
    assert bare["surprise"] is None
    assert bare["short_label"] == "PPI release"


@pytest.mark.unit
def test_checked_in_ppi_file_is_valid_and_current() -> None:
    prints = PpiPrints(PROJECT_ROOT / "config" / "ppi_prints.yaml")
    assert len(prints) >= 22  # 24-month backfill, releases 2024-11-14 on
    first = prints.between("2024-01-01", "2024-12-31")
    assert first[0].release_date == "2024-11-14"
    latest = prints.on("2026-09-10")
    assert latest is not None
    # As-printed values for the August 2026 release (BLS, 2026-09-10).
    assert latest.reference_period == "2026-08"
    assert latest.metrics["final_demand_mom"].actual == 0.4
    assert latest.metrics["final_demand_yoy"].actual == 5.4
    assert latest.metrics["core_mom"].actual == 0.2
    assert latest.metrics["core_yoy"].actual == 4.6
    # The October 2025 release was never published (shutdown): no row,
    # and the November 2025 print chains its prior to September 2025.
    assert all(
        p.reference_period != "2025-10"
        for p in prints.between("2024-01-01", "2026-12-31")
    )
    november = prints.on("2026-01-14")
    assert november is not None
    assert november.reference_period == "2025-11"
    assert november.metrics["final_demand_yoy"].prior == 2.7
    # Consensus discipline: no PPI survey median has been hand-verified,
    # so no release in the backfill carries a measurable surprise.
    for print_ in prints.between("2024-01-01", "2026-12-31"):
        assert print_.surprises() == {}


def _collector():
    spec = importlib.util.spec_from_file_location(
        "collect_ppi", PROJECT_ROOT / "scripts" / "collect_ppi.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TABLE_1_HTML = """
<html><head><title>Producer Price Index News Release - 2026 M08 Results</title></head>
<body>
<table>
<tr><td>Final demand</td><td>FD</td><td>4</td><td>100.000</td><td>5.4</td>
<td>1.1</td><td>0.5</td><td>-0.1</td><td>0.1</td><td>0.4</td></tr>
<tr><td>Final demand goods</td><td>FD</td><td>41</td><td>32.5</td><td>6.1</td>
<td>0.9</td><td>0.2</td><td>0.0</td><td>0.3</td><td>0.5</td></tr>
<tr><td>Final demand less foods and energy(5)</td><td>FD</td><td>49104</td>
<td>89.487</td><td>4.6</td><td>0.7</td><td>0.0</td><td>0.4</td><td>0.3</td><td>0.2</td></tr>
</table>
<table>
<tr><td>Final demand</td><td>FD</td><td>4</td><td>142.001</td><td>150.120</td>
<td>151.300</td><td>152.010</td><td>153.200</td><td>154.010</td></tr>
</table>
</body></html>
"""


@pytest.mark.unit
def test_collector_parses_table_1() -> None:
    collector = _collector()
    actuals = collector.parse_table_1(TABLE_1_HTML)
    assert actuals == {
        "final_demand_mom": 0.4,
        "final_demand_yoy": 5.4,
        "core_mom": 0.2,
        "core_yoy": 4.6,
    }
    assert collector.parse_reference_period(TABLE_1_HTML) == "2026-08"


@pytest.mark.unit
def test_collector_payload_chains_priors_and_no_consensus() -> None:
    collector = _collector()
    payload = collector.build_payload(
        [
            (
                "2026-08-13",
                "2026-07",
                {
                    "final_demand_mom": 0.0, "final_demand_yoy": 4.7,
                    "core_mom": 0.2, "core_yoy": 4.2,
                },
                [],
            ),
            (
                "2026-09-10",
                "2026-08",
                {
                    "final_demand_mom": 0.4, "final_demand_yoy": 5.4,
                    "core_mom": 0.2, "core_yoy": 4.6,
                },
                [],
            ),
        ],
        as_of="2026-09-10",
    )
    assert payload["series"] == "PPI"
    first, second = payload["releases"]
    assert first["metrics"]["final_demand_yoy"]["prior"] is None
    assert second["metrics"]["final_demand_yoy"]["prior"] == 4.7
    # No hand-verified PPI survey median exists yet: consensus stays null.
    assert second["metrics"]["final_demand_yoy"]["consensus"] is None
    assert second["url"].endswith("ppi_09102026.htm")
