"""Geocode stage: fill in missing lat/lng via Nominatim.

Wraps build_map.geocode (Nominatim, <=1 req/sec per usage policy). Places that
already carry coordinates are left untouched, so replaying a previously
geocoded analysis file performs zero network calls.

Set TA_OFFLINE=1 to forbid network access: any place that would need a live
lookup raises RuntimeError instead. Tests run with TA_OFFLINE=1.
"""
import os
import time

from . import ensure_scripts_on_path

ensure_scripts_on_path()
import build_map as _bm


def offline():
    return os.environ.get("TA_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def geocode_query(place, destination):
    return " ".join(str(x) for x in
                    [place.get("name", ""), place.get("area", ""), destination]
                    if x)


def enrich_places(obj, *, skip=False):
    """Geocode places missing lat/lng in place.

    Returns (n_geocoded, n_still_missing). With skip=True, counts the missing
    ones without any network traffic.
    """
    dest = obj.get("destination", "")
    n_geocoded, n_missing = 0, 0
    for p in obj.get("places", []):
        if p.get("lat") is not None and p.get("lng") is not None:
            continue
        n_missing += 1
        if skip:
            continue
        q = geocode_query(p, dest)
        if offline():
            raise RuntimeError(
                f"TA_OFFLINE=1: refusing network geocode for {q!r} "
                "(re-run with --skip-geocode or unset TA_OFFLINE)")
        p["lat"], p["lng"] = _bm.geocode(q)
        if p["lat"] is not None:
            n_geocoded += 1
            n_missing -= 1
        time.sleep(1.1)  # Nominatim usage policy
    return n_geocoded, n_missing
