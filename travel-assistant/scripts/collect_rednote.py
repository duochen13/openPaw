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
