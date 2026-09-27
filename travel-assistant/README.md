# Travel Research

A Claude Code skill that mines rednote (Xiaohongshu) for the places and restaurants
people love in a destination, publishes them to a Notion database, and marks them
as pins on a Google Map.

## Quickstart

```bash
cd travel-assistant
pip install -r requirements.txt   # fastapi/uvicorn/httpx (API service) + mcp (MCP server)

# 1. Research pipeline (CLI) — mines rednote for loved places in a destination
python3 -m travel_assistant.research --destination "Kyoto" --vibe food --queries "京都美食,京都必去,Kyoto food"
python3 -m travel_assistant.runs list                 # past runs
python3 -m travel_assistant.runs show 3 --places      # one run + its places

# 2. Local dashboard — maps of past runs in the browser (stdlib only, no keys)
python3 -m travel_assistant ui                        # serves http://127.0.0.1:8000

# 3. API service — async HTTP API over the pipeline (Bearer-key auth)
python3 -m travel_assistant.apikeys create --name dev # mint a key (raw key printed once)
python3 -m travel_assistant.service --port 8000       # or: uvicorn travel_assistant.service:app --port 8000
# POST /v1/research  -> 202 {job_id};  GET /v1/research/{job_id} -> poll for done

# 4. MCP server — one config line for Claude Code / Claude Desktop
# {"mcpServers": {"travel-assistant": {"command": "python3", "args": ["-m", "travel_assistant.mcp_server"], "cwd": "<absolute path to travel-assistant>"}}}
```
## Usage
```
/travel-research <destination> [--vibe food|sights|cafes|nightlife|all] [--no-publish]
```

## Prerequisites
- gstack `browse` binary (`~/.claude/skills/gstack/browse/dist/browse`).
- A logged-in `xiaohongshu.com` session imported via `/setup-browser-cookies`
  (otherwise the collector hits the login wall and the skill falls back to WebSearch).
- `notion` MCP tools connected (for publishing).

## How it works
scope → collect (rednote via headless browser) → fallback (WebSearch + Maps) →
analyze (subagent dedup/rank with cited quotes) → validate → geocode →
build map (KML for Google My Maps) → build interactive Google Map HTML →
publish (Notion database + a map page with the HTML/KML attached).

See `SKILL.md` for the full workflow and
`docs/superpowers/specs/2026-07-02-travel-assistant-design.md` for rationale.
Booking and multi-day route *sequencing* are planned future phases.

## Getting the places into Google Maps

Google has no public API that writes pins into a user's account.
Every route ends in either a file import or a browser driving the UI while signed in.
There are two destinations, and they are not interchangeable.

**My Maps** — import `data/maps/{slug}.kml` or `data/maps/{slug}_mymaps.csv` at
mymaps.google.com (Create a new map → Import).
Keeps per-type pin colors and the why-loved quote in each popup.
Renders in the Google Maps app on both iOS and Android, but only under
*Saved → Maps*; a custom map cannot be overlaid on the default map view.

**Saved list** — renders directly on the main map and stays visible during navigation.
This is what you want for a trip you are actually walking around with.
There is no bulk import: places go in one at a time, so 23 places means 23 saves.
Automating it needs a signed-in browser (see "Driving Google Maps signed in").

Prefer the **CSV** over the KML for My Maps.
The KML carries only the places that geocoded locally, while the CSV has an
`Address` column that Google geocodes on import — its coverage of small northern
businesses is far better than Nominatim's.
On the Yellowknife run that was the difference between 16 and 23 placed pins.

## Known gotchas

**Geocoding is the weak link outside major cities.**
For Yellowknife, Nominatim placed 2 of 23 on the default query and 8 with looser
query forms.
Pulling named POIs from the Overpass API and fuzzy-matching locally got it to 16.
Use `overpass-api.de` or `overpass.kumi.systems` — *not* `overpass.osm.ch`, which
is Switzerland-only and silently returns zero elements for anywhere else.
Google's Geocoding API is a separate product from the Maps JS API and is not
enabled on the key embedded in the generated HTML.

**Notion cannot take the map files as attachments.**
`notion-create-attachment` rejects `.kml` (unsupported extension) and Cloudflare
returns 403 on the `.html` because its inline JavaScript trips the WAF.
Publish the database and keep the map files local, or use `upload_to_notion.py`
with a `NOTION_TOKEN`.

**Paths are relative to this directory, not your working directory.**
`~/.claude/skills/travel-research` is a symlink here, and the scripts write
relative to themselves, so outputs land under this repo no matter where you
invoked the skill from.
Report absolute paths to the user.

## Driving Google Maps signed in

`browse cookie-import-browser chrome --domain google.com` has two failure modes
that look like one:

1. It refuses unless the browser is already on that domain — `goto
   https://www.google.com` first, or you get a "does not match current page
   domain" error that reads like a permissions problem.
2. It needs its own Keychain ACL entry for "Chrome Safe Storage" and prompts for it.

The `security` CLI usually already has that ACL, so the reliable path is to read
the key through it and decrypt Chrome's cookie jar directly:
PBKDF2-HMAC-SHA1(key, salt `saltysalt`, 1003 iterations, 16 bytes), AES-128-CBC,
IV of 16 spaces, then strip PKCS7 padding.
Chrome 130+ prefixes the plaintext with a 32-byte SHA-256 of the host — drop it
if the UTF-8 decode fails.
Filter to exactly `.google.com`; `cookie-import` aborts on the first cookie whose
domain does not match the page, and subdomain cookies like `.workspace.google.com`
will kill the whole import.

When automating the save loop, drive the DOM by `aria-label` and `role` rather
than snapshot refs — refs are invalidated on every navigation.
Google will also drop the session partway through a long run, so detect a
redirect to `accounts.google.com` and re-import before retrying.

## Python package (`travel_assistant`)

The same pipeline as an importable package with clean stages
(collect → analyze → validate → geocode → map). Every run is recorded in a
SQLite run store at `data/runs/runs.db` (params, per-place results, artifact
paths, timing, status).

```bash
cd travel-assistant
# replay a saved analysis (no browser / LLM / network with --skip-geocode)
python3 -m travel_assistant.research --from-analysis data/analysis/vancouver_places_20260709_030913.json --skip-geocode
# live collect (needs the browse browser + logged-in xiaohongshu session)
python3 -m travel_assistant.research --destination "Kyoto" --vibe food --queries "京都美食,京都必去,Kyoto food"
# query past runs
python3 -m travel_assistant.runs list
python3 -m travel_assistant.runs show 3 --places
```

Programmatic use:

```python
from travel_assistant import research
rec = research(destination="Kyoto", vibe="food",
               from_analysis="data/analysis/kyoto_places_20260701.json",
               skip_geocode=True)
```

Notes:
- The analyze step is the LLM subagent pass (SKILL.md Step 3); the package
  defines the stage interface but ships no default analyzer — pass
  `analyzer=<callable>` or replay with `--from-analysis`.
- Set `TA_OFFLINE=1` to forbid network geocoding (raises instead of calling
  Nominatim); `TA_DATA_ROOT` redirects the whole data tree (tests use this).
- `python3 -m travel_assistant.tests.test_research` runs the end-to-end test
  (replays the Vancouver fixture; asserts the KML pins match the committed
  `data/maps/vancouver_bc.kml`).
- `python3 -m travel_assistant.tests.test_mcp_server` drives both MCP tools
  end-to-end through a real stdio client (fixture replay, offline).

## Local dashboard (`travel-assistant ui`)

An MLflow-style local dashboard over the run store — the same core pipeline,
rendered as maps instead of metrics. Stdlib only (`http.server`); the server
reads `data/runs/runs.db` and takes no API keys. Pure renderer: no pipeline
changes, no auth, no network service.

Install (once) and run:

```bash
cd travel-assistant
pip install -e .
travel-assistant ui                      # serves http://127.0.0.1:8000
travel-assistant ui --port 8899 --db /tmp/demo/runs.db
python -m travel_assistant ui           # same, without installing
```

Pages:

- `/` — every past run (destination, vibe, date, # places, status), plus a
  two-run picker for side-by-side comparison.
- `/runs/<id>` — run detail: keyless self-contained SVG map with per-type
  colored pins (same palette as `scripts/build_gmap_html.py`), click-a-pin
  popups with the "why people love it" quote + source link, a cost rollup,
  and the full place list (places without coordinates are listed too).
- `/compare?a=<id>&b=<id>` — both trips' maps, rollups, and place lists
  side by side.

Why SVG instead of the Google Maps embeds from `scripts/build_gmap_html.py`:
those need `GOOGLE_MAPS_API_KEY` in the viewer's browser and render nothing
without one; the dashboard is keyless by design, so it draws its own map and
works fully offline.

Cost rollup: an estimate aggregated from the per-place `price_hint` values
recorded in the run store. The v1 analyzer never emits price hints, so v1
runs show "no price hints recorded" rather than invented totals. If a future
stage fills `price_hint`, the rollup picks it up with no code changes.

## MCP server (`travel_assistant.mcp_server`)

A thin MCP wrapper around the local package — the zero-friction way for an
MCP-capable client (Claude Code, Claude Desktop) to use the pipeline with one
config line. No API keys, no network service, no signup: it runs the local
package in-process over stdio.

Tools:
- `research_destination(destination, vibe="all", queries=None,
  from_analysis=None, from_raw=None, skip_geocode=False, region="",
  n_per_query=6)` — runs the research pipeline and returns run_id, status,
  structured places (name, category, lat/lng, why_loved, source_urls,
  price_hint), and the map bundle paths (KML + map HTML + CSV). A live
  collect takes several minutes of headless-browser time and runs
  synchronously; replaying a saved analysis with `from_analysis` +
  `skip_geocode=true` is the fast offline path.
- `get_research_result(run_id, include_places=true)` — fetches the run record
  and places from the SQLite run store (poll/fetch semantics).

Install the SDK (`pip install -r requirements.txt` — only the official `mcp`
package), then add one line to the client's `mcpServers` config
(Claude Code: `.mcp.json`; Claude Desktop: `claude_desktop_config.json`):

```json
{"mcpServers": {"travel-assistant": {"command": "python3", "args": ["-m", "travel_assistant.mcp_server"], "cwd": "<absolute path to travel-assistant>"}}}
```

Optional `env` entries: `TA_DATA_ROOT` to point the server at a different
data tree, `TA_RUNS_DB` to point at a different run-store SQLite file.

## Scripts
- `scripts/collect_rednote.py` — rednote collector (drives the browse browser).
- `scripts/validate_places.py` — validates analyzer output before publishing.
- `scripts/build_map.py` — geocodes places and emits the Google My Maps KML.
- `scripts/build_gmap_html.py` — renders places as a self-contained interactive Google Maps HTML viewer: pins + popups, a clickable category legend that filters, a Places search box for adding your own stops, and a driving-route overlay with per-leg times.
- `scripts/build_mymaps_csv.py` — emits `data/maps/{slug}_mymaps.csv` for Google My Maps import (position on the `Address` column, title on `Name`).
- `scripts/upload_to_notion.py` — uploads the map HTML/KML to Notion (File Upload API) and creates the destination's "Map" page. Needs `NOTION_TOKEN`.
- `python3 scripts/test_*.py` — run the unit tests for the pure helpers.
