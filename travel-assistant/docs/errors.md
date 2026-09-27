# Error catalog

All errors are `application/problem+json` with a machine-readable `code`:

```json
{
  "type": "https://travel-assistant.invalid/problems/<code>",
  "title": "<human title>",
  "status": 400,
  "code": "<code>",
  "detail": "<what happened>"
}
```

## Request errors

| HTTP | `code` | When | Recovery |
| --- | --- | --- | --- |
| 401 | `missing_api_key` | No `Authorization` header, or wrong scheme | Send `Authorization: Bearer <api_key>` (see [authentication](authentication.md)) |
| 401 | `invalid_api_key` | Token unknown or revoked | Check for typos; mint a new key |
| 400 | `invalid_request` | Body is not a JSON object, `from_analysis` path doesn't exist, **or** `from_analysis` escapes the service's `data/analysis` directory (absolute path outside the data tree, `../` traversal, tree-escaping symlink) | Send a JSON object; point `from_analysis` at a file under `data/analysis` |
| 400 | `invalid_destination` | `destination` empty/missing (and no `from_analysis`), **or** unknown `collector` name | Supply a destination; use `rednote` or `websearch` |
| 503 | `source_unavailable` | Collector backend missing at enqueue time (websearch with no search backend; rednote with no `browse` binary / login session) | Fix deployment config; retry later |
| 429 | `rate_limited` | Unfinished jobs at `TA_SERVICE_MAX_QUEUED` (default 8), **or** the calling key's own unfinished jobs at `TA_SERVICE_MAX_QUEUED_PER_KEY` (default 4) | Back off; poll an existing job instead |

Auth is checked before validation, so `401` precedes `400`.

## Job errors (via `GET /v1/research/{job_id}`)

A failed job returns **HTTP 500** with a problem+json body whose `status`
field is the string `"failed"` (not `500`) plus `http_status: 500`:

```json
{
  "type": "https://travel-assistant.invalid/problems/pipeline_error",
  "title": "Research failed",
  "status": "failed",
  "http_status": 500,
  "code": "pipeline_error",
  "detail": "RuntimeError: analyzer returned no places",
  "job_id": "9f3c..."
}
```

| `code` | When | Recovery |
| --- | --- | --- |
| `source_unavailable` | Primary collector failed with a source-flavored error **and** the websearch fallback also failed | Retry later, or re-enqueue with `collector: "websearch"` |
| `pipeline_error` | Anything else — a real bug or missing config (e.g. no analyzer injected) | **Do not blind-retry.** Surface `detail` to the operator |

## Lookup errors

| HTTP | `code` | When | Recovery |
| --- | --- | --- | --- |
| 404 | `not_found` | Unknown `job_id` on `GET /v1/research/{job_id}` | Check the id — jobs are process-local and vanish on restart |
| 404 | `not_found` | `GET /v1/maps/{job_id}.html` before the job is done | Poll until `done`, then fetch `map_bundle_url` |
| 404 | `not_found` | Map HTML missing on disk for a done job | Re-run with `fresh: true` |

Note: after a process restart, a cache-hit result's `map_bundle_url` still
resolves — the map HTML persists on disk and is found via the cache entry's
`run_id` even though the job registry is empty.
