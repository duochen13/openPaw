# Quickstart — first research job in 5 minutes

```bash
cd travel-assistant
pip install -r requirements.txt

# 1. Mint an API key (raw key printed once — save it)
python -m travel_assistant.apikeys create --name quickstart

# 2. Launch the service
python -m travel_assistant.service --port 8000
# or: uvicorn travel_assistant.service:app --port 8000
```

In another shell (replace `$TA_KEY`):

```bash
BASE=http://127.0.0.1:8000

# 3. Enqueue a research job -> 202 {job_id, status: "queued", estimated_seconds}
curl -s -X POST $BASE/v1/research \
  -H "Authorization: Bearer $TA_KEY" \
  -H "Content-Type: application/json" \
  -d '{"destination": "Kyoto", "vibe": "food",
       "idempotency_key": "quickstart-kyoto-food-001"}'
# {"job_id":"9f3c...","status":"queued","estimated_seconds":300,"cached":false}

# 4. Poll until done (research takes minutes of headless-browser time)
JOB=9f3c1a2b4d5e6f7890abcdef12345678
curl -s $BASE/v1/research/$JOB -H "Authorization: Bearer $TA_KEY"
# {"job_id":"...","status":"running","destination":"Kyoto","estimated_seconds":300}
# ... eventually:
# {"job_id":"...","status":"done","destination":"Kyoto","places":[...],
#  "map_bundle_url":"/v1/maps/9f3c....html", ...}

# 5. Fetch the standalone map bundle
curl -s $BASE/v1/maps/$JOB.html -H "Authorization: Bearer $TA_KEY" -o kyoto.html
```

## What just happened

1. `POST /v1/research` validated your key and params, then **enqueued** a
   background job (a bounded worker pool runs the pipeline; the HTTP call
   returns immediately).
2. `GET /v1/research/{job_id}` reported `queued` → `running` → `done`.
   The done payload carries the places in the API shape plus
   `map_bundle_url`, `degraded`, `collector`/`collector_requested`,
   `n_places`, and `duration_s`.
3. `GET /v1/maps/{job_id}.html` returned the stored standalone map HTML.

## Next steps

- **Agents:** implement the full loop (backoff, failure codes, degraded
  results) from [agent-pattern](agent-pattern.md) — don't just poll blindly.
- **Repeat calls:** learn how `idempotency_key` and the TTL cache keep
  re-runs cheap in [idempotency-metering](idempotency-metering.md).
- **Something failed?** Look up the `code` in the [error catalog](errors.md).
