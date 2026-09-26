"""Places-object schema constants.

Single source of truth for the analyzer output schema documented in
SKILL.md Step 3. Mirrors scripts/validate_places.py (which remains the
executable validator); import these when building new stages instead of
re-typing the enums.
"""
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
