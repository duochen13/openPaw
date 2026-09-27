"""Offline tests for `travel-assistant ui` (issue #78).

Seeds a temp run store by replaying the committed Vancouver + Yellowknife
analysis fixtures (from_analysis + skip_geocode, TA_OFFLINE=1), then checks:
  - the cost-rollup interpretation (v1 runs carry no price hints; synthetic
    places with hints roll up correctly),
  - the page builders render every run with its pins + "why people love it"
    quotes,
  - the HTTP server serves index / run-detail / compare pages over loopback
    (no external network),
  - the `travel-assistant` CLI dispatches `ui` and rejects bad commands.
"""
import os
import re
import tempfile
import threading
import urllib.request
import urllib.error

os.environ["TA_OFFLINE"] = "1"

from travel_assistant import cli as cli_mod
from travel_assistant import paths
from travel_assistant import ui as ui_mod
from travel_assistant.research import research as research_fn
from travel_assistant import store as store_mod

PROJ = paths.PROJECT_DIR
VAN = PROJ / "data" / "analysis" / "vancouver_places_20260709_030913.json"
YKN = PROJ / "data" / "analysis" / "yellowknife_places_20260903_055740.json"

_SEED = None  # (tmpdir, van_id, ykn_id)


def _fresh_env():
    d = tempfile.mkdtemp(prefix="ta_ui_")
    os.environ["TA_DATA_ROOT"] = d
    return d


def seed():
    """Replay both fixtures into a temp store; returns (van_id, ykn_id).

    Idempotent: the module owns TA_DATA_ROOT for its whole lifetime once
    seeded, so every test reads the same temp store.
    """
    global _SEED
    if _SEED is not None:
        return _SEED[1], _SEED[2]
    tmp = _fresh_env()  # leaves TA_DATA_ROOT pointing at tmp
    rec_v = research_fn(destination="Vancouver, BC", vibe="food",
                        from_analysis=str(VAN), skip_geocode=True)
    rec_y = research_fn(destination="Yellowknife", vibe="sights",
                        from_analysis=str(YKN), skip_geocode=True)
    assert rec_v["status"] == "complete" and rec_y["status"] == "complete"
    _SEED = (tmp, rec_v["id"], rec_y["id"])
    return rec_v["id"], rec_y["id"]


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read().decode("utf-8")


# -- cost rollup ------------------------------------------------------------
def test_cost_rollup_v1_runs_have_no_hints():
    van_id, ykn_id = seed()
    st = store_mod.RunStore()
    try:
        for rid in (van_id, ykn_id):
            r = ui_mod.cost_rollup(st.get_run(rid)["places"])
            assert r["n_with_hint"] == 0
            assert r["n_without_hint"] == r["n_total"] > 0
            assert r["hints"] == []
    finally:
        st.close()


def test_cost_rollup_with_hints():
    places = [
        {"name": "A", "price_hint": "$$"},
        {"name": "B", "price_hint": None},
        {"name": "C", "price_hint": "$45 entry"},
    ]
    r = ui_mod.cost_rollup(places)
    assert r == {"n_total": 3, "n_with_hint": 2, "n_without_hint": 1,
                 "hints": [("A", "$$"), ("C", "$45 entry")]}


# -- page builders ----------------------------------------------------------
def test_index_lists_all_runs():
    van_id, ykn_id = seed()
    st = store_mod.RunStore()
    try:
        html = ui_mod.index_page(st.list_runs(limit=100))
    finally:
        st.close()
    assert "Vancouver, BC" in html and "Yellowknife" in html
    assert f"/runs/{van_id}" in html and f"/runs/{ykn_id}" in html
    assert "compare" in html.lower()


def test_run_page_renders_pins_popups_quotes():
    van_id, _ = seed()
    st = store_mod.RunStore()
    try:
        rec = st.get_run(van_id)
        html = ui_mod.run_page(rec)
    finally:
        st.close()
    geo = ui_mod._geocoded(rec["places"])
    n_pins = len(re.findall(r'class="ta-pin"', html))
    assert n_pins == len(geo) == 25, (n_pins, len(geo))
    # every pin popup carries its quote
    for p in geo[:5]:
        assert p["why_loved"] in html, p["name"]
    # per-type colors present (sight green, restaurant red)
    assert "#2E9E4F" in html and "#E8453C" in html
    # skipped-without-coords note
    assert "without coordinates" in html
    # cost rollup says plainly there is nothing to roll up
    assert "No price hints recorded" in html


def test_compare_page_renders_both_maps():
    van_id, ykn_id = seed()
    st = store_mod.RunStore()
    try:
        ra, rb = st.get_run(van_id), st.get_run(ykn_id)
        html = ui_mod.compare_page(ra, rb, st.list_runs(limit=100))
    finally:
        st.close()
    assert "Vancouver, BC" in html and "Yellowknife" in html
    assert 'id="map-cmpA"' in html and 'id="map-cmpB"' in html
    n_pins = len(re.findall(r'class="ta-pin"', html))
    assert n_pins == 25 + 16, n_pins


def test_map_fragment_no_geo():
    html, geo = ui_mod.map_fragment({"destination": "Nowhere", "places": [
        {"name": "X", "category": "sight", "lat": None, "lng": None}]}, "z")
    assert geo == [] and "No geocoded places" in html


# -- HTTP roundtrip ---------------------------------------------------------
def test_http_serves_all_pages():
    van_id, ykn_id = seed()
    db = paths.runs_db_path()
    srv = ui_mod.make_server("127.0.0.1", 0, db)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        s, idx = _get(base + "/")
        assert s == 200 and "Vancouver, BC" in idx and "Yellowknife" in idx

        s, det = _get(base + f"/runs/{van_id}")
        assert s == 200
        assert len(re.findall(r'class="ta-pin"', det)) == 25
        assert "\u201c" in det  # quote marks around why-loved

        s, cmp_ = _get(base + f"/compare?a={van_id}&b={ykn_id}")
        assert s == 200
        assert "Vancouver, BC" in cmp_ and "Yellowknife" in cmp_

        try:
            _get(base + "/runs/999999")
        except urllib.error.HTTPError as e:
            assert e.code == 404
        else:
            raise AssertionError("expected 404 for unknown run")
    finally:
        srv.shutdown()
        t.join(timeout=5)
        srv.server_close()


# -- CLI dispatch -----------------------------------------------------------
def test_cli_ui_help_and_bad_command():
    try:
        cli_mod.main(["ui", "--help"])
    except SystemExit as e:
        assert e.code == 0
    else:
        raise AssertionError("ui --help should exit 0")
    try:
        cli_mod.main(["bogus"])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError("bad command should exit 2")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
