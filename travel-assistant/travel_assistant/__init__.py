"""travel_assistant: the travel-research pipeline as an importable package.

Stages: collect -> analyze -> validate -> geocode -> map.
Every run is recorded in a SQLite run store (store.RunStore).

    from travel_assistant import research  # resolves to travel_assistant.research
    from travel_assistant import RunStore
    rec = research(destination="Kyoto", vibe="food",
                   from_analysis="data/analysis/kyoto_places_20260701.json",
                   skip_geocode=True)

CLI:
    python -m travel_assistant.research --destination Kyoto --vibe food ...
    python -m travel_assistant.runs list

Note: research is intentionally not re-exported here — importing the
submodule eagerly would make `python -m travel_assistant.research` emit a
RuntimeWarning (module already in sys.modules before __main__ execution).
`from travel_assistant import research` still works via submodule fallback.
"""
from .store import RunStore

__version__ = "0.1.0"
__all__ = ["RunStore", "__version__"]
