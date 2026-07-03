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
