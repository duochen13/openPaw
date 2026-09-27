# travel-assistant API reference

> Generated from the live OpenAPI spec — do not edit by hand. Regenerate with `python3 docs/generate_api_docs.py` (run from the `travel-assistant/` directory).

**Version:** `0.1.0`

**Base URL:** `http://127.0.0.1:8000` (default; see `TA_SERVICE_HOST` / `TA_SERVICE_PORT`)

**Auth:** every endpoint requires `Authorization: Bearer <api_key>` — see [authentication](authentication.md).

**Errors:** `application/problem+json` with a machine-readable `code` — see the [error catalog](errors.md).

## Endpoints

- `POST /v1/research` — Enqueue a research run
- `GET /v1/research/{job_id}` — Poll a research job
- `GET /v1/usage` — Per-key metering summary
- `GET /v1/maps/{job_id}.html` — Fetch a job's map bundle

## `POST /v1/research`

*Enqueue a research run.*

Enqueue a research run — or serve a TTL cache hit.

`?fresh=true` (query param; a `fresh` body field is honoured too)
bypasses the cache, re-runs the pipeline, returns cached:false, and
refreshes the cache entry. Interaction rules (documented): the
idempotency_key lookup runs first — UNLESS fresh=true, which wins and
re-runs (the new job is registered under the idempotency key). An
idempotency_key opts the request out of the TTL result cache (idem-keyed
requests dedup via the idempotency registry).

### Parameters

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `fresh` | query | boolean | no | `False` |  |

### Request body

Content type: `application/json`

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `destination` | string | no |  | Required (non-empty), unless from_analysis derives it. |
| `vibe` | string | no | `all` | Place vibe filter, e.g. "food", "sights", "cafes", "nightlife", "all". |
| `queries` | array of string | no |  | Extra search queries; null lets the pipeline derive them. |
| `collector` | string (rednote | websearch) | no | `rednote` |  |
| `idempotency_key` | string | no |  | Client-chosen key; re-POST returns the ORIGINAL job (first-write-wins). Scoped per API key: another key's identical value is a separate job. Opts the request out of the TTL result cache. |
| `from_analysis` | string | no |  | Path to a saved analysis file to replay instead of collecting. Confined to the service's data/analysis directory: absolute paths outside the data tree, ../ traversals, and tree-escaping symlinks are rejected (400). |
| `skip_geocode` | boolean | no | `False` |  |
| `region` | string | no |  |  |
| `fresh` | boolean | no | `False` | Bypass the TTL cache and re-run the pipeline (beats idempotency_key). |

Example:

```json
{
  "destination": "Kyoto",
  "vibe": "food",
  "collector": "rednote",
  "idempotency_key": "trip-kyoto-food-001"
}
```

### Responses

#### `202` — Job enqueued — or an idempotent replay of an existing job for the same idempotency_key.

`application/json` example:

```json
{
  "job_id": "9f3c1a2b4d5e6f7890abcdef12345678",
  "status": "queued",
  "estimated_seconds": 300,
  "cached": false
}
```

#### `200` — TTL cache hit — the stored result is returned without re-running the pipeline.

`application/json` example:

```json
{
  "job_id": "9f3c1a2b4d5e6f7890abcdef12345678",
  "status": "done",
  "destination": "Kyoto",
  "collector": "rednote",
  "collector_requested": "rednote",
  "degraded": false,
  "run_id": 12,
  "cached": true,
  "map_bundle_url": "/v1/maps/9f3c1a2b4d5e6f7890abcdef12345678.html",
  "n_places": 8,
  "duration_s": 214.5,
  "places": [
    {
      "name": "Gion Karyo",
      "category": "restaurant",
      "lat": 35.0037,
      "lng": 135.7752,
      "why_loved": "Rednote users praise the seasonal kaiseki lunch queue...",
      "source_urls": [
        "https://www.xiaohongshu.com/explore/..."
      ],
      "source": "rednote",
      "validation": {}
    }
  ],
  "cache_hit": true,
  "ttl_remaining_s": 3540
}
```

#### `400` — Bad request

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `401` — Missing or invalid API key

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `429` — Research queue full

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `503` — Collector backend unavailable

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `422` — Validation Error

## `GET /v1/research/{job_id}`

*Poll a research job.*

Poll until `status` is `done` (full result) or `failed` (HTTP 500 problem+json carrying the pipeline error code). Jobs are process-local and do not survive restarts.

### Parameters

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | string | yes |  |  |

### Responses

#### `200` — Job state. Poll until status is done or failed.

`application/json` example (queued):

```json
{
  "job_id": "9f3c1a2b4d5e6f7890abcdef12345678",
  "status": "queued",
  "destination": "Kyoto",
  "estimated_seconds": 300
}
```

`application/json` example (done):

```json
{
  "job_id": "9f3c1a2b4d5e6f7890abcdef12345678",
  "status": "done",
  "destination": "Kyoto",
  "collector": "rednote",
  "collector_requested": "rednote",
  "degraded": false,
  "run_id": 12,
  "cached": false,
  "map_bundle_url": "/v1/maps/9f3c1a2b4d5e6f7890abcdef12345678.html",
  "n_places": 8,
  "duration_s": 214.5,
  "places": [
    {
      "name": "Gion Karyo",
      "category": "restaurant",
      "lat": 35.0037,
      "lng": 135.7752,
      "why_loved": "Rednote users praise the seasonal kaiseki lunch queue...",
      "source_urls": [
        "https://www.xiaohongshu.com/explore/..."
      ],
      "source": "rednote",
      "validation": {}
    }
  ]
}
```

#### `401` — Missing or invalid API key

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `404` — Unknown job id

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `500` — The job itself failed. Note the body shape: problem+json with status "failed" and the pipeline error code.

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/pipeline_error",
  "title": "Research failed",
  "status": "failed",
  "http_status": 500,
  "code": "pipeline_error",
  "detail": "RuntimeError: analyzer returned no places",
  "job_id": "9f3c1a2b4d5e6f7890abcdef12345678"
}
```

#### `422` — Validation Error

## `GET /v1/usage`

*Per-key metering summary.*

Per-key metering summary (NON-SPEC extra added in #80 — not part of
the v1 API spec; it exists so key holders can audit their own usage).

### Responses

#### `200` — Per-key metering summary (non-spec #80 extra).

`application/json` example:

```json
{
  "key_id": 3,
  "total_calls": 41,
  "by_endpoint": {
    "POST /v1/research": 5,
    "GET /v1/research/{job_id}": 30,
    "GET /v1/usage": 6
  },
  "by_cost_tier": {
    "fresh": 2,
    "cached": 39
  },
  "cached_calls": 39,
  "fresh_calls": 2,
  "key_name": "agent-alpha",
  "note": "non-spec #80 extra: cost_tier is 'fresh' iff the call enqueued a new pipeline run, else 'cached'; no price points are recorded"
}
```

#### `401` — Missing or invalid API key

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

## `GET /v1/maps/{job_id}.html`

*Fetch a job's map bundle.*

Returns the run's stored standalone map HTML bundle. Only available once the job is done.

### Parameters

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | string | yes |  |  |

### Responses

#### `200` — Standalone map HTML bundle for a done job.

Returns `text/html`.

#### `401` — Missing or invalid API key

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `404` — Unknown job, or map bundle not ready/missing

`application/problem+json` example:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_destination",
  "title": "Invalid destination",
  "status": 400,
  "code": "invalid_destination",
  "detail": "destination is required (non-empty string), unless from_analysis derives it"
}
```

#### `422` — Validation Error
