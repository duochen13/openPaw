# Travel Research

A Claude Code skill that mines rednote (Xiaohongshu) for the places and restaurants
people love in a destination, publishes them to a Notion database, and marks them
as pins on a Google Map.

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

The map is delivered as a `.kml` you import into Google My Maps (Create map →
Import), producing one map with a colored pin per place — visible in the Google
Maps app under *Your places → Maps*. See `SKILL.md` for the full workflow and
`docs/superpowers/specs/2026-07-02-travel-assistant-design.md` for rationale.
Booking and multi-day route *sequencing* are planned future phases.

## Scripts
- `scripts/collect_rednote.py` — rednote collector (drives the browse browser).
- `scripts/validate_places.py` — validates analyzer output before publishing.
- `scripts/build_map.py` — geocodes places and emits the Google My Maps KML.
- `scripts/build_gmap_html.py` — renders places as a self-contained interactive Google Maps HTML viewer (pins + popups).
- `scripts/upload_to_notion.py` — uploads the map HTML/KML to Notion (File Upload API) and creates the destination's "Map" page. Needs `NOTION_TOKEN`.
- `python3 scripts/test_*.py` — run the unit tests for the pure helpers.
