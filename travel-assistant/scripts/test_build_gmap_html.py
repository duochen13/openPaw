#!/usr/bin/env python3
"""Unit tests for the pure helpers in build_gmap_html.py. Run: python3 test_build_gmap_html.py"""
import json
import build_gmap_html as m


def test_filter_places_keeps_only_valid_coords():
    places = [
        {"name": "A", "lat": 49.1, "lng": -123.5},
        {"name": "B", "lat": None, "lng": -123.5},
        {"name": "C", "lat": 49.2},                       # missing lng
        {"name": "D", "lat": "49.3", "lng": "-123.4"},    # strings are not coords
        {"name": "E", "lat": 0, "lng": 0},                # 0/0 is valid (equator)
    ]
    kept, skipped = m.filter_places(places)
    assert [p["name"] for p in kept] == ["A", "E"], kept
    assert [p["name"] for p in skipped] == ["B", "C", "D"], skipped


def test_filter_places_empty():
    assert m.filter_places([]) == ([], [])
    assert m.filter_places(None) == ([], [])


def test_safe_json_escapes_closing_script_tag():
    out = m.safe_json([{"why_loved": "great </script> spot"}])
    assert "</script>" not in out
    assert "<\\/script>" in out
    # still valid JSON after unescaping the backslash the browser removes
    assert json.loads(out.replace("<\\/", "</"))[0]["why_loved"] == "great </script> spot"


def test_safe_json_preserves_unicode():
    out = m.safe_json([{"name": "Café · 日本"}])
    assert "Café · 日本" in out


def test_slugify():
    assert m.slugify("Sunshine Coast BC") == "sunshine_coast_bc"
    assert m.slugify("Tokyo!!") == "tokyo"
    assert m.slugify("") == "trip"
    assert m.slugify(None) == "trip"


def test_build_html_placeholder_warning_and_counts():
    data = {"destination": "Testville", "places": [
        {"name": "A", "lat": 1.0, "lng": 2.0, "type": "cafe"},
        {"name": "B"},  # no coords -> skipped
    ]}
    html, kept, skipped = m.build_html(data, "YOUR_API_KEY")
    assert len(kept) == 1 and len(skipped) == 1
    assert "1 places shown" in html and "1 skipped" in html
    assert "add your Google Maps API key" in html
    assert "YOUR_API_KEY" in html
    assert '"name": "A"' in html or '"name":"A"' in html


def test_build_html_has_category_colors_and_legend():
    data = {"destination": "Testville", "places": [
        {"name": "A", "lat": 1.0, "lng": 2.0, "type": "restaurant"},
        {"name": "B", "lat": 3.0, "lng": 4.0, "type": "sight"},
    ]}
    html, _, _ = m.build_html(data, "K")
    # category map, colored-pin helper, and legend scaffolding are all present
    assert "const CATS" in html
    assert '"#E8453C"' in html and '"#2E9E4F"' in html  # food + outdoors colors
    assert "function pinIcon" in html
    assert 'id="legend"' in html and "buildLegend(PRESENT)" in html
    assert "icon: pinIcon(CATS[cat].color)" in html
    # legend is an interactive category filter
    assert "function toggleCat" in html
    assert "MARKERS_BY_CAT" in html and "m.setVisible(SELECTED[cat])" in html
    assert 'data-cat="' in html and "click to filter" in html


def test_build_html_has_driving_route():
    data = {"destination": "Testville", "places": [
        {"name": "A", "lat": 1.0, "lng": 2.0, "type": "restaurant"},
        {"name": "B", "lat": 3.0, "lng": 4.0, "type": "cafe"},
    ]}
    html, _, _ = m.build_html(data, "K")
    # the ROUTE_JS marker was replaced with the real route code
    assert "//__ROUTE_JS__" not in html
    assert "function rebuildRoute" in html and "rebuildRoute()" in html
    assert 'importLibrary("routes")' in html and "Route.computeRoutes" in html
    assert "function orderPins" in html
    assert "Driving route" in html and "toggleRoute" in html
    assert "MIN_LEG_MIN = 10" in html            # legs < 10 min are not drawn
    assert "function visiblePlaced" in html       # route follows the category filter
    assert "libraries=routes" in html
    assert "enable the Routes API" in html        # estimate-fallback note


def test_build_html_has_places_search():
    data = {"destination": "Testville", "places": [
        {"name": "A", "lat": 1.0, "lng": 2.0, "type": "restaurant"},
    ]}
    html, _, _ = m.build_html(data, "K")
    assert "//__SEARCH_JS__" not in html
    assert "libraries=routes,places" in html
    assert "PlaceAutocompleteElement" in html and 'gmp-select' in html
    assert "function initSearch" in html and "function addPlace" in html
    assert "function removePlace" in html and "iw-remove" in html
    assert 'id="searchbox"' in html
    assert '"#D81B8C"' in html and '"Added by you"' in html  # the added-pin category


def test_build_html_injects_real_key():
    data = {"destination": "Testville", "places": [{"name": "A", "lat": 1.0, "lng": 2.0}]}
    html, kept, _ = m.build_html(data, "REALKEY123")
    assert "key=REALKEY123&libraries=routes,places&callback=initMap" in html
    assert "add your Google Maps API key" not in html


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("ok", fn.__name__)
    print("\nAll {} tests passed.".format(len(fns)))
