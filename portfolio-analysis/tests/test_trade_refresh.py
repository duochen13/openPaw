"""Trade-marker auto-refresh from Plaid (follow-up to issue #65).

Covers parsing a `plaid investments-transactions` payload into trades,
merge-safe refresh semantics (fresh Plaid pull replaces only plaid-tagged
trades; CSV/manual trades survive), idempotent re-runs, and legacy files
that only carry a top-level meta.source tag.
"""

from pathlib import Path

from portfolio_analysis.positions import (
    Trade,
    load_trades,
    merge_trades,
    plaid_transactions_to_trades,
    trade_key,
    write_trades,
)

PLAID_BASIC = {
    "body": {
        "investment_transactions": [
            {
                "type": "buy",
                "date": "2026-09-24",
                "quantity": 6,
                "price": 349.93,
                "security_id": "s-googl",
            },
            {
                "type": "sell",
                "date": "2026-09-23",
                "quantity": -1,
                "price": 83.92,
                "security_id": "s-dal",
            },
            {
                "type": "cash",
                "subtype": "dividend",
                "date": "2026-09-20",
                "quantity": 0,
                "price": 0,
                "amount": 10.5,
                "security_id": "s-googl",
            },
            {
                "type": "fee",
                "subtype": "miscellaneous fee",
                "date": "2026-09-19",
                "quantity": 0,
                "price": 0,
                "amount": 5.0,
                "security_id": "s-googl",
            },
            {
                "type": "transfer",
                "date": "2026-09-18",
                "quantity": 100,
                "price": 1.0,
                "security_id": "s-googl",
            },
        ],
        "securities": [
            {"security_id": "s-googl", "ticker_symbol": "googl"},
            {"security_id": "s-dal", "ticker_symbol": "DAL"},
        ],
        "total_investment_transactions": 5,
    }
}

PLAID_MESSY = {
    "investment_transactions": [  # bare body, no envelope
        {
            "type": "buy",
            "date": "2026-09-24",
            "quantity": 2,
            "price": 109.63,
            "security_id": "s-now",
        },
        {
            "type": "buy",
            "date": "not-a-date",
            "quantity": 1,
            "price": 10.0,
            "security_id": "s-now",
        },
        {
            "type": "buy",
            "date": "2026-09-24",
            "quantity": 0,
            "price": 10.0,
            "security_id": "s-now",
        },
        {
            "type": "buy",
            "date": "2026-09-24",
            "quantity": 1,
            "price": None,
            "security_id": "s-now",
        },
        {
            "type": "buy",
            "date": "2026-09-24",
            "quantity": 1,
            "price": 5.0,
            "security_id": "s-unknown",
        },
        {
            "type": "buy",
            "date": "2026-09-24",
            "quantity": 5,
            "price": 2.5,
            "security_id": "s-opt",
        },
    ],
    "securities": [
        {"security_id": "s-now", "ticker_symbol": "NOW"},
        {"security_id": "s-opt", "ticker_symbol": "AAPL  260919C00150000"},
    ],
}


def test_plaid_parse_keeps_only_buys_and_sells() -> None:
    trades = plaid_transactions_to_trades(PLAID_BASIC)
    assert [(t.symbol, t.side, t.qty, t.price) for t in trades] == [
        ("DAL", "sell", 1.0, 83.92),
        ("GOOGL", "buy", 6.0, 349.93),
    ]
    assert all(t.source == "plaid" for t in trades)
    assert [t.date for t in trades] == ["2026-09-23", "2026-09-24"]


def test_plaid_parse_skips_malformed_rows() -> None:
    trades = plaid_transactions_to_trades(PLAID_MESSY)
    assert [(t.symbol, t.side, t.qty, t.price) for t in trades] == [("NOW", "buy", 2.0, 109.63)]


def test_plaid_parse_not_a_dict() -> None:
    assert plaid_transactions_to_trades({}) == []
    assert plaid_transactions_to_trades({"body": None}) == []  # type: ignore[arg-type]


def test_merge_replaces_only_plaid_trades() -> None:
    existing = [
        Trade("GOOGL", "2026-08-12", "buy", 15.0, 350.0, source="plaid"),
        Trade("NOW", "2026-01-05", "buy", 10.0, 90.0, source="manual"),
    ]
    fresh = [Trade("GOOGL", "2026-09-24", "buy", 6.0, 349.93, source="plaid")]
    merged = merge_trades(existing, fresh)
    assert [(t.symbol, t.date, t.source) for t in merged] == [
        ("NOW", "2026-01-05", "manual"),
        ("GOOGL", "2026-09-24", "plaid"),
    ]


def test_merge_legacy_file_without_per_trade_source(tmp_path: Path) -> None:
    # Files written before per-trade provenance carry only meta.source.
    legacy = tmp_path / "trades.yaml"
    legacy.write_text(
        "meta:\n  source: plaid\n"
        "trades:\n"
        "- symbol: GOOGL\n  date: '2026-08-12'\n  side: buy\n  qty: 15\n  price: 350.0\n"
        "- symbol: META\n  date: '2020-03-16'\n  side: buy\n"
        "  qty: 5\n  price: 150.0\n  source: manual\n",
        encoding="utf-8",
    )
    existing = load_trades(legacy)
    assert existing is not None
    fresh = [Trade("GOOGL", "2026-09-24", "buy", 6.0, 349.93, source="plaid")]
    merged = merge_trades(existing, fresh, legacy_source="plaid")
    assert [(t.symbol, t.date) for t in merged] == [
        ("META", "2020-03-16"),
        ("GOOGL", "2026-09-24"),
    ]


def test_merge_keeps_two_identical_plaid_orders() -> None:
    # Regression: two genuinely separate but identical orders (same day,
    # side, symbol, qty, price) in one Plaid pull must both survive. The
    # old set-based dedupe collapsed the second into the first and lost
    # 35 NOW shares.
    fresh = [
        Trade("NOW", "2026-09-01", "buy", 35.0, 142.25, source="plaid"),
        Trade("NOW", "2026-09-01", "buy", 35.0, 142.25, source="plaid"),
    ]
    merged = merge_trades(None, fresh)
    assert len(merged) == 2
    assert sum(t.qty for t in merged) == 70.0
    # Re-running the same pull stays idempotent.
    assert merge_trades(merged, fresh) == merged


def test_merge_skips_only_recorded_manual_occurrences() -> None:
    # One manual entry for an execution suppresses exactly one matching
    # fresh occurrence; a second identical fresh order is still kept.
    existing = [Trade("NOW", "2026-09-01", "buy", 35.0, 142.25, source="manual")]
    fresh = [
        Trade("NOW", "2026-09-01", "buy", 35.0, 142.25, source="plaid"),
        Trade("NOW", "2026-09-01", "buy", 35.0, 142.25, source="plaid"),
    ]
    merged = merge_trades(existing, fresh)
    assert len(merged) == 2  # manual entry + one genuinely separate order
    assert sum(1 for t in merged if t.source == "manual") == 1
    assert sum(1 for t in merged if t.source == "plaid") == 1


def test_refresh_round_trip_preserves_provenance(tmp_path: Path) -> None:
    existing = [
        Trade("NOW", "2026-01-05", "buy", 10.0, 90.0, source="manual"),
        Trade("GOOGL", "2026-08-12", "buy", 15.0, 350.0, source="plaid"),
    ]
    target = write_trades(existing, tmp_path / "trades.yaml", source=None)
    loaded = load_trades(target)
    assert loaded is not None
    merged = merge_trades(loaded, plaid_transactions_to_trades(PLAID_BASIC), legacy_source=None)
    write_trades(merged, target, source=None)
    reloaded = load_trades(target)
    assert reloaded is not None
    by_symbol = {t.symbol: t for t in reloaded}
    assert by_symbol["NOW"].source == "manual"
    assert by_symbol["GOOGL"].source == "plaid"
    assert by_symbol["DAL"].source == "plaid"


def test_merge_price_revision_is_not_a_new_trade() -> None:
    # Plaid revises fill prices by fractions of a cent between pulls.
    existing = [Trade("BAC", "2026-09-24", "sell", 1.0, 56.05, source="plaid")]
    fresh = [Trade("BAC", "2026-09-24", "sell", 1.0, 56.0502, source="plaid")]
    merged = merge_trades(existing, fresh)
    assert len(merged) == 1
    assert merged[0].price == 56.0502  # fresh pull wins, silently
    assert trade_key(merged[0]) in {trade_key(t) for t in existing}
