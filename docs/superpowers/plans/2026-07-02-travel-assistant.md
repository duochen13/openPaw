# Travel Assistant — Destination Research (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Claude Code skill `/travel-research <destination>` that mines rednote (Xiaohongshu) for places/restaurants people love, deduplicates and ranks them with cited quotes, publishes one row per place to a Notion database, and marks every place as a pin on a Google Map (My Maps via KML import).

**Architecture:** Mirrors the existing `market-research` skill exactly — a `SKILL.md` orchestration doc plus Python helper scripts that drive the gstack `browse` headless-browser binary. Collection is a Python script (`collect_rednote.py`); analysis is a dispatched general-purpose subagent (LLM, documented in SKILL.md); the Google Map is built by `build_map.py` (geocode via Nominatim → KML for Google My Maps); publishing uses the connected `notion` MCP tools driven by Claude. Two small pure-Python units carry automated tests: the schema validator (`validate_places.py`) that gates analyzer output before publish, and the KML builder (`build_map.py`).

**Tech Stack:** Python 3 (stdlib only — `subprocess`, `json`, `urllib`), gstack `browse` binary at `~/.claude/skills/gstack/browse/dist/browse`, `notion` MCP tools, `WebSearch`. No test framework — tests are plain runnable `assert` scripts (matching the repo's zero-framework convention for skills).

**Spec:** `docs/superpowers/specs/2026-07-02-travel-assistant-design.md`

---

## File Structure

```
travel-assistant/
  SKILL.md                      # orchestration doc — the primary deliverable
  README.md                     # quick usage + prerequisites
  scripts/
    collect_rednote.py          # browse-driven rednote collector -> data/raw/*.json
    validate_places.py          # pure validator for analyzer output (importable + CLI)
    build_map.py                # geocode (Nominatim) + KML generation -> data/maps/*.kml
    test_collect_rednote.py     # asserts pure helpers: slugify/dedup/rank
    test_validate_places.py     # asserts schema validation
    test_build_map.py           # asserts KML generation (pure)
  data/
    raw/.gitkeep                # {slug}_rednote_{ts}.json (collector output)
    analysis/.gitkeep           # {slug}_places_{ts}.json (analyzer output)
    maps/.gitkeep               # {slug}.kml (Google My Maps import file)
```

**Responsibilities:**
- `collect_rednote.py` — destination/queries in → raw posts JSON out. Knows nothing about Notion or the schema. Owns browse + selector logic.
- `validate_places.py` — a places object in → `(ok, errors)` out. Pure, deterministic, tested.
- `SKILL.md` — the workflow Claude follows: scope → collect → fallback → analyze (subagent) → validate → geocode → publish (Notion MCP).

---

## Shared data contract (referenced by multiple tasks)

**Raw collector output** (`data/raw/{slug}_rednote_{ts}.json`):
```json
{
  "destination": "Lisbon",
  "slug": "lisbon",
  "source": "rednote",
  "timestamp": "2026-07-02T18:00:00Z",
  "discussions": [
    {"title": "里斯本必去", "url": "https://www.xiaohongshu.com/explore/abc",
     "likes": 1200, "content": "...post text...", "comments": ["...","..."]}
  ]
}
```

**Analyzer / publish contract** (`data/analysis/{slug}_places_{ts}.json`) — produced by the analyzer subagent, checked by `validate_places.py`, consumed by the Notion publisher:
```json
{
  "destination": "Lisbon",
  "generated_at": "2026-07-02T18:05:00Z",
  "source_mode": "rednote",
  "places": [
    {
      "name": "Time Out Market",
      "type": "restaurant",
      "area": "Cais do Sodré",
      "why_loved": "verbatim quote from a post/comment",
      "source_urls": ["https://www.xiaohongshu.com/explore/abc"],
      "mention_count": 4,
      "sentiment": "positive",
      "map_link": null,
      "rating": null,
      "lat": null,
      "lng": null,
      "tags": ["food-hall", "must-book"]
    }
  ]
}
```
Enums: `type` ∈ {restaurant, sight, cafe, bar, shop, other}; `sentiment` ∈ {positive, mixed, negative}; `source_mode` ∈ {rednote, fallback, mixed}. `map_link`/`rating`/`lat`/`lng` are `null` until the geocode step fills them. `lat`/`lng` feed the KML pins; `map_link` is the per-place Google Maps link for Notion.

---

### Task 1: Scaffold the skill directory + SKILL.md skeleton

**Files:**
- Create: `travel-assistant/SKILL.md`
- Create: `travel-assistant/data/raw/.gitkeep`
- Create: `travel-assistant/data/analysis/.gitkeep`

- [ ] **Step 1: Create data dirs with keep files**

```bash
mkdir -p travel-assistant/data/raw travel-assistant/data/analysis
touch travel-assistant/data/raw/.gitkeep travel-assistant/data/analysis/.gitkeep
```

- [ ] **Step 2: Write SKILL.md frontmatter + overview**

Create `travel-assistant/SKILL.md` with exactly this content (later tasks append workflow sections):

```markdown
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
```

- [ ] **Step 3: Verify frontmatter parses**

Run:
```bash
python3 -c "import re,sys; t=open('travel-assistant/SKILL.md').read(); m=re.match(r'^---\n(.*?)\n---', t, re.S); assert m and 'name: travel-research' in m.group(1) and 'description:' in m.group(1); print('frontmatter OK')"
```
Expected: `frontmatter OK`

- [ ] **Step 4: Commit**

```bash
git add travel-assistant/SKILL.md travel-assistant/data/raw/.gitkeep travel-assistant/data/analysis/.gitkeep
git commit -m "feat(travel): scaffold travel-research skill skeleton"
```

---

### Task 2: Pure collector helpers (TDD) — slugify, dedup, rank

**Files:**
- Create: `travel-assistant/scripts/collect_rednote.py` (helpers only in this task)
- Test: `travel-assistant/scripts/test_collect_rednote.py`

- [ ] **Step 1: Write the failing test**

Create `travel-assistant/scripts/test_collect_rednote.py`:
```python
import collect_rednote as c

def test_slugify_ascii_and_spaces():
    assert c.slugify("Lisbon") == "lisbon"
    assert c.slugify("San Francisco") == "san_francisco"
    assert c.slugify("Tokyo!! 2026") == "tokyo_2026"

def test_dedup_by_url_keeps_first():
    items = [{"url": "u1", "likes": 5}, {"url": "u1", "likes": 9}, {"url": "u2", "likes": 1}]
    out = c.dedup_by_url(items)
    assert [i["url"] for i in out] == ["u1", "u2"]

def test_rank_by_likes_desc():
    items = [{"url": "a", "likes": 3}, {"url": "b", "likes": 30}, {"url": "c", "likes": 10}]
    out = c.rank_by_likes(items)
    assert [i["url"] for i in out] == ["b", "c", "a"]

def test_rank_handles_missing_likes():
    items = [{"url": "a"}, {"url": "b", "likes": 2}]
    out = c.rank_by_likes(items)
    assert out[0]["url"] == "b"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd travel-assistant/scripts && python3 test_collect_rednote.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'collect_rednote'` (file doesn't exist yet).

- [ ] **Step 3: Write minimal implementation (helpers)**

Create `travel-assistant/scripts/collect_rednote.py`:
```python
#!/usr/bin/env python3
"""Collect rednote (Xiaohongshu) posts via the gstack `browse` headless browser.

WHY THIS WAY (expected gotchas, mirror of collect_reddit.py):
  - Xiaohongshu has NO public content API and signs requests (x-s/x-t). Do not
    try the JSON endpoints — use the rendered web pages via `browse`.
  - Most content is login-walled. Import a logged-in xiaohongshu.com session with
    /setup-browser-cookies first. If not logged in, the search page renders a login
    modal and yields 0 note cards -> the caller (SKILL.md) falls back to WebSearch.
  - DOM selectors below are BEST-EFFORT and MUST be verified live (see Task 3).
"""
import subprocess, json, os, re, time, argparse, glob, tempfile, urllib.parse
from datetime import datetime, timezone

def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower())
    return s.strip("_")

def dedup_by_url(items):
    seen, out = set(), []
    for i in items:
        u = i.get("url")
        if u and u not in seen:
            seen.add(u); out.append(i)
    return out

def rank_by_likes(items):
    return sorted(items, key=lambda x: int(x.get("likes", 0) or 0), reverse=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd travel-assistant/scripts && python3 test_collect_rednote.py
```
Expected: `PASS test_slugify_ascii_and_spaces` … `all passed`

- [ ] **Step 5: Commit**

```bash
git add travel-assistant/scripts/collect_rednote.py travel-assistant/scripts/test_collect_rednote.py
git commit -m "feat(travel): rednote collector pure helpers with tests"
```

---

### Task 3: Collector browse-driving core + CLI

**Files:**
- Modify: `travel-assistant/scripts/collect_rednote.py` (append browse driver + `collect()` + `__main__`)

- [ ] **Step 1: Append the browse driver, extractors, and collect() below the helpers**

Append to `travel-assistant/scripts/collect_rednote.py`:
```python
DATA_RAW = os.environ.get("TA_DATA_RAW",
    os.path.join(os.path.dirname(__file__), "..", "data", "raw"))

def find_browse():
    p = os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")
    if os.path.exists(p):
        return p
    hits = glob.glob(os.path.expanduser("~/**/gstack/browse/dist/browse"), recursive=True)
    return hits[0] if hits else "browse"

B = find_browse()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def run(args, timeout=70):
    try:
        return subprocess.run([B] + args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""

def goto(url, timeout=70):
    run(["goto", url], timeout); time.sleep(2.0)

# This browse binary's `eval` takes a FILE PATH (not inline JS) and prints result
# lines to stdout; write JS to a temp file, eval it, parse the last line starting
# with `prefix`. Mirrors market-research/collect_reddit.py (verified convention).
EVAL_TMP = os.path.join(tempfile.gettempdir(), "_ta_eval.js")

def eval_js(js, prefix):
    with open(EVAL_TMP, "w") as f:
        f.write(js)
    raw = run(["eval", EVAL_TMP])
    ln = [l for l in raw.splitlines() if l.strip().startswith(prefix)]
    if not ln:
        return None
    try:
        return json.loads(ln[-1])
    except Exception:
        return None

# BEST-EFFORT selectors — verify live in Step 2 and adjust before relying on output.
SEARCH_LIST_JS = r'''(()=>{const o=[];document.querySelectorAll('section.note-item, div.note-item').forEach(el=>{const a=el.querySelector('a[href*="/explore/"], a[href*="/search_result/"]');const t=el.querySelector('.title, span.title, .footer .title');const lk=el.querySelector('.like-wrapper .count, .count');if(!a)return;o.push({title:(t?t.innerText:'').trim(),url:a.href,likes:(lk?lk.innerText:'0').replace(/[^0-9]/g,'')||'0'});});return JSON.stringify(o);})()'''
POST_JS = r'''(()=>{const c=document.querySelector('#detail-desc, .note-content, .desc');const cs=[];document.querySelectorAll('.comment-item .content, .comments-container .content').forEach(e=>{const t=e.innerText.trim();if(t)cs.push(t);});return JSON.stringify({content:c?c.innerText.trim():'',comments:cs.slice(0,20)});})()'''

def get_post(url):
    goto(url)
    pd = eval_js(POST_JS, "{")
    return pd if pd else {"content": "", "comments": []}

def collect(destination, queries, n_per_query=6):
    run(["useragent", UA])
    slug = slugify(destination)
    sid = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_items = []
    for q in queries:
        url = "https://www.xiaohongshu.com/search_result?keyword=" + urllib.parse.quote(q)
        goto(url)
        items = eval_js(SEARCH_LIST_JS, "[") or []
        print(f"[{q}] {len(items)} cards")
        all_items.extend(items)
    picked = rank_by_likes(dedup_by_url(all_items))[: n_per_query * len(queries)]
    discussions = []
    for it in picked:
        pd = get_post(it["url"])
        discussions.append({"title": it.get("title", ""), "url": it["url"],
                            "likes": int(it.get("likes", 0) or 0),
                            "content": pd.get("content", ""), "comments": pd.get("comments", [])})
        time.sleep(0.4)
    os.makedirs(DATA_RAW, exist_ok=True)
    out_file = os.path.join(DATA_RAW, f"{slug}_rednote_{sid}.json")
    data = {"destination": destination, "slug": slug, "source": "rednote",
            "timestamp": datetime.now(timezone.utc).isoformat(), "discussions": discussions}
    json.dump(data, open(out_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"[{slug}] saved {len(discussions)} posts -> {out_file}")
    return out_file

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--destination", required=True)
    ap.add_argument("--queries", required=True, help="comma-separated search terms")
    ap.add_argument("--n", type=int, default=6)
    a = ap.parse_args()
    qs = [q.strip() for q in a.queries.split(",") if q.strip()]
    try:
        collect(a.destination, qs, a.n)
    finally:
        run(["stop"])
```

- [ ] **Step 2: Verify pure helpers still pass and selectors live**

Run the unit tests (must still pass — Task 2 behavior unchanged):
```bash
cd travel-assistant/scripts && python3 test_collect_rednote.py
```
Expected: `all passed`

Then verify the DOM selectors against live rednote using the browse tool directly (selectors change often; this step confirms/repairs them). Note the installed binary's CLI: `useragent <str>` and `js <expr>` for a one-off inline expression (the collector itself uses `eval <file>`):
```bash
BR=~/.claude/skills/gstack/browse/dist/browse
$BR useragent "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
$BR goto "https://www.xiaohongshu.com/search_result?keyword=%E9%87%8C%E6%96%AF%E6%9C%AC%E7%BE%8E%E9%A3%9F"
$BR js 'document.querySelectorAll("section.note-item, div.note-item").length'
$BR stop
```
Expected: a non-zero count if logged in. If it prints `0`, either (a) not logged in → the login wall is up (expected → SKILL.md fallback handles it), or (b) selectors drifted → inspect the page and update `SEARCH_LIST_JS`/`POST_JS`, then re-run. Record the working selectors. (This requires running outside the sandbox and with a logged-in session; if neither is available, defer to a human live check.)

- [ ] **Step 3: Commit**

```bash
git add travel-assistant/scripts/collect_rednote.py
git commit -m "feat(travel): rednote browse-driven collector + CLI"
```

---

### Task 4: Places validator (TDD)

**Files:**
- Create: `travel-assistant/scripts/validate_places.py`
- Test: `travel-assistant/scripts/test_validate_places.py`

- [ ] **Step 1: Write the failing test**

Create `travel-assistant/scripts/test_validate_places.py`:
```python
import validate_places as v

GOOD = {
    "destination": "Lisbon", "generated_at": "2026-07-02T18:05:00Z",
    "source_mode": "rednote",
    "places": [{
        "name": "Time Out Market", "type": "restaurant", "area": "Cais do Sodré",
        "why_loved": "great food hall", "source_urls": ["https://x.com/a"],
        "mention_count": 4, "sentiment": "positive",
        "map_link": None, "rating": None, "tags": ["food-hall"]
    }]
}

def test_good_object_passes():
    ok, errors = v.validate(GOOD)
    assert ok and errors == []

def test_missing_source_urls_fails():
    bad = {**GOOD, "places": [{**GOOD["places"][0], "source_urls": []}]}
    ok, errors = v.validate(bad)
    assert not ok and any("source_urls" in e for e in errors)

def test_bad_type_enum_fails():
    bad = {**GOOD, "places": [{**GOOD["places"][0], "type": "hotel"}]}
    ok, errors = v.validate(bad)
    assert not ok and any("type" in e for e in errors)

def test_bad_source_mode_fails():
    bad = {**GOOD, "source_mode": "guess"}
    ok, errors = v.validate(bad)
    assert not ok and any("source_mode" in e for e in errors)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd travel-assistant/scripts && python3 test_validate_places.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'validate_places'`.

- [ ] **Step 3: Write minimal implementation**

Create `travel-assistant/scripts/validate_places.py`:
```python
#!/usr/bin/env python3
"""Validate the analyzer's places object before Notion publish. Pure + CLI."""
import json, sys, argparse

TYPES = {"restaurant", "sight", "cafe", "bar", "shop", "other"}
SENTIMENTS = {"positive", "mixed", "negative"}
MODES = {"rednote", "fallback", "mixed"}

def validate(obj):
    errors = []
    for k in ("destination", "generated_at", "source_mode", "places"):
        if k not in obj:
            errors.append(f"missing top-level key: {k}")
    if obj.get("source_mode") not in MODES:
        errors.append(f"source_mode must be one of {sorted(MODES)}")
    for idx, p in enumerate(obj.get("places", [])):
        tag = f"places[{idx}]"
        if not p.get("name"):
            errors.append(f"{tag}.name is required")
        if p.get("type") not in TYPES:
            errors.append(f"{tag}.type must be one of {sorted(TYPES)}")
        if p.get("sentiment") not in SENTIMENTS:
            errors.append(f"{tag}.sentiment must be one of {sorted(SENTIMENTS)}")
        if not p.get("source_urls"):
            errors.append(f"{tag}.source_urls must be a non-empty list")
        if not isinstance(p.get("mention_count"), int):
            errors.append(f"{tag}.mention_count must be an int")
    return (len(errors) == 0, errors)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    a = ap.parse_args()
    ok, errors = validate(json.load(open(a.file, encoding="utf-8")))
    if ok:
        print("valid"); sys.exit(0)
    print("INVALID:"); [print(" -", e) for e in errors]; sys.exit(1)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd travel-assistant/scripts && python3 test_validate_places.py
```
Expected: `all passed`

- [ ] **Step 5: Commit**

```bash
git add travel-assistant/scripts/validate_places.py travel-assistant/scripts/test_validate_places.py
git commit -m "feat(travel): places-schema validator with tests"
```

---

### Task 5: SKILL.md — collection + fallback workflow

**Files:**
- Modify: `travel-assistant/SKILL.md` (replace the placeholder workflow line)

- [ ] **Step 1: Replace the workflow placeholder with Steps 0–2**

In `travel-assistant/SKILL.md`, replace this line:
```markdown
(scope → collect → fallback → analyze → validate → geocode → publish — filled in below)
```
with:
```markdown
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
```
```

- [ ] **Step 2: Verify the file still has valid frontmatter and the new sections**

Run:
```bash
grep -q "Step 1 — Collect from rednote" travel-assistant/SKILL.md && grep -q "Step 2 — Fallback" travel-assistant/SKILL.md && echo "sections OK"
```
Expected: `sections OK`

- [ ] **Step 3: Commit**

```bash
git add travel-assistant/SKILL.md
git commit -m "docs(travel): SKILL collection + fallback workflow"
```

---

### Task 6: SKILL.md — analysis subagent + validation

**Files:**
- Modify: `travel-assistant/SKILL.md` (append Steps 3–4)

- [ ] **Step 1: Append the analysis + validate sections**

Append to `travel-assistant/SKILL.md`:
```markdown
### Step 3 — Analyze (dispatch a subagent — do NOT read all posts yourself)
A raw file can hold thousands of comments. Dispatch **one general-purpose `Agent`** to
read `data/raw/{slug}_rednote_{ts}.json` (or the fallback results) and write structured
analysis to `data/analysis/{slug}_places_{ts}.json`. Give the agent this exact schema
and rules:

- One object per place with keys: `name`, `type` (restaurant|sight|cafe|bar|shop|other),
  `area`, `why_loved` (a **verbatim** quote from a post/comment), `source_urls`
  (non-empty list of the posts that mention it), `mention_count` (int), `sentiment`
  (positive|mixed|negative), `tags` (list), plus `map_link: null` and `rating: null`.
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
```

- [ ] **Step 2: Verify sections present**

Run:
```bash
grep -q "Step 3 — Analyze" travel-assistant/SKILL.md && grep -q "Step 4 — Validate" travel-assistant/SKILL.md && echo "sections OK"
```
Expected: `sections OK`

- [ ] **Step 3: Commit**

```bash
git add travel-assistant/SKILL.md
git commit -m "docs(travel): SKILL analysis subagent + validation"
```

---

### Task 7: SKILL.md — geocode + Notion publish

**Files:**
- Modify: `travel-assistant/SKILL.md` (append Steps 5–6 + data layout)

- [ ] **Step 1: Append geocode + publish + data-layout sections**

Append to `travel-assistant/SKILL.md`:
```markdown
### Step 5 — Geocode each place
For each place, add a Google Maps search link and (if easily found) a rating:
- `map_link`: `https://www.google.com/maps/search/?api=1&query=` + URL-encoded
  `"<name> <area> <destination>"`.
- `rating`: use `WebSearch` for the Google rating only when it surfaces quickly; leave
  `null` otherwise. Do not block the run on ratings.
Write the enriched objects back into the same `data/analysis/{slug}_places_{ts}.json`.

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
```

- [ ] **Step 2: Verify full workflow present**

Run:
```bash
for s in "Step 5 — Geocode" "Step 6 — Publish" "Data layout"; do grep -q "$s" travel-assistant/SKILL.md || { echo "MISSING: $s"; exit 1; }; done; echo "workflow complete"
```
Expected: `workflow complete`

- [ ] **Step 3: Commit**

```bash
git add travel-assistant/SKILL.md
git commit -m "docs(travel): SKILL geocode + Notion publish + data layout"
```

---

### Task 8: Google My Maps — geocode + KML builder (TDD)

**Files:**
- Create: `travel-assistant/scripts/build_map.py`
- Test: `travel-assistant/scripts/test_build_map.py`
- Create: `travel-assistant/data/maps/.gitkeep`

- [ ] **Step 1: Write the failing test**

Create `travel-assistant/scripts/test_build_map.py`:
```python
import build_map as m

PLACE = {"name": "Time Out <Market>", "type": "restaurant", "area": "Cais",
         "why_loved": "great & cheap", "source_urls": ["https://x.com/a"],
         "rating": 4.5, "lat": 38.70, "lng": -9.14}

def test_placemark_has_name_and_coords():
    pm = m.placemark(PLACE)
    assert "<Placemark>" in pm and "</Placemark>" in pm
    # coordinates are lng,lat,0 order per KML spec
    assert "-9.14,38.7,0" in pm.replace(" ", "")

def test_placemark_escapes_xml():
    pm = m.placemark(PLACE)
    assert "&lt;Market&gt;" in pm and "&amp;" in pm
    assert "<Market>" not in pm.replace("<Placemark>", "")

def test_style_id_by_type():
    assert m.style_id("restaurant") == "restaurant"
    assert m.style_id("unknown-type") == "other"

def test_build_kml_skips_placeless_coords_and_counts():
    places = [PLACE, {"name": "No Coords", "type": "sight", "lat": None, "lng": None}]
    kml, n = m.build_kml("Lisbon", places)
    assert kml.startswith("<?xml") and "<kml" in kml
    assert kml.count("<Placemark>") == 1 and n == 1
    assert "Lisbon" in kml

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
cd travel-assistant/scripts && python3 test_build_map.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'build_map'`.

- [ ] **Step 3: Write minimal implementation**

Create `travel-assistant/scripts/build_map.py`:
```python
#!/usr/bin/env python3
"""Geocode places (Nominatim/OpenStreetMap) and emit a KML for Google My Maps import.

WHY KML: Google Maps has no public API to add pins to a user's saved lists. The
robust path is Google My Maps -> Create new map -> Import -> select this .kml,
which drops every place as a colored pin on one shareable map (also visible in
the Google Maps app under Your places -> Maps).

Geocoding uses Nominatim (free, no API key). Usage policy: <=1 req/sec and a
descriptive User-Agent. Pins are colored by place type.
"""
import json, os, re, time, argparse, urllib.parse, urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "openpaw-travel-assistant/1.0 (personal trip planning)"
TYPE_COLORS = {  # KML line/icon colors are aabbggrr hex
    "restaurant": "ff0000ff", "cafe": "ff00a5ff", "bar": "ff800080",
    "sight": "ff00ff00", "shop": "ffff0000", "other": "ff808080",
}

def style_id(place_type):
    return place_type if place_type in TYPE_COLORS else "other"

def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def placemark(p):
    sid = style_id(p.get("type", "other"))
    desc_parts = []
    if p.get("why_loved"): desc_parts.append(p["why_loved"])
    if p.get("area"): desc_parts.append("Area: " + str(p["area"]))
    if p.get("rating") not in (None, ""): desc_parts.append("Rating: " + str(p["rating"]))
    for u in p.get("source_urls", []) or []:
        desc_parts.append(u)
    desc = _esc("\n".join(desc_parts))
    return (f"    <Placemark>\n"
            f"      <name>{_esc(p.get('name',''))}</name>\n"
            f"      <description>{desc}</description>\n"
            f"      <styleUrl>#{sid}</styleUrl>\n"
            f"      <Point><coordinates>{p['lng']},{p['lat']},0</coordinates></Point>\n"
            f"    </Placemark>")

def _styles():
    out = []
    for sid, color in TYPE_COLORS.items():
        out.append(f'    <Style id="{sid}"><IconStyle><color>{color}</color></IconStyle></Style>')
    return "\n".join(out)

def build_kml(destination, places):
    marks, n = [], 0
    for p in places:
        if p.get("lat") is None or p.get("lng") is None:
            continue
        marks.append(placemark(p)); n += 1
    body = "\n".join(marks)
    kml = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<kml xmlns="http://www.opengis.net/kml/2.2">\n'
           f'  <Document>\n'
           f'    <name>{_esc("Travel — " + destination)}</name>\n'
           f'{_styles()}\n'
           f'{body}\n'
           f'  </Document>\n'
           f'</kml>\n')
    return kml, n

def geocode(query):
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            hits = json.loads(r.read().decode())
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception as e:
        print(f"  geocode err [{query}]: {e}")
    return None, None

def enrich_and_build(path):
    obj = json.load(open(path, encoding="utf-8"))
    dest = obj.get("destination", "")
    for p in obj.get("places", []):
        if p.get("lat") is None or p.get("lng") is None:
            q = " ".join(str(x) for x in [p.get("name",""), p.get("area",""), dest] if x)
            p["lat"], p["lng"] = geocode(q)
            time.sleep(1.1)  # Nominatim: <=1 req/sec
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    kml, n = build_kml(dest, obj.get("places", []))
    maps_dir = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    os.makedirs(maps_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", dest.strip().lower()).strip("_") or "map"
    out = os.path.join(maps_dir, f"{slug}.kml")
    open(out, "w", encoding="utf-8").write(kml)
    print(f"[{slug}] {n} pins -> {out}")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="path to a validated {slug}_places_*.json")
    a = ap.parse_args()
    enrich_and_build(a.file)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd travel-assistant/scripts && python3 test_build_map.py
```
Expected: `PASS test_placemark_has_name_and_coords` … `all passed`

- [ ] **Step 5: Add the maps data dir keep file**

```bash
touch travel-assistant/data/maps/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add travel-assistant/scripts/build_map.py travel-assistant/scripts/test_build_map.py travel-assistant/data/maps/.gitkeep
git commit -m "feat(travel): geocode + KML map builder for Google My Maps"
```

---

### Task 9: SKILL.md — build the Google Map step

**Files:**
- Modify: `travel-assistant/SKILL.md` (insert a map step and update the workflow one-liner)

- [ ] **Step 1: Append the Google Map step after the publish section**

Append to `travel-assistant/SKILL.md` (after the `## Common mistakes` section):
```markdown
## Step 7 — Build the Google Map (pins for the trip)
After the places JSON is validated (and geocoded for `map_link`), build the map file:
```bash
python3 scripts/build_map.py data/analysis/{slug}_places_{ts}.json
```
`build_map.py` geocodes each place to lat/lng via Nominatim (writes `lat`/`lng` back
into the JSON) and emits `data/maps/{slug}.kml` with one colored pin per place.

Then tell the user how to load it (this is the "mark in Google Maps" step):
1. Open **Google My Maps** (mymaps.google.com) → **Create a new map**.
2. **Import** → upload `data/maps/{slug}.kml`.
3. All places appear as colored pins on one map (by type). It's now under
   *Your places → Maps* in the Google Maps app on phone + desktop.

Run this even under `--no-publish` (the KML is the deliverable); only the Notion
step is skipped in that mode.
```

- [ ] **Step 2: Update the workflow one-liner in the Overview**

In `travel-assistant/SKILL.md`, the earlier fallback block ends the collect section.
No change needed there. Just verify the map step is present:
```bash
grep -q "Step 7 — Build the Google Map" travel-assistant/SKILL.md && grep -q "build_map.py" travel-assistant/SKILL.md && echo "map step OK"
```
Expected: `map step OK`

- [ ] **Step 3: Commit**

```bash
git add travel-assistant/SKILL.md
git commit -m "docs(travel): SKILL Google My Maps build step"
```

---

### Task 10: README + end-to-end dry run

**Files:**
- Create: `travel-assistant/README.md`

- [ ] **Step 1: Write the README**

Create `travel-assistant/README.md`:
```markdown
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
build map (KML for Google My Maps) → publish (Notion).

The map is delivered as a `.kml` you import into Google My Maps (Create map →
Import), producing one map with a colored pin per place — visible in the Google
Maps app under *Your places → Maps*. See `SKILL.md` for the full workflow and
`docs/superpowers/specs/2026-07-02-travel-assistant-design.md` for rationale.
Booking and multi-day route *sequencing* are planned future phases.

## Scripts
- `scripts/collect_rednote.py` — rednote collector (drives the browse browser).
- `scripts/validate_places.py` — validates analyzer output before publishing.
- `scripts/build_map.py` — geocodes places and emits the Google My Maps KML.
- `python3 scripts/test_*.py` — run the unit tests for the pure helpers.
```

- [ ] **Step 2: Run all unit tests once more (regression gate)**

Run:
```bash
cd travel-assistant/scripts && python3 test_collect_rednote.py && python3 test_validate_places.py && python3 test_build_map.py
```
Expected: all three print `all passed`.

- [ ] **Step 3: End-to-end dry run (manual, real destination)**

Verify the full skill flow with publishing off. Invoke `/travel-research Lisbon --no-publish`
and confirm: the collector writes a raw file (or the fallback triggers with a printed
notice), the analyzer produces `data/analysis/lisbon_places_*.json`,
`python3 scripts/validate_places.py data/analysis/lisbon_places_*.json` prints `valid`,
and `python3 scripts/build_map.py data/analysis/lisbon_places_*.json` writes
`data/maps/lisbon.kml` with a pin count > 0. Open the KML in Google My Maps (Import)
and confirm pins appear. If rednote is login-walled, confirm the WebSearch fallback
path runs and `source_mode` is `fallback`.

- [ ] **Step 4: Commit**

```bash
git add travel-assistant/README.md
git commit -m "docs(travel): README + dry-run verification"
```

---

## Self-Review

**Spec coverage:**
- Hybrid data source (browse rednote + WebSearch/Maps fallback) → Tasks 3, 5 (collect), Task 5-SKILL Step 2 (fallback). ✓
- Claude Code skill shape (`/travel-research`) → Task 1 frontmatter, Task 10 README. ✓
- Units (collector / analyzer / geocoder / map builder / publisher) → collector Tasks 2–3; analyzer Task 6; geocoder Task 7 Step 5 + Task 8 (lat/lng via Nominatim); map builder Task 8; publisher Task 7 Step 6. ✓
- "Every place cites a real source" principle → Task 1 overview, Task 6 rules, Task 4 validator enforces non-empty `source_urls`. ✓
- Notion schema (all 10 fields) → Task 7 Step 1 matches the spec table. ✓
- Google Map marking (My Maps via KML, geocode via Nominatim, colored pins) → Task 8 (build_map.py + KML), Task 9 (SKILL import step), Task 10 README. ✓
- Error handling (login-wall fallback, thin coverage, Notion failure keeps JSON, geocode miss skips pin, `--no-publish` still builds KML) → Task 5 Step 2, Task 7 Step 6.4, Task 8 `build_kml` skips null coords, Task 9 note. ✓
- Testing (collector helpers, validator, KML builder, e2e dry run) → Tasks 2, 4, 8, 10. Collector's browser layer, the analyzer subagent, Notion MCP, and live Nominatim/geocoding are verified via the dry run (Task 3 Step 2, Task 10 Step 3) because they depend on live login/LLM/MCP/network and the repo has no mocking harness — matching `market-research`'s zero-framework convention. ✓
- Out-of-scope (booking, multi-day route *sequencing*) explicitly deferred → Task 1 overview, README. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every verify step shows an exact command + expected output.

**Type consistency:** `slugify`, `dedup_by_url`, `rank_by_likes` (Task 2) are the names used in `collect()` (Task 3), and `eval_js(js, prefix)` (Task 3, corrected) matches its callers. `validate(obj) -> (ok, errors)` (Task 4) matches its test and the SKILL Step 4 usage. `placemark`/`style_id`/`build_kml`/`enrich_and_build` (Task 8) match `test_build_map.py`. The places-object keys in the shared contract (incl. `lat`/`lng`), the analyzer prompt (Task 6), the validator (Task 4), the map builder (Task 8), and the Notion mapping (Task 7) all agree.
