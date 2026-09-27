"""Regression tests for output-encoding security fixes (#136, #137, #138).

Run from the travel-assistant dir:  python3 -m pytest travel_assistant/tests/
"""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import build_gmap_html as gmap_mod
import build_mymaps_csv as csv_mod
import validate_places as validate_mod

from travel_assistant import schema as schema_mod
from travel_assistant import ui as ui_mod


def _place(**kw):
    p = {"name": "Cafe Luna", "type": "cafe", "area": "Downtown",
         "why_loved": "great pour-over", "source_urls": ["https://example.com/a"],
         "mention_count": 3, "sentiment": "positive", "tags": [],
         "map_link": None, "rating": 4.5, "lat": 49.1, "lng": -123.1}
    p.update(kw)
    return p


def _valid_obj(place):
    return {"destination": "Testville", "generated_at": "2026-09-27T00:00:00",
            "source_mode": "rednote", "places": [place]}


# --------------------------------------------------------------------------
# #136 — CSV formula injection (OWASP: prefix = + - @ and tab/CR with ').
# --------------------------------------------------------------------------
def _csv_rows(tmp_path, place):
    out = str(tmp_path / "t.csv")
    csv_mod.write_csv(_valid_obj(place), out)
    with open(out, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_csv_prefixes_formula_name(tmp_path):
    rows = _csv_rows(tmp_path, _place(name='=HYPERLINK("http://evil")'))
    assert rows[1][0] == "'=HYPERLINK(\"http://evil\")", rows[1][0]


def test_csv_prefixes_all_formula_leaders(tmp_path):
    rows = _csv_rows(
        tmp_path,
        _place(name="+cmd", area="-x", why_loved="@evil", type="\tspam"))
    assert rows[1][0] == "'+cmd"            # Name
    assert rows[1][1].startswith("'")       # Address (built from name+area)
    assert rows[1][4] == "'\tspam"          # Type
    assert rows[1][5] == "'@evil"           # Why people love it


def test_csv_prefixes_carriage_return_leader(tmp_path):
    rows = _csv_rows(tmp_path, _place(why_loved="\r=2+2"))
    assert rows[1][5] == "'\r=2+2"


def test_csv_leaves_normal_cells_untouched(tmp_path):
    rows = _csv_rows(tmp_path, _place())
    assert rows[1][0] == "Cafe Luna"
    assert rows[1][5] == "great pour-over"
    assert rows[1][6] == "https://example.com/a"  # Source URL unquoted-plain


# --------------------------------------------------------------------------
# #137 — stored HTML injection via unescaped `destination` in <title>.
# --------------------------------------------------------------------------
def test_title_escapes_destination():
    payload = "</title><script>alert(1)</script>"
    html, kept, skipped = gmap_mod.build_html(
        {"destination": payload, "places": []}, "YOUR_API_KEY")
    assert payload not in html
    assert "<title>Map — &lt;/title&gt;&lt;script&gt;alert(1)&lt;/script&gt;</title>" in html


def test_title_escapes_quotes_and_ampersand():
    payload = 'A "quoted" & <b>trip</b>'
    html, _, _ = gmap_mod.build_html({"destination": payload, "places": []},
                                     "YOUR_API_KEY")
    assert payload not in html
    assert "A &quot;quoted&quot; &amp; &lt;b&gt;trip&lt;/b&gt;" in html


# --------------------------------------------------------------------------
# #138 — javascript: URLs must never reach an href.
# --------------------------------------------------------------------------
def test_safe_url_allowlists_http_only():
    assert schema_mod.is_safe_url("https://example.com/a?b=c")
    assert schema_mod.is_safe_url("http://example.com/")
    assert schema_mod.is_safe_url("  https://example.com  ")  # padded
    assert not schema_mod.is_safe_url("javascript:alert(1)")
    assert not schema_mod.is_safe_url("JaVaScRiPt:alert(1)")
    assert not schema_mod.is_safe_url("data:text/html,<script>alert(1)</script>")
    assert not schema_mod.is_safe_url("vbscript:msgbox(1)")
    assert not schema_mod.is_safe_url("&#106;avascript:alert(1)")  # entity-obfuscated
    assert not schema_mod.is_safe_url("")
    assert not schema_mod.is_safe_url(None)
    assert not schema_mod.is_safe_url(123)


def test_safe_url_returns_stripped_or_none():
    assert schema_mod.safe_url("  https://example.com/a ") == "https://example.com/a"
    assert schema_mod.safe_url("javascript:alert(1)") is None


def test_sanitize_place_urls_drops_bad_keeps_good():
    p = _place(source_urls=["javascript:alert(1)", "https://good.example/x"],
               map_link="data:text/html,evil")
    out = schema_mod.sanitize_place_urls(p)
    assert out["source_urls"] == ["https://good.example/x"]
    assert out["map_link"] is None
    # input not mutated
    assert p["source_urls"] == ["javascript:alert(1)", "https://good.example/x"]


def test_validate_rejects_javascript_source_url():
    ok, errors = validate_mod.validate(
        _valid_obj(_place(source_urls=["javascript:alert(1)"])))
    assert not ok
    assert any("source_urls[0]" in e and "http(s)" in e for e in errors), errors


def test_validate_rejects_javascript_map_link():
    ok, errors = validate_mod.validate(
        _valid_obj(_place(map_link="javascript:alert(1)")))
    assert not ok
    assert any("map_link" in e for e in errors), errors


def test_validate_accepts_https_urls():
    ok, errors = validate_mod.validate(
        _valid_obj(_place(source_urls=["https://example.com/a"],
                           map_link="https://maps.example/m")))
    assert ok, errors


def test_build_html_never_embeds_javascript_href():
    p = _place(source_urls=["javascript:alert(1)"], map_link="javascript:alert(2)")
    html, _, _ = gmap_mod.build_html({"destination": "T", "places": [p]},
                                     "YOUR_API_KEY")
    assert "javascript:" not in html
    assert '"source_urls": []' in html  # dropped before embedding
    # https URLs still flow through to the popup link
    html2, _, _ = gmap_mod.build_html(
        {"destination": "T", "places": [_place()]}, "YOUR_API_KEY")
    assert "https://example.com/a" in html2


def test_ui_place_card_never_renders_javascript_href():
    card = ui_mod._place_card(_place(source_urls=["javascript:alert(1)"]))
    assert "javascript:" not in card
    assert "href" not in card  # no link rendered at all
    card2 = ui_mod._place_card(_place())
    assert "href='https://example.com/a'" in card2


def test_ui_map_fragment_never_embeds_javascript_url():
    run = {"destination": "T",
           "places": [_place(source_urls=["javascript:alert(1)"],
                              map_link="javascript:alert(2)")]}
    frag, geo = ui_mod.map_fragment(run, "sec138")
    assert "javascript:" not in frag
    assert '"url": ""' in frag  # popup data carries no URL
    # https URLs still reach the popup payload
    frag2, _ = ui_mod.map_fragment(
        {"destination": "T", "places": [_place()]}, "sec138b")
    assert '"url": "https://example.com/a"' in frag2
