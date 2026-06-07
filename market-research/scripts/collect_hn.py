#!/usr/bin/env python3
"""Collect HackerNews discussions via the free Algolia API (no auth, no browser).

Usage:
    python3 collect_hn.py --domain ml_engineer --queries "MLOps,GPU training,experiment tracking"
    python3 collect_hn.py --domain ml_engineer --queries-file queries.json   # JSON array of strings

Output: data/raw/{domain}_hn_{timestamp}.json  (schema compatible with the analyzer)

Why a list of focused queries beats one long phrase: Algolia ranks by keyword
match, so "MLOps" + "GPU training" each return sharp results, while a 12-word
natural-language query returns noise. Run several, dedup by objectID.
"""
import urllib.request, urllib.parse, json, re, time, os, argparse
from datetime import datetime, timezone

DATA_RAW = os.environ.get("MR_DATA_RAW",
    "/Users/duochen/Desktop/career/workflow/claude_code/data/raw")


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "market-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def search(query, max_stories=15, min_points=10):
    q = urllib.parse.quote(query)
    url = (f"https://hn.algolia.com/api/v1/search?query={q}&tags=story"
           f"&hitsPerPage={max_stories}&numericFilters=points%3E{min_points}")
    try:
        return fetch_json(url).get("hits", [])
    except Exception as e:
        print(f"  search err [{query}]: {e}")
        return []


def clean(t):
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", "", t)
    for a, b in [("&#x27;", "'"), ("&gt;", ">"), ("&lt;", "<"),
                 ("&amp;", "&"), ("&quot;", '"'), ("&#x2F;", "/")]:
        t = t.replace(a, b)
    return t.strip()


def extract_comments(node, depth=0, max_depth=3, collected=None):
    if collected is None:
        collected = []
    if depth > max_depth:
        return collected
    for child in node.get("children", []):
        if child.get("type") == "comment" and child.get("text"):
            collected.append({
                "id": str(child.get("id", "")), "author": child.get("author", ""),
                "created_utc": child.get("created_at", ""), "score": child.get("points") or 0,
                "content": clean(child.get("text", "")), "depth": depth})
        extract_comments(child, depth + 1, max_depth, collected)
    return collected


def collect(domain, queries, max_comments=25):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    session_id = f"{domain}_hn_{ts}"
    os.makedirs(DATA_RAW, exist_ok=True)
    out_file = os.path.join(DATA_RAW, f"{session_id}.json")

    seen, stories = set(), []
    for q in queries:
        for h in search(q):
            oid = h["objectID"]
            if oid in seen:
                continue
            seen.add(oid)
            stories.append(h)
        time.sleep(0.3)
    print(f"[{domain}] {len(stories)} unique stories across {len(queries)} queries")

    discussions = []
    for s in stories:
        sid = s["objectID"]
        try:
            item = fetch_json(f"https://hn.algolia.com/api/v1/items/{sid}")
            comments = extract_comments(item)[:max_comments]
            discussions.append({
                "id": str(sid), "url": f"https://news.ycombinator.com/item?id={sid}",
                "external_url": s.get("url", ""), "title": s.get("title", ""),
                "source": "hackernews", "subreddit": "hackernews", "author": s.get("author", ""),
                "created_utc": s.get("created_at", ""), "score": s.get("points", 0),
                "num_comments": s.get("num_comments", 0),
                "content": clean(s.get("story_text") or ""), "comments": comments})
            time.sleep(0.25)
        except Exception as e:
            print(f"  item err {sid}: {e}")

    discussions = [d for d in discussions if d["comments"]]
    data = {"session_id": session_id, "source": "hackernews",
            "search_query": queries[0] if queries else "", "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(), "discussions": discussions}
    json.dump(data, open(out_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    tc = sum(len(d["comments"]) for d in discussions)
    print(f"[{domain}] saved {len(discussions)} discussions, {tc} comments -> {out_file}")
    for t in sorted(discussions, key=lambda d: d["score"], reverse=True)[:5]:
        print(f"   {t['score']}pts  {t['title'][:70]}")
    return out_file


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True)
    ap.add_argument("--queries", help="comma-separated search queries")
    ap.add_argument("--queries-file", help="path to JSON array of query strings")
    ap.add_argument("--max-comments", type=int, default=25)
    a = ap.parse_args()
    if a.queries_file:
        qs = json.load(open(a.queries_file))
    elif a.queries:
        qs = [q.strip() for q in a.queries.split(",") if q.strip()]
    else:
        raise SystemExit("provide --queries or --queries-file")
    collect(a.domain, qs, a.max_comments)
