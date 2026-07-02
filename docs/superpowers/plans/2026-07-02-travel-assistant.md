# Travel Assistant — Destination Research (v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Claude Code skill `/travel-research <destination>` that mines rednote (Xiaohongshu) for places/restaurants people love, deduplicates and ranks them with cited quotes, and publishes one row per place to a Notion database.

**Architecture:** Mirrors the existing `market-research` skill exactly — a `SKILL.md` orchestration doc plus Python helper scripts that drive the gstack `browse` headless-browser binary. Collection is a Python script (`collect_rednote.py`); analysis is a dispatched general-purpose subagent (LLM, documented in SKILL.md); geocoding uses `WebSearch`; publishing uses the connected `notion` MCP tools driven by Claude. A small pure-Python validator (`validate_places.py`) gates the analyzer output before publish, and is the one piece under automated tests.

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
    test_collect_rednote.py     # asserts pure helpers: slugify/dedup/rank
    test_validate_places.py     # asserts schema validation
  data/
    raw/.gitkeep                # {slug}_rednote_{ts}.json (collector output)
    analysis/.gitkeep           # {slug}_places_{ts}.json (analyzer output)
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
      "tags": ["food-hall", "must-book"]
    }
  ]
}
```
Enums: `type` ∈ {restaurant, sight, cafe, bar, shop, other}; `sentiment` ∈ {positive, mixed, negative}; `source_mode` ∈ {rednote, fallback, mixed}. `map_link`/`rating` are `null` until the geocode step fills them.

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
import subprocess, json, os, re, time, argparse, glob, urllib.parse
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

def eval_js(js):
    out = run(["eval", js])
    try:
        start = out.index("[") if "[" in out else out.index("{")
        return json.loads(out[start:out.rindex("]" if "[" in out else "}") + 1])
    except Exception:
        return []

# BEST-EFFORT selectors — verify live in Step 2 and adjust before relying on output.
SEARCH_LIST_JS = r'''(()=>{const o=[];document.querySelectorAll('section.note-item, div.note-item').forEach(el=>{const a=el.querySelector('a[href*="/explore/"], a[href*="/search_result/"]');const t=el.querySelector('.title, span.title, .footer .title');const lk=el.querySelector('.like-wrapper .count, .count');if(!a)return;o.push({title:(t?t.innerText:'').trim(),url:a.href,likes:(lk?lk.innerText:'0').replace(/[^0-9]/g,'')||'0'});});return JSON.stringify(o);})()'''
POST_JS = r'''(()=>{const c=document.querySelector('#detail-desc, .note-content, .desc');const cs=[];document.querySelectorAll('.comment-item .content, .comments-container .content').forEach(e=>{const t=e.innerText.trim();if(t)cs.push(t);});return JSON.stringify({content:c?c.innerText.trim():'',comments:cs.slice(0,20)});})()'''

def get_post(url):
    goto(url)
    out = run(["eval", POST_JS])
    try:
        start = out.index("{"); return json.loads(out[start:out.rindex("}") + 1])
    except Exception:
        return {"content": "", "comments": []}

def collect(destination, queries, n_per_query=6):
    run(["set-ua", UA])
    slug = slugify(destination)
    sid = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    all_items = []
    for q in queries:
        url = "https://www.xiaohongshu.com/search_result?keyword=" + urllib.parse.quote(q)
        goto(url)
        items = eval_js(SEARCH_LIST_JS)
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

Then verify the DOM selectors against live rednote using the browse tool directly (selectors change often; this step confirms/repairs them):
```bash
~/.claude/skills/gstack/browse/dist/browse set-ua "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
~/.claude/skills/gstack/browse/dist/browse goto "https://www.xiaohongshu.com/search_result?keyword=%E9%87%8C%E6%96%AF%E6%9C%AC%E7%BE%8E%E9%A3%9F"
~/.claude/skills/gstack/browse/dist/browse eval 'document.querySelectorAll("section.note-item, div.note-item").length'
~/.claude/skills/gstack/browse/dist/browse stop
```
Expected: a non-zero count if logged in. If it prints `0`, either (a) not logged in → the login wall is up (expected → SKILL.md fallback handles it), or (b) selectors drifted → inspect the page and update `SEARCH_LIST_JS`/`POST_JS`, then re-run. Record the working selectors.

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

### Task 8: README + end-to-end dry run

**Files:**
- Create: `travel-assistant/README.md`

- [ ] **Step 1: Write the README**

Create `travel-assistant/README.md`:
```markdown
# Travel Research

A Claude Code skill that mines rednote (Xiaohongshu) for the places and restaurants
people love in a destination, then publishes them to a Notion database.

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
analyze (subagent dedup/rank with cited quotes) → validate → geocode → publish (Notion).

See `SKILL.md` for the full workflow and `docs/superpowers/specs/2026-07-02-travel-assistant-design.md`
for the design rationale. Booking and Maps route-marking are planned future phases.

## Scripts
- `scripts/collect_rednote.py` — rednote collector (drives the browse browser).
- `scripts/validate_places.py` — validates analyzer output before publishing.
- `python3 scripts/test_*.py` — run the unit tests for the pure helpers.
```

- [ ] **Step 2: Run all unit tests once more (regression gate)**

Run:
```bash
cd travel-assistant/scripts && python3 test_collect_rednote.py && python3 test_validate_places.py
```
Expected: both print `all passed`.

- [ ] **Step 3: End-to-end dry run (manual, real destination)**

Verify the full skill flow with publishing off. Invoke `/travel-research Lisbon --no-publish`
and confirm: the collector writes a raw file (or the fallback triggers with a printed
notice), the analyzer produces `data/analysis/lisbon_places_*.json`, and
`python3 scripts/validate_places.py data/analysis/lisbon_places_*.json` prints `valid`.
If rednote is login-walled, confirm the WebSearch fallback path runs and `source_mode`
is `fallback`.

- [ ] **Step 4: Commit**

```bash
git add travel-assistant/README.md
git commit -m "docs(travel): README + dry-run verification"
```

---

## Self-Review

**Spec coverage:**
- Hybrid data source (browse rednote + WebSearch/Maps fallback) → Tasks 3, 5 (collect), Task 5-SKILL Step 2 (fallback). ✓
- Claude Code skill shape (`/travel-research`) → Task 1 frontmatter, Task 8 README. ✓
- Units (collector / analyzer / geocoder / publisher) → collector Tasks 2–3; analyzer Task 6; geocoder Task 7 Step 5; publisher Task 7 Step 6. ✓
- "Every place cites a real source" principle → Task 1 overview, Task 6 rules, Task 4 validator enforces non-empty `source_urls`. ✓
- Notion schema (all 10 fields) → Task 7 Step 1 matches the spec table. ✓
- Error handling (login-wall fallback, thin coverage, Notion failure keeps JSON, `--no-publish`) → Task 5 Step 2, Task 7 Step 6.4, Task 6 README/skip. ✓
- Testing (collector helpers, validator, e2e dry run) → Tasks 2, 4, 8. Collector's browser/analyzer/MCP layers are verified manually (Task 3 Step 2, Task 8 Step 3) because they depend on live login/LLM/MCP and the repo has no mocking harness for them — matching `market-research`'s zero-framework convention. ✓
- Out-of-scope (booking, maps-routing) explicitly deferred → Task 1 overview, README. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every verify step shows an exact command + expected output.

**Type consistency:** `slugify`, `dedup_by_url`, `rank_by_likes` (Task 2) are the names used in `collect()` (Task 3). `validate(obj) -> (ok, errors)` (Task 4) matches its test and the SKILL Step 4 usage. The places-object keys in the shared contract, the analyzer prompt (Task 6), the validator (Task 4), and the Notion mapping (Task 7) all agree.
