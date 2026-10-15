"""Checked-in macro release dates with explicit per-series coverage."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from portfolio_analysis.events.base import Document, VerifiedFact
from portfolio_analysis.events.macro_prints import CpiPrints


class MacroSource:
    name = "macro"

    def __init__(self, path: Path) -> None:
        raw = path.read_text()
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        data = yaml.safe_load(raw)
        if data.get("schema_version") != 1:
            raise ValueError("unsupported macro calendar schema")
        #: Issue #7: when the checked-in calendar was last revised; surfaced as
        #: the source timestamp in per-event context blocks.
        self.as_of: str = str(data.get("as_of") or "")
        self._series: dict[str, Any] = data["series"]
        decisions_path = path.with_name("fomc_decisions.yaml")
        self._fomc_decisions: dict[str, Any] = (
            yaml.safe_load(decisions_path.read_text()) if decisions_path.exists() else {}
        )
        #: Issue #153: CPI release prints (actual vs consensus), loaded like
        #: the FOMC decisions — a checked-in sibling of the calendar. Absent
        #: file means dates only, exactly the pre-#153 behavior.
        prints_path = path.with_name("cpi_prints.yaml")
        self.cpi_prints: CpiPrints | None = (
            CpiPrints(prints_path) if prints_path.exists() else None
        )
        if set(self._series) != {"FOMC", "CPI", "PCE"}:
            raise ValueError("macro calendar needs FOMC, CPI, and PCE")
        for series in self._series.values():
            for lo, hi in series["coverage"]:
                if date.fromisoformat(str(lo)) > date.fromisoformat(str(hi)):
                    raise ValueError("reversed macro coverage interval")
            for event in series["events"]:
                date.fromisoformat(str(event["date"]))
                if not str(event["url"]).startswith("https://"):
                    raise ValueError("macro release requires a source URL")

    def coverage(self, start: str, end: str) -> dict[str, bool]:
        return {
            name: any(str(lo) <= start <= end <= str(hi) for lo, hi in series["coverage"])
            for name, series in self._series.items()
        }

    def catalog(self) -> dict[str, list[dict[str, Any]]]:
        """Return the checked-in release dates for interactive analysis."""
        catalog: dict[str, list[dict[str, Any]]] = {}
        for name, series in self._series.items():
            rows: list[dict[str, Any]] = []
            for event in series["events"]:
                row: dict[str, Any] = {
                    "date": str(event["date"]),
                    "url": str(event["url"]),
                    **(
                        self._fomc_decisions.get(str(event["date"]), {})
                        if name == "FOMC"
                        else {}
                    ),
                }
                if name == "CPI" and self.cpi_prints is not None:
                    print_ = self.cpi_prints.on(str(event["date"]))
                    if print_ is not None:
                        row["print"] = print_.as_dict()
                rows.append(row)
            catalog[name] = rows
        return catalog

    def collect(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> tuple[list[Document], list[VerifiedFact]]:
        facts = [
            VerifiedFact(
                key="macro_release",
                value={"release": name, "date": str(event["date"]), "url": event["url"]},
                source=event["url"],
                detail=f"{name} release on {event['date']}",
            )
            for name, series in self._series.items()
            for event in series["events"]
            if start <= str(event["date"]) <= end
        ]
        facts.sort(key=lambda fact: (fact.value["date"], fact.value["release"]))
        if self.cpi_prints is not None:
            # Issue #153: the print itself is a verified fact, sourced from
            # the BLS release — distinct from the calendar's macro_release
            # date fact, and the input to bundle macro classification.
            for print_ in self.cpi_prints.between(start, end):
                headline = print_.metrics["headline_yoy"]
                facts.append(
                    VerifiedFact(
                        key="macro_print",
                        value=print_.fact_value(),
                        source=print_.url,
                        detail=(
                            f"CPI print {print_.reference_period}: headline "
                            f"{headline.actual}% y/y on {print_.release_date}"
                        ),
                    )
                )
            facts.sort(key=lambda fact: (fact.value["date"], fact.key))
        return [], facts
