"""`python -m travel_assistant`: print usage."""
print("""travel_assistant — importable travel-research pipeline.

Usage:
  python -m travel_assistant.research --destination "Kyoto" --vibe food \\
      --from-analysis data/analysis/kyoto_places_20260701.json --skip-geocode
  python -m travel_assistant.runs list
  python -m travel_assistant.runs show 3 --places

Stages: collect -> analyze -> validate -> geocode -> map.
Every run is recorded in the SQLite run store (data/runs/runs.db).
See README.md "Python package" section for details.
""")
