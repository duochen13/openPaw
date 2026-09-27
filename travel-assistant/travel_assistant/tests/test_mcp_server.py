"""End-to-end tests for the MCP server wrapper (issue #77).

Drives BOTH tools through the real MCP SDK stdio client against a server
subprocess, fully offline:

  TA_DATA_ROOT=<tmpdir>  — fresh data tree (analysis, maps, runs)
  TA_OFFLINE=1           — forbids any network geocoding
  from_analysis=<committed Vancouver fixture> + skip_geocode=True

Asserts:
  - list_tools exposes research_destination + get_research_result
  - research_destination returns run_id/status + structured places +
    a real map bundle path (kml/html/csv files exist on disk)
  - get_research_result(run_id) round-trips the same run
"""
import asyncio
import json
import os
import tempfile
from datetime import timedelta
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJ = Path(__file__).resolve().parents[2]  # travel-assistant/
FIXTURE = PROJ / "data" / "analysis" / "vancouver_places_20260709_030913.json"

TOOL_TIMEOUT = timedelta(seconds=180)


def _server_params(tmpdir):
    env = dict(os.environ)
    env["TA_DATA_ROOT"] = tmpdir
    env["TA_OFFLINE"] = "1"
    return StdioServerParameters(
        command="python3",
        args=["-m", "travel_assistant.mcp_server"],
        cwd=str(PROJ),
        env=env,
    )


def _tool_json(result):
    """Extract the JSON payload from a CallToolResult's content blocks."""
    text = "".join(
        b.text for b in result.content if b.type == "text")
    return json.loads(text)


async def _run_flow():
    tmpdir = tempfile.mkdtemp(prefix="ta_mcp_e2e_")
    async with stdio_client(_server_params(tmpdir)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert names == {"research_destination", "get_research_result"}, \
                names

            # -- tool 1: research_destination (offline fixture replay)
            res = await session.call_tool(
                "research_destination",
                {
                    "destination": "Vancouver, BC",
                    "vibe": "food",
                    "from_analysis": str(FIXTURE),
                    "skip_geocode": True,
                },
                read_timeout_seconds=TOOL_TIMEOUT,
            )
            out = _tool_json(res)
            assert out["status"] == "complete", out.get("error")
            assert isinstance(out["run_id"], int)
            places = out["places"]
            assert len(places) == 39, len(places)
            p0 = places[0]
            assert p0["name"] == "Capilano Suspension Bridge"
            assert p0["category"] == "sight"
            assert abs(p0["lat"] - 49.342704) < 1e-6
            assert p0["why_loved"] and p0["source_urls"]
            # price_hint is reserved for future stages; key must be present
            assert "price_hint" in p0

            bundle = out["map_bundle"]
            for key in ("kml_path", "map_html_path", "csv_path"):
                assert bundle[key] and Path(bundle[key]).is_file(), key
            assert bundle["kml_path"].endswith("vancouver_bc.kml")

            run_id = out["run_id"]

            # -- tool 2: get_research_result round-trips the run
            res2 = await session.call_tool(
                "get_research_result",
                {"run_id": run_id},
                read_timeout_seconds=TOOL_TIMEOUT,
            )
            out2 = _tool_json(res2)
            assert out2["run_id"] == run_id
            assert out2["status"] == "complete"
            assert out2["destination"] == "Vancouver, BC"
            assert len(out2["places"]) == 39
            assert out2["map_bundle"]["kml_path"] == bundle["kml_path"]

            # metadata-only variant
            res3 = await session.call_tool(
                "get_research_result",
                {"run_id": run_id, "include_places": False},
                read_timeout_seconds=TOOL_TIMEOUT,
            )
            out3 = _tool_json(res3)
            assert "places" not in out3
            assert out3["run_id"] == run_id

            # unknown run
            res4 = await session.call_tool(
                "get_research_result",
                {"run_id": 999999},
                read_timeout_seconds=TOOL_TIMEOUT,
            )
            out4 = _tool_json(res4)
            assert out4["status"] == "not_found"
    return True


def test_mcp_tools_e2e():
    assert asyncio.run(_run_flow())


if __name__ == "__main__":
    test_mcp_tools_e2e()
    print("PASS test_mcp_tools_e2e")
