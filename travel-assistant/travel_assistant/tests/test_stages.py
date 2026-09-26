"""Unit tests for the stage wrappers (no network: TA_OFFLINE=1)."""
import os
import tempfile

os.environ["TA_OFFLINE"] = "1"

from travel_assistant.stages import analyze as st_analyze
from travel_assistant.stages import collect as st_collect
from travel_assistant.stages import geocode as st_geocode
from travel_assistant.stages import map as st_map
from travel_assistant.stages import validate as st_validate

GOOD = {
    "destination": "Lisbon", "generated_at": "2026-07-02T18:05:00Z",
    "source_mode": "rednote",
    "places": [{
        "name": "Time Out Market", "type": "restaurant", "area": "Cais",
        "why_loved": "great food hall", "source_urls": ["https://x.com/a"],
        "mention_count": 4, "sentiment": "positive",
        "map_link": None, "rating": None, "tags": ["food-hall"],
        "lat": 38.7071, "lng": -9.1355,
    }],
}


def test_validate_good_passes_and_bad_raises():
    ok, errors = st_validate.validate_places(GOOD)
    assert ok and errors == []
    assert st_validate.check(GOOD) is True
    bad = {"destination": "X", "generated_at": "t", "source_mode": "nope",
           "places": []}
    ok, errors = st_validate.validate_places(bad)
    assert not ok and errors
    try:
        st_validate.check(bad)
    except ValueError as e:
        assert "source_mode" in str(e)
    else:
        raise AssertionError("check() should raise on invalid")


def test_analyze_requires_analyzer_or_replay():
    try:
        st_analyze.analyze_raw({"discussions": []}, destination="X")
    except NotImplementedError as e:
        assert "from_analysis" in str(e)
    else:
        raise AssertionError("should raise without analyzer")
    obj = st_analyze.analyze_raw({"discussions": []}, destination="X",
                                 analyzer=lambda raw, destination, vibe: GOOD)
    assert obj["destination"] == "Lisbon"


def test_geocode_skips_places_with_coords_no_network():
    import copy
    obj = copy.deepcopy(GOOD)
    n_geo, n_missing = st_geocode.enrich_places(obj, skip=False)
    assert (n_geo, n_missing) == (0, 0)  # no network touched


def test_geocode_offline_refuses_network():
    import copy
    obj = copy.deepcopy(GOOD)
    obj["places"][0]["lat"] = None
    obj["places"][0]["lng"] = None
    n_geo, n_missing = st_geocode.enrich_places(obj, skip=True)
    assert (n_geo, n_missing) == (0, 1)  # counted, not fetched
    try:
        st_geocode.enrich_places(obj, skip=False)
    except RuntimeError as e:
        assert "TA_OFFLINE" in str(e)
    else:
        raise AssertionError("should refuse network geocode when offline")


def test_map_stage_builds_all_artifacts():
    import copy
    d = tempfile.mkdtemp(prefix="ta_map_")
    obj = copy.deepcopy(GOOD)
    # add a coord-less place: skipped from KML/HTML, kept in CSV
    obj["places"].append({**obj["places"][0], "name": "No Coords",
                          "lat": None, "lng": None})
    art = st_map.build_artifacts(obj, out_dir=d, region="PT")
    assert art["n_pins"] == 1 and art["n_html_kept"] == 1
    assert art["n_html_skipped"] == 1 and art["n_csv_rows"] == 2
    for key in ("kml_path", "map_html_path", "csv_path"):
        assert os.path.exists(art[key]), key
    kml = open(art["kml_path"], encoding="utf-8").read()
    assert kml.count("<Placemark>") == 1 and "Time Out Market" in kml
    html = open(art["map_html_path"], encoding="utf-8").read()
    assert "Map — Lisbon" in html and "Time Out Market" in html
    csv_text = open(art["csv_path"], encoding="utf-8").read()
    assert csv_text.count("\n") == 3  # header + 2 rows
    assert "Lisbon, PT" in csv_text


def test_collect_raw_helpers():
    raw = {"destination": "Kyoto", "source": "rednote",
           "discussions": [{"title": "t"}]}
    s = st_collect.raw_summary(raw)
    assert s == {"destination": "Kyoto", "source": "rednote",
                 "n_discussions": 1}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("all passed")
