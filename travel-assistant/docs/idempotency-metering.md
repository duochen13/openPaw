# Idempotency, caching, metering & rate limits

## Idempotency keys

`POST /v1/research` honours a client-supplied `idempotency_key`:

- **First-write-wins.** Re-POSTing the same key returns the **original**
  job — `202` with the original `job_id`, current `status`, and
  `"idempotent_replay": true`. No duplicate pipeline run is launched.
- An `idempotency_key` **opts the request out of the TTL result cache**:
  idem-keyed requests dedup through the idempotency registry, keeping
  dedup semantics deterministic regardless of cache state.
- **`fresh=true` beats `idempotency_key`.** With `?fresh=true` (or
  `"fresh": true` in the body), the pipeline re-runs and the **new** job is
  registered under the key.

Keys are process-local (like jobs) and do not survive restarts. Choose
keys deterministically (e.g. `f"{destination}-{vibe}-{collector}"`) so a
restarted client resumes rather than duplicates.

## TTL result cache

A repeat `POST /v1/research` **without** `idempotency_key` and without
`fresh=true` first checks the TTL cache, keyed by
`(destination, vibe, collector, region, queries-hash, skip_geocode, from_analysis)`:

- **Hit** → `200` (note: not 202) with the stored result,
  `"cached": true`, `"cache_hit": true`, and `"ttl_remaining_s"`.
  The pipeline is **not** re-run.
- **Miss** → normal enqueue (`202`).

TTL is per-category with **shortest-category-wins**: a run's TTL is the
shortest category TTL among its places (see `cache.CATEGORY_TTLS`), so a
mixed run expires on the restaurant schedule. `?fresh=true` bypasses the
cache, re-runs, returns `"cached": false`, and refreshes the entry.

## Cost tiers & metering

Every `/v1` call appends a row to the `usage` table. The cost tier is:

- `"fresh"` — **iff** the call enqueued a **new** pipeline run.
- `"cached"` — everything else: cache hits, idempotent replays, polls,
  rejected calls.

There are **no price points** — the tier strings are the whole pricing
signal (a business decision, out of scope for the API). Audit your own
usage:

```bash
curl -s $BASE/v1/usage -H "Authorization: Bearer $TA_KEY"
```

```json
{
  "key_id": 3,
  "total_calls": 41,
  "by_endpoint": {"POST /v1/research": 5, "GET /v1/research/{job_id}": 30},
  "by_cost_tier": {"fresh": 2, "cached": 39},
  "cached_calls": 39,
  "fresh_calls": 2,
  "key_name": "agent-alpha"
}
```

(`GET /v1/usage` is a non-spec extra — it isn't part of the v1 contract,
it exists so key holders can audit themselves.) Metering never breaks the
API: a broken usage store is logged and swallowed.

## Rate limits

`429 rate_limited` is a **process-level** guard: `POST /v1/research` is
rejected when unfinished jobs (`queued` + `running`) reach
`TA_SERVICE_MAX_QUEUED` (default 8). Poll an existing job or retry later
with backoff. Per-key quotas are future work.
