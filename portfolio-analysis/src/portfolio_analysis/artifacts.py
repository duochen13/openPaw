"""The data/moves/<TICKER>.json artifact (spec §12).

This file is the contract between `detect-moves` and Plan 2's
`collect-events`. It carries the parameters and the coverage alongside the
moves, because a move list without its threshold is not reproducible, and a
consumer otherwise cannot tell a quiet five years from a five-year window that
was never evaluated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from portfolio_analysis.config import MoveParams
from portfolio_analysis.moves import Coverage, Move
from portfolio_analysis.naming import safe_ticker_component

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MovesArtifact:
    ticker: str
    benchmark: str
    params: MoveParams
    coverage: Coverage
    moves: list[Move]


def _coverage_dict(coverage: Coverage) -> dict[str, object]:
    return {
        "price_series": list(coverage.price_series) if coverage.price_series else None,
        "evaluated": list(coverage.evaluated) if coverage.evaluated else None,
        "evaluated_days": coverage.evaluated_days,
        "flagged_days": coverage.flagged_days,
    }


def write_moves(directory: Path, artifact: MovesArtifact) -> Path:
    symbol = safe_ticker_component(artifact.ticker)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ticker": symbol,
        "benchmark": artifact.benchmark,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "params": {
            "beta_window": artifact.params.beta_window,
            "sigma_window": artifact.params.sigma_window,
            "z_threshold": artifact.params.z_threshold,
        },
        "coverage": _coverage_dict(artifact.coverage),
        "moves": [
            {
                "date": m.date,
                "ret": m.ret,
                "benchmark_return": m.benchmark_return,
                "beta": m.beta,
                "abnormal_return": m.abnormal_return,
                "sigma_60": m.sigma_60,
                "z": m.z,
            }
            for m in artifact.moves
        ],
    }
    path = directory / f"{symbol}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def read_moves(path: Path) -> MovesArtifact:
    raw = json.loads(Path(path).read_text())
    if raw["schema_version"] != SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version {raw['schema_version']}, expected {SCHEMA_VERSION}"
        )
    cov = raw["coverage"]
    ticker, benchmark = raw["ticker"], raw["benchmark"]
    return MovesArtifact(
        ticker=ticker,
        benchmark=benchmark,
        params=MoveParams(
            beta_window=int(raw["params"]["beta_window"]),
            sigma_window=int(raw["params"]["sigma_window"]),
            z_threshold=float(raw["params"]["z_threshold"]),
        ),
        coverage=Coverage(
            price_series=tuple(cov["price_series"]) if cov["price_series"] else None,
            evaluated=tuple(cov["evaluated"]) if cov["evaluated"] else None,
            evaluated_days=int(cov["evaluated_days"]),
            flagged_days=int(cov["flagged_days"]),
        ),
        moves=[
            Move(
                ticker=ticker,
                date=m["date"],
                ret=float(m["ret"]),
                benchmark=benchmark,
                benchmark_return=float(m["benchmark_return"]),
                beta=float(m["beta"]),
                abnormal_return=float(m["abnormal_return"]),
                sigma_60=float(m["sigma_60"]),
                z=float(m["z"]),
            )
            for m in raw["moves"]
        ],
    )
