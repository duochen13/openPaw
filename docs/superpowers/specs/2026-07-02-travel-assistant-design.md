# Travel Assistant — Destination Research (v1) Design

**Date:** 2026-07-02
**Status:** Draft — awaiting user review
**Location in repo:** `travel-assistant/`

## Problem

Personal trip-planning flow today: 1–2 days before a trip, manually search
rednote (Xiaohongshu / RED) for a destination, find the places and restaurants
people love, book transport + housing, and mark a route in Google Maps.

The most time-consuming, least automated part is the **research**: reading
dozens of rednote posts to distill "where do people who went actually love
going" into an organized shortlist. This project automates that first step.

## Goal (v1)

Given a destination, produce an organized, deduped, ranked list of
places/restaurants that rednote users love — with the *reason* they love each
one and a source link — publish it to a Notion database, **and mark every place
as a pin on a Google Map** the user can open on the trip.

**Explicitly out of scope for v1** (future phases):
- Booking transport or housing.
- Multi-day itinerary / route *sequencing* (optimal order between pins).
  (v1 marks the pins; it does not order them into a day-by-day route.)

## Key constraint: rednote has no usable public API

Xiaohongshu / RED (rednote) offers **no public content API**. It is heavily
bot-protected: requests need signed `x-s`/`x-t` headers, most content is
login-walled, and scraping violates ToS (account-ban risk). This is the same
class of problem the existing `market-research` skill solved for Reddit — which
uses the gstack `browse` headless browser against a real logged-in session and
supplements with `WebSearch` when coverage is thin.

**Chosen approach — hybrid:**
1. **Primary:** headless `browse` of rednote search results using the user's
   logged-in session, reading the top N posts for a destination.
2. **Fallback:** when rednote is blocked or returns thin results, use
   `WebSearch` for rednote-aggregator blogs + Google Maps ratings/reviews.

This favors the real taste signal (rednote) while degrading gracefully. A
browse-only v1 is acceptable if the fallback proves unnecessary in practice;
the fallback is designed in from the start because rednote blocking is expected.

## Shape

A **Claude Code skill** (mirrors `market-research`), not a deployed Lambda.
Trip research is ad-hoc and interactive, run when planning a trip — unlike the
scheduled `daily-report` Lambda.

Invocation:
```
/travel-research <destination> [--vibe food|sights|cafes|nightlife|all] [--no-publish]
```

## Architecture & data flow

```
/travel-research <destination>
  1. scope     → confirm destination + interests (one AskUserQuestion; skip if clear)
  2. collect   → headless browse rednote search ("<dest> 攻略 / 美食 / 必去 / citywalk")
                 read top N posts; extract place mentions + why-loved text + URLs
                 (fallback: WebSearch rednote blogs + Google Maps ratings)
  3. analyze   → dispatch a subagent to read raw posts: dedup place names,
                 cluster by area, rank by mention frequency + sentiment,
                 copy a verbatim "why people love it" quote + source URL per place
  4. geocode   → resolve each place to lat/lng + a Maps link + neighborhood
                 (Nominatim / OpenStreetMap — free, no API key)
  5. build map → generate a KML file of all pins → import into Google My Maps
  6. publish   → create/update a Notion database, one row per place
```

## Units (each independently testable)

- **collector** — `destination → raw posts JSON`. Knows nothing about Notion.
  Owns the browse/search + fallback logic. Output: array of
  `{ post_url, text, images_alt }`.
- **analyzer** (subagent) — `raw posts JSON → places JSON`. Dedup, cluster,
  rank, extract quotes. Never reads the whole corpus in the main context —
  dispatched as a general-purpose Agent like `market-research` does.
  Output: array of place records (schema below).
- **geocoder** — `place name + destination → { lat, lng, map_link, neighborhood }`.
  Uses Nominatim (OpenStreetMap) — free, no API key, 1 req/sec, descriptive UA.
- **map builder** — `places JSON (with lat/lng) → KML file`. Pure KML generation;
  one `<Placemark>` per place, colored by `type`. Knows nothing about rednote/Notion.
- **publisher** — `places JSON → Notion rows`. Knows nothing about rednote.
  Uses the connected `notion` MCP tools.

**Core principle (inherited from market-research):** every place traces to a
real rednote post / source URL. No place is invented from model memory.

## Notion schema (one row per place)

| Field | Type | Notes |
|---|---|---|
| Name | title | Place / restaurant name |
| Type | select | restaurant / sight / cafe / bar / shop / other |
| Area | text/select | Neighborhood |
| Why people love it | text | Verbatim quote distilled from posts |
| Source links | url/multi | rednote post URLs (+ blog fallback) |
| Map link | url | Google Maps link |
| Rating | number | From maps, if available |
| Tags | multi-select | e.g. cheap-eats, view, must-book, hidden-gem |
| Destination | select/relation | Trip destination |
| Status | select | want-to-go / booked / visited (default: want-to-go) |

## Google Map output (marking the places)

Google Maps has **no public API** to add pins to a user's saved lists
(Favorites / Want-to-go). The robust, ToS-safe, no-login, no-API-key path is
**Google My Maps import**:

1. `build_map.py` geocodes each place (Nominatim) and writes
   `data/maps/{slug}.kml` — one `<Placemark>` per place with name, description
   (why-loved quote + source URL + rating), coordinates, and a `<Style>` color
   keyed by `type` (restaurant/sight/cafe/bar/shop).
2. The user opens **Google My Maps → Create a new map → Import**, selects the
   `.kml`, and every place appears as a colored pin on one shareable map. That
   map is then visible in the Google Maps app under *Your places → Maps* on both
   desktop and mobile.

Rationale for KML-import over alternatives: auto-driving the My Maps UI via the
browser is fragile and needs a Google login; a standalone HTML/Maps-JS page needs
an API key and isn't "inside Google Maps"; per-place links don't produce one
unified map. KML import is a one-time two-click step that yields a real, editable
Google map.

## Note: browse CLI convention (correction)

The installed gstack `browse` binary uses `useragent <str>` (not `set-ua`) and
`eval <file-path>` that prints result lines to stdout (not inline JS). The
collector writes its JS to a temp file, evals the file, and parses the last
stdout line starting with `[`/`{` — mirroring `market-research/collect_reddit.py`.
(The DOM selectors for rednote remain best-effort and need a one-time live
verification against a logged-in session.)

If a Notion database for a destination already exists, upsert into it (match by
Name); otherwise create the database first.

## Error handling

- **rednote login-walled / blocked:** log it, switch to WebSearch fallback,
  and note in the run summary that results came from fallback (not pure rednote).
- **Thin coverage for a place:** supplement from WebSearch + maps; mark the
  source in the record. (Mirrors market-research's "thin Reddit coverage" rule.)
- **Notion publish failure:** keep the local places JSON so nothing is lost;
  report the error and the JSON path.
- **Geocode miss:** if Nominatim returns no hit for a place, skip its pin (keep
  it in Notion) and note the skipped count in the run summary.
- **`--no-publish`:** run collect → analyze → geocode → build map (still writes
  the KML) and print the places JSON; skip only the Notion step.

## Testing

- **collector:** saved rednote-search HTML fixture → asserts N places extracted;
  a blocked-page fixture → asserts fallback path is taken.
- **analyzer:** raw-posts fixture JSON → asserts dedup + ranking + quote/URL present.
- **publisher:** mock `notion` MCP → asserts correct row payload and upsert-by-Name.
- **map builder:** places-with-coords fixture → asserts valid KML with one
  placemark per place and correct color-by-type styling.
- **end-to-end dry run:** `--no-publish` prints valid places JSON + writes a
  `.kml` for a real destination.

## Future phases (not built now)

1. Transport + housing option research (surface, not book).
2. Multi-day itinerary **sequencing** by area to minimize travel (v1 only marks
   the pins; it does not order them into a route).

## Open decisions (confirmed)

- v1 = research → Notion + **Google Map pins**. *(map-marking pulled into v1 per user)*
- Shape = Claude Code skill.
- Output = Notion database **and** a Google My Maps KML import.
- Data source = hybrid browse + web fallback.
- Map delivery = Google My Maps via KML import; geocoding = Nominatim (no API key).
