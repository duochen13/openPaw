# travel-assistant API documentation

HTTP API over the travel-research pipeline: enqueue an async research job,
poll it, and fetch the results plus a standalone map bundle. The primary
consumers are agents (see [agent-pattern](agent-pattern.md)).

- **Base URL:** `http://127.0.0.1:8000` by default
  (`TA_SERVICE_HOST` / `TA_SERVICE_PORT`)
- **Version:** `0.1.0` — see [versioning](versioning.md)
- **Auth:** `Authorization: Bearer <api_key>` on every `/v1/*` route —
  see [authentication](authentication.md)

## Guides

| Guide | What it covers |
| --- | --- |
| [authentication](authentication.md) | Minting keys, dev keys, revocation, 401 handling |
| [quickstart](quickstart.md) | First research job in 5 minutes (curl) |
| [agent-pattern](agent-pattern.md) | The async job loop agents should implement |
| [idempotency-metering](idempotency-metering.md) | Idempotency keys, TTL cache, cost tiers, rate limits |
| [errors](errors.md) | Every `problem+json` error code: meaning + recovery |
| [versioning](versioning.md) | Version policy + changelog |

## Reference

| Document | Source |
| --- | --- |
| [api-reference](api-reference.md) | **Generated** from the live OpenAPI spec — do not edit by hand |
| [openapi.json](openapi.json) | **Generated** machine-readable contract — agents: consume this, don't scrape these docs |

Regenerate both with (from the `travel-assistant/` directory):

```bash
python3 docs/generate_api_docs.py        # regenerate
python3 docs/generate_api_docs.py --check  # fail if committed docs are stale
```

The reference is generated from `travel_assistant.service`'s FastAPI app,
so endpoint/parameter/schema changes land in the docs automatically on
regen. The OpenAPI metadata lives on the route decorators in
`travel_assistant/service.py` — that is the single source of truth.
