#!/usr/bin/env python3
"""Emit a Google My Maps import CSV from a validated places file.

WHY A CSV WHEN build_map.py ALREADY MAKES A KML: the KML can only carry places
that geocoded locally, and Nominatim's coverage of small-town businesses is poor
(2/23 on the first Yellowknife pass). The CSV instead ships an `Address` column
and lets Google geocode it at import time, which places rows we could not.

On import, choose `Address` to position the placemarks and `Name` to title them.
Latitude/Longitude are included as a fallback for rows Google places wrongly.
"""
import argparse, csv, json, os, re


def address_for(place, destination):
    """Build a geocodable one-line address from name + area.

    `area` is free text from the analyzer and often carries a parenthetical or an
    em-dash note ("Ingraham Trail teepee site — pin is the downtown office").
    Everything after the first "—", "(", or "/" is commentary, not address.
    """
    area = re.split(r"[—(/]", place.get("area", ""))[0].strip().rstrip(",")
    name = place["name"].split("(")[0].strip()
    return ", ".join(x for x in [name, area, destination] if x)


def write_csv(obj, out_path, region="NT, Canada"):
    dest = obj.get("destination", "")
    suffix = f"{dest}, {region}" if region else dest
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Name", "Address", "Latitude", "Longitude", "Type",
                    "Why people love it", "Source", "Google Maps link"])
        for p in obj.get("places", []):
            w.writerow([p["name"], address_for(p, suffix),
                        p.get("lat") or "", p.get("lng") or "", p.get("type", ""),
                        p.get("why_loved", ""),
                        (p.get("source_urls") or [""])[0],
                        p.get("map_link") or ""])
    return len(obj.get("places", []))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file", help="path to a validated {slug}_places_*.json")
    ap.add_argument("--region", default="NT, Canada",
                    help="region appended to each address, e.g. 'BC, Canada'")
    a = ap.parse_args()

    obj = json.load(open(a.file, encoding="utf-8"))
    slug = re.sub(r"[^a-z0-9]+", "_", obj.get("destination", "").lower()).strip("_") or "map"
    maps_dir = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    os.makedirs(maps_dir, exist_ok=True)
    out = os.path.join(maps_dir, f"{slug}_mymaps.csv")
    n = write_csv(obj, out, a.region)
    print(f"[{slug}] {n} rows -> {out}")
    print("  My Maps: Create a new map -> Import -> position on 'Address', title on 'Name'")
