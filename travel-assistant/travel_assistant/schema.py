"""Places-object schema constants.

Single source of truth for the analyzer output schema documented in
SKILL.md Step 3. Mirrors scripts/validate_places.py (which remains the
executable validator); import these when building new stages instead of
re-typing the enums.
"""
import html as _html
import re as _re
from urllib.parse import urlsplit as _urlsplit

TYPES = ("restaurant", "sight", "cafe", "bar", "shop", "other")
SENTIMENTS = ("positive", "mixed", "negative")
SOURCE_MODES = ("rednote", "fallback", "mixed")

REQUIRED_TOP_LEVEL = ("destination", "generated_at", "source_mode", "places")

# Per-place keys the analyzer must emit (lat/lng/map_link/rating may be null;
# geocoding fills lat/lng later). price_hint / geocode_confidence are reserved
# for future stages — the run store already has columns for them.
PLACE_KEYS = ("name", "type", "area", "why_loved", "source_urls",
              "mention_count", "sentiment", "tags",
              "map_link", "rating", "lat", "lng")

# Optional per-place keys the pipeline itself may add (not required of the
# analyzer). "source" is the collector label ("rednote" / "websearch"),
# stamped by research() via travel_assistant.collectors.label_places and
# persisted per place in the run store (issue #76).
OPTIONAL_PLACE_KEYS = ("source",)


# --------------------------------------------------------------------------
# URL safety (output-encoding hardening, issues #136/#137/#138 family).
#
# Place URLs (source_urls, map_link) end up as href values in generated HTML:
# the map bundle (scripts/build_gmap_html.py popups) and the local dashboard
# (travel_assistant/ui.py popups + place cards). html.escape() stops
# attribute breakout but does NOT stop a `javascript:` scheme, which the
# browser executes on click — so every URL bound for an href must pass this
# allowlist. Only http/https are legitimate here; anything else is dropped
# (never rendered, never passed through).
# --------------------------------------------------------------------------
_HTTP_SCHEMES = ("http", "https")
_WS_STRIP = _re.compile(r"[\t\n\r]")  # browsers strip these before parsing a URL


def _url_scheme(url):
    """Scheme of `url` after undoing the obfuscations browsers tolerate."""
    u = _WS_STRIP.sub("", _html.unescape(url.strip()))
    try:
        return _urlsplit(u).scheme.lower()
    except ValueError:
        return ""


def is_safe_url(url):
    """True if `url` is a non-empty string with an http(s) scheme.

    Rejects `javascript:` / `data:` / `vbscript:` and friends, including
    HTML-entity-obfuscated (`&#106;avascript:`) and whitespace-padded forms.
    """
    return (isinstance(url, str) and bool(url.strip())
            and _url_scheme(url) in _HTTP_SCHEMES)


def safe_url(url):
    """Return `url` (stripped) if it passes :func:`is_safe_url`, else None."""
    return url.strip() if is_safe_url(url) else None


def sanitize_place_urls(place):
    """Copy of `place` with non-http(s) `source_urls` / `map_link` dropped.

    Defense in depth: validate_places.py rejects such URLs at intake, but
    renderers (build_gmap_html.py, ui.py) must not trust their input either.
    """
    p = dict(place)
    p["source_urls"] = [u for u in (p.get("source_urls") or []) if is_safe_url(u)]
    ml = p.get("map_link")
    p["map_link"] = ml if is_safe_url(ml) else None
    return p
