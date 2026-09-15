"""Checked-in macro release dates with explicit per-series coverage."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from portfolio_analysis.events.base import Document, VerifiedFact


class MacroSource:
    name = "macro"

    def __init__(self, path: Path) -> None:
        raw = path.read_text()
        self.fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        data = yaml.safe_load(raw)
        if data.get("schema_version") != 1:
            raise ValueError("unsupported macro calendar schema")
        self._series: dict[str, Any] = data["series"]
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
        return [], facts
