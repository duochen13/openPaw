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

## Scripts
- `scripts/collect_rednote.py` — rednote collector (drives the browse browser).
- `scripts/validate_places.py` — validates analyzer output before publishing.
- `scripts/build_map.py` — geocodes places and emits the Google My Maps KML.
- `scripts/build_gmap_html.py` — renders places as a self-contained interactive Google Maps HTML viewer: pins + popups, a clickable category legend that filters, a Places search box for adding your own stops, and a driving-route overlay with per-leg times.
- `scripts/build_mymaps_csv.py` — emits `data/maps/{slug}_mymaps.csv` for Google My Maps import (position on the `Address` column, title on `Name`).
- `scripts/upload_to_notion.py` — uploads the map HTML/KML to Notion (File Upload API) and creates the destination's "Map" page. Needs `NOTION_TOKEN`.
- `python3 scripts/test_*.py` — run the unit tests for the pure helpers.
