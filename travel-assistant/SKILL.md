---
name: travel-research
description: Use when asked to "travel research", "/travel-research", plan a trip, or "find the best places/restaurants in <destination>". Mines rednote (Xiaohongshu) for places locals and travelers love, deduplicates and ranks them with cited quotes, and publishes them to a Notion database.
---

# Travel Research

## Overview

Given a `<destination>`, produce an organized, deduped, ranked list of places and
restaurants that rednote (Xiaohongshu) users love — each with the *reason* people
love it and a source URL — and publish it to a Notion database (one row per place).

**Core principle: every place traces to a real rednote post/comment or source URL.
Never invent a place from model memory.**

## When to use
- "Do travel research on <destination>" / "/travel-research <destination>"
- "Find the best restaurants / sights / cafes in <destination>"
- Trip planning 1–2 days out, when you want a shortlist of loved spots.

## Out of scope (v1)
- Booking transport or housing.
- Google Maps route-marking / itinerary sequencing.
(These are planned future phases — see the design spec.)

## Prerequisites
- gstack `browse` binary installed (default: `~/.claude/skills/gstack/browse/dist/browse`).
- A logged-in Xiaohongshu session in the browse browser. Run `/setup-browser-cookies`
  and import `xiaohongshu.com` cookies once, or the collector will hit the login wall
  (which triggers the WebSearch fallback below).
- The `notion` MCP tools connected (for publishing).

## Workflow

### Step 0 — Scope (ask only if ambiguous)
Confirm with one `AskUserQuestion` only when the destination is broad or the intent
is unclear: interest vibe (food / sights / cafes / nightlife / all) and whether to
publish to Notion (default: yes). Pick a short slug (e.g. `lisbon`, `tokyo`). Skip
the question for a clearly-scoped request and state your assumptions instead.

### Step 1 — Collect from rednote (`scripts/collect_rednote.py`)
Build 4–6 focused search terms mixing the destination with intent words. Prefer
Chinese terms (rednote is Chinese-first) plus the destination name, e.g. for Lisbon:
`里斯本美食, 里斯本必去, 里斯本攻略, Lisbon citywalk, 里斯本咖啡`.
```bash
python3 scripts/collect_rednote.py --destination "Lisbon" \
  --queries "里斯本美食,里斯本必去,里斯本攻略,Lisbon citywalk,里斯本咖啡" --n 6
```
Output: `data/raw/{slug}_rednote_{ts}.json`.

### Step 2 — Fallback when rednote is blocked or thin
If the collector saved **0 posts** (login wall) or **< 5 posts with content**, do NOT
stop. Run `WebSearch` for rednote-aggregator blogs and "best <type> in <destination>"
plus Google Maps top-rated lists, and hand those results to the analyzer instead.
Record which mode you used — it becomes `source_mode` (`rednote` / `fallback` / `mixed`).

### Step 3 — Analyze (dispatch a subagent — do NOT read all posts yourself)
A raw file can hold thousands of comments. Dispatch **one general-purpose `Agent`** to
read `data/raw/{slug}_rednote_{ts}.json` (or the fallback results) and write structured
analysis to `data/analysis/{slug}_places_{ts}.json`. Give the agent this exact schema
and rules:

- One object per place with keys: `name`, `type` (restaurant|sight|cafe|bar|shop|other),
  `area`, `why_loved` (a **verbatim** quote from a post/comment), `source_urls`
  (non-empty list of the posts that mention it), `mention_count` (int), `sentiment`
  (positive|mixed|negative), `tags` (list), plus `map_link: null`, `rating: null`,
  `lat: null`, `lng: null`.
- Top-level: `destination`, `generated_at` (ISO), `source_mode`, `places`.
- Rules: dedup places that are the same venue under different spellings; rank by
  `mention_count` then sentiment; keep only places with a real source URL; copy quotes
  verbatim (do not paraphrase into praise); never invent a place.

### Step 4 — Validate before publishing
```bash
python3 scripts/validate_places.py data/analysis/{slug}_places_{ts}.json
```
Expected: `valid`. If it prints `INVALID`, fix the analyzer output (re-dispatch with the
listed errors) until it validates. Do not publish an invalid file.

### Step 5 — Geocode each place
For each place, add a Google Maps search link and (if easily found) a rating:
- `map_link`: `https://www.google.com/maps/search/?api=1&query=` + URL-encoded
  `"<name> <area> <destination>"`.
- `rating`: use `WebSearch` for the Google rating only when it surfaces quickly; leave
  `null` otherwise. Do not block the run on ratings.
Write the enriched objects back into the same `data/analysis/{slug}_places_{ts}.json`.
(Precise lat/lng for the map pins are resolved separately by `build_map.py` in Step 7.)

### Step 6 — Publish to Notion (via the `notion` MCP tools)
Skip this step entirely if the user passed `--no-publish` (print the places JSON instead).

1. `notion-search` for a database titled `Travel — <Destination>`.
2. If none exists, `notion-create-database` with these properties:
   - `Name` (title), `Type` (select), `Area` (rich_text), `Why people love it`
     (rich_text), `Source links` (url), `Map link` (url), `Rating` (number),
     `Tags` (multi_select), `Destination` (select), `Status` (select: want-to-go /
     booked / visited).
3. For each place, **upsert by `Name`**: `notion-query-data-sources` to check if a row
   with that Name exists; if yes `notion-update-page`, else `notion-create-pages`.
   Map `why_loved`→`Why people love it`, first `source_urls`→`Source links`,
   `map_link`→`Map link`, `Status` default `want-to-go`.
4. On any Notion failure, keep `data/analysis/{slug}_places_{ts}.json` and report its
   path — nothing is lost.

## Data layout
```
data/raw/       {slug}_rednote_{ts}.json          (collector output)
data/analysis/  {slug}_places_{ts}.json           (analyzer output, validated)
data/maps/      {slug}.kml                         (Google My Maps import file)
```
Override the raw dir with env var `TA_DATA_RAW` if needed.

## Common mistakes
- Publishing paraphrased praise instead of a verbatim quote + source URL.
- Skipping validation and pushing a malformed row to Notion.
- Treating rednote sentiment as a survey — it skews to enthusiasts; say so if asked.
- Giving up when the login wall appears instead of using the WebSearch fallback.
