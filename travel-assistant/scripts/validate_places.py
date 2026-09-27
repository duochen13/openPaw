#!/usr/bin/env python3
"""Validate the analyzer's places object before Notion publish. Pure + CLI."""
import json, sys, argparse, os

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # import the travel_assistant package
from travel_assistant.schema import is_safe_url

TYPES = {"restaurant", "sight", "cafe", "bar", "shop", "other"}
SENTIMENTS = {"positive", "mixed", "negative"}
MODES = {"rednote", "fallback", "mixed"}

def validate(obj):
    errors = []
    for k in ("destination", "generated_at", "source_mode", "places"):
        if k not in obj:
            errors.append(f"missing top-level key: {k}")
    if obj.get("source_mode") not in MODES:
        errors.append(f"source_mode must be one of {sorted(MODES)}")
    for idx, p in enumerate(obj.get("places", [])):
        tag = f"places[{idx}]"
        if not p.get("name"):
            errors.append(f"{tag}.name is required")
        if p.get("type") not in TYPES:
            errors.append(f"{tag}.type must be one of {sorted(TYPES)}")
        if p.get("sentiment") not in SENTIMENTS:
            errors.append(f"{tag}.sentiment must be one of {sorted(SENTIMENTS)}")
        if not p.get("source_urls"):
            errors.append(f"{tag}.source_urls must be a non-empty list")
        # Issue #138: source_urls / map_link become hrefs in generated HTML;
        # only http(s) URLs are safe there (`javascript:` executes on click).
        for i, u in enumerate(p.get("source_urls") or []):
            if not is_safe_url(u):
                errors.append(f"{tag}.source_urls[{i}] must be an http(s) URL, got {u!r}")
        if p.get("map_link") and not is_safe_url(p["map_link"]):
            errors.append(f"{tag}.map_link must be an http(s) URL, got {p['map_link']!r}")
        if not isinstance(p.get("mention_count"), int):
            errors.append(f"{tag}.mention_count must be an int")
    return (len(errors) == 0, errors)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    a = ap.parse_args()
    ok, errors = validate(json.load(open(a.file, encoding="utf-8")))
    if ok:
        print("valid"); sys.exit(0)
    print("INVALID:"); [print(" -", e) for e in errors]; sys.exit(1)
