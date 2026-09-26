"""`travel-assistant` console entry point: subcommand dispatcher.

    travel-assistant ui [--db PATH] [--host HOST] [--port PORT]
    travel-assistant research [--destination ...]   (full pipeline CLI)
    travel-assistant runs list|show ...             (run-store queries)

New commands (e.g. a future `server` API mode) slot in by adding an entry to
COMMANDS. Imports are lazy on purpose: `python -m travel_assistant.research`
must keep working without the eager-import RuntimeWarning that importing
`research` at package scope would trigger (see travel_assistant/__init__.py).
"""
import argparse


def _ui(argv):
    from . import ui
    return ui.main(argv)


def _research(argv):
    from . import research
    return research.main(argv)


def _runs(argv):
    from . import runs
    return runs.main(argv)


COMMANDS = {
    "ui": (_ui, "local dashboard over the run store (localhost map server)"),
    "research": (_research, "run the travel-research pipeline"),
    "runs": (_runs, "query the SQLite run store"),
}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="travel-assistant",
        description="Travel-research pipeline CLI.")
    ap.add_argument("command", choices=sorted(COMMANDS),
                    help="subcommand to run")
    ap.add_argument("rest", nargs=argparse.REMAINDER,
                    help="arguments passed through to the subcommand")
    a = ap.parse_args(argv)
    fn, _ = COMMANDS[a.command]
    rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
