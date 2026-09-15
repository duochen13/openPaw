"""Self-contained evidence chart. Source headlines are not causal attribution."""

from __future__ import annotations

import html
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from portfolio_analysis.artifacts import MovesArtifact, read_moves
from portfolio_analysis.bundle import SCHEMA_VERSION, bundle_hash, move_payload
from portfolio_analysis.config import Portfolio
from portfolio_analysis.naming import safe_ticker_component
from portfolio_analysis.store import Store


def safe_url(value: object) -> str:
    text = str(value or "").strip()
    try:
        parsed = urlsplit(text)
        return text if parsed.scheme in {"https", "http"} and parsed.netloc else ""
    except ValueError:
        return ""


def _plain(value: object) -> str:
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or "")))


def _facts(bundle: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for fact in bundle["verified"]:
        value = fact.get("value")
        if not isinstance(value, dict):
            continue
        kind = fact["key"]
        if kind == "filing":
            label, day = f"{value['form']} filing", value["filed"]
        elif kind == "earnings_reported":
            label, day = "Quarterly earnings reported", value["reportedDate"]
        elif kind == "macro_release":
            label, day = f"{value['release']} release", value["date"]
        else:
            continue
        rows.append(
            {
                "label": label,
                "date": day,
                "detail": str(fact.get("detail", "")),
                "url": safe_url(value.get("url") or fact.get("source")),
            }
        )
    return sorted(rows, key=lambda row: (row["date"], row["label"]))


def _documents(bundle: dict[str, Any], aliases: tuple[str, ...]) -> list[dict[str, Any]]:
    docs = [
        {
            "id": doc["doc_id"],
            "title": _plain(doc["title"]),
            "summary": _plain(doc.get("summary", "")),
            "url": safe_url(doc["url"]),
            "source": doc["source"],
            "published_at": doc["published_at"],
            "relevance": doc.get("relevance"),
        }
        for doc in bundle["documents"]
    ]
    # Editorial ordering only, never a causal score or support count.
    words = re.compile(
        r"\b(stock|shares|earnings|revenue|profit|capex|guidance|antitrust|lawsuit)\b", re.I
    )
    company = re.compile(
        r"\b(?:" + "|".join(re.escape(a) for a in (bundle["ticker"], *aliases)) + r")\b", re.I
    )
    return sorted(
        docs,
        key=lambda doc: (
            -int(doc["source"] == "alphavantage_news"),
            -int(bool(company.search(doc["title"]))),
            -len(words.findall(doc["title"])),
            -float(doc["relevance"] or 0),
            doc["published_at"],
            doc["id"],
        ),
    )


def chart_data(
    artifact: MovesArtifact,
    asset: dict[str, float],
    benchmark: dict[str, float],
    events_dir: Path,
    *,
    name: str,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    dates = sorted(set(asset) & set(benchmark))
    if artifact.coverage.evaluated:
        lo, hi = artifact.coverage.evaluated
        dates = [day for day in dates if lo <= day <= hi]
    if len(dates) < 2:
        raise ValueError("need at least two price dates to render; run ingest-prices first")
    if any(
        not math.isfinite(series[d]) or series[d] <= 0
        for series in (asset, benchmark)
        for d in dates
    ):
        raise ValueError("chart prices must be finite and positive")
    symbol = safe_ticker_component(artifact.ticker)
    moves = []
    for move in artifact.moves:
        if move.date not in dates:
            raise ValueError(f"move {move.date} is outside the rendered price series")
        row: dict[str, Any] = {
            "date": move.date,
            **move_payload(move),
            "facts": [],
            "documents": [],
            "coverage": None,
            "evidence_status": "missing",
        }
        path = events_dir / symbol / f"{move.date}.json"
        if path.exists():
            try:
                bundle = json.loads(path.read_text())
                if (
                    bundle["schema_version"] != SCHEMA_VERSION
                    or bundle["bundle_sha256"] != bundle_hash(bundle)
                    or bundle["ticker"] != symbol
                    or bundle["date"] != move.date
                ):
                    raise ValueError("invalid evidence bundle")
                if bundle["move"] != move_payload(move):
                    row["evidence_status"] = "stale"
                else:
                    facts, documents = _facts(bundle), _documents(bundle, aliases)
                    row.update(
                        facts=facts,
                        documents=documents,
                        coverage=bundle["coverage"],
                        evidence_status="available",
                    )
            except (ValueError, KeyError, TypeError):
                row["evidence_status"] = "invalid"
        moves.append(row)
    return {
        "ticker": symbol,
        "name": name,
        "benchmark": artifact.benchmark,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dates": dates,
        "prices": [asset[d] for d in dates],
        "benchmark_prices": [benchmark[d] for d in dates],
        "moves": moves,
        "threshold": artifact.params.z_threshold,
        "beta_window": artifact.params.beta_window,
        "sigma_window": artifact.params.sigma_window,
    }


def render_html(data: dict[str, Any]) -> str:
    template = Path(__file__).with_name("templates").joinpath("chart.html").read_text()
    # JSON is inert text. Escape HTML delimiters so hostile article text cannot
    # end the script element, even though the UI only uses textContent.
    payload = json.dumps(data, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c")
    payload = (
        payload.replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )
    rows = "".join(
        f"<tr><td>{html.escape(m['date'])}</td><td>{m['return']:+.2%}</td>"
        f"<td>{m['abnormal_return']:+.2%}</td><td>{m['z']:+.2f}</td></tr>"
        for m in data["moves"]
    )
    return (
        template.replace("__TITLE__", html.escape(f"{data['ticker']} · Price & events"))
        .replace("__FALLBACK_ROWS__", rows)
        .replace("__DATA__", payload)
    )


def render_chart(
    portfolio: Portfolio,
    symbol: str,
    *,
    db: Path,
    moves_dir: Path,
    events_dir: Path,
    out_dir: Path,
) -> Path:
    symbol = safe_ticker_component(symbol)
    artifact = read_moves(moves_dir / f"{symbol}.json")
    if artifact.ticker != symbol or artifact.benchmark != portfolio.benchmark:
        raise ValueError("move artifact does not match configured ticker/benchmark")
    store = Store.open(db)
    try:
        data = chart_data(
            artifact,
            store.adjusted_series(symbol),
            store.adjusted_series(artifact.benchmark),
            events_dir,
            name=portfolio.entry(symbol).name,
            aliases=portfolio.entry(symbol).aliases,
        )
    finally:
        store.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{symbol}.html"
    target.write_text(render_html(data))
    return target
