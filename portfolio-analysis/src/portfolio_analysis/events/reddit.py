"""Reddit community commentary via the Arctic Shift archive (issue #7).

Why this backend: Reddit's own unauthenticated JSON endpoints return 403 from
datacenter IPs, and Pushshift is unavailable to non-moderators, so historical
comment search needs the bulk archive the v1 spec (§4.3) said this required.
Arctic Shift (arctic-shift.photon-reddit.com) is that archive: no auth, keyed
comment search scoped to a subreddit, results ranked client-side by score.

The archive sorts by creation date only, so "ranked by Reddit score" happens
here, in pure functions that offline tests can cover. Collection is resumable:
per-event files are skipped on reruns, quota exhaustion stops the run without
touching finished events, and failed events are retried next time.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from portfolio_analysis.events.edgar import GetJson
from portfolio_analysis.events.macro import MacroSource
from portfolio_analysis.http import CachedHttp, ProviderError, QuotaExhausted, atomic_json

ARCTIC_SHIFT_BASE = "https://arctic-shift.photon-reddit.com/api"
REDDIT_BASE = "https://www.reddit.com"

#: Issue #7: at most five Reddit comments per event window, enforced after
#: deduplication and before rendering.
MAX_COMMENTS = 5

#: One `body` keyword request per (subreddit, keyword); the archive only
#: supports keyword search scoped to a subreddit, not global keyword search.
EVENT_QUERIES: dict[str, dict[str, tuple[str, ...]]] = {
    "FOMC": {"subreddits": ("economics", "investing"), "keywords": ("fomc",)},
    "CPI": {"subreddits": ("economics", "investing"), "keywords": ("cpi",)},
    "PCE": {"subreddits": ("economics", "investing"), "keywords": ("pce",)},
}

_DELETED_BODIES = frozenset({"[deleted]", "[removed]"})


@dataclass(frozen=True)
class RedditComment:
    """One Reddit comment, kept separate from Document on purpose: community
    commentary must never be presentable as a verified fact."""

    comment_id: str
    score: int
    author: str
    created_utc: int
    subreddit: str
    permalink: str
    body: str

    @property
    def url(self) -> str:
        # Permalinks from the archive always start with "/". Anything else is
        # unexpected input, so fall back to the Reddit home page rather than
        # concatenating it into a link target.
        if self.permalink.startswith("/"):
            return REDDIT_BASE + self.permalink
        return REDDIT_BASE

    def excerpt(self, limit: int = 280) -> str:
        text = " ".join(self.body.split())
        if len(text) <= limit:
            return text
        cut = text[:limit].rsplit(" ", 1)[0]
        return (cut or text[:limit]) + "…"

    def as_dict(self) -> dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "score": self.score,
            "author": self.author,
            "created_utc": self.created_utc,
            "subreddit": self.subreddit,
            "permalink": self.permalink,
            "url": self.url,
            "excerpt": self.excerpt(),
            "body": self.body,
        }


def rank_reddit_comments(
    comments: list[RedditComment], limit: int = MAX_COMMENTS
) -> list[RedditComment]:
    """Dedup by comment id (keep highest score), drop deleted/empty bodies,
    then rank by score descending with ties resolved by recency. Pure function:
    the cap is enforced here, before rendering."""
    best: dict[str, RedditComment] = {}
    for comment in comments:
        stripped = comment.body.strip()
        if not stripped or stripped in _DELETED_BODIES:
            continue
        current = best.get(comment.comment_id)
        if current is None or comment.score > current.score:
            best[comment.comment_id] = comment
    ranked = sorted(
        best.values(), key=lambda c: (c.score, c.created_utc), reverse=True
    )
    return ranked[:limit]


def _comment_from_row(row: dict[str, Any]) -> RedditComment | None:
    comment_id = row.get("id")
    body = row.get("body")
    if not isinstance(comment_id, str) or not comment_id:
        return None
    if not isinstance(body, str) or not body.strip():
        return None
    try:
        score = int(row.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    try:
        created = int(row.get("created_utc") or 0)
    except (TypeError, ValueError):
        created = 0
    permalink = row.get("permalink")
    return RedditComment(
        comment_id=comment_id,
        score=score,
        author=str(row.get("author") or "[unknown]"),
        created_utc=created,
        subreddit=str(row.get("subreddit") or ""),
        permalink=permalink if isinstance(permalink, str) else "",
        body=body,
    )


def _search_url(subreddit: str, keyword: str, start: str, end: str) -> str:
    return ARCTIC_SHIFT_BASE + "/comments/search?" + urlencode(
        {
            "subreddit": subreddit,
            "body": keyword,
            "after": start,
            "before": end,
            "limit": 100,
            "sort": "desc",
        }
    )


def fetch_event_comments(
    get_json: GetJson,
    event_type: str,
    event_date: str,
    *,
    daily_limit: int | None,
) -> tuple[list[RedditComment], str]:
    """Collect ranked Reddit comments for one macro event window.

    Returns (comments, status) where status is "ok", "no_results", or "error".
    Provider errors become an explicit "error" status rather than an exception
    so one bad event never erases the rest of the collection.
    """
    query = EVENT_QUERIES.get(event_type)
    if query is None:
        return [], "no_results"
    day = date.fromisoformat(event_date)
    start = (day - timedelta(days=1)).isoformat()
    end = (day + timedelta(days=2)).isoformat()
    gathered: list[RedditComment] = []
    try:
        for subreddit in query["subreddits"]:
            for keyword in query["keywords"]:
                payload = get_json(
                    "arctic_shift",
                    _search_url(subreddit, keyword, start, end),
                    daily_limit=daily_limit,
                    max_age=None,  # historical windows are immutable; cache forever
                )
                rows = payload.get("data")
                if not isinstance(rows, list):
                    raise ProviderError("arctic_shift: missing data list")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    comment = _comment_from_row(row)
                    if comment is None:
                        continue
                    # Server-side keyword match is token-based; keep only
                    # comments that actually mention the keyword.
                    if keyword.lower() not in comment.body.lower():
                        continue
                    gathered.append(comment)
    except (ProviderError, ValueError, KeyError, TypeError) as exc:
        return [], f"error: {type(exc).__name__}"
    ranked = rank_reddit_comments(gathered)
    return ranked, "ok" if ranked else "no_results"


@dataclass(frozen=True)
class RedditCollectionResult:
    completed: int
    remaining: int
    quota_exhausted: bool = False


def collect_reddit_for_events(
    calendar: MacroSource,
    reddit_dir: Path,
    http: CachedHttp,
    *,
    daily_limit: int | None = 400,
    rebuild: bool = False,
    report: Callable[[str], None] = print,
) -> RedditCollectionResult:
    """Fetch Reddit commentary for every macro event, resumably.

    Each event gets one JSON file, `<TYPE>_<date>.json`. Events already
    collected ("ok"/"no_results") are skipped; "error" files are retried.
    Quota exhaustion stops the run immediately — finished events keep their
    files, so a rerun picks up where this one stopped.
    """
    events = sorted(
        (kind, row["date"])
        for kind, rows in calendar.catalog().items()
        for row in rows
    )
    completed = 0
    for kind, event_date in events:
        target = reddit_dir / f"{kind}_{event_date}.json"
        if not rebuild and target.exists():
            try:
                if json.loads(target.read_text()).get("status") in ("ok", "no_results"):
                    completed += 1
                    continue
            except (ValueError, OSError):
                pass  # corrupt file: re-collect below
        try:
            comments, status = fetch_event_comments(
                http.get_json, kind, event_date, daily_limit=daily_limit
            )
        except QuotaExhausted:
            return RedditCollectionResult(completed, len(events) - completed, True)
        atomic_json(
            target,
            {
                "event_type": kind,
                "event_date": event_date,
                "status": status,
                "comments": [comment.as_dict() for comment in comments],
            },
        )
        completed += 1
        report(f"{kind} {event_date}: {status}, {len(comments)} comments -> {target.name}")
    return RedditCollectionResult(completed, 0, False)
