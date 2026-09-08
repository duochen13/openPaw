#!/usr/bin/env python3
"""Unit tests for the pure block-builders in upload_to_notion.py (no network)."""
import upload_to_notion as u


def test_file_block_shape():
    b = u.file_block("fu-123", "open me")
    assert b["type"] == "file"
    assert b["file"]["type"] == "file_upload"
    assert b["file"]["file_upload"]["id"] == "fu-123"
    assert b["file"]["caption"][0]["text"]["content"] == "open me"


def test_build_children_both_files_and_db():
    kids = u.build_children("html-id", "kml-id", "https://notion.so/db")
    types = [k["type"] for k in kids]
    assert types[0] == "paragraph"                    # how-to note first
    assert types.count("file") == 2                   # html + kml
    # the db link paragraph carries a link
    last = kids[-1]["paragraph"]["rich_text"][0]
    assert last["text"]["link"]["url"] == "https://notion.so/db"
    # file blocks reference the right upload ids
    ids = [k["file"]["file_upload"]["id"] for k in kids if k["type"] == "file"]
    assert ids == ["html-id", "kml-id"]


def test_build_children_kml_only_no_db():
    kids = u.build_children(None, "kml-id", None)
    assert [k["type"] for k in kids] == ["paragraph", "file"]
    assert kids[1]["file"]["file_upload"]["id"] == "kml-id"


def test_mime_map():
    assert u.MIME[".html"] == "text/html"
    assert ".kml" in u.MIME


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print("ok", fn.__name__)
    print("\nAll {} tests passed.".format(len(fns)))
