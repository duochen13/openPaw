import collect_rednote as c

def test_slugify_ascii_and_spaces():
    assert c.slugify("Lisbon") == "lisbon"
    assert c.slugify("San Francisco") == "san_francisco"
    assert c.slugify("Tokyo!! 2026") == "tokyo_2026"

def test_dedup_by_url_keeps_first():
    items = [{"url": "u1", "likes": 5}, {"url": "u1", "likes": 9}, {"url": "u2", "likes": 1}]
    out = c.dedup_by_url(items)
    assert [i["url"] for i in out] == ["u1", "u2"]

def test_rank_by_likes_desc():
    items = [{"url": "a", "likes": 3}, {"url": "b", "likes": 30}, {"url": "c", "likes": 10}]
    out = c.rank_by_likes(items)
    assert [i["url"] for i in out] == ["b", "c", "a"]

def test_rank_handles_missing_likes():
    items = [{"url": "a"}, {"url": "b", "likes": 2}]
    out = c.rank_by_likes(items)
    assert out[0]["url"] == "b"

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print(f"PASS {name}")
    print("all passed")
