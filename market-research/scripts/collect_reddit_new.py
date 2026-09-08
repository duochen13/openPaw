#!/usr/bin/env python3
"""Collect Reddit discussions via the gstack `browse` headless browser + www.reddit.com.

WHY THIS EXISTS (2026-09): old.reddit.com now hard-gates behind login
("Log in to use old Reddit"), which broke the skill's collect_reddit.py.
That script fails SILENTLY -- it returns 0 posts for every task and still
exits 0, so a run looks successful while producing an empty corpus.
New Reddit (www.reddit.com) renders fine in `browse` and exposes clean
custom elements:
  - listing/search: <shreddit-post permalink post-title score comment-count
                     subreddit-prefixed-name author>
  - comment page:   <shreddit-comment author score depth> with the body in
                     div[slot="comment"]
Both feeds lazy-load, so we scroll until we have enough items.

ALSO NOTE: the browse daemon binds a local port and cannot start under the
Claude Code bash sandbox ("No available port after 5 attempts in range
10000-60000"). Run this with the sandbox disabled.

Config (same shape as the original script):
{
  "domain": "quantum_computing",
  "sub_tasks":   [{"label":"Quantum Computing","subreddit":"QuantumComputing","n":12,"t":"year"}],
  "search_tasks":[{"label":"IonQ","query":"IonQ","keywords":["ionq"],"n":6}],
  "min_score": 5,
  "max_comments": 30
}

Usage: python3 collect_reddit_new.py --config config.json
Output: $MR_DATA_RAW/{domain}_{timestamp}.json
"""
import subprocess, json, time, os, urllib.parse, argparse, glob
from datetime import datetime, timezone

DATA_RAW = os.environ.get("MR_DATA_RAW", os.path.join(os.getcwd(), "data/raw"))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def find_browse():
    p = os.path.expanduser("~/.claude/skills/gstack/browse/dist/browse")
    if os.path.exists(p):
        return p
    hits = glob.glob(os.path.expanduser("~/**/gstack/browse/dist/browse"), recursive=True)
    return hits[0] if hits else "browse"


B = find_browse()
# NOTE: browse can only read a few fixed paths; /tmp/_mr_eval.js is the one
# the sandbox policy allows. Do not move this into $TMPDIR.
_JS = "/tmp/_mr_eval.js"


def run(args, timeout=90):
    try:
        return subprocess.run([B] + args, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def eval_js(js):
    with open(_JS, "w") as f:
        f.write(js)
    raw = run(["eval", _JS])
    for ln in reversed(raw.splitlines()):
        ln = ln.strip()
        if ln.startswith("{") or ln.startswith("["):
            try:
                return json.loads(ln)
            except Exception:
                continue
    return None


LIST_JS = r'''(()=>{const o=[];document.querySelectorAll('shreddit-post').forEach(p=>{
const g=n=>p.getAttribute(n)||'';const pl=g('permalink');if(!pl)return;
o.push({title:g('post-title'),url:'https://www.reddit.com'+pl,score:g('score')||'0',
num_comments:g('comment-count')||'0',subreddit:(g('subreddit-prefixed-name')||'').replace(/^r\//,'')});});
return JSON.stringify(o);})()'''

# Search results are NOT shreddit-post elements — they render as plain anchors
# inside search-telemetry-tracker wrappers. Climb to the enclosing card to read
# the "N votes · M comments" line.
SEARCH_JS = r"""(()=>{const o=[];const seen=new Set();
document.querySelectorAll('a[data-testid="post-title-text"]').forEach(a=>{
const href=a.getAttribute('href');if(!href||seen.has(href))return;seen.add(href);
let el=a,txt='';for(let i=0;i<8&&el;i++){el=el.parentElement;if(el&&/comment/i.test(el.innerText||'')){txt=el.innerText;break;}}
const v=(txt.match(/([\d.,]+[KkMm]?)\s*(?:vote|upvote|point)/i)||[])[1]||'0';
const c=(txt.match(/([\d.,]+[KkMm]?)\s*comment/i)||[])[1]||'0';
const sr=(href.match(/^\/r\/([^/]+)\//)||[])[1]||'';
const num=s=>{s=String(s).replace(/,/g,'');const m=s.match(/^([\d.]+)([KkMm])?$/);if(!m)return 0;
let n=parseFloat(m[1]);if(/[Kk]/.test(m[2]||''))n*=1000;if(/[Mm]/.test(m[2]||''))n*=1e6;return Math.round(n);};
o.push({title:a.innerText.trim(),url:'https://www.reddit.com'+href,score:String(num(v)),num_comments:String(num(c)),subreddit:sr});});
return JSON.stringify(o);})()"""

POST_JS = r'''(()=>{const p=document.querySelector('shreddit-post');
const tb=p?p.querySelector('div[slot="text-body"]'):null;
const comments=[];document.querySelectorAll('shreddit-comment').forEach(c=>{
const b=c.querySelector('div[slot="comment"]');if(!b)return;const tx=b.innerText.trim();
if(!tx||tx==='[deleted]'||tx==='[removed]')return;
comments.push({author:c.getAttribute('author')||'',score:c.getAttribute('score')||'0',
content:tx,depth:parseInt(c.getAttribute('depth')||'0',10)});});
return JSON.stringify({subreddit:p?(p.getAttribute('subreddit-name')||''):'',
author:p?(p.getAttribute('author')||''):'',content:tb?tb.innerText.trim():'',comments:comments});})()'''

SCROLL_JS = "window.scrollTo(0,document.body.scrollHeight);'ok'"


def goto(url, wait=2.5):
    run(["goto", url])
    time.sleep(wait)


def load_listing(url, want, js=None):
    """Navigate + scroll until we have `want` posts (or the feed stops growing)."""
    js = js or LIST_JS
    goto(url, 3)
    items, last = eval_js(js) or [], -1
    tries = 0
    while len(items) < want and len(items) != last and tries < 8:
        last = len(items)
        with open(_JS, "w") as f:
            f.write(SCROLL_JS)
        run(["eval", _JS])
        time.sleep(2.0)
        items = eval_js(js) or items
        tries += 1
    return items


def get_post(url, max_comments):
    goto(url, 3)
    # one scroll pulls in the next batch of lazily-rendered comments
    with open(_JS, "w") as f:
        f.write(SCROLL_JS)
    run(["eval", _JS])
    time.sleep(2.0)
    pd = eval_js(POST_JS)
    if pd:
        cs = pd.get("comments", [])
        cs.sort(key=lambda c: int(c.get("score") or 0), reverse=True)
        pd["comments"] = cs[:max_comments]
    return pd


def _mk(label, it, pd, sub):
    return {"label": label, "title": it["title"], "url": it["url"],
            "subreddit": pd.get("subreddit") or sub, "score": it.get("score_int", 0),
            "num_comments": int(it.get("num_comments", "0") or 0),
            "content": pd.get("content", ""), "comments": pd["comments"]}


def _norm(items, seen, kws=None, min_score=0):
    out = []
    for i in items:
        if i["url"] in seen:
            continue
        if kws and not any(k in i["title"].lower() for k in kws):
            continue
        try:
            i["score_int"] = int(str(i.get("score", "0")).replace(",", "") or 0)
        except ValueError:
            i["score_int"] = 0
        if i["score_int"] < min_score:
            continue
        out.append(i)
    out.sort(key=lambda x: x["score_int"], reverse=True)
    return out


def collect(cfg):
    domain = cfg["domain"]
    min_score = cfg.get("min_score", 5)
    max_comments = cfg.get("max_comments", 30)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    sid = f"{domain}_{ts}"
    os.makedirs(DATA_RAW, exist_ok=True)
    out_file = os.path.join(DATA_RAW, f"{sid}.json")

    run(["goto", "https://www.reddit.com"])
    run(["useragent", UA])

    seen, disc = set(), []

    def harvest(label, picked, fallback_sub=""):
        for it in picked:
            seen.add(it["url"])
            pd = get_post(it["url"], max_comments)
            if not pd or not pd.get("comments"):
                print(f"   (no comments) {it['title'][:50]}")
                continue
            disc.append(_mk(label, it, pd, it.get("subreddit") or fallback_sub))
            print(f"   {it['score_int']}pts {len(pd['comments'])}c  {it['title'][:60]}")

    for t in cfg.get("sub_tasks", []):
        sub, n = t["subreddit"], t.get("n", 6)
        label, tf = t.get("label", t["subreddit"]), t.get("t", "year")
        items = _norm(load_listing(
            f"https://www.reddit.com/r/{sub}/top/?t={tf}", n + 4), seen)
        print(f"[{label} | r/{sub} top/{tf}] {len(items)} posts -> {min(n, len(items))}")
        harvest(label, items[:n], sub)

    for t in cfg.get("search_tasks", []):
        q, n = t["query"], t.get("n", 4)
        kws = [k.lower() for k in t.get("keywords", [])]
        label = t.get("label", t["query"])
        srt, tf = t.get("sort", "relevance"), t.get("t", "year")
        url = (f"https://www.reddit.com/search/?q={urllib.parse.quote(q)}"
               f"&type=posts&sort={srt}&t={tf}")
        items = _norm(load_listing(url, n + 12, SEARCH_JS), seen, kws, min_score)
        print(f"[{label} | search {q}] {len(items)} on-topic -> {min(n, len(items))}")
        harvest(label, items[:n])

    data = {"session_id": sid, "source": "reddit", "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(), "discussions": disc}
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tc = sum(len(d["comments"]) for d in disc)
    print(f"\n[{domain}] saved {len(disc)} discussions, {tc} comments -> {out_file}")
    return out_file


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    try:
        collect(json.load(open(a.config)))
    finally:
        run(["stop"])
