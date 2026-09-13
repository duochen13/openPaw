# src/portfolio_analysis/config.py
"""Configuration loading.

The universe is config, never hardcoded, so it can be widened without touching
code (spec §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: The package lives at <root>/src/portfolio_analysis/, so the project root is
#: two levels up. Paths resolve against this rather than the process cwd, so
#: the CLI writes to the same database regardless of which directory it was
#: invoked from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = PROJECT_ROOT / "config"


def resolve_path(relative: str) -> Path:
    """Resolve a configured relative path against the project root."""
    return PROJECT_ROOT / relative


@dataclass(frozen=True)
class MoveParams:
    """Parameters of the move-detection rule (spec §5)."""

    beta_window: int
    sigma_window: int
    z_threshold: float

    def __post_init__(self) -> None:
        if self.sigma_window >= self.beta_window:
            raise ValueError(
                "sigma_window must be smaller than beta_window: sigma is derived "
                f"inside the beta window, got {self.sigma_window} >= {self.beta_window}"
            )
        if self.z_threshold <= 0:
            raise ValueError(f"z_threshold must be positive, got {self.z_threshold}")


@dataclass(frozen=True)
class PortfolioEntry:
    symbol: str
    cik: int
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class Portfolio:
    entries: tuple[PortfolioEntry, ...]
    benchmark: str
    price_years: int
    move_params: MoveParams
    news_coverage_start: str
    paths: dict[str, str]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(e.symbol for e in self.entries)

    def entry(self, symbol: str) -> PortfolioEntry:
        for e in self.entries:
            if e.symbol == symbol.upper():
                return e
        raise KeyError(f"{symbol!r} is not in the portfolio")

    def resolve(self, text: str) -> str | None:
        """Resolve a ticker, company name, or alias to a symbol.

        Returns None when unknown. Matching is exact after case folding.
        """
        needle = text.strip().casefold()
        for e in self.entries:
            if any(needle == c.casefold() for c in (e.symbol, e.name, *e.aliases)):
                return e.symbol
        return None

    def path(self, key: str) -> Path:
        return resolve_path(self.paths[key])


def load_portfolio(path: Path | None = None) -> Portfolio:
    raw: dict[str, Any] = yaml.safe_load(
        (path or _CONFIG_DIR / "portfolio.yaml").read_text()
    )
    entries = tuple(
        PortfolioEntry(
            symbol=t["symbol"],
            cik=int(t["cik"]),
            name=t["name"],
            aliases=tuple(t.get("aliases", ())),
        )
        for t in raw["tickers"]
    )
    moves = raw["moves"]
    return Portfolio(
        entries=entries,
        benchmark=raw["benchmark"],
        price_years=int(raw["price_years"]),
        move_params=MoveParams(
            beta_window=int(moves["beta_window"]),
            sigma_window=int(moves["sigma_window"]),
            z_threshold=float(moves["z_threshold"]),
        ),
        news_coverage_start=str(raw["news_coverage_start"]),
        paths=dict(raw["paths"]),
    )
