"""Dated earnings and vendor-stored EPS; consensus vintage is unknown."""

from __future__ import annotations

import math
from datetime import date
from urllib.parse import urlencode

from portfolio_analysis.events.base import Document, VerifiedFact
from portfolio_analysis.events.edgar import GetJson
from portfolio_analysis.http import ProviderError


def optional_number(value: object) -> float | None:
    if value is None or str(value) in {"None", "", "null"}:
        return None
    number = float(str(value))
    if not math.isfinite(number):
        raise ValueError("non-finite earnings or relevance value")
    return number


class EarningsSource:
    name = "earnings"

    def __init__(self, get_json: GetJson, *, api_key: str) -> None:
        self._get_json, self._api_key = get_json, api_key

    def collect(
        self, ticker: str, start: str, end: str
    ) -> tuple[list[Document], list[VerifiedFact]]:
        url = "https://www.alphavantage.co/query?" + urlencode(
            {
                "function": "EARNINGS",
                "symbol": ticker,
                "apikey": self._api_key,
            }
        )
        payload = self._get_json("alphavantage", url, daily_limit=25, max_age=86400)
        rows = payload.get("quarterlyEarnings")
        if not isinstance(rows, list):
            raise ProviderError("earnings: missing quarterlyEarnings")
        facts = []
        for row in rows:
            reported = row.get("reportedDate")
            if reported in (None, "None", ""):
                continue
            reported = date.fromisoformat(reported).isoformat()
            if not start <= reported <= end:
                continue
            values = {
                key: optional_number(row.get(key))
                for key in (
                    "reportedEPS",
                    "estimatedEPS",
                    "surprise",
                    "surprisePercentage",
                )
            }
            facts.append(
                VerifiedFact(
                    key="earnings_reported",
                    value={
                        "reportedDate": reported,
                        "fiscalDateEnding": row["fiscalDateEnding"],
                        "reportTime": row.get("reportTime"),
                        **values,
                    },
                    source="alphavantage:EARNINGS",
                    detail=f"reportedDate {reported}; consensus vintage unknown; "
                    "vendor-stored EPS surprise does not establish the cause or sign of a move",
                )
            )
        facts.sort(key=lambda fact: str(fact.value["reportedDate"]))
        return [], facts
