#!/usr/bin/env python3
"""Collect Reddit discussions via the gstack `browse` headless browser + old.reddit.com.

WHY THIS WAY (hard-won gotchas):
  - Reddit's JSON API (www.reddit.com/search.json) and new Reddit return HTTP 403
    to scripts and headless browsers. DO NOT use them.
  - old.reddit.com renders server-side HTML and works in `browse` IF you set a
    desktop browser User-Agent first.
  - Sitewide search with sort=top&t=all pulls VIRAL JUNK (a query for "Bee" returns
    top-all-time posts that merely contain the word). Use sort=relevance + t=year
    AND post-filter titles to contain a required keyword.
  - For named products/companies, pull `top` posts from the dedicated subreddit
    (every post is on-topic) instead of searching.

Config is a JSON file describing what to collect:
{
  "domain": "ai_wearables",
  "sub_tasks":   [{"label":"Rabbit R1","subreddit":"RabbitR1","n":6}, ...],
  "search_tasks":[{"label":"Plaud","query":"\"Plaud\"","keywords":["plaud"],"n":4}, ...],
  "min_score": 5,          // for search_tasks only
  "max_comments": 30
}

Usage:
    python3 collect_reddit.py --config config.json

Output: data/raw/{domain}_{timestamp}.json
"""
import subprocess, json, time, os, urllib.parse, argparse, glob
from datetime import datetime, timezone

DATA_RAW = os.environ.get("MR_DATA_RAW",
    "/Users/duochen/Desktop/career/workflow/claude_code/data/raw")

def find_browse():
    for p in [os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")]:
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
    run(["goto", url], timeout)
    time.sleep(1.5)

# Listing extractor for a subreddit front/top page (#siteTable .thing.link)
LIST_SUB_JS = r'''(()=>{const o=[];document.querySelectorAll('#siteTable .thing.link').forEach(el=>{const a=el.querySelector('a.title');const sc=el.querySelector('.score.unvoted');const pl=el.getAttribute('data-permalink');const cm=el.getAttribute('data-comments-count');if(!a)return;o.push({title:a.innerText.trim(),url:pl?('https://old.reddit.com'+pl):a.href,score:sc?(sc.getAttribute('title')||sc.innerText).replace(/[^0-9]/g,''):'0',num_comments:cm||'0',subreddit:el.getAttribute('data-subreddit')||''});});return JSON.stringify(o);})()'''
# Listing extractor for a search results page (.search-result-link)
LIST_SEARCH_JS = r'''(()=>{const o=[];document.querySelectorAll('.search-result-link').forEach(el=>{const t=el.querySelector('a.search-title');const sc=el.querySelector('.search-score');const cm=el.querySelector('.search-comments');const sb=el.querySelector('.search-subreddit-link');if(!t)return;o.push({title:t.innerText.trim(),url:t.href,score:sc?sc.innerText.replace(/[^0-9]/g,''):'0',num_comments:cm?cm.innerText.replace(/[^0-9]/g,''):'0',subreddit:sb?sb.innerText.trim():''});});return JSON.stringify(o);})()'''
# Post + comments extractor
COMMENTS_JS = r'''(()=>{let content='';const sd=document.querySelector('.expando .usertext-body, #siteTable .usertext-body');if(sd)content=sd.innerText.trim();const lk=document.querySelector('.thing.link');const sub=lk?lk.getAttribute('data-subreddit'):'';const author=lk?lk.getAttribute('data-author'):'';const comments=[];document.querySelectorAll('.commentarea .thing.comment').forEach(c=>{const b=c.querySelector('.usertext-body .md');const sc=c.querySelector('.score.unvoted');if(!b)return;const tx=b.innerText.trim();if(!tx||tx==='[deleted]'||tx==='[removed]')return;comments.push({author:c.getAttribute('data-author')||'',score:sc?(sc.getAttribute('title')||sc.innerText).replace(/[^0-9-]/g,''):'0',content:tx,depth:0});});return JSON.stringify({subreddit:sub||'',author:author||'',content:content,comments:comments});})()'''


def eval_js(js, prefix):
    with open("/tmp/_mr_eval.js", "w") as f:
        f.write(js)
    raw = run(["eval", "/tmp/_mr_eval.js"])
    ln = [l for l in raw.splitlines() if l.strip().startswith(prefix)]
    if not ln:
        return None
    try:
        return json.loads(ln[-1])
    except Exception:
        return None


def get_post(url, max_comments):
    goto(url)
    pd = eval_js(COMMENTS_JS, "{")
    if pd:
        pd["comments"] = pd.get("comments", [])[:max_comments]
    return pd


def collect(cfg):
    domain = cfg["domain"]
    min_score = cfg.get("min_score", 5)
    max_comments = cfg.get("max_comments", 30)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sid = f"{domain}_{ts}"
    os.makedirs(DATA_RAW, exist_ok=True)
    out_file = os.path.join(DATA_RAW, f"{sid}.json")

    # warm up daemon + set desktop UA (required or old.reddit may block)
    run(["goto", "https://old.reddit.com"])
    run(["useragent", UA])

    seen, disc = set(), []

    for t in cfg.get("sub_tasks", []):
        sub, n, label = t["subreddit"], t.get("n", 6), t.get("label", t["subreddit"])
        goto(f"https://old.reddit.com/r/{sub}/top/?sort=top&t=all")
        items = eval_js(LIST_SUB_JS, "[") or []
        items = [i for i in items if i["url"] not in seen]
        for i in items:
            i["score_int"] = int(i.get("score", "0") or 0)
        items.sort(key=lambda x: x["score_int"], reverse=True)
        picked = items[:n]
        print(f"[{label} | r/{sub}] {len(items)} posts -> {len(picked)}")
        for it in picked:
            seen.add(it["url"])
            pd = get_post(it["url"], max_comments)
            if not pd or not pd.get("comments"):
                continue
            disc.append(_mk(label, it, pd, sub))
            print(f"   {it['score_int']}pts {len(pd['comments'])}c  {it['title'][:50]}")
            time.sleep(0.3)

    for t in cfg.get("search_tasks", []):
        q, kws, n, label = t["query"], [k.lower() for k in t.get("keywords", [])], t.get("n", 4), t.get("label", t["query"])
        srt = t.get("sort", "relevance")
        tt = t.get("t", "year")
        goto(f"https://old.reddit.com/search?q={urllib.parse.quote(q)}&sort={srt}&t={tt}&type=link")
        items = eval_js(LIST_SEARCH_JS, "[") or []
        # REQUIRED: title must contain a keyword, else search returns off-topic viral posts
        items = [i for i in items
                 if (not kws or any(k in i["title"].lower() for k in kws)) and i["url"] not in seen]
        for i in items:
            i["score_int"] = int(i.get("score", "0") or 0)
        items = [i for i in items if i["score_int"] >= min_score]
        items.sort(key=lambda x: x["score_int"], reverse=True)
        picked = items[:n]
        print(f"[{label} | search {q}] {len(items)} on-topic -> {len(picked)}")
        for it in picked:
            seen.add(it["url"])
            pd = get_post(it["url"], max_comments)
            if not pd or not pd.get("comments"):
                continue
            disc.append(_mk(label, it, pd, it.get("subreddit", "")))
            print(f"   {it['score_int']}pts {len(pd['comments'])}c  {it['title'][:50]}")
            time.sleep(0.3)

    data = {"session_id": sid, "source": "reddit", "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(), "discussions": disc}
    json.dump(data, open(out_file, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    tc = sum(len(d["comments"]) for d in disc)
    print(f"\n[{domain}] saved {len(disc)} discussions, {tc} comments -> {out_file}")
    return out_file


def _mk(label, it, pd, sub):
    return {"label": label, "title": it["title"], "url": it["url"],
            "subreddit": pd.get("subreddit") or sub, "score": it.get("score_int", 0),
            "num_comments": int(it.get("num_comments", "0") or 0),
            "content": pd.get("content", ""), "comments": pd["comments"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    try:
        collect(cfg)
    finally:
        run(["stop"])  # free the browser daemon
