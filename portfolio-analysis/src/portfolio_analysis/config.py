"""Configuration loading.

The universe is config, never hardcoded, so it can be widened without touching
code (spec §3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from portfolio_analysis.naming import safe_ticker_component

#: The package lives at <root>/src/portfolio_analysis/, so the project root is
#: two levels up. Paths resolve against this rather than the process cwd, so
#: the CLI writes to the same database regardless of which directory it was
#: invoked from.
#:
#: This assumes a source checkout or an editable install. Under a real wheel
#: install parents[2] lands in site-packages; load_portfolio checks for that and
#: says so, rather than silently creating data directories inside the venv. A
#: wheel is not a supported distribution mode here anyway - the hatch wheel
#: target ships src/portfolio_analysis and not config/.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_DIR = PROJECT_ROOT / "config"

#: The smallest window that has a variance at all.
_MIN_WINDOW = 2


def resolve_path(relative: str) -> Path:
    """Resolve a configured relative path against the project root.

    An absolute value is returned unchanged, per pathlib's `/` semantics. Config
    is author-controlled, so that is a convenience rather than a hole.
    """
    return PROJECT_ROOT / relative


@dataclass(frozen=True)
class MoveParams:
    """Parameters of the move-detection rule (spec §5)."""

    beta_window: int
    sigma_window: int
    z_threshold: float

    def __post_init__(self) -> None:
        if self.beta_window < _MIN_WINDOW or self.sigma_window < _MIN_WINDOW:
            raise ValueError(
                f"windows need at least {_MIN_WINDOW} observations, got "
                f"beta_window={self.beta_window}, sigma_window={self.sigma_window}"
            )
        if self.sigma_window >= self.beta_window:
            raise ValueError(
                "sigma_window must be smaller than beta_window: sigma is derived "
                f"inside the beta window, got {self.sigma_window} >= {self.beta_window}"
            )
        # NaN is the dangerous case here, not a negative. Every `abs(z) >= nan`
        # comparison is False, so a NaN threshold does not raise - it reports
        # zero large moves, which is indistinguishable from a quiet market.
        if not math.isfinite(self.z_threshold) or self.z_threshold <= 0:
            raise ValueError(
                f"z_threshold must be finite and positive, got {self.z_threshold}"
            )


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
    # Defaulted so older constructions (and configs without the key) keep
    # working: unmapped means the two-line chart, not an error.
    industry_benchmarks: dict[str, str] = field(default_factory=dict)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(e.symbol for e in self.entries)

    def industry_benchmark(self, symbol: str) -> str | None:
        """The industry benchmark ticker for a symbol, or None when unmapped.

        Unmapped symbols render the two-line chart exactly as before.
        """
        return self.industry_benchmarks.get(symbol.upper())

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
        if key not in self.paths:
            raise KeyError(
                f"{key!r} is not a configured path; known: {sorted(self.paths)}"
            )
        return resolve_path(self.paths[key])


def load_portfolio(path: Path | None = None) -> Portfolio:
    if path is None and not (PROJECT_ROOT / "pyproject.toml").is_file():
        raise RuntimeError(
            f"expected the project root at {PROJECT_ROOT}, but there is no "
            "pyproject.toml there. This tool resolves config and data paths "
            "against the source checkout and does not support a wheel install."
        )
    source = path or _CONFIG_DIR / "portfolio.yaml"
    raw: dict[str, Any] = yaml.safe_load(source.read_text())
    entries = tuple(
        PortfolioEntry(
            # Sanitized at the boundary so naming.py's promise - every ticker
            # crossing an I/O boundary passes through here first - holds by
            # construction rather than by convention. entry() compares against
            # symbol.upper() and silently depends on it.
            symbol=safe_ticker_component(t["symbol"]),
            cik=int(t["cik"]),
            name=t["name"],
            aliases=tuple(t.get("aliases", ())),
        )
        for t in raw["tickers"]
    )
    moves = raw["moves"]
    return Portfolio(
        entries=entries,
        benchmark=safe_ticker_component(raw["benchmark"]),
        # Keys and values are sanitized like every other ticker crossing an
        # I/O boundary. Absent entirely in old configs: unmapped means the
        # two-line chart, not an error.
        industry_benchmarks={
            safe_ticker_component(str(symbol)): safe_ticker_component(str(ticker))
            for symbol, ticker in (raw.get("industry_benchmarks") or {}).items()
        },
        price_years=int(raw["price_years"]),
        move_params=MoveParams(
            beta_window=int(moves["beta_window"]),
            sigma_window=int(moves["sigma_window"]),
            z_threshold=float(moves["z_threshold"]),
        ),
        # Parsed, then re-emitted in canonical ISO form. Parsing makes an
        # unreadable date fail here instead of in Plan 2 wherever it is first
        # compared; keeping the field a str means it compares directly against
        # the ISO dates the store guarantees.
        news_coverage_start=date.fromisoformat(
            str(raw["news_coverage_start"])
        ).isoformat(),
        paths=dict(raw["paths"]),
    )
