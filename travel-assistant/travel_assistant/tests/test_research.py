"""End-to-end test: replay the real Vancouver analysis fixture through the
full pipeline with TA_DATA_ROOT pointed at a tmp dir and TA_OFFLINE=1.

No network, no browser, no LLM: --from-analysis skips collect+analyze and
--skip-geocode skips Nominatim (the fixture's geocoded places are kept).
"""
import hashlib
import json
import os
import re
import tempfile

os.environ["TA_OFFLINE"] = "1"

from travel_assistant import paths
from travel_assistant.research import research as research_fn
from travel_assistant import store as store_mod

PROJ = paths.PROJECT_DIR
FIXTURE = PROJ / "data" / "analysis" / "vancouver_places_20260709_030913.json"
COMMITTED_KML = PROJ / "data" / "maps" / "vancouver_bc.kml"


def _pin_names(kml_path):
    txt = open(kml_path, encoding="utf-8").read()
    return re.findall(r"<Placemark>\s*<name>(.*?)</name>", txt)


def _fresh_env():
    d = tempfile.mkdtemp(prefix="ta_e2e_")
    os.environ["TA_DATA_ROOT"] = d
    return d


def _restore_env(old):
    if old is None:
        os.environ.pop("TA_DATA_ROOT", None)
    else:
        os.environ["TA_DATA_ROOT"] = old


def test_e2e_replay_matches_committed_artifacts():
    old = os.environ.get("TA_DATA_ROOT")
    tmp = _fresh_env()
    try:
        before = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
        rec = research_fn(
            destination="Vancouver, BC", vibe="food",
            dates={"start": "2026-12-08", "end": "2026-12-12"},
            budget_tier="mid", from_analysis=str(FIXTURE),
            skip_geocode=True, region="BC, Canada")
        # input fixture must not be mutated
        after = hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest()
        assert before == after, "input analysis file was mutated"

        assert rec["status"] == "complete"
        assert rec["destination"] == "Vancouver, BC" and rec["vibe"] == "food"
        assert rec["date_start"] == "2026-12-08" and rec["budget_tier"] == "mid"
        assert rec["source_mode"] == "fallback"
        assert rec["n_places"] == 39 and rec["n_geocoded"] == 0
        assert rec["n_missing_coords"] == 14
        assert rec["duration_s"] >= 0

        art = rec["artifacts"]
        assert art["n_pins"] == 25 and art["n_csv_rows"] == 39
        for key in ("kml_path", "map_html_path", "csv_path"):
            assert os.path.exists(art[key]), key
        # slug matches the committed run's naming
        assert art["kml_path"].endswith("vancouver_bc.kml")

        # same pins as the committed KML built from this fixture
        assert _pin_names(art["kml_path"]) == _pin_names(COMMITTED_KML)

        # enriched analysis is a NEW timestamped file, not the input
        assert rec["analysis_path"] != str(FIXTURE)
        assert os.path.exists(rec["analysis_path"])
        assert len(os.listdir(os.path.join(tmp, "analysis"))) == 1

        # run store rows are queryable
        st = store_mod.RunStore()
        try:
            rows = st.list_runs()
            assert len(rows) == 1 and rows[0]["id"] == rec["id"]
            full = st.get_run(rec["id"])
            assert len(full["places"]) == 39
            assert full["places"][0]["source_urls"]  # JSON decoded
            assert full["kml_path"] == art["kml_path"]
        finally:
            st.close()

        # a second run appends cleanly (distinct run_uuid)
        rec2 = research_fn(
            destination="Vancouver, BC", from_analysis=str(FIXTURE),
            skip_geocode=True)
        assert rec2["id"] != rec["id"]
        assert rec2["run_uuid"] != rec["run_uuid"]
        st = store_mod.RunStore()
        try:
            assert len(st.list_runs()) == 2
        finally:
            st.close()
    finally:
        _restore_env(old)


def test_e2e_invalid_analysis_marks_run_failed():
    old = os.environ.get("TA_DATA_ROOT")
    tmp = _fresh_env()
    try:
        bad = os.path.join(tmp, "bad.json")
        json.dump({"destination": "X"}, open(bad, "w"))
        try:
            research_fn(destination="X", from_analysis=bad,
                                  skip_geocode=True)
        except ValueError as e:
            assert "INVALID" in str(e)
        else:
            raise AssertionError("should raise on invalid analysis")
        st = store_mod.RunStore()
        try:
            rows = st.list_runs()
            assert len(rows) == 1 and rows[0]["status"] == "failed"
            assert "INVALID" in rows[0]["error"]
        finally:
            st.close()
    finally:
        _restore_env(old)


def test_e2e_destination_required():
    old = os.environ.get("TA_DATA_ROOT")
    _fresh_env()
    try:
        try:
            research_fn()
        except ValueError as e:
            assert "destination is required" in str(e)
        else:
            raise AssertionError("should require a destination")
    finally:
        _restore_env(old)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
