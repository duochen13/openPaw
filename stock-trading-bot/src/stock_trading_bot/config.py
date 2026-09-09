"""Configuration loading.

The watchlist is config, never hardcoded, so the universe can be swapped
without touching code (spec §3.2).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: The package lives at <root>/src/stock_trading_bot/, so the project root is
#: two levels up. Config paths resolve against this rather than the process
#: cwd, so the CLI writes to the same database regardless of which directory
#: it was invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = PROJECT_ROOT / "config"


def resolve_path(relative: str) -> Path:
    """Resolve a path from run.yaml against the project root."""
    return PROJECT_ROOT / relative


@dataclass(frozen=True)
class WatchlistEntry:
    symbol: str
    cik: int
    name: str
    aliases: tuple[str, ...]
    require_cashtag: bool


@dataclass(frozen=True)
class Watchlist:
    entries: tuple[WatchlistEntry, ...]
    benchmark: str

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(e.symbol for e in self.entries)

    def entry(self, symbol: str) -> WatchlistEntry:
        for e in self.entries:
            if e.symbol == symbol.upper():
                return e
        raise KeyError(f"{symbol!r} is not in the watchlist")

    def resolve(self, text: str) -> str | None:
        """Resolve a ticker, company name, or alias to a symbol.

        Returns None when unknown. Matching is exact after case folding: a
        bare-word argument is unambiguous in a way a scraped comment is not,
        so require_cashtag does not apply here (spec §10.1).
        """
        needle = text.strip().casefold()
        for e in self.entries:
            candidates = (e.symbol, e.name, *e.aliases)
            if any(needle == c.casefold() for c in candidates):
                return e.symbol
        return None


def load_run_config(path: Path | None = None) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((path or _CONFIG_DIR / "run.yaml").read_text())
    return raw


def load_watchlist(path: Path | None = None) -> Watchlist:
    raw = yaml.safe_load((path or _CONFIG_DIR / "watchlist.yaml").read_text())
    entries = tuple(
        WatchlistEntry(
            symbol=t["symbol"],
            cik=int(t["cik"]),
            name=t["name"],
            aliases=tuple(t.get("aliases", ())),
            require_cashtag=bool(t.get("require_cashtag", False)),
        )
        for t in raw["tickers"]
    )
    return Watchlist(entries=entries, benchmark=raw["benchmark"])
