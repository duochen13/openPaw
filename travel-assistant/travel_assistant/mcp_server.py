"""MCP server wrapper around the local travel_assistant research pipeline.

Thin layer only: the two tools call into the importable package
(research.py / store.py) directly. No network service, no API keys, no auth.

Start over stdio:

    cd travel-assistant && python -m travel_assistant.mcp_server

Data locations follow the package defaults (data/ under travel-assistant/),
honouring the TA_DATA_ROOT and TA_RUNS_DB env overrides, so a client can
point the server at its own data tree in the mcpServers config.
"""
import contextlib
import json
import sys

from mcp.server.fastmcp import FastMCP

from .research import research
from . import store as store_mod

mcp = FastMCP("travel-assistant")

_LIVE_COLLECT_NOTE = (
    "A live collect (no from_raw/from_analysis) drives a headless browser "
    "against rednote and takes several minutes; this tool runs synchronously. "
    "For a fast offline run, replay a saved analysis with from_analysis + "
    "skip_geocode."
)


def _place_out(p):
    """Public shape of one place for tool output."""
    return {
        "name": p.get("name"),
        "category": p.get("category") or p.get("type"),
        "area": p.get("area"),
        "lat": p.get("lat"),
        "lng": p.get("lng"),
        "why_loved": p.get("why_loved"),
        "source_urls": p.get("source_urls") or [],
        "price_hint": p.get("price_hint"),
        "mention_count": p.get("mention_count"),
        "sentiment": p.get("sentiment"),
        "rating": p.get("rating"),
        "tags": p.get("tags") or [],
    }


def _map_bundle(rec):
    """Map artifact paths ('map bundle') from a run record."""
    art = rec.get("artifacts") or {}
    return {
        "kml_path": art.get("kml_path") or rec.get("kml_path"),
        "map_html_path": art.get("map_html_path") or rec.get("map_html_path"),
        "csv_path": art.get("csv_path") or rec.get("csv_path"),
        "n_pins": art.get("n_pins"),
    }


def _run_out(rec, *, include_places=True):
    out = {
        "run_id": rec.get("id"),
        "run_uuid": rec.get("run_uuid"),
        "status": rec.get("status"),
        "destination": rec.get("destination"),
        "vibe": rec.get("vibe"),
        "n_places": rec.get("n_places"),
        "n_geocoded": rec.get("n_geocoded"),
        "n_missing_coords": rec.get("n_missing_coords"),
        "error": rec.get("error"),
        "started_at": rec.get("started_at"),
        "ended_at": rec.get("ended_at"),
        "duration_s": rec.get("duration_s"),
        "analysis_path": rec.get("analysis_path"),
        "map_bundle": _map_bundle(rec),
    }
    if include_places:
        out["places"] = [_place_out(p) for p in rec.get("places") or []]
    return out


@mcp.tool()
def research_destination(
    destination: str = "",
    vibe: str = "all",
    queries: list[str] | None = None,
    from_analysis: str | None = None,
    from_raw: str | None = None,
    skip_geocode: bool = False,
    region: str = "",
    n_per_query: int = 6,
) -> dict:
    """Run destination research against the local pipeline.

    A live collect (queries + headless browser) takes several minutes and this
    tool runs synchronously. For a fast offline run, replay a saved analysis:
    pass from_analysis (path to a data/analysis/*_places_*.json file) with
    skip_geocode=true.

    Returns run_id, status, structured places, and map bundle paths.
    """
    try:
        # The pipeline prints progress to stdout (e.g. the map builder's
        # API-key note); over MCP stdio that would corrupt the JSON-RPC
        # stream, so route it to stderr instead.
        with contextlib.redirect_stdout(sys.stderr):
            rec = research(
                destination=destination or None,
                vibe=vibe,
                queries=queries,
                from_analysis=from_analysis,
                from_raw=from_raw,
                skip_geocode=skip_geocode,
                region=region,
                n_per_query=n_per_query,
            )
    except Exception as e:  # run is already marked failed in the store
        return {"status": "failed", "error": str(e),
                "note": _LIVE_COLLECT_NOTE if not (from_analysis or from_raw)
                else None}
    out = _run_out(rec, include_places=True)
    if not (from_analysis or from_raw):
        out["note"] = _LIVE_COLLECT_NOTE
    return out


@mcp.tool()
def get_research_result(run_id: int, include_places: bool = True) -> dict:
    """Fetch a research run from the local SQLite run store by run_id.

    Use this to poll a run or to re-fetch results without re-running.
    Set include_places=false for a light metadata-only response.
    """
    store = store_mod.RunStore()
    try:
        rec = store.get_run(run_id)
    finally:
        store.close()
    if rec is None:
        return {"status": "not_found",
                "error": f"no run with run_id={run_id}"}
    return _run_out(rec, include_places=include_places)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
