"""Unit tests for the SQLite run store (temp DB, no fixtures)."""
import os
import tempfile

from travel_assistant import store as store_mod


def _tmp_store():
    d = tempfile.mkdtemp(prefix="ta_store_")
    return store_mod.RunStore(os.path.join(d, "runs.db")), d


def test_create_and_get_run():
    st, _ = _tmp_store()
    rid = st.create_run(destination="Kyoto", slug="kyoto", vibe="food",
                        date_start="2026-12-08", date_end="2026-12-12",
                        budget_tier="mid", source_mode="rednote")
    rec = st.get_run(rid)
    assert rec["destination"] == "Kyoto" and rec["vibe"] == "food"
    assert rec["date_start"] == "2026-12-08" and rec["budget_tier"] == "mid"
    assert rec["status"] == "running" and rec["places"] == []
    assert rec["run_uuid"] and len(rec["run_uuid"]) == 32
    st.close()


def test_add_places_round_trip():
    st, _ = _tmp_store()
    rid = st.create_run(destination="Kyoto", slug="kyoto")
    places = [{"name": "Gion Karyo", "type": "restaurant", "area": "Gion",
               "lat": 35.0037, "lng": 135.7752, "why_loved": "great",
               "source_urls": ["https://x.com/1"], "mention_count": 5,
               "sentiment": "positive", "tags": ["a", "b"],
               "map_link": None, "rating": 4.5}]
    assert st.add_places(rid, places) == 1
    rec = st.get_run(rid)
    p = rec["places"][0]
    assert p["name"] == "Gion Karyo" and p["category"] == "restaurant"
    assert p["lat"] == 35.0037 and p["source_urls"] == ["https://x.com/1"]
    assert p["tags"] == ["a", "b"] and p["rating"] == 4.5
    # reserved-for-future columns default to NULL
    assert p["price_hint"] is None and p["geocode_confidence"] is None
    st.close()


def test_complete_and_fail():
    st, _ = _tmp_store()
    rid = st.create_run(destination="Kyoto", slug="kyoto")
    started = st.get_run(rid)["started_at"]
    st.complete_run(rid, n_places=10, n_geocoded=8, kml_path="/x.kml",
                    started_at=started)
    rec = st.get_run(rid)
    assert rec["status"] == "complete" and rec["n_places"] == 10
    assert rec["kml_path"] == "/x.kml" and rec["duration_s"] >= 0
    rid2 = st.create_run(destination="Osaka", slug="osaka")
    st.fail_run(rid2, ValueError("boom"))
    rec2 = st.get_run(rid2)
    assert rec2["status"] == "failed" and "boom" in rec2["error"]
    st.close()


def test_list_runs_order_and_filter():
    st, _ = _tmp_store()
    st.create_run(destination="Kyoto", slug="kyoto")
    st.create_run(destination="Osaka", slug="osaka")
    st.create_run(destination="Kyoto", slug="kyoto")
    rows = st.list_runs()
    assert [r["destination"] for r in rows] == ["Kyoto", "Osaka", "Kyoto"]
    assert [r["id"] for r in rows] == sorted(
        [r["id"] for r in rows], reverse=True)
    kyoto = st.list_runs(destination="Kyoto")
    assert len(kyoto) == 2 and all(r["destination"] == "Kyoto" for r in kyoto)
    assert st.latest_run()["destination"] == "Kyoto"
    assert st.get_run(99999) is None
    st.close()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
