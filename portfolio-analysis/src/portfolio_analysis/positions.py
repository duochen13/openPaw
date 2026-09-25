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

# ---------------------------------------------------------------------------
# Trade history (issue #65): buy/sell markers for the per-stock dashboards.
# ---------------------------------------------------------------------------

# Robinhood order-history CSV exports ("Activity Date", "Instrument",
# "Trans Code", "Quantity", "Price", ...). Header names are matched
# tolerantly, the same convention as the positions import.
_TRADE_DATE_COLUMNS = {
    "activity date",
    "date",
    "trade date",
    "execution date",
    "executed on",
}
_SIDE_COLUMNS = {"trans code", "transaction code", "side", "action", "type"}
_FILL_PRICE_COLUMNS = {
    "price",
    "fill price",
    "execution price",
    "avg fill price",
    "fill",
}

_BUY_CODES = {"buy", "bought", "purchase", "purchased"}
_SELL_CODES = {"sell", "sold"}


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


# ---------------------------------------------------------------------------
# Trade history (issue #65)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trade:
    symbol: str
    date: str  # ISO YYYY-MM-DD
    side: str  # "buy" | "sell"
    qty: float
    price: float
    source: str | None = None  # provenance tag: "plaid" | "robinhood-csv" | "manual"


@dataclass(frozen=True)
class TradeImportResult:
    trades: tuple[Trade, ...]
    skipped: tuple[SkippedRow, ...]
    filtered_out: int = 0


def _read_headers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            raise ValueError(f"{path}: empty CSV, no header row") from None


def detect_robinhood_csv_kind(path: str | Path) -> str:
    """Classify a Robinhood CSV export as ``"orders"`` or ``"positions"``.

    An export with a side column (Trans Code / Side) plus a date column is
    order history; one with an average-cost column is a positions snapshot.
    Raises ``ValueError`` when the headers match neither flavor.
    """
    headers = _read_headers(Path(path))
    has_side = _find_column(headers, _SIDE_COLUMNS) is not None
    has_date = _find_column(headers, _TRADE_DATE_COLUMNS) is not None
    has_cost = _find_column(headers, _AVG_COST_COLUMNS) is not None
    if has_side and has_date:
        return "orders"
    if has_cost:
        return "positions"
    raise ValueError(
        f"{path}: cannot tell positions from order history (headers seen: {', '.join(headers)})"
    )


def _normalize_side(raw: str, row: int) -> str | None:
    """Map a Trans Code to "buy"/"sell"; None for non-trade activity.

    Dividends, fees, interest, transfers, and deposits are skipped with a
    recorded reason instead of failing the import.
    """
    code = raw.strip().lower()
    if code in _BUY_CODES:
        return "buy"
    if code in _SELL_CODES:
        return "sell"
    return None


_TRADE_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d")


def _parse_trade_date(raw: str, row: int) -> str:
    text = raw.strip()
    for fmt in _TRADE_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        raise ValueError(f"row {row}: trade date {raw!r} is not a recognized date") from None


def parse_robinhood_orders_csv(
    path: str | Path,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> TradeImportResult:
    """Parse a Robinhood order-history CSV export into buy/sell trades.

    Only buy/sell executions become trades; dividends, fees, interest, and
    transfers are skipped with a reason. ``start_date``/``end_date``
    (``YYYY-MM-DD``, inclusive) filter the trades after parsing.
    """
    for label, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"{label} {value!r} is not YYYY-MM-DD") from None
    if start_date and end_date and start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")

    path = Path(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError(f"{path}: empty CSV, no header row") from None
        date_col = _find_column(headers, _TRADE_DATE_COLUMNS)
        sym_col = _find_column(headers, _SYMBOL_COLUMNS | {"instrument"})
        side_col = _find_column(headers, _SIDE_COLUMNS)
        qty_col = _find_column(headers, _SHARES_COLUMNS)
        price_col = _find_column(headers, _FILL_PRICE_COLUMNS)
        missing = [
            name
            for name, col in (
                ("trade date", date_col),
                ("symbol", sym_col),
                ("side", side_col),
                ("quantity", qty_col),
                ("price", price_col),
            )
            if col is None
        ]
        if missing:
            raise ValueError(
                f"{path}: missing required column(s): {', '.join(missing)} "
                f"(headers seen: {', '.join(headers)})"
            )
        assert (
            date_col is not None
            and sym_col is not None
            and side_col is not None
            and qty_col is not None
            and price_col is not None
        )

        trades: list[Trade] = []
        skipped: list[SkippedRow] = []
        filtered_out = 0
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
            raw_side = row[side_col] if side_col < len(row) else ""
            side = _normalize_side(raw_side, row_no)
            if side is None:
                skipped.append(
                    SkippedRow(row_no, symbol, f"non-trade activity {raw_side.strip()!r} skipped")
                )
                continue
            try:
                date = _parse_trade_date(row[date_col], row_no)
                qty = _parse_number(row[qty_col], "quantity", row_no)
                price = _parse_number(row[price_col], "price", row_no)
            except (IndexError, ValueError) as exc:
                skipped.append(SkippedRow(row_no, symbol, str(exc)))
                continue
            if qty <= 0:
                skipped.append(SkippedRow(row_no, symbol, f"non-positive quantity {qty}"))
                continue
            if price < 0:
                skipped.append(SkippedRow(row_no, symbol, f"negative price {price}"))
                continue
            if (start_date and date < start_date) or (end_date and date > end_date):
                filtered_out += 1
                continue
            trades.append(Trade(symbol=symbol, date=date, side=side, qty=qty, price=price))

    trades.sort(key=lambda t: (t.date, t.symbol, t.side))
    return TradeImportResult(
        trades=tuple(trades), skipped=tuple(skipped), filtered_out=filtered_out
    )


def default_trades_path() -> Path:
    from portfolio_analysis.config import PROJECT_ROOT

    return PROJECT_ROOT / "config" / "trades.yaml"


def write_trades(
    trades: TradeImportResult | tuple[Trade, ...] | list[Trade],
    path: str | Path | None = None,
    *,
    source: str | None = "robinhood-csv",
) -> Path:
    """Write the trade history consumed by the per-stock dashboards (#65).

    Every trade is stamped with a provenance tag (its own ``source`` when
    set, else the ``source`` argument) so a later refresh from another
    origin can replace just its own trades instead of clobbering the file.
    """
    if isinstance(trades, TradeImportResult):
        trades = trades.trades
    target = Path(path) if path is not None else default_trades_path()
    entries = []
    for t in trades:
        entry: dict[str, Any] = {
            "symbol": t.symbol,
            "date": t.date,
            "side": t.side,
            "qty": t.qty,
            "price": round(t.price, 4),
        }
        tag = t.source or source
        if tag:
            entry["source"] = tag
        entries.append(entry)
    tags = sorted({tag for t in trades if (tag := t.source or source)})
    doc: dict[str, Any] = {
        "meta": {"source": source or ", ".join(tags) or None},
        "trades": entries,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return target


def load_trades(path: str | Path | None = None) -> list[Trade] | None:
    """Load the trade history, or ``None`` when no order import has happened.

    A present-but-malformed file raises ``ValueError``: dashboards must not
    silently render corrupt trade markers.
    """
    target = Path(path) if path is not None else default_trades_path()
    if not target.exists():
        return None
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{target}: invalid YAML ({exc})") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"{target}: expected a mapping at the top level")
    raw_trades = doc.get("trades", [])
    if not isinstance(raw_trades, list):
        raise ValueError(f"{target}: 'trades' must be a list")
    meta = doc.get("meta", {})
    legacy_source = meta.get("source") if isinstance(meta, dict) else None
    if legacy_source is not None and not isinstance(legacy_source, str):
        raise ValueError(f"{target}: meta.source must be a string")
    trades: list[Trade] = []
    for i, item in enumerate(raw_trades):
        if not isinstance(item, dict):
            raise ValueError(f"{target}: trade #{i} must be a mapping")
        symbol = item.get("symbol")
        date = item.get("date")
        side = item.get("side")
        qty = item.get("qty")
        price = item.get("price")
        source = item.get("source", legacy_source)
        if not isinstance(symbol, str) or not _EQUITY_SYMBOL.match(symbol.strip().upper()):
            raise ValueError(f"{target}: trade #{i} has an invalid symbol {symbol!r}")
        if not isinstance(date, str):
            raise ValueError(f"{target}: trade #{i} has an invalid date {date!r}")
        try:
            date = _parse_trade_date(date, i)
        except ValueError:
            raise ValueError(f"{target}: trade #{i} has an invalid date {date!r}") from None
        if side not in ("buy", "sell"):
            raise ValueError(f"{target}: trade #{i} has an invalid side {side!r}")
        if not isinstance(qty, (int, float)) or not math.isfinite(qty) or qty <= 0:
            raise ValueError(f"{target}: trade #{i} has invalid qty {qty!r}")
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
            raise ValueError(f"{target}: trade #{i} has invalid price {price!r}")
        if source is not None and not isinstance(source, str):
            raise ValueError(f"{target}: trade #{i} has invalid source {source!r}")
        trades.append(
            Trade(
                symbol=symbol.strip().upper(),
                date=date,
                side=side,
                qty=float(qty),
                price=float(price),
                source=source,
            )
        )
    trades.sort(key=lambda t: (t.date, t.symbol, t.side))
    return trades


def read_trades_meta(path: str | Path | None = None) -> dict[str, Any]:
    """Return the ``meta`` mapping of a trades file ({} when absent)."""
    target = Path(path) if path is not None else default_trades_path()
    if not target.exists():
        return {}
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{target}: invalid YAML ({exc})") from exc
    if not isinstance(doc, dict):
        return {}
    meta = doc.get("meta", {})
    return meta if isinstance(meta, dict) else {}


def trades_for_symbol(trades: list[Trade] | None, symbol: str) -> list[Trade]:
    """This ticker's trades only — dashboards never show another stock's."""
    if not trades:
        return []
    want = symbol.strip().upper()
    return [t for t in trades if t.symbol == want]


PLAID_TRADE_SOURCE = "plaid"


def plaid_transactions_to_trades(payload: Any) -> list[Trade]:
    """Convert a ``plaid investments-transactions`` JSON payload to trades.

    Accepts either the raw CLI envelope (``{"body": {...}}``) or the body
    itself. Only buy/sell investment transactions become trades; cash
    activity (dividends, interest, fees, transfers) is skipped. Malformed
    rows are skipped rather than failing the whole refresh.
    """
    if not isinstance(payload, dict):
        return []
    body = payload.get("body", payload)
    if not isinstance(body, dict):
        return []
    raw_txs = body.get("investment_transactions", []) or []
    raw_secs = body.get("securities", []) or []
    tickers: dict[Any, str] = {}
    for sec in raw_secs:
        if not isinstance(sec, dict):
            continue
        ticker = (sec.get("ticker_symbol") or "").strip().upper()
        if ticker and _EQUITY_SYMBOL.match(ticker):
            tickers[sec.get("security_id")] = ticker
    trades: list[Trade] = []
    for n, tx in enumerate(raw_txs):
        if not isinstance(tx, dict):
            continue
        if tx.get("type") not in ("buy", "sell"):
            continue
        symbol = tickers.get(tx.get("security_id"))
        if not symbol:
            continue
        raw_qty = tx.get("quantity")
        raw_price = tx.get("price")
        if raw_qty is None or raw_price is None:
            continue
        try:
            qty = abs(float(raw_qty))
            price = float(raw_price)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(qty) or qty <= 0:
            continue
        if not math.isfinite(price) or price < 0:
            continue
        raw_date = tx.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            date = _parse_trade_date(raw_date, n)
        except ValueError:
            continue
        trades.append(
            Trade(
                symbol=symbol,
                date=date,
                side=tx["type"],
                qty=qty,
                price=price,
                source=PLAID_TRADE_SOURCE,
            )
        )
    trades.sort(key=lambda t: (t.date, t.symbol, t.side))
    return trades


def trade_key(t: Trade) -> tuple[str, str, str, float, float]:
    """Identity of a trade for merge/dedupe.

    Price is rounded to the cent: Plaid revises fill prices by fractions
    of a cent between pulls (56.05 -> 56.0502), and that revision noise
    must not read as a new trade.
    """
    return (t.date, t.side, t.symbol, t.qty, round(t.price, 2))


def merge_trades(
    existing: list[Trade] | None,
    fresh: list[Trade],
    *,
    fresh_source: str = PLAID_TRADE_SOURCE,
    legacy_source: str | None = None,
) -> list[Trade]:
    """Merge freshly pulled trades into the stored history.

    Existing trades whose effective provenance (their own ``source`` tag,
    else ``legacy_source`` from the file's ``meta`` block) matches
    ``fresh_source`` are replaced by the fresh pull; trades from any other
    origin (CSV import, manual entries) are kept. Exact duplicates are
    collapsed, so re-running a refresh is idempotent.
    """
    kept: list[Trade] = []
    for t in existing or []:
        if (t.source or legacy_source) == fresh_source:
            continue
        kept.append(t)
    seen = {trade_key(t) for t in kept}
    merged = list(kept)
    for t in fresh:
        key = trade_key(t)
        if key in seen:
            continue
        seen.add(key)
        merged.append(t)
    merged.sort(key=lambda t: (t.date, t.symbol, t.side))
    return merged
