"""Brokerage position imports and the timestamped holdings snapshot (issue #55).

v1 covers the lowest-risk path: importing a Robinhood positions CSV export
(ticker, shares, average cost) into ``config/positions.yaml``. No credentials,
no unofficial API, no trading — read-only portfolio sync so the dashboard can
render holdings next to the alpha signals.

The snapshot is timestamped on every import; a stale import is visible in the
dashboard instead of silently drifting from the real account.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# A snapshot older than this renders with a "stale" badge in the dashboard.
STALE_AFTER_DAYS = 30

# Header aliases, matched case-insensitively after normalizing separators.
_SYMBOL_COLUMNS = {"symbol", "ticker", "instrument", "stock"}
_SHARES_COLUMNS = {"quantity", "qty", "shares", "share count"}
_AVG_COST_COLUMNS = {
    "average cost",
    "avg cost",
    "cost basis per share",
    "avg price",
    "average price",
}

# Plain equity tickers only. Robinhood exports also list options contracts
# ("AAPL  260919C00150000") and crypto pairs ("DOGEUSD"); those are skipped
# with a reason rather than corrupting the snapshot.
_EQUITY_SYMBOL = re.compile(r"^[A-Z]{1,6}(\.[A-Z])?$")


@dataclass(frozen=True)
class Position:
    symbol: str
    shares: float
    avg_cost: float


@dataclass(frozen=True)
class SkippedRow:
    row: int
    symbol: str
    reason: str


@dataclass(frozen=True)
class ImportResult:
    positions: tuple[Position, ...]
    skipped: tuple[SkippedRow, ...]


@dataclass(frozen=True)
class Snapshot:
    imported_at: datetime
    source: str
    positions: tuple[Position, ...] = field(default=())

    def age_days(self, now: datetime | None = None) -> int:
        now = now or datetime.now(UTC)
        return max(0, (now - self.imported_at.astimezone(UTC)).days)

    @property
    def stale(self) -> bool:
        return self.age_days() > STALE_AFTER_DAYS


def _normalize_header(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip().lower().replace("_", " "))


def _parse_number(raw: str, what: str, row: int) -> float:
    cleaned = raw.strip().replace("$", "").replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError(f"row {row}: {what} {raw!r} is not a number") from None
    if not math.isfinite(value):
        raise ValueError(f"row {row}: {what} {raw!r} is not finite")
    return value


def _find_column(headers: list[str], aliases: set[str]) -> int | None:
    for i, header in enumerate(headers):
        if _normalize_header(header) in aliases:
            return i
    return None


def parse_robinhood_csv(path: str | Path) -> ImportResult:
    """Parse a Robinhood positions CSV export.

    Tolerates header-name variants and skips non-equity rows (options,
    crypto) with a recorded reason. Raises ``ValueError`` when the required
    columns (symbol, shares, average cost) are missing entirely.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: empty CSV, no header row") from None
        sym_col = _find_column(headers, _SYMBOL_COLUMNS)
        qty_col = _find_column(headers, _SHARES_COLUMNS)
        cost_col = _find_column(headers, _AVG_COST_COLUMNS)
        missing = [
            name
            for name, col in (("symbol", sym_col), ("shares", qty_col), ("avg cost", cost_col))
            if col is None
        ]
        if missing:
            raise ValueError(
                f"{path}: missing required column(s): {', '.join(missing)} "
                f"(headers seen: {', '.join(headers)})"
            )
        assert sym_col is not None and qty_col is not None and cost_col is not None

        lots: dict[str, tuple[float, float]] = {}  # symbol -> (shares, cost*qty)
        skipped: list[SkippedRow] = []
        for row_no, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            symbol = row[sym_col].strip().upper() if sym_col < len(row) else ""
            if not symbol:
                skipped.append(SkippedRow(row_no, "", "blank symbol"))
                continue
            if not _EQUITY_SYMBOL.match(symbol):
                skipped.append(
                    SkippedRow(row_no, symbol, "not an equity ticker (options/crypto skipped)")
                )
                continue
            try:
                shares = _parse_number(row[qty_col], "shares", row_no)
                avg_cost = _parse_number(row[cost_col], "avg cost", row_no)
            except (IndexError, ValueError) as exc:
                skipped.append(SkippedRow(row_no, symbol, str(exc)))
                continue
            if shares == 0:
                skipped.append(SkippedRow(row_no, symbol, "zero shares"))
                continue
            if avg_cost < 0:
                skipped.append(SkippedRow(row_no, symbol, f"negative avg cost {avg_cost}"))
                continue
            # Duplicate symbols (multiple lots) merge with a weighted average cost.
            prev_shares, prev_cost = lots.get(symbol, (0.0, 0.0))
            total = prev_shares + shares
            lots[symbol] = (total, prev_cost + avg_cost * shares)

        positions = tuple(
            Position(symbol=symbol, shares=shares, avg_cost=cost / shares if shares else 0.0)
            for symbol, (shares, cost) in sorted(lots.items())
        )
        return ImportResult(positions=positions, skipped=tuple(skipped))


def default_snapshot_path() -> Path:
    from portfolio_analysis.config import PROJECT_ROOT

    return PROJECT_ROOT / "config" / "positions.yaml"


def write_snapshot(
    positions: ImportResult | tuple[Position, ...] | list[Position],
    path: str | Path | None = None,
    *,
    source: str = "robinhood-csv",
    imported_at: datetime | None = None,
) -> Path:
    """Write the timestamped holdings snapshot consumed by the dashboards."""
    if isinstance(positions, ImportResult):
        positions = positions.positions
    target = Path(path) if path is not None else default_snapshot_path()
    stamp = (imported_at or datetime.now().astimezone()).isoformat()
    doc: dict[str, Any] = {
        "snapshot": {"imported_at": stamp, "source": source},
        "positions": [
            {"symbol": p.symbol, "shares": p.shares, "avg_cost": round(p.avg_cost, 4)}
            for p in positions
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return target


def load_snapshot(path: str | Path | None = None) -> Snapshot | None:
    """Load the holdings snapshot, or ``None`` when no import has happened yet.

    A present-but-malformed file raises ``ValueError``: dashboards must not
    silently render corrupt holdings.
    """
    target = Path(path) if path is not None else default_snapshot_path()
    if not target.exists():
        return None
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{target}: invalid YAML ({exc})") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"{target}: expected a mapping at the top level")
    meta = doc.get("snapshot")
    if not isinstance(meta, dict):
        raise ValueError(f"{target}: missing 'snapshot' section with 'imported_at'")
    raw_ts = meta.get("imported_at")
    if not isinstance(raw_ts, str):
        raise ValueError(f"{target}: snapshot.imported_at must be a string")
    try:
        imported_at = datetime.fromisoformat(raw_ts)
    except ValueError:
        raise ValueError(f"{target}: snapshot.imported_at {raw_ts!r} is not ISO-8601") from None
    raw_positions = doc.get("positions", [])
    if not isinstance(raw_positions, list):
        raise ValueError(f"{target}: 'positions' must be a list")
    positions: list[Position] = []
    for i, item in enumerate(raw_positions):
        if not isinstance(item, dict):
            raise ValueError(f"{target}: position #{i} must be a mapping")
        symbol = item.get("symbol")
        shares = item.get("shares")
        avg_cost = item.get("avg_cost")
        if not isinstance(symbol, str) or not _EQUITY_SYMBOL.match(symbol.strip().upper()):
            raise ValueError(f"{target}: position #{i} has an invalid symbol {symbol!r}")
        if not isinstance(shares, (int, float)) or not math.isfinite(shares):
            raise ValueError(f"{target}: position #{i} has invalid shares {shares!r}")
        if not isinstance(avg_cost, (int, float)) or not math.isfinite(avg_cost) or avg_cost < 0:
            raise ValueError(f"{target}: position #{i} has invalid avg_cost {avg_cost!r}")
        positions.append(
            Position(symbol=symbol.strip().upper(), shares=float(shares), avg_cost=float(avg_cost))
        )
    return Snapshot(
        imported_at=imported_at,
        source=str(meta.get("source", "")),
        positions=tuple(positions),
    )
