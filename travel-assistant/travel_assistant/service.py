"""Async FastAPI service for the travel-research pipeline (issue #79).

Endpoints (all under /v1):

- POST /v1/research          -> 202 {job_id, status: "queued", estimated_seconds}
- GET  /v1/research/{job_id} -> poll: {job_id, status}; done: full result +
                                places in the #73 schema, `cached` flag,
                                `map_bundle_url`
- GET  /v1/maps/{job_id}.html -> the run's stored standalone map HTML bundle

Research takes minutes of headless-browser time, so POST only enqueues; a
bounded ThreadPoolExecutor (default 2 workers) executes the pipeline in the
background and the client polls GET until status is "done" (or "failed").

Job lifecycle: queued -> running -> done | failed. The registry is
process-local (a lock-guarded dict); it does not survive restarts.

Idempotency: POST honours `idempotency_key` — re-POSTing the same key returns
the ORIGINAL job (202, original job_id, first-write-wins). Also process-local.

`cached` is always false for fresh pipeline runs here: #80 owns TTL caching
and will add cache-hit semantics there. This field exists so clients can rely
on it now.

---------------------------------------------------------------------
Issue #80 (this change): API keys + metering + cached/fresh two-tier pricing.

Auth: every /v1/* route requires `Authorization: Bearer <api_key>`
(missing/invalid -> 401 problem+json, codes missing_api_key/invalid_api_key).
Keys are minted with `python -m travel_assistant.apikeys create --name NAME`
(raw key printed once; only the sha256 hash is stored — see apikeys.py);
TA_DEV_API_KEYS seeds process-local dev keys.

Metering: every /v1 call appends a row to the `usage` table (key id,
endpoint, timestamp, cached flag, cost tier "fresh"|"cached"). Tier is
"fresh" iff the call enqueued a NEW pipeline run; everything else (cache
hits, idempotent replays, polls, rejected calls) is "cached". No price
points — the strings are the whole pricing signal (business decision, out
of scope per #80). GET /v1/usage returns the calling key's own summary; it
is a non-spec extra (not in the v1 spec), documented here.

Cache: POST /v1/research (no idempotency_key, no fresh=true) first checks
the TTL cache keyed by (destination, vibe, collector, region, queries-hash,
skip_geocode, from_analysis). Hit within TTL -> 200 with the stored result,
`cached: true`, `cache_hit: true`, `ttl_remaining_s` — the pipeline is NOT
re-run. TTLs are per-category (see cache.py CATEGORY_TTLS): a run's TTL is
the SHORTEST category TTL among its places ("shortest-category wins", so a
mixed run expires on the restaurant schedule). `?fresh=true` (query param;
body field `fresh` also honoured) bypasses the cache, re-runs the pipeline,
returns `cached: false`, and refreshes the cache entry. Interaction rules:
idempotency_key is honoured first (existing job returned); fresh=true beats
idempotency_key (re-run wins, new job registered under the key). An
idempotency_key opts the request OUT of the TTL result cache: idem-keyed
requests dedup through the idempotency registry, keeping #79's idempotency
semantics deterministic regardless of cache state.

Degradation: if the requested (primary) collector fails mid-run with a
source-flavored error, the job retries once with the WebSearchCollector
fallback (search backend injected via service.config.search_backend) instead
of failing; returned places carry their true per-place `source` labels and
the result carries degraded:true / served_by. If the fallback is also
unavailable, the job fails with source_unavailable. Analyzer for live
collects is injected via service.config.analyzer (tests); production wiring
of a real search backend / analyzer is deployment config, not #80.

`estimated_seconds` is a rough heuristic (replay vs live collect), not a
guarantee: from-analysis replays land in seconds; live rednote collection is
minutes of browser work.

`rate_limited` (429) is still a process-level placeholder: POST is rejected
when the number of unfinished jobs (queued + running) reaches
TA_SERVICE_MAX_QUEUED. Per-key quotas are future work, not #80.

Error shape: application/problem+json with a machine-readable `code`:
  invalid_destination  (400) - missing/empty destination (or unreadable
                                from_analysis path)
  source_unavailable   (503) - collector backend missing: websearch with no
                                search backend configured, rednote with no
                                browse binary found
  rate_limited         (429) - bounded queue full (see above)
  not_found / invalid_request - non-spec codes used for unknown job ids and
                                other malformed params; documented here, not
                                in the v1 spec.

Place mapping (stored place row -> API shape), per schema.py:
  category              <- analyzer `type` ("restaurant"|"sight"|...)
  price_hint            <- reserved column; the v1 analyzer does not emit it,
                           so this is currently null (stage TBD)
  validation.geocode_confidence <- reserved column; currently null (the
                           geocode stage fills lat/lng but does not score
                           confidence yet)
  source                <- per-place collector label stamped by research()
                           via collectors.label_places (issue #76)

Launch:  python -m travel_assistant.service [--port 8000]
   or:   uvicorn travel_assistant.service:app --port 8000
"""
import os
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import apikeys as apikeys_mod
from . import cache as cache_mod
from . import collectors as collectors_mod
from . import metering as metering_mod
from . import paths
from .research import research as research_fn

# --------------------------------------------------------------------------
# config (env knobs; read once at import)

WORKERS = int(os.environ.get("TA_SERVICE_WORKERS", "2"))
HOST = os.environ.get("TA_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("TA_SERVICE_PORT", "8000"))


class _Config:
    """Mutable process knobs; tests may set these directly."""
    max_queued = int(os.environ.get("TA_SERVICE_MAX_QUEUED", "8"))
    # Search backend for the websearch collector/fallback:
    #   search(query: str, n: int) -> [{"title", "url", "snippet"?}, ...]
    # None -> websearch live collects are refused (503) and the fallback
    # degrades to source_unavailable. Deployment config, not #80's scope.
    search_backend = None
    # Test hook: name -> Collector instance, bypassing collector_for().
    collector_override = {}
    # Analyzer callable for live collects (the LLM step has no default
    # implementation; tests inject a fake). None -> live collect jobs fail
    # with pipeline_error (honest: no analyzer configured).
    analyzer = None


config = _Config()

# estimated_seconds heuristics (documented estimates, not guarantees)
EST_REPLAY_SKIP_GEOCODE = 15
EST_REPLAY_GEOCODE = 60
EST_WEBSEARCH_LIVE = 120
EST_REDNOTE_LIVE = 300

app = FastAPI(title="travel-assistant API", version="0.1.0")

_executor = ThreadPoolExecutor(max_workers=WORKERS,
                               thread_name_prefix="ta-research")


# --------------------------------------------------------------------------
# problem+json

def problem(status, code, title, detail=None, **extra):
    body = {
        "type": f"https://travel-assistant.invalid/problems/{code}",
        "title": title,
        "status": status,
        "code": code,
    }
    if detail is not None:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(status_code=status, content=body,
                        media_type="application/problem+json")


# --------------------------------------------------------------------------
# auth + metering (issue #80)

def _record_usage(key_row, request, cached, cost_tier):
    """Meter one /v1 call. key_row None -> auth failed (key_id NULL).

    Metering must never break the API: failures are reported to stderr and
    swallowed so a broken usage DB can't 500 research calls.
    """
    try:
        metering_mod.UsageStore().record(
            key_id=key_row["id"] if key_row else None,
            endpoint=request.url.path, method=request.method,
            cached=cached, cost_tier=cost_tier)
    except Exception as e:  # noqa: BLE001
        print(f"[travel-assistant] metering failed: {e!r}", file=sys.stderr)


def _require_key(request):
    """Return the verified API-key row, or a 401 problem+json response.

    Every /v1/* route calls this first: auth failures are metered (key_id
    NULL) and returned before any validation, so 401 precedes 400.
    """
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    token = token.strip()
    if not token or scheme.lower() != "bearer":
        _record_usage(None, request, cached=True, cost_tier="cached")
        return problem(401, "missing_api_key", "API key required",
                       "Send Authorization: Bearer <api_key> on every /v1 "
                       "request (mint one with "
                       "`python -m travel_assistant.apikeys create --name NAME`).")
    row = apikeys_mod.ApiKeyStore().verify(token)
    if row is None:
        _record_usage(None, request, cached=True, cost_tier="cached")
        return problem(401, "invalid_api_key", "Invalid API key",
                       "The bearer token is unknown or has been revoked.")
    return row


# --------------------------------------------------------------------------
# job registry (process-local)

class _Registry:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}          # job_id -> job dict
        self._by_idem = {}       # idempotency_key -> job_id

    def active_count(self):
        with self._lock:
            return sum(1 for j in self._jobs.values()
                       if j["status"] in ("queued", "running"))

    def create(self, job_id, params, estimated_seconds):
        job = {
            "job_id": job_id,
            "status": "queued",
            "params": params,
            "estimated_seconds": estimated_seconds,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "result": None,          # filled on done
            "error": None,           # {"code","message"} on failed
        }
        with self._lock:
            self._jobs[job_id] = job
            key = params.get("idempotency_key")
            if key:
                self._by_idem[key] = job_id
        return job

    def by_idempotency_key(self, key):
        with self._lock:
            jid = self._by_idem.get(key)
            return self._jobs.get(jid) if jid else None

    def get(self, job_id):
        with self._lock:
            return self._jobs.get(job_id)

    def set_running(self, job_id):
        with self._lock:
            self._jobs[job_id]["status"] = "running"

    def set_done(self, job_id, result):
        with self._lock:
            j = self._jobs[job_id]
            j["status"] = "done"
            j["result"] = result

    def set_failed(self, job_id, code, message):
        with self._lock:
            j = self._jobs[job_id]
            j["status"] = "failed"
            j["error"] = {"code": code, "message": message}


registry = _Registry()


# --------------------------------------------------------------------------
# helpers

def _place_view(p):
    """Map a stored place row to the #73 API place shape (see module doc)."""
    return {
        "name": p.get("name"),
        "category": p.get("category"),
        "lat": p.get("lat"),
        "lng": p.get("lng"),
        "why_loved": p.get("why_loved"),
        "source_urls": p.get("source_urls") or [],
        "price_hint": p.get("price_hint"),
        "source": p.get("source"),
        "validation": {"geocode_confidence": p.get("geocode_confidence")},
    }


def _rednote_browser_present():
    """Cheap mirror of collect_rednote.find_browse(): is the browse binary
    discoverable without importing that module (import probes the home dir)?"""
    default = Path.home() / ".claude" / "skills" / "gstack" / "browse" \
        / "dist" / "browse"
    return default.is_file() or shutil.which("browse") is not None


def _check_source_available(collector_name, from_analysis):
    """Return an error message if the collector backend is missing, else None.

    Skipped entirely for from_analysis replays (no collection happens there).
    """
    if from_analysis:
        return None
    if collector_name == "websearch":
        # A search backend is injected via service.config.search_backend
        # (deployment config). Without one, refuse to emit an empty/garbage
        # raw file (same stance as the collector itself).
        if config.search_backend is None:
            return ("WebSearchCollector has no search backend configured in "
                    "this service process: set service.config.search_backend "
                    "to a search(query, n) callable.")
        return None
    if collector_name == "rednote":
        if not _rednote_browser_present():
            return ("rednote collector backend missing: headless `browse` "
                    "binary not found (needs the gstack browse browser plus "
                    "a logged-in xiaohongshu.com session).")
    return None


class _FallbackExhausted(Exception):
    """Primary collector failed AND the websearch fallback also failed."""


def _make_collector(name):
    """Collector instance for a live run (config.collector_override is the
    test hook; otherwise the registered collector class)."""
    if name in config.collector_override:
        return config.collector_override[name]
    return collectors_mod.collector_for(name)()


# Substrings (lowercased "ExcType: message") that mark a failure as the
# SOURCE being unavailable/flaky rather than a pipeline bug. Heuristic and
# documented: a fake failing collector in tests raises e.g.
# RuntimeError("rednote scrape blocked: source unavailable").
_SOURCE_FAILURE_HINTS = ("backend", "source unavailable", "browse",
                         "login wall", "blocked", "captcha", "forbidden")


def _is_source_failure(exc):
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(h in msg for h in _SOURCE_FAILURE_HINTS)


def _run_pipeline(params):
    """Run the research pipeline with graceful degradation (issue #80).

    Returns (run_record, degraded: bool, served_by: str).
    If the primary collector raises a source-flavored error, the run is
    retried once with the WebSearchCollector fallback (search backend from
    config.search_backend); the returned places then carry the fallback's
    per-place `source` labels. If the fallback is also unavailable, raises
    _FallbackExhausted, which the caller maps to source_unavailable. A
    websearch primary that fails has no distinct fallback -> raises as-is.
    """
    base = dict(
        destination=params["destination"] or None,
        vibe=params.get("vibe") or "all",
        queries=params.get("queries"),
        from_analysis=params["from_analysis"],
        skip_geocode=params.get("skip_geocode", False),
        region=params.get("region") or "",
        db_path=None,  # resolves via TA_RUNS_DB / TA_DATA_ROOT in paths
        analyzer=config.analyzer,
    )
    if params["from_analysis"]:
        # Replay: no collection, nothing to degrade.
        return research_fn(**base), False, params["collector"]
    primary = _make_collector(params["collector"])
    try:
        return (research_fn(collector=primary, **base), False,
                getattr(primary, "source", None) or params["collector"])
    except Exception as e:  # noqa: BLE001
        if not _is_source_failure(e) or params["collector"] == "websearch":
            raise
        fallback = collectors_mod.WebSearchCollector(
            search=config.search_backend)
        try:
            rec = research_fn(collector=fallback, **base)
        except Exception as e2:  # noqa: BLE001
            raise _FallbackExhausted(
                f"primary collector {params['collector']!r} failed ({e}); "
                f"fallback 'websearch' also unavailable ({e2})") from e2
        return rec, True, fallback.source


def _write_cache(params, job_id, result, rec):
    """Store a completed run's result in the TTL cache (issue #80).

    TTL is derived from the run's places via the documented
    shortest-category-wins rule (cache.ttl_for_places). Failures are
    reported to stderr and swallowed: a broken cache must not fail jobs.
    """
    try:
        ttl_s = cache_mod.ttl_for_places(rec.get("places", []),
                                         destination=params.get("destination"))
        cache_mod.CacheStore().put(
            cache_mod.cache_key_for(params), payload=result, ttl_s=ttl_s,
            job_id=job_id, run_id=rec.get("id"))
    except Exception as e:  # noqa: BLE001
        print(f"[travel-assistant] cache write failed: {e!r}",
              file=sys.stderr)


def _execute_job(job_id):
    job = registry.get(job_id)
    params = job["params"]
    registry.set_running(job_id)
    try:
        rec, degraded, served_by = _run_pipeline(params)
        places = [_place_view(p) for p in rec.get("places", [])]
        result = {
            "job_id": job_id,
            "status": "done",
            "destination": rec.get("destination"),
            "collector": served_by,          # the source that actually served
            "collector_requested": params["collector"],
            "degraded": degraded,             # True iff fallback served it
            "run_id": rec.get("id"),
            "cached": False,  # fresh pipeline run; cache hits override this
            "map_bundle_url": f"/v1/maps/{job_id}.html",
            "n_places": rec.get("n_places"),
            "duration_s": rec.get("duration_s"),
            "places": places,
        }
        # Cache BEFORE the done marker: a job that polls as "done" is then
        # always cache-visible to the next POST.
        _write_cache(params, job_id, result, rec)
        registry.set_done(job_id, result)
    except Exception as e:  # noqa: BLE001 - report any pipeline failure
        msg = f"{type(e).__name__}: {e}"
        code = ("source_unavailable"
                if isinstance(e, _FallbackExhausted)
                or "backend" in msg.lower()
                else "pipeline_error")
        registry.set_failed(job_id, code, msg)


def _estimate_seconds(params):
    if params["from_analysis"]:
        return (EST_REPLAY_SKIP_GEOCODE if params.get("skip_geocode")
                else EST_REPLAY_GEOCODE)
    return (EST_WEBSEARCH_LIVE if params["collector"] == "websearch"
            else EST_REDNOTE_LIVE)


# --------------------------------------------------------------------------
# routes

@app.post("/v1/research", status_code=202)
def post_research(payload: dict, request: Request, fresh: bool = False):
    """Enqueue a research run — or serve a TTL cache hit.

    `?fresh=true` (query param; a `fresh` body field is honoured too)
    bypasses the cache, re-runs the pipeline, returns cached:false, and
    refreshes the cache entry. Interaction rules (documented): the
    idempotency_key lookup runs first — UNLESS fresh=true, which wins and
    re-runs (the new job is registered under the idempotency key). An
    idempotency_key opts the request out of the TTL result cache (idem-keyed
    requests dedup via the idempotency registry).
    """
    key = _require_key(request)
    if isinstance(key, JSONResponse):
        return key

    def _reject(status, code, title, detail):
        _record_usage(key, request, cached=True, cost_tier="cached")
        return problem(status, code, title, detail)

    if not isinstance(payload, dict):
        return _reject(400, "invalid_request", "Bad request",
                       "JSON object body required")
    fresh = fresh or bool(payload.get("fresh"))
    destination = (payload.get("destination") or "").strip()
    if not destination and not payload.get("from_analysis"):
        return _reject(400, "invalid_destination", "Invalid destination",
                       "destination is required (non-empty string), unless "
                       "from_analysis derives it")
    collector_name = (payload.get("collector") or "rednote").lower()
    try:
        collectors_mod.collector_for(collector_name)
    except ValueError as e:
        return _reject(400, "invalid_destination", "Unknown collector",
                       f"{e}")
    from_analysis = payload.get("from_analysis")
    if from_analysis and not Path(from_analysis).is_file():
        return _reject(400, "invalid_request", "Analysis file not found",
                       f"from_analysis file does not exist: {from_analysis}")

    params = {
        "destination": destination,
        "vibe": payload.get("vibe") or "all",
        "queries": payload.get("queries"),
        "collector": collector_name,
        "idempotency_key": None,
        "from_analysis": from_analysis,
        "skip_geocode": bool(payload.get("skip_geocode", False)),
        "region": payload.get("region") or "",
    }

    # Idempotency first — unless fresh=true wins (documented: fresh wins).
    idem = payload.get("idempotency_key")
    if idem and not fresh:
        existing = registry.by_idempotency_key(str(idem))
        if existing is not None:
            _record_usage(key, request, cached=True, cost_tier="cached")
            return JSONResponse(
                status_code=202,
                content={"job_id": existing["job_id"],
                         "status": existing["status"],
                         "estimated_seconds": existing["estimated_seconds"],
                         "idempotent_replay": True})
    if idem:
        params["idempotency_key"] = str(idem)

    # TTL cache: repeat call within TTL returns the stored result cheaply
    # WITHOUT re-running the pipeline (200, cached:true). Skipped when an
    # idempotency_key is present: idem-keyed requests dedup through the
    # idempotency registry instead (keeps #79's idempotency semantics
    # deterministic regardless of cache state).
    if not fresh and not idem:
        entry = cache_mod.CacheStore().get(cache_mod.cache_key_for(params))
        if entry is not None:
            hit = dict(entry["payload"])
            hit["cached"] = True
            hit["cache_hit"] = True
            hit["ttl_remaining_s"] = entry["ttl_remaining_s"]
            _record_usage(key, request, cached=True, cost_tier="cached")
            return JSONResponse(status_code=200, content=hit)

    unavailable = _check_source_available(collector_name, from_analysis)
    if unavailable:
        return _reject(503, "source_unavailable", "Collector backend "
                       "unavailable", unavailable)

    if registry.active_count() >= config.max_queued:
        return _reject(429, "rate_limited", "Research queue full",
                       f"{config.max_queued} unfinished jobs already in the "
                       "queue; poll an existing job or retry later. (Per-key "
                       "quotas are future work, not #80.)")

    job_id = uuid.uuid4().hex
    estimated = _estimate_seconds(params)
    registry.create(job_id, params, estimated)
    _executor.submit(_execute_job, job_id)
    _record_usage(key, request, cached=False, cost_tier="fresh")
    return {"job_id": job_id, "status": "queued",
            "estimated_seconds": estimated, "cached": False}


@app.get("/v1/research/{job_id}")
def get_research(job_id: str, request: Request):
    key = _require_key(request)
    if isinstance(key, JSONResponse):
        return key
    _record_usage(key, request, cached=True, cost_tier="cached")
    job = registry.get(job_id)
    if job is None:
        return problem(404, "not_found", "Unknown job",
                       f"no research job {job_id!r} in this process")
    if job["status"] in ("queued", "running"):
        return {"job_id": job_id, "status": job["status"],
                "destination": job["params"]["destination"] or None,
                "estimated_seconds": job["estimated_seconds"]}
    if job["status"] == "failed":
        body = {
            "type": "https://travel-assistant.invalid/problems/"
                    + job["error"]["code"],
            "title": "Research failed",
            "status": "failed",
            "http_status": 500,
            "code": job["error"]["code"],
            "detail": job["error"]["message"],
            "job_id": job_id,
        }
        return JSONResponse(status_code=500, content=body,
                            media_type="application/problem+json")
    return job["result"]


@app.get("/v1/usage")
def get_usage(request: Request):
    """Per-key metering summary (NON-SPEC extra added in #80 — not part of
    the v1 API spec; it exists so key holders can audit their own usage).
    """
    key = _require_key(request)
    if isinstance(key, JSONResponse):
        return key
    _record_usage(key, request, cached=True, cost_tier="cached")
    summary = metering_mod.UsageStore().summary(key["id"])
    summary["key_name"] = key["name"]
    summary["note"] = ("non-spec #80 extra: cost_tier is 'fresh' iff the "
                       "call enqueued a new pipeline run, else 'cached'; "
                       "no price points are recorded")
    return summary


@app.get("/v1/maps/{job_id}.html")
def get_map_bundle(job_id: str, request: Request):
    key = _require_key(request)
    if isinstance(key, JSONResponse):
        return key
    _record_usage(key, request, cached=True, cost_tier="cached")
    job = registry.get(job_id)
    if job is None:
        # Cache-hit results reference their ORIGINAL job id; after a process
        # restart that job is gone from the registry, but the map HTML
        # persists on disk — resolve via the cache entry's run_id.
        entry = cache_mod.CacheStore().find_job(job_id)
        if entry is not None:
            rec_path = _run_map_html_path({"result": {"run_id": entry["run_id"]}})
            if rec_path is not None and rec_path.is_file():
                return FileResponse(str(rec_path), media_type="text/html",
                                    filename=f"{job_id}.html")
        return problem(404, "not_found", "Unknown job",
                       f"no research job {job_id!r} in this process")
    if job["status"] != "done":
        return problem(404, "not_found", "Map bundle not ready",
                       f"job {job_id} is {job['status']}; poll "
                       f"/v1/research/{job_id} until done")
    rec_path = _run_map_html_path(job)
    if rec_path is None or not rec_path.is_file():
        return problem(404, "not_found", "Map bundle missing",
                       f"stored map HTML for job {job_id} not found on disk")
    return FileResponse(str(rec_path), media_type="text/html",
                        filename=f"{job_id}.html")


def _run_map_html_path(job):
    """Resolve the stored map HTML path for a done job via the run record."""
    result = job.get("result") or {}
    run_id = result.get("run_id")
    if not run_id:
        return None
    from . import store as store_mod
    st = store_mod.RunStore(None)  # respects TA_RUNS_DB / TA_DATA_ROOT
    try:
        rec = st.get_run(run_id)
    finally:
        st.close()
    if not rec or not rec.get("map_html_path"):
        return None
    return Path(rec["map_html_path"])


# --------------------------------------------------------------------------
# launch

def main(argv=None):
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser(description="travel-assistant API service")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)
    uvicorn.run("travel_assistant.service:app", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
