"""Dated credit-stress snapshots for a stock page (issue #165).

Some numbers decide an issuer's story but have no EDGAR/XBRL source and no
honest live feed: secondary bond yields, CDS spreads, a company-reported
backlog headline. The AI-trade tab solved the same problem for CDS with
dated, sourced snapshot prints (``data/ai_trade/cds_snapshots.csv``); this
module applies that philosophy per ticker. Entries live in
``config/credit_snapshots.yaml``, are hand-vendored, and every entry must
carry its value's as-of date and source - an undated or unsourced number
fails validation loudly instead of rendering as if it were current.

Nothing here fetches anything: the block renders exactly what the file
says, labeled with dates and sources, and a ticker without entries renders
no block at all (the same "no made-up numbers" rule the KPI panels keep).
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import yaml

#: Same project-root resolution as kpis.py (this project does not support
#: a wheel install; paths resolve against the source checkout).
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "credit_snapshots.yaml"

#: Value formats the template knows how to display: "percent" (a fraction,
#: 0.151 -> 15.1%), "currency" (raw USD, formatted $35.6B style), "bp"
#: (a spread in basis points, 1117 -> 1,117 bp).
_FORMATS = ("percent", "currency", "bp")

_REQUIRED = ("key", "label", "value", "format", "as_of", "source")
_KNOWN = frozenset((*_REQUIRED, "note"))


class CreditError(ValueError):
    """credit_snapshots.yaml is malformed or fails validation."""


def load_credit_snapshots(path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Ticker -> ordered snapshot entries from ``credit_snapshots.yaml``.

    Every entry is validated strictly - required fields present, no
    unknown fields, a finite numeric value, a known format, an ISO
    ``as_of`` date, a non-empty source, and no duplicate metric keys per
    ticker. A typo must fail here, in tests and CLI runs, never render
    silently wrong on a stock page.
    """
    source = Path(path) if path else _CONFIG_PATH
    try:
        raw = yaml.safe_load(source.read_text())
    except FileNotFoundError as exc:
        raise CreditError(f"credit snapshot config not found: {source}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("credit_snapshots"), dict):
        raise CreditError(f"{source} must define a top-level 'credit_snapshots' mapping")
    out: dict[str, list[dict[str, Any]]] = {}
    for ticker, entries in raw["credit_snapshots"].items():
        symbol = str(ticker).upper()
        if not isinstance(entries, list) or not entries:
            raise CreditError(f"{source}: {symbol!r} must list at least one snapshot entry")
        seen: set[str] = set()
        cleaned: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise CreditError(f"{source}: {symbol!r} entries must be mappings")
            unknown = set(entry) - _KNOWN
            if unknown:
                raise CreditError(
                    f"{source}: {symbol!r} entry has unknown field(s) {sorted(unknown)}"
                )
            missing = [k for k in _REQUIRED if k not in entry]
            if missing:
                raise CreditError(f"{source}: {symbol!r} entry is missing {missing}")
            key = str(entry["key"])
            if key in seen:
                raise CreditError(f"{source}: {symbol!r} duplicates metric key {key!r}")
            seen.add(key)
            value = entry["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise CreditError(f"{source}: {symbol!r} {key!r} value must be a number")
            if not math.isfinite(value):
                raise CreditError(f"{source}: {symbol!r} {key!r} value must be finite")
            fmt = str(entry["format"])
            if fmt not in _FORMATS:
                raise CreditError(
                    f"{source}: {symbol!r} {key!r} format {fmt!r} not in {list(_FORMATS)}"
                )
            as_of = str(entry["as_of"])
            try:
                date.fromisoformat(as_of)
            except ValueError as exc:
                raise CreditError(
                    f"{source}: {symbol!r} {key!r} as_of {as_of!r} is not an ISO date"
                ) from exc
            label = str(entry["label"]).strip()
            src = str(entry["source"]).strip()
            if not label or not src:
                raise CreditError(
                    f"{source}: {symbol!r} {key!r} needs a non-empty label and source"
                )
            cleaned.append(
                {
                    "key": key,
                    "label": label,
                    "value": float(value),
                    "format": fmt,
                    "as_of": as_of,
                    "source": src,
                    "note": str(entry.get("note", "")).strip(),
                }
            )
        out[symbol] = cleaned
    return out


def credit_block(
    symbol: str, snapshots: dict[str, list[dict[str, Any]]] | None = None
) -> dict[str, Any] | None:
    """Render-ready credit snapshot block for one ticker, or None.

    ``snapshots`` defaults to the shipped config. A ticker with no entries
    gets None - the template hides the section entirely rather than
    showing an empty frame.
    """
    book = load_credit_snapshots() if snapshots is None else snapshots
    entries = book.get(symbol.upper())
    if not entries:
        return None
    return {"entries": entries}
