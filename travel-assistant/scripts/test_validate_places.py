import validate_places as v

GOOD = {
    "destination": "Lisbon", "generated_at": "2026-07-02T18:05:00Z",
    "source_mode": "rednote",
    "places": [{
        "name": "Time Out Market", "type": "restaurant", "area": "Cais do Sodré",
        "why_loved": "great food hall", "source_urls": ["https://x.com/a"],
        "mention_count": 4, "sentiment": "positive",
        "map_link": None, "rating": None, "tags": ["food-hall"]
    }]
}

def test_good_object_passes():
    ok, errors = v.validate(GOOD)
    assert ok and errors == []

def test_missing_source_urls_fails():
    bad = {**GOOD, "places": [{**GOOD["places"][0], "source_urls": []}]}
    ok, errors = v.validate(bad)
    assert not ok and any("source_urls" in e for e in errors)

def test_bad_type_enum_fails():
    bad = {**GOOD, "places": [{**GOOD["places"][0], "type": "hotel"}]}
    ok, errors = v.validate(bad)
    assert not ok and any("type" in e for e in errors)

def test_bad_source_mode_fails():
    bad = {**GOOD, "source_mode": "guess"}
    ok, errors = v.validate(bad)
    assert not ok and any("source_mode" in e for e in errors)

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
