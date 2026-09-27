"""`python -m travel_assistant`: dispatch to the `travel-assistant` CLI."""
import sys

from . import cli

USAGE = """travel_assistant — importable travel-research pipeline.

Usage:
  python -m travel_assistant ui [--db PATH] [--host HOST] [--port PORT]
  python -m travel_assistant research --destination "Kyoto" --vibe food \\
      --from-analysis data/analysis/kyoto_places_20260701.json --skip-geocode
  python -m travel_assistant runs list
  python -m travel_assistant runs show 3 --places

Or, after `pip install -e .`:  travel-assistant <ui|research|runs> ...

Stages: collect -> analyze -> validate -> geocode -> map.
Every run is recorded in the SQLite run store (data/runs/runs.db).
See README.md "Python package" section for details.
"""


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if argv[0] not in cli.COMMANDS:
        print(USAGE, file=sys.stderr)
        return 2
    return cli.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
