"""Windowed Alpha Vantage articles with relevance for the requested ticker."""

from __future__ import annotations

import hashlib
from urllib.parse import urlencode

from portfolio_analysis.events.base import Document, VerifiedFact, utc_bounds
from portfolio_analysis.events.earnings import optional_number
from portfolio_analysis.events.edgar import GetJson
from portfolio_analysis.http import ProviderError


class NewsSource:
    name = "alphavantage_news"

    def __init__(self, get_json: GetJson, *, api_key: str) -> None:
        self._get_json, self._api_key = get_json, api_key

    def collect(
        self, ticker: str, start: str, end: str
    ) -> tuple[list[Document], list[VerifiedFact]]:
        lo, hi = utc_bounds(start, end)
        url = "https://www.alphavantage.co/query?" + urlencode(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ticker,
                "time_from": lo.strftime("%Y%m%dT%H%M"),
                "time_to": hi.strftime("%Y%m%dT%H%M"),
                "limit": 1000,
                "sort": "EARLIEST",
                "apikey": self._api_key,
            }
        )
        payload = self._get_json("alphavantage", url, daily_limit=25)
        rows = payload.get("feed")
        if not isinstance(rows, list):
            raise ProviderError("news: missing feed")
        if len(rows) >= 1000:
            raise ProviderError("news: result limit reached; window needs subdivision")
        docs: dict[str, Document] = {}
        for row in rows:
            relevance = next(
                (
                    optional_number(item.get("relevance_score"))
                    for item in row.get("ticker_sentiment", [])
                    if item.get("ticker") == ticker
                ),
                None,
            )
            doc = Document.make(
                source=self.name,
                native_id=hashlib.sha256(row["url"].encode()).hexdigest(),
                published_at=row["time_published"],
                title=row["title"],
                url=row["url"],
                summary=row.get("summary") or "",
                relevance=relevance,
            )
            if start <= doc.eastern_date <= end:
                previous = docs.get(doc.doc_id)
                if previous and previous.as_dict() != doc.as_dict():
                    raise ProviderError("news: conflicting articles with the same URL")
                docs[doc.doc_id] = doc
        return sorted(docs.values()), []
