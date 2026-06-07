---
name: market-research
description: Use when asked to "market research", "/market-research", research a market/industry/product category, find top companies and what they do, gather user pain points or feedback on a topic, validate a startup idea, or size demand from real user discussion. Pulls HackerNews + Reddit + web, analyzes, writes a report.
---

# Market Research

## Overview

Given a `<topic>` (a market, product category, role, or company set), produce a cited
markdown research report covering: top players and what they do, real user pain points
and feedback, competitor/tool sentiment, and opportunities. Evidence comes from
HackerNews (Algolia API), Reddit (headless browser), and web search — never from memory.

**Core principle: every claim traces to a real quote, post, or source URL.**

## When to use
- "Do market research on X" / "/market-research X"
- "Find the top companies in X and what users say about them"
- "What do people complain about with X?" / pain-point discovery
- Startup idea validation, demand signal, competitor sentiment

## Workflow

```
scope → identify players (web) → collect (HN + Reddit) → merge → analyze (subagents) → report
```

### Step 0 — Scope (ask only if ambiguous)
Confirm with one `AskUserQuestion` only when the topic is broad or two-sided:
focus/segment, sources (default: HN + Reddit + web), and output (default: markdown report).
Pick a short `domain` slug (e.g. `ai_wearables`, `ml_engineer`). Skip the question for a
clearly-scoped topic and state your assumptions instead.

### Step 1 — Identify the players (web)
For company/product topics, run 2–3 `WebSearch` calls to list the top companies, what
each does, status/funding, and notable failures. This list drives the Reddit subreddit
targeting in Step 2. Skip for pure pain-point topics (e.g. "daily SWE workflow").

### Step 2 — Collect discussions (run both, they're independent)

**HackerNews** (fast, no browser) — `scripts/collect_hn.py`:
```bash
python3 scripts/collect_hn.py --domain <slug> --queries "term1,term2,term3,..."
```
Use 8–12 *focused* keyword queries, not one long sentence (Algolia ranks by keyword match).

**Reddit** — `scripts/collect_reddit.py` with a JSON config. Reddit is **bot-protected**;
the script uses the gstack `browse` headless browser against **old.reddit.com** with a
desktop User-Agent. Two task types:
- `sub_tasks`: pull `top` posts from a dedicated subreddit (every post is on-topic). Best
  for named products/companies. Probe a subreddit exists first (front page has `.thing.link`).
- `search_tasks`: sitewide search with **sort=relevance, t=year**, and a **required title
  keyword** filter. Needed for topics without a clean subreddit.

```bash
python3 scripts/collect_reddit.py --config /tmp/reddit_<slug>.json
```
Config schema and gotchas are documented at the top of `scripts/collect_reddit.py` — read it.

### Step 3 — Merge (if both sources)
Combine the two `data/raw/*.json` files for a domain into one `*_combined_*.json`
(concatenate the `discussions` arrays; keep one metadata header).

### Step 4 — Analyze (dispatch subagents — do NOT read 1000s of comments yourself)
A merged file can hold thousands of comments. Dispatch **one `Agent` (general-purpose) per
domain** to read its file and write structured analysis JSON to `data/analysis/`. Give the
agent the exact schema you want. Run multiple domains' agents in parallel.

Extract: **pain points** (category, priority, frequency, quotes), **competitors/tools**
(mentions, sentiment, context), **sentiment** distribution, and for product topics
**per-product user feedback** (what users like / complain about). Tell the agent to base
everything on real text and copy verbatim quotes with source URLs.

### Step 5 — Report
Generate `reports/<slug>_report_<timestamp>.md` from the analysis JSON: TL;DR, a companies
table (what they do + status), ranked pain points with quotes, tool sentiment, comparison
(if multiple domains), opportunities, and a caveats/methodology section. Cite source URLs.
End by listing the report path and the raw/analysis files. Notion publishing is optional
(only if the user asks and `config/notion_config.json` is set up).

## Critical gotchas (learned the hard way)

| Trap | Reality |
|---|---|
| Reddit JSON API / new Reddit | Return **HTTP 403** to scripts and headless browsers. Use **old.reddit.com via `browse`** with a desktop UA. |
| Sitewide search `sort=top&t=all` | Pulls **viral junk** that merely contains the word (e.g. "Bee" → Trump megathreads). Use `sort=relevance&t=year` **and filter titles by keyword**. |
| One long natural-language HN query | Algolia ranks by keyword — returns noise. Use many short focused queries, dedup by objectID. |
| Reading the whole corpus yourself | Thousands of comments blow context. **Dispatch a subagent per domain** to analyze and return structured JSON. |
| Generic product names in subreddit probe | Confirm a subreddit has real posts (`.thing.link` count > 0) before relying on it; fall back to keyword-filtered search. |
| Thin Reddit coverage for a product | Supplement that product's profile from `WebSearch` and say so in the caveats. |

## Data layout
```
data/raw/        {slug}_hn_*.json, {slug}_*.json (reddit), {slug}_combined_*.json
data/analysis/   pain_points_*.json, competitors_*.json, sentiment_*.json, *_feedback.json
reports/         {slug}_report_*.md
```
Override the base with env var `MR_DATA_RAW` if needed (defaults to this project's `data/raw`).

## Common mistakes
- Reporting numbers without quotes — every pain point needs a real source URL.
- Treating Reddit sentiment as a survey — it skews to enthusiasts and complainers; say so.
- Skipping the web step for company topics — you'll miss acquisitions/shutdowns that flip a profile.
- Letting one launch/AMA thread inflate a tool's mention count — dedup by hand.
