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

`estimated_seconds` is a rough heuristic (replay vs live collect), not a
guarantee: from-analysis replays land in seconds; live rednote collection is
minutes of browser work.

`rate_limited` (429) is a process-level placeholder: POST is rejected when the
number of unfinished jobs (queued + running) reaches TA_SERVICE_MAX_QUEUED.
#80's per-key metering replaces this with real quotas.

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
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import collectors as collectors_mod
from . import paths
from .research import research as research_fn

# --------------------------------------------------------------------------
# config (env knobs; read once at import)

WORKERS = int(os.environ.get("TA_SERVICE_WORKERS", "2"))
HOST = os.environ.get("TA_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("TA_SERVICE_PORT", "8000"))


class _Config:
    """Mutable process knobs; tests may set max_queued directly."""
    max_queued = int(os.environ.get("TA_SERVICE_MAX_QUEUED", "8"))


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
        # No injectable search backend in the service process -> refuse to
        # emit an empty/garbage raw file (same stance as the collector).
        return ("WebSearchCollector has no search backend configured in "
                "this service (issue #80 wires provider keys + metering).")
    if collector_name == "rednote":
        if not _rednote_browser_present():
            return ("rednote collector backend missing: headless `browse` "
                    "binary not found (needs the gstack browse browser plus "
                    "a logged-in xiaohongshu.com session).")
    return None


def _execute_job(job_id):
    job = registry.get(job_id)
    params = job["params"]
    registry.set_running(job_id)
    try:
        collector = None
        if not params["from_analysis"]:
            collector = collectors_mod.collector_for(params["collector"])()
        rec = research_fn(
            destination=params["destination"] or None,
            vibe=params.get("vibe") or "all",
            queries=params.get("queries"),
            collector=collector,
            from_analysis=params["from_analysis"],
            skip_geocode=params.get("skip_geocode", False),
            region=params.get("region") or "",
            db_path=None,  # resolves via TA_RUNS_DB / TA_DATA_ROOT in paths
        )
        places = [_place_view(p) for p in rec.get("places", [])]
        result = {
            "job_id": job_id,
            "status": "done",
            "destination": rec.get("destination"),
            "collector": params["collector"],
            "run_id": rec.get("id"),
            "cached": False,  # #80 owns TTL caching; fresh runs are never cached
            "map_bundle_url": f"/v1/maps/{job_id}.html",
            "n_places": rec.get("n_places"),
            "duration_s": rec.get("duration_s"),
            "places": places,
        }
        registry.set_done(job_id, result)
    except Exception as e:  # noqa: BLE001 - report any pipeline failure
        msg = f"{type(e).__name__}: {e}"
        code = "source_unavailable" if "backend" in msg.lower() else "pipeline_error"
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
def post_research(payload: dict, request: Request):
    if not isinstance(payload, dict):
        return problem(400, "invalid_request", "Bad request",
                       "JSON object body required")
    destination = (payload.get("destination") or "").strip()
    if not destination and not payload.get("from_analysis"):
        return problem(400, "invalid_destination", "Invalid destination",
                       "destination is required (non-empty string), unless "
                       "from_analysis derives it")
    collector_name = (payload.get("collector") or "rednote").lower()
    try:
        collectors_mod.collector_for(collector_name)
    except ValueError as e:
        return problem(400, "invalid_destination", "Unknown collector",
                       f"{e}")
    from_analysis = payload.get("from_analysis")
    if from_analysis and not Path(from_analysis).is_file():
        return problem(400, "invalid_request", "Analysis file not found",
                       f"from_analysis file does not exist: {from_analysis}")

    idem = payload.get("idempotency_key")
    if idem:
        existing = registry.by_idempotency_key(str(idem))
        if existing is not None:
            return JSONResponse(
                status_code=202,
                content={"job_id": existing["job_id"],
                         "status": existing["status"],
                         "estimated_seconds": existing["estimated_seconds"],
                         "idempotent_replay": True})

    unavailable = _check_source_available(collector_name, from_analysis)
    if unavailable:
        return problem(503, "source_unavailable", "Collector backend "
                       "unavailable", unavailable)

    if registry.active_count() >= config.max_queued:
        return problem(429, "rate_limited", "Research queue full",
                       f"{config.max_queued} unfinished jobs already in the "
                       "queue; poll an existing job or retry later. (#80 "
                       "replaces this process-level cap with per-key "
                       "metering.)")

    job_id = uuid.uuid4().hex
    params = {
        "destination": destination,
        "vibe": payload.get("vibe") or "all",
        "queries": payload.get("queries"),
        "collector": collector_name,
        "idempotency_key": str(idem) if idem else None,
        "from_analysis": from_analysis,
        "skip_geocode": bool(payload.get("skip_geocode", False)),
        "region": payload.get("region") or "",
    }
    estimated = _estimate_seconds(params)
    registry.create(job_id, params, estimated)
    _executor.submit(_execute_job, job_id)
    return {"job_id": job_id, "status": "queued",
            "estimated_seconds": estimated}


@app.get("/v1/research/{job_id}")
def get_research(job_id: str):
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


@app.get("/v1/maps/{job_id}.html")
def get_map_bundle(job_id: str):
    job = registry.get(job_id)
    if job is None:
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
