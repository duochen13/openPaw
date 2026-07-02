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

(scope → collect → fallback → analyze → validate → geocode → publish — filled in below)
