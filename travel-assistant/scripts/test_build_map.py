import build_map as m

PLACE = {"name": "Time Out <Market>", "type": "restaurant", "area": "Cais",
         "why_loved": "great & cheap", "source_urls": ["https://x.com/a"],
         "rating": 4.5, "lat": 38.70, "lng": -9.14}

def test_placemark_has_name_and_coords():
    pm = m.placemark(PLACE)
    assert "<Placemark>" in pm and "</Placemark>" in pm
    # coordinates are lng,lat,0 order per KML spec
    assert "-9.14,38.7,0" in pm.replace(" ", "")

def test_placemark_escapes_xml():
    pm = m.placemark(PLACE)
    assert "&lt;Market&gt;" in pm and "&amp;" in pm
    assert "<Market>" not in pm.replace("<Placemark>", "")

def test_style_id_by_type():
    assert m.style_id("restaurant") == "restaurant"
    assert m.style_id("unknown-type") == "other"

def test_build_kml_skips_placeless_coords_and_counts():
    places = [PLACE, {"name": "No Coords", "type": "sight", "lat": None, "lng": None}]
    kml, n = m.build_kml("Lisbon", places)
    assert kml.startswith("<?xml") and "<kml" in kml
    assert kml.count("<Placemark>") == 1 and n == 1
    assert "Lisbon" in kml

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
