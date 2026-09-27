"""Tests for the source-pluggable collectors (issue #76). All OFFLINE.

- Both collectors emit the identical raw file shape (the one
  scripts/collect_rednote.py writes), so downstream stages are untouched.
- WebSearchCollector takes an injectable search backend; tests use a fake.
- With no backend it raises loudly instead of emitting garbage.
- End-to-end: a WebSearchCollector + stub analyzer run labels every stored
  place with "websearch", and replaying the committed Vancouver fixture
  keeps the pipeline output schema unchanged while the label survives into
  the run store.
"""
import json
import os
import shutil
import sys
import tempfile
import types

os.environ["TA_OFFLINE"] = "1"

from travel_assistant import collectors
from travel_assistant import paths
from travel_assistant import store as store_mod
from travel_assistant.collectors import (Collector, RednoteCollector,
                                         WebSearchCollector)
from travel_assistant.research import research as research_fn
from travel_assistant.stages import validate as st_validate

PROJ = paths.PROJECT_DIR
FIXTURE = PROJ / "data" / "analysis" / "vancouver_places_20260709_030913.json"

_RAW_TOP_KEYS = set(collectors.RAW_TOP_KEYS)
_DISC_KEYS = set(collectors.DISCUSSION_KEYS)


def _fresh_env():
    d = tempfile.mkdtemp(prefix="ta_col76_")
    old = os.environ.get("TA_DATA_ROOT")
    os.environ["TA_DATA_ROOT"] = d
    return d, old


def _restore_env(old):
    if old is None:
        os.environ.pop("TA_DATA_ROOT", None)
    else:
        os.environ["TA_DATA_ROOT"] = old


def _fake_search():
    def search(query, n=6):
        return [{"title": f"{query} spot {i}",
                 "url": f"https://example.com/{query.replace(' ', '-')}-{i}",
                 "snippet": f"snippet {i} for {query}"}
                for i in range(n)]
    return search


def _stub_analyzer(raw, destination, vibe):
    assert raw["source"] in ("rednote", "websearch")
    return {
        "destination": destination,
        "generated_at": "2026-09-26T00:00:00Z",
        "source_mode": "fallback",
        "places": [{
            "name": "Example Ramen", "type": "restaurant", "area": "Downtown",
            "why_loved": "great broth", "source_urls": ["https://example.com/1"],
            "mention_count": 3, "sentiment": "positive",
            "map_link": None, "rating": None, "tags": ["ramen"],
            "lat": 35.0, "lng": 135.0,
        }],
    }


def test_collector_interface_importable():
    assert issubclass(RednoteCollector, Collector)
    assert issubclass(WebSearchCollector, Collector)
    assert RednoteCollector.source == "rednote"
    assert WebSearchCollector.source == "websearch"
    assert collectors.collector_for("rednote") is RednoteCollector
    assert collectors.collector_for("websearch") is WebSearchCollector
    try:
        collectors.collector_for("instagram")
    except ValueError as e:
        assert "rednote" in str(e) and "websearch" in str(e)
    else:
        raise AssertionError("unknown collector should raise ValueError")


def test_websearch_collector_matches_rednote_raw_shape():
    d, old = _fresh_env()
    try:
        c = WebSearchCollector(search=_fake_search())
        raw_path = c("Testville", ["food", "sights"], 2)
        raw = json.load(open(raw_path, encoding="utf-8"))
        assert _RAW_TOP_KEYS == set(raw), f"top keys: {sorted(raw)}"
        assert raw["source"] == "websearch"
        assert raw["destination"] == "Testville"
        assert len(raw["discussions"]) == 4
        for disc in raw["discussions"]:
            assert _DISC_KEYS == set(disc), f"discussion keys: {sorted(disc)}"
        urls = [x["url"] for x in raw["discussions"]]
        assert len(set(urls)) == len(urls), "duplicate urls not deduped"
        # raw file lands under TA_DATA_ROOT/raw with the source in its name
        assert raw_path.startswith(os.path.join(d, "raw"))
        assert "_websearch_" in os.path.basename(raw_path)
    finally:
        _restore_env(old)


def test_websearch_collector_requires_backend():
    c = WebSearchCollector()
    try:
        c.collect("Testville", ["food"])
    except RuntimeError as e:
        assert "no search backend" in str(e)
    else:
        raise AssertionError("missing backend must raise, not emit garbage")


def test_rednote_collector_wraps_script_module():
    # fake the lazily-imported scripts/collect_rednote module
    mod = types.ModuleType("collect_rednote")
    calls = {}

    def fake_collect(destination, queries, n):
        calls["args"] = (destination, queries, n)
        return "/tmp/fake_raw.json"

    mod.collect = fake_collect
    sys.modules["collect_rednote"] = mod
    try:
        c = RednoteCollector()
        # Collector instances stay usable wherever the old callable protocol was
        assert c("Kyoto", ["food"], 2) == "/tmp/fake_raw.json"
        assert calls["args"] == ("Kyoto", ["food"], 2)
    finally:
        del sys.modules["collect_rednote"]


def test_label_places_does_not_override():
    obj = {"places": [{"name": "A", "source": "rednote"}, {"name": "B"}]}
    collectors.label_places(obj, "websearch")
    assert obj["places"][0]["source"] == "rednote"
    assert obj["places"][1]["source"] == "websearch"
    collectors.label_places({"places": []}, None)  # no-op, no crash


def test_e2e_websearch_collect_labels_stored_places():
    d, old = _fresh_env()
    try:
        c = WebSearchCollector(search=_fake_search())
        rec = research_fn(
            destination="Testville", vibe="food", queries=["food"],
            n_per_query=2, collector=c, analyzer=_stub_analyzer,
            skip_geocode=True)
        assert rec["status"] == "complete"
        assert rec["n_places"] == 1
        # raw file written by the collector keeps the canonical shape
        raw = json.load(open(rec["raw_path"], encoding="utf-8"))
        assert raw["source"] == "websearch"
        assert set(raw["discussions"][0]) == _DISC_KEYS
        # the label flows through the pipeline into the run store
        st = store_mod.RunStore()
        try:
            full = st.get_run(rec["id"])
            assert len(full["places"]) == 1
            assert full["places"][0]["source"] == "websearch"
            assert full["places"][0]["name"] == "Example Ramen"
        finally:
            st.close()
        # and into the persisted enriched analysis
        enriched = json.load(open(rec["analysis_path"], encoding="utf-8"))
        assert enriched["places"][0]["source"] == "websearch"
    finally:
        _restore_env(old)


def test_e2e_vancouver_fixture_replay_source_label_survives():
    # Replay the committed fixture (with per-place source labels added to a
    # throwaway copy): the label must survive into the run store and the
    # pipeline output schema must be unchanged.
    d, old = _fresh_env()
    try:
        fixture_copy = os.path.join(d, "vancouver_labeled.json")
        obj = json.load(open(FIXTURE, encoding="utf-8"))
        fixture_place_keys = set(obj["places"][0])
        for p in obj["places"]:
            p["source"] = "websearch"
        json.dump(obj, open(fixture_copy, "w", encoding="utf-8"),
                  ensure_ascii=False)

        rec = research_fn(destination="Vancouver, BC", vibe="food",
                          from_analysis=fixture_copy, skip_geocode=True,
                          region="BC, Canada")
        assert rec["status"] == "complete"
        assert rec["n_places"] == 39

        enriched = json.load(open(rec["analysis_path"], encoding="utf-8"))
        # output schema unchanged: same top-level keys, place keys + "source"
        assert set(enriched) == {"destination", "generated_at", "source_mode",
                                 "places"}
        assert set(enriched["places"][0]) == fixture_place_keys | {"source"}
        assert st_validate.check(enriched) is True

        st = store_mod.RunStore()
        try:
            full = st.get_run(rec["id"])
            assert len(full["places"]) == 39
            assert {p["source"] for p in full["places"]} == {"websearch"}
        finally:
            st.close()
    finally:
        _restore_env(old)


def test_store_migrates_legacy_db():
    # a DB created without the places.source column upgrades cleanly
    d = tempfile.mkdtemp(prefix="ta_mig76_")
    db = os.path.join(d, "runs.db")
    import sqlite3
    conn = sqlite3.connect(db)
    conn.executescript(
        store_mod.SCHEMA.replace("source             TEXT,                 "
                                 "-- collector label (issue #76)\n", ""))
    conn.execute(
        "INSERT INTO runs (run_uuid, destination, slug, status, started_at)"
        " VALUES ('u1', 'Kyoto', 'kyoto', 'complete', 't')")
    conn.commit()
    conn.close()
    st = store_mod.RunStore(db)
    try:
        assert st.add_places(1, [{"name": "X", "source": "rednote"}]) == 1
        rec = st.get_run(1)
        assert rec["places"][0]["source"] == "rednote"
    finally:
        st.close()
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
