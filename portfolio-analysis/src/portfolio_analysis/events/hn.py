"""Historical HackerNews search, including every returned page."""

from __future__ import annotations

from urllib.parse import urlencode

from portfolio_analysis.events.base import Document, VerifiedFact, utc_bounds
from portfolio_analysis.events.edgar import GetJson
from portfolio_analysis.http import ProviderError


class HackerNewsSource:
    name = "hackernews"
    coverage_status = "ok"

    def __init__(self, get_json: GetJson, *, query: str, aliases: tuple[str, ...] = ()) -> None:
        self._queries = tuple(dict.fromkeys((query, *aliases)))
        self._get_json, self._query = get_json, query

    def collect(
        self, ticker: str, start: str, end: str
    ) -> tuple[list[Document], list[VerifiedFact]]:
        self.coverage_status = "ok"
        lo, hi = utc_bounds(start, end)
        docs: dict[str, Document] = {}
        for query in self._queries:
            page = 0
            while True:
                url = "https://hn.algolia.com/api/v1/search_by_date?" + urlencode(
                    {
                        "query": query,
                        "tags": "story",
                        "hitsPerPage": 100,
                        "numericFilters": f"created_at_i>={int(lo.timestamp())},"
                        f"created_at_i<{int(hi.timestamp())}",
                        "page": page,
                    }
                )
                payload = self._get_json("hackernews", url, daily_limit=None)
                rows = payload.get("hits")
                if not isinstance(rows, list) or "nbPages" not in payload:
                    raise ProviderError("hackernews: missing hits or page count")
                if payload.get("exhaustiveNbHits") is False:
                    self.coverage_status = "approximate_hit_count"
                for row in rows:
                    identity = str(row["objectID"])
                    doc = Document.make(
                        source=self.name,
                        native_id=identity,
                        published_at=row["created_at"],
                        title=row.get("title") or row.get("story_title") or "Untitled discussion",
                        url=row.get("url") or f"https://news.ycombinator.com/item?id={identity}",
                        summary=row.get("story_text") or row.get("comment_text") or "",
                    )
                    if start <= doc.eastern_date <= end:
                        docs[doc.doc_id] = doc
                page += 1
                if page >= int(payload["nbPages"]):
                    break
                if not rows and self.coverage_status == "approximate_hit_count":
                    break
                if page >= 100 or not rows:
                    raise ProviderError("hackernews: pagination incomplete")
        return sorted(docs.values()), []
