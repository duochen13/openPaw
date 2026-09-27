# Agent call pattern

The API is built for agents: jobs are **asynchronous** (research takes
minutes of headless-browser time), so the correct client is a small state
machine, not a single request. Machine-readable contract first: fetch
`docs/openapi.json` (or `/openapi.json` from a running service) and drive
the API from that — don't scrape these docs.

## The loop

```python
import time, httpx

BASE = "http://127.0.0.1:8000"
H = {"Authorization": f"Bearer {API_KEY}"}

def research(destination, vibe="all", collector="rednote", idem_key=None):
    # 1. Enqueue. Always send an idempotency_key: a retry after a network
    #    blip returns the ORIGINAL job instead of launching a duplicate.
    r = httpx.post(f"{BASE}/v1/research", headers=H, json={
        "destination": destination, "vibe": vibe, "collector": collector,
        "idempotency_key": idem_key or f"{destination}-{vibe}-{collector}",
    })
    if r.status_code == 429:
        time.sleep(30)                       # queue full — back off, don't spin
        return research(destination, vibe, collector, idem_key)
    r.raise_for_status()
    body = r.json()

    if r.status_code == 200 and body.get("cache_hit"):
        return body                          # TTL cache hit: result is ready now

    job_id, eta = body["job_id"], body.get("estimated_seconds", 120)

    # 2. Poll with backoff. eta is a rough heuristic (replay ~15-60s,
    #    websearch ~120s, rednote ~300s), not a guarantee.
    wait = min(max(eta / 6, 5), 30)
    while True:
        time.sleep(wait)
        p = httpx.get(f"{BASE}/v1/research/{job_id}", headers=H)
        if p.status_code == 500:
            err = p.json()                   # {"status": "failed", "code": ...}
            return handle_failure(err)
        job = p.json()
        if job["status"] == "done":
            break
        wait = min(wait * 1.5, 60)           # gentle backoff while running

    # 3. Inspect quality signals before trusting the result.
    if job.get("degraded"):
        # Fallback served it: job["collector"] != job["collector_requested"].
        # Places carry true per-place `source` labels — surface that.
        note_degraded(job["collector_requested"], job["collector"])
    return job

def handle_failure(err):
    code = err.get("code")
    if code == "source_unavailable":
        # Collector backend down (or primary + fallback both failed).
        # Retry later, or re-enqueue with collector="websearch".
        raise Retryable(code, err.get("detail"))
    # pipeline_error: a real bug or missing config (e.g. no analyzer) —
    # do NOT blind-retry; surface err["detail"] to the operator.
    raise Fatal(code, err.get("detail"))
```

## Rules of the road

- **Idempotency keys are mandatory in practice.** Derive them
  deterministically from the request (`f"{destination}-{vibe}-{collector}"`)
  so a crashed-and-restarted agent resumes the same job instead of
  double-enqueueing. Replays return `202` with `"idempotent_replay": true`.
- **Respect `estimated_seconds`, then back off.** Polling every 2 seconds
  for a 5-minute rednote job just burns your `cached`-tier quota.
- **`degraded: true` is not failure.** The result is usable — but tell the
  user which collector actually served it (`collector` vs
  `collector_requested`) and that per-place `source` labels reflect reality.
- **A `200` on POST means "already answered."** `cache_hit: true` results
  are complete — don't poll afterwards.
- **`fresh: true` is a deliberate re-run.** It bypasses the TTL cache and
  beats idempotency — use it when the user explicitly asks for new data,
  not as a default.
- **Jobs are process-local.** A service restart wipes the registry: an old
  `job_id` becomes `404 not_found`. Persist the final result, not the job id.
- **Fetch the map bundle only for `done` jobs** via `map_bundle_url`
  (`/v1/maps/{job_id}.html`); before that it 404s with "not ready".

## Anti-patterns

| Don't | Why |
| --- | --- |
| Poll on a fixed 2s interval | Wastes quota; use `estimated_seconds` + backoff |
| Retry `pipeline_error` in a tight loop | It's a bug/config issue — surface it |
| Re-POST without `idempotency_key` after a timeout | Launches a duplicate pipeline run |
| Treat `degraded` as failure | The fallback result is legitimate data |
| Scrape these markdown docs | Consume `openapi.json` — it's the contract |
