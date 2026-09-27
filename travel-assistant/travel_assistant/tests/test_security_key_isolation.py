"""Security regression tests: per-key isolation for the service layer.

Covers issues #139 (TTL cache shared across API keys), #140
(`from_analysis` accepts any server-side path), #141 (idempotency
registry not namespaced per API key), and #142 (one key can fill the
global queue and 429-starve others).

ALL OFFLINE: TA_OFFLINE=1, TA_DATA_ROOT -> tmp dir. Jobs replay the real
Vancouver analysis fixture with --skip-geocode semantics so nothing
touches the network, the browser, or an LLM.
"""
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

os.environ["TA_OFFLINE"] = "1"

TA_ROOT = tempfile.mkdtemp(prefix="ta_sec_")
os.environ["TA_DATA_ROOT"] = TA_ROOT

from fastapi.testclient import TestClient  # noqa: E402

from travel_assistant import apikeys as apikeys_mod  # noqa: E402
from travel_assistant import paths  # noqa: E402
from travel_assistant import service  # noqa: E402

FIXTURE = str(paths.PROJECT_DIR / "data" / "analysis"
              / "vancouver_places_20260709_030913.json")

client = TestClient(service.app)


def _mint(name):
    return apikeys_mod.ApiKeyStore().create_key(name)


def _auth(raw):
    return {"Authorization": f"Bearer {raw}"}


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
            return {"status": "failed", **r.json()}
        assert r.status_code == 200, r.text
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} not terminal after {timeout}s")


# --------------------------------------------------------------------------
# #141 — idempotency registry namespaced per API key

def test_idempotency_key_namespaced_per_key():
    a = _mint("sec-idem-a")
    b = _mint("sec-idem-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    r1 = client.post("/v1/research",
                     json=_replay_body("sec-141", idempotency_key="sec-141-k"),
                     headers=Ha)
    assert r1.status_code == 202, r1.text
    j1 = r1.json()["job_id"]

    # same idempotency_key from a DIFFERENT key -> a distinct job, never a
    # replay of the first key's job
    r2 = client.post("/v1/research",
                     json=_replay_body("sec-141", idempotency_key="sec-141-k"),
                     headers=Hb)
    assert r2.status_code == 202, r2.text
    j2 = r2.json()["job_id"]
    assert j2 != j1
    assert "idempotent_replay" not in r2.json()

    # and replaying under the second key returns the second key's job
    r3 = client.post("/v1/research",
                     json=_replay_body("sec-141", idempotency_key="sec-141-k"),
                     headers=Hb)
    assert r3.json()["job_id"] == j2
    assert r3.json()["idempotent_replay"] is True

    # the creating key is recorded on the job dicts
    assert service.registry.get(j1)["key_id"] == a["id"]
    assert service.registry.get(j2)["key_id"] == b["id"]

    _poll_terminal(Ha, j1)
    _poll_terminal(Hb, j2)


def test_poll_other_keys_job_is_denied():
    a = _mint("sec-poll-a")
    b = _mint("sec-poll-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    r = client.post("/v1/research",
                    json=_replay_body("sec-141-poll",
                                      idempotency_key="sec-141-poll-k"),
                    headers=Ha)
    assert r.status_code == 202, r.text
    j1 = r.json()["job_id"]
    _poll_terminal(Ha, j1)

    # owner can poll and gets the full result
    r = client.get(f"/v1/research/{j1}", headers=Ha)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"

    # another valid key gets the same 404 as an unknown job (no existence
    # oracle, no result payload)
    r = client.get(f"/v1/research/{j1}", headers=Hb)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "not_found"


# --------------------------------------------------------------------------
# #139 — TTL result cache isolated per API key

def test_cache_hit_isolated_per_key():
    a = _mint("sec-cache-a")
    b = _mint("sec-cache-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    # key A runs and warms the cache (no idempotency_key -> TTL cache path)
    r1 = client.post("/v1/research", json=_replay_body("sec-139"),
                     headers=Ha)
    assert r1.status_code == 202, r1.text
    j1 = r1.json()["job_id"]
    _poll_terminal(Ha, j1)

    # key A re-posts identical params -> cache hit with A's own job_id
    r2 = client.post("/v1/research", json=_replay_body("sec-139"),
                     headers=Ha)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["cache_hit"] is True
    assert d2["job_id"] == j1

    # key B posts the IDENTICAL params -> must NOT get a cross-key cache hit
    r3 = client.post("/v1/research", json=_replay_body("sec-139"),
                     headers=Hb)
    assert r3.status_code == 202, r3.text
    assert "cache_hit" not in r3.json()
    j3 = r3.json()["job_id"]
    assert j3 != j1
    _poll_terminal(Hb, j3)


def test_map_bundle_denied_cross_key():
    a = _mint("sec-map-a")
    b = _mint("sec-map-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    r = client.post("/v1/research",
                    json=_replay_body("sec-139-map",
                                      idempotency_key="sec-139-map-k"),
                    headers=Ha)
    assert r.status_code == 202, r.text
    j1 = r.json()["job_id"]
    done = _poll_terminal(Ha, j1)
    assert done["status"] == "done"

    # owner gets the bundle
    r = client.get(f"/v1/maps/{j1}.html", headers=Ha)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")

    # another valid key is denied (404, like an unknown job)
    r = client.get(f"/v1/maps/{j1}.html", headers=Hb)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "not_found"


def test_map_bundle_restart_fallback_is_key_scoped():
    """Simulate a process restart (registry empty, cache + HTML on disk):
    the map-bundle fallback serves the entry only to its creating key."""
    a = _mint("sec-mapre-a")
    b = _mint("sec-mapre-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    r = client.post("/v1/research", json=_replay_body("sec-139-mapre"),
                    headers=Ha)
    assert r.status_code == 202, r.text
    j1 = r.json()["job_id"]
    _poll_terminal(Ha, j1)

    # "restart": drop the job from the in-memory registry
    assert service.registry.get(j1) is not None
    with service.registry._lock:
        del service.registry._jobs[j1]

    # the creating key still resolves via the cache entry's run_id
    r = client.get(f"/v1/maps/{j1}.html", headers=Ha)
    assert r.status_code == 200, r.text
    # the other key does not
    r = client.get(f"/v1/maps/{j1}.html", headers=Hb)
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "not_found"


# --------------------------------------------------------------------------
# #140 — from_analysis path confinement

def test_from_analysis_outside_tree_rejected():
    rec = _mint("sec-fa-1")
    H = _auth(rec["key"])
    outside = tempfile.NamedTemporaryFile(suffix=".json", dir="/tmp",
                                          delete=False)
    outside.write(b'{"destination": "X", "places": []}')
    outside.close()
    try:
        r = client.post("/v1/research",
                        json={"destination": "X",
                              "from_analysis": outside.name,
                              "skip_geocode": True},
                        headers=H)
        assert r.status_code == 400, r.text
        assert r.json()["code"] == "invalid_request"
    finally:
        os.unlink(outside.name)


def test_from_analysis_traversal_rejected():
    rec = _mint("sec-fa-2")
    H = _auth(rec["key"])
    # exists on disk (is_file() is true) but lives outside data/analysis
    trav = str(Path(FIXTURE).parent / ".." / ".." / "README.md")
    assert Path(trav).is_file(), "test precondition"
    r = client.post("/v1/research",
                    json={"destination": "X", "from_analysis": trav,
                          "skip_geocode": True},
                    headers=H)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "invalid_request"


def test_from_analysis_symlink_escape_rejected():
    rec = _mint("sec-fa-3")
    H = _auth(rec["key"])
    target = os.path.join(tempfile.gettempdir(), "sec140_target.json")
    with open(target, "w") as f:
        f.write('{"destination": "X", "places": []}')
    link_dir = paths.data_root() / "analysis"
    link_dir.mkdir(parents=True, exist_ok=True)
    link = link_dir / "evil_link_sec140.json"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(target)
    try:
        # the symlink sits INSIDE the allowed dir but resolves outside it
        r = client.post("/v1/research",
                        json={"destination": "X",
                              "from_analysis": str(link),
                              "skip_geocode": True},
                        headers=H)
        assert r.status_code == 400, r.text
        assert r.json()["code"] == "invalid_request"
    finally:
        link.unlink()
        os.unlink(target)


def test_from_analysis_in_tree_accepted():
    rec = _mint("sec-fa-4")
    H = _auth(rec["key"])

    # the committed fixture under the package data tree
    r = client.post("/v1/research",
                    json={"destination": "Vancouver",
                          "from_analysis": FIXTURE, "skip_geocode": True,
                          "idempotency_key": "sec-140-ok-1"},
                    headers=H)
    assert r.status_code == 202, r.text

    # a file under the effective (TA_DATA_ROOT) analysis dir — resolved at
    # call time, since sibling test modules may override TA_DATA_ROOT
    legit_dir = paths.analysis_dir()
    legit_dir.mkdir(parents=True, exist_ok=True)
    legit = legit_dir / "legit_replay_sec140.json"
    shutil.copyfile(FIXTURE, legit)
    r = client.post("/v1/research",
                    json={"destination": "Vancouver",
                          "from_analysis": str(legit), "skip_geocode": True,
                          "idempotency_key": "sec-140-ok-2"},
                    headers=H)
    assert r.status_code == 202, r.text


def test_from_analysis_missing_still_400():
    rec = _mint("sec-fa-5")
    H = _auth(rec["key"])
    r = client.post("/v1/research",
                    json={"destination": "X",
                          "from_analysis": FIXTURE + "-does-not-exist",
                          "skip_geocode": True},
                    headers=H)
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "invalid_request"


# --------------------------------------------------------------------------
# #142 — per-key queue cap

def test_per_key_cap_429_but_other_key_can_submit(monkeypatch):
    a = _mint("sec-perkey-a")
    b = _mint("sec-perkey-b")
    Ha, Hb = _auth(a["key"]), _auth(b["key"])

    # block job execution so jobs pile up as unfinished
    gate = threading.Event()

    def _block(job_id):
        service.registry.set_running(job_id)
        gate.wait(30)
        service.registry.set_done(job_id, {"job_id": job_id,
                                           "status": "done"})

    monkeypatch.setattr(service, "_execute_job", _block)
    old_global, old_perkey = (service.config.max_queued,
                              service.config.max_queued_per_key)
    service.config.max_queued = 100      # global bound out of the way
    service.config.max_queued_per_key = 2
    try:
        r1 = client.post("/v1/research",
                         json=_replay_body("sec-142",
                                           idempotency_key="sec-142-a1"),
                         headers=Ha)
        r2 = client.post("/v1/research",
                         json=_replay_body("sec-142",
                                           idempotency_key="sec-142-a2"),
                         headers=Ha)
        assert r1.status_code == 202, r1.text
        assert r2.status_code == 202, r2.text

        # third job from the same key -> 429 (per-key cap hit)
        r3 = client.post("/v1/research",
                         json=_replay_body("sec-142",
                                           idempotency_key="sec-142-a3"),
                         headers=Ha)
        assert r3.status_code == 429, r3.text
        assert r3.json()["code"] == "rate_limited"
        assert service.registry.active_count(a["id"]) == 2

        # a second key still has room in the global queue -> 202
        rb = client.post("/v1/research",
                         json=_replay_body("sec-142",
                                           idempotency_key="sec-142-b1"),
                         headers=Hb)
        assert rb.status_code == 202, rb.text
    finally:
        service.config.max_queued = old_global
        service.config.max_queued_per_key = old_perkey
        gate.set()


def test_global_cap_still_binds():
    old_global = service.config.max_queued
    service.config.max_queued = 0
    try:
        rec = _mint("sec-perkey-g")
        r = client.post("/v1/research",
                        json=_replay_body("sec-142-g",
                                          idempotency_key="sec-142-g1"),
                        headers=_auth(rec["key"]))
        assert r.status_code == 429, r.text
        assert r.json()["code"] == "rate_limited"
    finally:
        service.config.max_queued = old_global
