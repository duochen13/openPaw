"""SEC EDGAR filings as verified facts (spec §4.1, §8).

A filing either exists with an accession number or it does not, so EDGAR emits
VerifiedFacts and never Documents.

CRITICAL: `filings.recent` holds only the most recent 1000 filings. Measured on
2026-09-14, META's `recent` begins at 2024-06-11 - two thirds of a five-year
window is absent from it. The older filings live in the archive files listed
under `filings.files[]`, and this adapter merges them. An adapter reading only
`recent` reports "no filing" for most of the window, silently, as an absence
rather than an error.

EDGAR is free and has no daily quota, so it passes daily_limit=None. It does
require a descriptive User-Agent, which http.py sets.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from portfolio_analysis.events.base import Document, VerifiedFact
from portfolio_analysis.http import ProviderError

_INDEX_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
_ARCHIVE_URL = "https://data.sec.gov/submissions/{name}"
_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}/{document}"

#: Forms that can move a price. Deliberately narrow - see the Form 4 test.
_MATERIAL_FORMS = frozenset({"8-K", "8-K/A", "10-Q", "10-Q/A", "10-K", "10-K/A"})

GetJson = Callable[..., dict[str, Any]]


class EdgarSource:
    name = "edgar"

    def __init__(self, get_json: GetJson, *, cik: int | None = None) -> None:
        self._cik = cik
        self._get_json = get_json

    def _pages(self, cik: int) -> list[dict[str, Any]]:
        index = self._get_json("edgar", _INDEX_URL.format(cik=cik), daily_limit=None, max_age=86400)
        pages = [index["filings"]["recent"]]
        for entry in index["filings"].get("files", []):
            pages.append(
                self._get_json(
                    "edgar",
                    _ARCHIVE_URL.format(name=entry["name"]),
                    daily_limit=None,
                    max_age=86400,
                )
            )
        return pages

    def collect(
        self, ticker: str, start: str, end: str, *, cik: int | None = None
    ) -> tuple[list[Document], list[VerifiedFact]]:
        cik = cik if cik is not None else self._cik
        if cik is None or cik <= 0:
            raise ValueError("EDGAR requires a positive CIK")
        facts: list[VerifiedFact] = []
        seen: set[str] = set()
        for page in self._pages(cik):
            columns = [
                page.get(key)
                for key in ("form", "primaryDocument", "filingDate", "accessionNumber")
            ]
            if any(not isinstance(column, list) for column in columns):
                raise ProviderError("edgar: missing filing columns")
            forms: list[str] = page["form"]
            documents = page["primaryDocument"]
            if any(not isinstance(column, list) or len(column) != len(forms) for column in columns):
                raise ProviderError("edgar: filing column lengths differ")
            for i, form in enumerate(forms):
                filed = date.fromisoformat(page["filingDate"][i]).isoformat()
                if not (start <= filed <= end) or form not in _MATERIAL_FORMS:
                    continue
                accession = page["accessionNumber"][i]
                if accession in seen:
                    continue
                seen.add(accession)
                facts.append(
                    VerifiedFact(
                        key="filing",
                        value={
                            "form": form,
                            "filed": filed,
                            "accession": accession,
                            "url": _DOC_URL.format(
                                cik=cik,
                                nodash=accession.replace("-", ""),
                                document=documents[i],
                            ),
                        },
                        source=f"edgar:CIK{cik:010d}",
                        detail=f"{form} {accession} filed {filed}",
                    )
                )
        facts.sort(key=lambda f: (f.value["filed"], f.value["accession"]))
        return [], facts
