#!/usr/bin/env python3
"""Geocode places (Nominatim/OpenStreetMap) and emit a KML for Google My Maps import.

WHY KML: Google Maps has no public API to add pins to a user's saved lists. The
robust path is Google My Maps -> Create new map -> Import -> select this .kml,
which drops every place as a colored pin on one shareable map (also visible in
the Google Maps app under Your places -> Maps).

Geocoding uses Nominatim (free, no API key). Usage policy: <=1 req/sec and a
descriptive User-Agent. Pins are colored by place type.
"""
import json, os, re, time, argparse, urllib.parse, urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "openpaw-travel-assistant/1.0 (personal trip planning)"
TYPE_COLORS = {  # KML line/icon colors are aabbggrr hex
    "restaurant": "ff0000ff", "cafe": "ff00a5ff", "bar": "ff800080",
    "sight": "ff00ff00", "shop": "ffff0000", "other": "ff808080",
}

def style_id(place_type):
    return place_type if place_type in TYPE_COLORS else "other"

def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def placemark(p):
    sid = style_id(p.get("type", "other"))
    desc_parts = []
    if p.get("why_loved"): desc_parts.append(p["why_loved"])
    if p.get("area"): desc_parts.append("Area: " + str(p["area"]))
    if p.get("rating") not in (None, ""): desc_parts.append("Rating: " + str(p["rating"]))
    for u in p.get("source_urls", []) or []:
        desc_parts.append(u)
    desc = _esc("\n".join(desc_parts))
    return (f"    <Placemark>\n"
            f"      <name>{_esc(p.get('name',''))}</name>\n"
            f"      <description>{desc}</description>\n"
            f"      <styleUrl>#{sid}</styleUrl>\n"
            f"      <Point><coordinates>{p['lng']},{p['lat']},0</coordinates></Point>\n"
            f"    </Placemark>")

def _styles():
    out = []
    for sid, color in TYPE_COLORS.items():
        out.append(f'    <Style id="{sid}"><IconStyle><color>{color}</color></IconStyle></Style>')
    return "\n".join(out)

def build_kml(destination, places):
    marks, n = [], 0
    for p in places:
        if p.get("lat") is None or p.get("lng") is None:
            continue
        marks.append(placemark(p)); n += 1
    body = "\n".join(marks)
    kml = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<kml xmlns="http://www.opengis.net/kml/2.2">\n'
           f'  <Document>\n'
           f'    <name>{_esc("Travel — " + destination)}</name>\n'
           f'{_styles()}\n'
           f'{body}\n'
           f'  </Document>\n'
           f'</kml>\n')
    return kml, n

def geocode(query):
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(f"{NOMINATIM}?{params}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            hits = json.loads(r.read().decode())
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"])
    except Exception as e:
        print(f"  geocode err [{query}]: {e}")
    return None, None

def enrich_and_build(path):
    obj = json.load(open(path, encoding="utf-8"))
    dest = obj.get("destination", "")
    for p in obj.get("places", []):
        if p.get("lat") is None or p.get("lng") is None:
            q = " ".join(str(x) for x in [p.get("name",""), p.get("area",""), dest] if x)
            p["lat"], p["lng"] = geocode(q)
            time.sleep(1.1)  # Nominatim: <=1 req/sec
    json.dump(obj, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    kml, n = build_kml(dest, obj.get("places", []))
    maps_dir = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    os.makedirs(maps_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "_", dest.strip().lower()).strip("_") or "map"
    out = os.path.join(maps_dir, f"{slug}.kml")
    open(out, "w", encoding="utf-8").write(kml)
    print(f"[{slug}] {n} pins -> {out}")
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="path to a validated {slug}_places_*.json")
    a = ap.parse_args()
    enrich_and_build(a.file)
