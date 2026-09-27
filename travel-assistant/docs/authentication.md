# Authentication

Every `/v1/*` route requires a bearer API key:

```http
Authorization: Bearer <api_key>
```

Auth is checked **first**, before any request validation — a missing or bad
key returns `401` even if the request body is also invalid.

## Minting keys

```bash
cd travel-assistant
python -m travel_assistant.apikeys create --name agent-alpha
```

The raw key is printed **once** — only its SHA-256 hash is stored. Save it
immediately; it cannot be recovered later.

```bash
python -m travel_assistant.apikeys list    # list key names (never raw keys)
python -m travel_assistant.apikeys revoke agent-alpha
```

## Dev keys

Set `TA_DEV_API_KEYS` to seed process-local dev keys (comma-separated).
The first request with a dev key creates a `dev:<n>` row so metering has a
`key_id` to bill against. Dev keys are for local development only.

## Failure codes

| HTTP | `code` | Meaning | Recovery |
| --- | --- | --- | --- |
| 401 | `missing_api_key` | No `Authorization` header, or not `Bearer` scheme | Send `Authorization: Bearer <api_key>` |
| 401 | `invalid_api_key` | Token unknown or revoked | Mint a new key; check for typos/whitespace |

Both are returned as `application/problem+json`:

```json
{
  "type": "https://travel-assistant.invalid/problems/invalid_api_key",
  "title": "Invalid API key",
  "status": 401,
  "code": "invalid_api_key",
  "detail": "The bearer token is unknown or has been revoked."
}
```

## Notes

- Keys identify the caller for metering: `GET /v1/usage` returns the
  calling key's own usage summary (see
  [idempotency-metering](idempotency-metering.md)).
- Auth failures are metered too (with a null key id) — repeated 401s from
  one client are visible server-side.
- There are no scopes or per-key quotas yet (per-key quotas are future
  work); a key either accesses the whole `/v1` API or nothing.
