"""Service tests for issue #80: API keys + metering + TTL cache + degradation.

ALL OFFLINE: TA_OFFLINE=1, TA_DATA_ROOT -> tmp dir, TA_API_DB -> tmp file.
Jobs replay the real Vancouver analysis fixture (from_analysis), except the
degradation tests, which use a fake failing primary collector, a fake
search backend for websearch, and a fake analyzer (no LLM, no network).
"""
import os
import tempfile
import time

os.environ["TA_OFFLINE"] = "1"

TA_ROOT = tempfile.mkdtemp(prefix="ta_80_")
os.environ["TA_DATA_ROOT"] = TA_ROOT
os.environ["TA_API_DB"] = os.path.join(TA_ROOT, "api.db")

from fastapi.testclient import TestClient  # noqa: E402

from travel_assistant import apikeys as apikeys_mod  # noqa: E402
from travel_assistant import cache as cache_mod  # noqa: E402
from travel_assistant import metering as metering_mod  # noqa: E402
from travel_assistant import paths  # noqa: E402
from travel_assistant import service  # noqa: E402
from travel_assistant import store as store_mod  # noqa: E402
from travel_assistant.collectors import Collector  # noqa: E402

FIXTURE = str(paths.PROJECT_DIR / "data" / "analysis"
              / "vancouver_places_20260709_030913.json")

client = TestClient(service.app)


def _mint(name):
    return apikeys_mod.ApiKeyStore().create_key(name)


def _auth(raw):
    return {"Authorization": f"Bearer {raw}"}


def _post(body, headers):
    return client.post("/v1/research", json=body, headers=headers)


def _replay_body(region, **kw):
    body = {
        "destination": "Vancouver",
        "vibe": "all",
        "collector": "rednote",
        "from_analysis": FIXTURE,
        "skip_geocode": True,
        "region": region,  # unique per test: keeps cache keys from colliding
    }
    body.update(kw)
    return body


def _poll_terminal(headers, job_id, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/v1/research/{job_id}", headers=headers)
        if r.status_code == 500:
            # failed jobs surface as problem+json
            return {"status": "failed", **r.json()}
        assert r.status_code == 200, r.text
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} not terminal after {timeout}s")


def _run_count():
    st = store_mod.RunStore()
    try:
        return len(st.list_runs(limit=1000000))
    finally:
        st.close()


# --------------------------------------------------------------------------
# auth

def test_no_key_is_401():
    r = client.post("/v1/research", json={"destination": "X"})
    assert r.status_code == 401, r.text
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "missing_api_key"


def test_bad_key_is_401():
    r = client.get("/v1/research/nope", headers=_auth("ta_bogus_key"))
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "invalid_api_key"


def test_key_lifecycle_create_verify_revoke():
    rec = _mint("k-lifecycle")
    raw = rec["key"]
    assert raw.startswith("ta_")

    # raw key verifies
    row = apikeys_mod.ApiKeyStore().verify(raw)
    assert row and row["name"] == "k-lifecycle"

    # list() exposes metadata only — never hashes, never raw keys
    listed = {k["name"]: k for k in apikeys_mod.ApiKeyStore().list_keys()}
    assert "k-lifecycle" in listed
    assert "key_hash" not in listed["k-lifecycle"]
    assert "key" not in listed["k-lifecycle"]

    # works on the API, then stops working after revoke
    H = _auth(raw)
    r = client.get("/v1/usage", headers=H)
    assert r.status_code == 200, r.text
    assert apikeys_mod.ApiKeyStore().revoke("k-lifecycle") is True
    r = client.get("/v1/usage", headers=H)
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_api_key"


def test_dev_key_from_env(monkeypatch):
    monkeypatch.setenv("TA_DEV_API_KEYS", "dev-secret-xyz")
    r = client.get("/v1/usage", headers=_auth("dev-secret-xyz"))
    assert r.status_code == 200, r.text
    assert r.json()["key_name"] == "dev:0"


# --------------------------------------------------------------------------
# TTL cache

def test_repeat_post_within_ttl_returns_cached_without_rerun():
    rec = _mint("k-cache-1")
    H = _auth(rec["key"])
    body = _replay_body("ttl-region-1")

    before = _run_count()
    r1 = _post(body, H)
    assert r1.status_code == 202, r1.text
    job1 = r1.json()["job_id"]
    done1 = _poll_terminal(H, job1)
    assert done1["status"] == "done"
    assert done1["cached"] is False
    assert _run_count() == before + 1  # exactly one pipeline run

    # repeat call: cache hit, no new pipeline run
    r2 = _post(body, H)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["cached"] is True
    assert d2["cache_hit"] is True
    assert d2["job_id"] == job1
    assert d2["ttl_remaining_s"] > 0
    assert len(d2["places"]) == 39
    assert _run_count() == before + 1  # pipeline NOT re-run


def test_fresh_true_reruns_pipeline_and_refreshes_cache():
    rec = _mint("k-fresh-1")
    H = _auth(rec["key"])
    body = _replay_body("ttl-region-fresh")

    r1 = _post(body, H)
    assert r1.status_code == 202
    job1 = r1.json()["job_id"]
    done1 = _poll_terminal(H, job1)
    assert done1["cached"] is False

    before = _run_count()
    r2 = client.post("/v1/research?fresh=true", json=body, headers=H)
    assert r2.status_code == 202, r2.text
    job2 = r2.json()["job_id"]
    assert job2 != job1  # a genuinely new run
    done2 = _poll_terminal(H, job2)
    assert done2["status"] == "done"
    assert done2["cached"] is False
    assert _run_count() == before + 1  # the fresh run was recorded

    # cache now serves the FRESH result
    r3 = _post(body, H)
    assert r3.status_code == 200
    assert r3.json()["job_id"] == job2
    assert r3.json()["cached"] is True


def test_cache_entry_expires_after_ttl(monkeypatch):
    # shrink every category TTL so expiry is observable in-test
    monkeypatch.setattr(cache_mod, "CATEGORY_TTLS",
                        {k: 0.05 for k in cache_mod.CATEGORY_TTLS})
    rec = _mint("k-ttl-1")
    H = _auth(rec["key"])
    body = _replay_body("ttl-region-expire")

    r1 = _post(body, H)
    assert r1.status_code == 202
    _poll_terminal(H, r1.json()["job_id"])

    time.sleep(0.2)  # exceed the 0.05s TTL
    before = _run_count()
    r2 = _post(body, H)
    assert r2.status_code == 202, r2.text  # expired -> fresh run again
    _poll_terminal(H, r2.json()["job_id"])
    assert _run_count() == before + 1


def test_ttl_shortest_category_wins():
    assert cache_mod.ttl_for_places(
        [{"category": "sight"}, {"category": "restaurant"}]
    ) == cache_mod.SHORT_TTL_S
    assert cache_mod.ttl_for_places(
        [{"category": "sight"}]) == cache_mod.LONG_TTL_S
    assert cache_mod.ttl_for_places(
        [{"category": "shop"}]) == cache_mod.DEFAULT_TTL_S
    assert cache_mod.ttl_for_places([]) == cache_mod.DEFAULT_TTL_S


def test_cache_key_varies_with_params():
    base = {"destination": "Kyoto", "vibe": "food", "collector": "rednote",
            "region": "", "queries": ["a"], "skip_geocode": True,
            "from_analysis": None}
    k1 = cache_mod.cache_key_for(base)
    assert k1 == cache_mod.cache_key_for(dict(base))  # deterministic
    assert cache_mod.cache_key_for({**base, "region": "x"}) != k1
    assert cache_mod.cache_key_for({**base, "vibe": "all"}) != k1
    assert cache_mod.cache_key_for({**base, "skip_geocode": False}) != k1


def test_fresh_beats_idempotency_key():
    rec = _mint("k-idem-1")
    H = _auth(rec["key"])
    body = _replay_body("ttl-region-idem", idempotency_key="idem-80-freshwins")

    r1 = _post(body, H)
    assert r1.status_code == 202
    j1 = r1.json()["job_id"]
    _poll_terminal(H, j1)

    # plain re-POST with the same idempotency key -> original job
    r_idem = _post(body, H)
    assert r_idem.status_code == 202
    assert r_idem.json()["job_id"] == j1
    assert r_idem.json()["idempotent_replay"] is True

    # fresh=true + idempotency_key -> fresh wins, re-runs
    before = _run_count()
    r2 = client.post("/v1/research?fresh=true", json=body, headers=H)
    assert r2.status_code == 202, r2.text
    j2 = r2.json()["job_id"]
    assert j2 != j1
    assert "idempotent_replay" not in r2.json()
    _poll_terminal(H, j2)
    assert _run_count() == before + 1


# --------------------------------------------------------------------------
# metering

def test_per_key_metering_isolated():
    a = _mint("k-meter-a")
    b = _mint("k-meter-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    client.get("/v1/usage", headers=Ha)
    client.get("/v1/usage", headers=Ha)
    client.get("/v1/usage", headers=Hb)

    sa = metering_mod.UsageStore().summary(a["id"])
    sb = metering_mod.UsageStore().summary(b["id"])
    assert sa["total_calls"] == 2, sa
    assert sb["total_calls"] == 1, sb
    assert sa["by_endpoint"] == {"GET /v1/usage": 2}
    assert sa["by_cost_tier"] == {"fresh": 0, "cached": 2}
    assert sa["cached_calls"] == 2 and sa["fresh_calls"] == 0


def test_fresh_post_metered_as_fresh_tier():
    rec = _mint("k-meter-f")
    H = _auth(rec["key"])
    body = _replay_body("ttl-region-meter")

    r = _post(body, H)
    assert r.status_code == 202
    s = metering_mod.UsageStore().summary(rec["id"])
    assert s["by_cost_tier"]["fresh"] == 1, s
    assert s["by_endpoint"].get("POST /v1/research") == 1


def test_usage_endpoint_shape():
    rec = _mint("k-usage-shape")
    H = _auth(rec["key"])
    r = client.get("/v1/usage", headers=H)
    assert r.status_code == 200
    d = r.json()
    assert d["key_name"] == "k-usage-shape"
    assert d["total_calls"] >= 1
    assert "by_endpoint" in d and "by_cost_tier" in d


# --------------------------------------------------------------------------
# graceful degradation

class _FailingRednote(Collector):
    source = "rednote"

    def collect(self, destination, queries, n_per_query=6):
        raise RuntimeError(
            "rednote scrape blocked by login wall: source unavailable")


def _fake_search(query, n):
    return [{"title": f"{query} — noodle hit",
             "url": "https://example.com/noodles",
             "snippet": "hand-pulled noodles, cash only"}]


def _fake_analyzer(raw, *, destination, vibe):
    return {
        "destination": destination,
        "generated_at": "2026-09-26T00:00:00+00:00",
        "source_mode": "fallback",
        "places": [{
            "name": "Test Noodle House",
            "type": "restaurant",
            "area": "Downtown",
            "why_loved": "fake but schema-valid",
            "source_urls": ["https://example.com/noodles"],
            "mention_count": 1,
            "sentiment": "positive",
            "tags": ["noodles"],
            "lat": 49.28,
            "lng": -123.12,
        }],
    }


def test_primary_failure_degrades_to_websearch(monkeypatch):
    monkeypatch.setattr(service, "_rednote_browser_present", lambda: True)
    monkeypatch.setitem(service.config.collector_override, "rednote",
                        _FailingRednote())
    monkeypatch.setattr(service.config, "search_backend", _fake_search)
    monkeypatch.setattr(service.config, "analyzer", _fake_analyzer)

    rec = _mint("k-degrade-1")
    H = _auth(rec["key"])
    r = _post({"destination": "Testville", "collector": "rednote",
               "queries": ["noodles"], "skip_geocode": True}, H)
    assert r.status_code == 202, r.text
    done = _poll_terminal(H, r.json()["job_id"])

    assert done["status"] == "done"
    assert done["degraded"] is True
    assert done["collector"] == "websearch"        # what actually served
    assert done["collector_requested"] == "rednote"
    assert done["places"], "degraded run must return places"
    assert all(p["source"] == "websearch" for p in done["places"]), \
        "places must carry the true fallback source label"


def test_fallback_unavailable_fails_source_unavailable(monkeypatch):
    monkeypatch.setattr(service, "_rednote_browser_present", lambda: True)
    monkeypatch.setitem(service.config.collector_override, "rednote",
                        _FailingRednote())
    # config.search_backend stays None -> fallback raises "no search backend"
    monkeypatch.setattr(service.config, "analyzer", _fake_analyzer)

    rec = _mint("k-degrade-2")
    H = _auth(rec["key"])
    # distinct region -> distinct cache key from the previous degradation test
    r = _post({"destination": "Testville", "collector": "rednote",
               "queries": ["noodles"], "skip_geocode": True,
               "region": "degrade-2"}, H)
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    done = _poll_terminal(H, job_id)
    assert done["status"] == "failed", done

    r = client.get(f"/v1/research/{job_id}", headers=H)
    assert r.status_code == 500, r.text
    assert r.json()["code"] == "source_unavailable"
