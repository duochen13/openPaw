"""Service tests (issue #79): full async round-trip, idempotency, errors.

ALL OFFLINE: TA_OFFLINE=1, TA_DATA_ROOT -> tmp dir, and jobs replay the real
Vancouver analysis fixture with --skip-geocode semantics so nothing touches
the network, the browser, or an LLM.
"""
import os
import tempfile
import time

os.environ["TA_OFFLINE"] = "1"

TA_ROOT = tempfile.mkdtemp(prefix="ta_svc_")
os.environ["TA_DATA_ROOT"] = TA_ROOT

from fastapi.testclient import TestClient  # noqa: E402

from travel_assistant import paths  # noqa: E402
from travel_assistant import service  # noqa: E402
from travel_assistant.apikeys import ApiKeyStore  # noqa: E402

FIXTURE = str(paths.PROJECT_DIR / "data" / "analysis"
              / "vancouver_places_20260709_030913.json")

client = TestClient(service.app)

# #80: every /v1/* route requires a bearer API key.
_SVC_KEY = ApiKeyStore().create_key("svc-tests")["key"]
AUTH = {"Authorization": f"Bearer {_SVC_KEY}"}


def _replay_body(**kw):
    body = {
        "destination": "Vancouver",
        "vibe": "all",
        "collector": "rednote",
        "from_analysis": FIXTURE,
        "skip_geocode": True,
    }
    body.update(kw)
    return body


def _post(body):
    r = client.post("/v1/research", json=body, headers=AUTH)
    ct = r.headers["content-type"]
    assert ct.startswith("application/json") or ct == "application/problem+json", ct
    return r


def _get(path):
    return client.get(path, headers=AUTH)


def _poll_done(job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = _get(f"/v1/research/{job_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        if data["status"] == "done":
            return data
        assert data["status"] in ("queued", "running"), data
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} not done after {timeout}s")


def test_round_trip_replay():
    r = _post(_replay_body())
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["status"] == "queued"
    assert data["job_id"]
    assert data["estimated_seconds"] == service.EST_REPLAY_SKIP_GEOCODE

    job_id = data["job_id"]
    done = _poll_done(job_id)

    assert done["status"] == "done"
    assert done["cached"] is False  # #80 owns TTL caching; always false here
    assert done["map_bundle_url"] == f"/v1/maps/{job_id}.html"
    assert done["run_id"]
    assert done["n_places"] == 39

    # places in the #73 schema shape
    assert len(done["places"]) == 39
    p = done["places"][0]
    for key in ("name", "category", "lat", "lng", "why_loved",
                "source_urls", "price_hint", "source", "validation"):
        assert key in p, f"missing key {key} in place {p}"
    assert p["category"] == "sight"  # stored `category` <- analyzer `type`
    assert isinstance(p["source_urls"], list) and p["source_urls"]
    assert "geocode_confidence" in p["validation"]  # reserved, null from v1


def test_idempotent_repost_returns_existing_job():
    body = _replay_body(idempotency_key="idem-79-1")
    r1 = _post(body)
    assert r1.status_code == 202
    job_id = r1.json()["job_id"]

    r2 = _post(body)
    assert r2.status_code == 202
    d2 = r2.json()
    assert d2["job_id"] == job_id
    assert d2["idempotent_replay"] is True
    _poll_done(job_id)  # still completes normally


def test_empty_destination_is_400():
    r = _post({"destination": "   "})
    assert r.status_code == 400, r.text
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["code"] == "invalid_destination"

    r = _post({})  # missing entirely
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_destination"


def test_unknown_collector_is_400():
    r = _post(_replay_body(collector="yelp"))
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_destination"


def test_unknown_job_is_404():
    r = _get("/v1/research/nope")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"

    r = _get("/v1/maps/nope.html")
    assert r.status_code == 404


def test_websearch_without_backend_is_503():
    # live collect with no search backend configured -> source_unavailable
    r = _post({"destination": "Kyoto", "collector": "websearch",
               "queries": ["Kyoto food"]})
    assert r.status_code == 503, r.text
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "source_unavailable"


def test_queue_full_is_429():
    old = service.config.max_queued
    service.config.max_queued = 0
    try:
        # idempotency_key bypasses the TTL cache, so this reaches the
        # queue-full check instead of serving a cache hit.
        r = _post(_replay_body(idempotency_key="idem-79-429"))
        assert r.status_code == 429, r.text
        assert r.headers["content-type"] == "application/problem+json"
        assert r.json()["code"] == "rate_limited"
    finally:
        service.config.max_queued = old


def test_map_bundle_served():
    r = _post(_replay_body())
    job_id = r.json()["job_id"]
    done = _poll_done(job_id)

    r = _get(f"/v1/maps/{job_id}.html")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "<html" in html.lower()
    # pins + per-place popups embedded in the bundle
    assert done["places"][0]["name"] in html


def test_map_not_ready_is_404():
    r = _post(_replay_body(idempotency_key="idem-79-mapwait"))
    job_id = r.json()["job_id"]
    # likely still queued/running; if it raced to done, the bundle exists
    r = _get(f"/v1/maps/{job_id}.html")
    assert r.status_code in (200, 404)
    if r.status_code == 404:
        assert r.headers["content-type"] == "application/problem+json"
    _poll_done(job_id)
