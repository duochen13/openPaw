"""Unit tests for credit.py - the dated credit snapshot block (issue #165).

Network-free: loader tests run against hand-written tmp_path YAML, and the
shipped-config tests only read the real config file (the same exception
the shipped-config tests in test_config.py / test_kpis.py make).
"""

from pathlib import Path

import pytest
import yaml

from portfolio_analysis import credit, render

pytestmark = pytest.mark.unit

_ENTRY = {
    "key": "cds_5y",
    "label": "5Y CDS spread",
    "value": 1117,
    "format": "bp",
    "as_of": "2026-10-14",
    "source": "data/ai_trade/cds_snapshots.csv (press reports)",
}


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "credit_snapshots.yaml"
    path.write_text(yaml.safe_dump(payload))
    return path


def test_loader_parses_a_valid_file(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"crwv": [dict(_ENTRY, note="range note")]}})
    book = credit.load_credit_snapshots(path)
    assert list(book) == ["CRWV"]  # tickers are normalized to upper case
    (entry,) = book["CRWV"]
    assert entry["value"] == 1117.0
    assert entry["format"] == "bp"
    assert entry["as_of"] == "2026-10-14"
    assert entry["note"] == "range note"


def test_loader_defaults_note_to_empty(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [_ENTRY]}})
    (entry,) = credit.load_credit_snapshots(path)["CRWV"]
    assert entry["note"] == ""


@pytest.mark.parametrize("missing", ["source", "as_of", "value", "format", "label", "key"])
def test_loader_requires_every_dated_field(tmp_path, missing):
    entry = {k: v for k, v in _ENTRY.items() if k != missing}
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [entry]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_unknown_field(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [dict(_ENTRY, live=True)]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_unknown_format(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [dict(_ENTRY, format="multiple")]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_non_iso_as_of(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [dict(_ENTRY, as_of="Oct 2026")]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_non_numeric_value(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [dict(_ENTRY, value="~1,100")]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_duplicate_keys(tmp_path):
    path = _write(tmp_path, {"credit_snapshots": {"CRWV": [_ENTRY, _ENTRY]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_loader_rejects_missing_top_level(tmp_path):
    path = _write(tmp_path, {"snapshots": {"CRWV": [_ENTRY]}})
    with pytest.raises(credit.CreditError):
        credit.load_credit_snapshots(path)


def test_credit_block_none_for_unlisted_ticker():
    assert credit.credit_block("META", {"CRWV": [dict(_ENTRY)]}) is None


def test_credit_block_returns_entries_case_insensitively():
    block = credit.credit_block("crwv", {"CRWV": [dict(_ENTRY)]})
    assert block is not None
    assert [e["key"] for e in block["entries"]] == ["cds_5y"]


def test_shipped_config_has_dated_sourced_crwv_entries():
    book = credit.load_credit_snapshots()
    entries = book["CRWV"]
    keys = {e["key"] for e in entries}
    # The issue-#165 acceptance set: market prints + filing anchors.
    assert {
        "notes_2032_yield",
        "cds_5y",
        "gross_margin",
        "net_margin",
        "interest_expense",
        "revenue_backlog",
        "total_debt",
    } <= keys
    by_key = {e["key"]: e for e in entries}
    # Vendored anchors cross-checked against EDGAR (CIK 1769628) and the
    # repo's own CDS snapshot file - a typo here should fail loudly.
    assert by_key["total_debt"]["value"] == 35_550_000_000
    assert by_key["revenue_backlog"]["value"] == 104_200_000_000
    assert by_key["gross_margin"]["value"] == pytest.approx(0.659)
    assert by_key["net_margin"]["value"] == pytest.approx(-0.243)
    assert by_key["cds_5y"]["value"] == 1117
    assert by_key["cds_5y"]["as_of"] == "2026-10-14"


def test_render_credit_data_only_for_snapshot_tickers():
    assert render._credit_data("CRWV") is not None
    assert render._credit_data("META") is None
