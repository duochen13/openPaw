# Versioning & changelog

**Current version:** `0.1.0` (served as the FastAPI `version`; visible in
`openapi.json` → `info.version` and the generated
[reference](api-reference.md)).

## Policy

- **Additive changes** (new optional fields, new endpoints, new error
  codes): minor version bump. Old clients keep working.
- **Breaking changes** (removing/renaming fields, changing status codes or
  the `places` shape): served under a new path prefix (`/v2/...`) with the
  old prefix kept until the changelog says otherwise. Never silently break
  `/v1`.
- Every change updates this changelog and the OpenAPI metadata in
  `travel_assistant/service.py`, then `docs/generate_api_docs.py` is
  re-run so the reference and `openapi.json` stay in sync.

## Changelog

### 0.1.0

- Initial versioned API surface.
- Async research jobs: `POST /v1/research` → `202 {job_id}`,
  `GET /v1/research/{job_id}` poll (`queued` → `running` → `done` | `failed`),
  `GET /v1/maps/{job_id}.html` map bundle (issue #79).
- Bearer-key auth on all `/v1/*` routes; per-key metering with
  `fresh`/`cached` cost tiers; `GET /v1/usage` audit endpoint; TTL result
  cache with shortest-category-wins expiry; `idempotency_key` first-write-wins
  semantics (issue #80).
- Graceful degradation: source-flavored primary failure retries once via
  the websearch fallback; results carry `degraded` / `served_by`
  (`collector` vs `collector_requested`).
- OpenAPI metadata enrichment + this docs page: generated reference,
  agent call pattern, error catalog (issue #126).
