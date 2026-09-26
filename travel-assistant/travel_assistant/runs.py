"""Query the run store: `python -m travel_assistant.runs list|show`."""
import argparse
import json

from . import paths
from . import store as store_mod


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query the travel run store.")
    ap.add_argument("--db", default=None, help="run-store SQLite path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list recent runs")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--destination", default=None)

    p_show = sub.add_parser("show", help="show one run with its places")
    p_show.add_argument("run_id", type=int)
    p_show.add_argument("--places", action="store_true",
                        help="include the per-place rows")

    a = ap.parse_args(argv)
    db = a.db or paths.runs_db_path()
    st = store_mod.RunStore(db)
    try:
        if a.cmd == "list":
            rows = st.list_runs(limit=a.limit, destination=a.destination)
            print(f"{len(rows)} run(s) in {db}")
            for r in rows:
                print(f"  #{r['id']} [{r['status']}] {r['destination']} "
                      f"vibe={r['vibe']} places={r['n_places']} "
                      f"started={r['started_at']}")
        elif a.cmd == "show":
            rec = st.get_run(a.run_id)
            if rec is None:
                print(f"no run #{a.run_id} in {db}")
                return 1
            if not a.places:
                rec = {k: v for k, v in rec.items() if k != "places"}
                rec["n_place_rows"] = len(st.get_run(a.run_id)["places"])
            print(json.dumps(rec, indent=2, ensure_ascii=False)[:6000])
    finally:
        st.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
