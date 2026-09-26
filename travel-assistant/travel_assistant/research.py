"""End-to-end research run: collect -> analyze -> validate -> geocode -> map.

Every run is recorded in the SQLite run store (see store.py). Analysis inputs
are never mutated: the enriched (geocoded) analysis is written to a new
timestamped file under data/analysis/.

Offline / test usage: replay a saved analysis file
    python -m travel_assistant.research --from-analysis data/analysis/vancouver_places_20260709_030913.json --skip-geocode
Live usage (needs the browse browser + logged-in xiaohongshu session, and an
analyzer callable for the LLM step — see stages/analyze.py):
    python -m travel_assistant.research --destination "Kyoto" --vibe food \\
        --queries "京都美食,京都必去,Kyoto food"
"""
import argparse
import time
from datetime import datetime, timezone

from . import paths
from . import store as store_mod
from .stages import collect as st_collect
from .stages import analyze as st_analyze
from .stages import validate as st_validate
from .stages import geocode as st_geocode
from .stages import map as st_map


def _utc_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def research(destination=None, *, vibe="all", dates=None, budget_tier=None,
             queries=None, n_per_query=6,
             from_raw=None, from_analysis=None, analyzer=None,
             collector=None, skip_geocode=False, region="", db_path=None):
    """Run the full pipeline and record it. Returns the completed run record.

    dates: optional {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}.
    """
    t0 = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    store = store_mod.RunStore(db_path)
    try:
        analysis, raw_path, analysis_path = None, None, None

        if from_analysis:
            analysis_path = str(from_analysis)
            analysis = st_analyze.load_analysis(analysis_path)
            destination = destination or analysis.get("destination")
        if not destination:
            if from_raw:
                raw = st_collect.load_raw(from_raw)
                destination = raw.get("destination")
            if not destination:
                raise ValueError(
                    "destination is required (pass --destination, or derive it "
                    "from --from-analysis / --from-raw)")
        slug = paths.slugify(destination)
        dates = dates or {}

        run_id = store.create_run(
            destination=destination, slug=slug, vibe=vibe,
            date_start=dates.get("start"), date_end=dates.get("end"),
            budget_tier=budget_tier,
            source_mode=(analysis or {}).get("source_mode"),
            raw_path=raw_path, analysis_path=analysis_path,
            started_at=started_at)
        try:
            # -- collect + analyze (skipped when replaying a saved analysis)
            if analysis is None:
                if from_raw:
                    raw_path = str(from_raw)
                    raw = st_collect.load_raw(raw_path)
                else:
                    if not queries:
                        raise ValueError(
                            "collect needs --queries (or --from-raw to replay "
                            "a saved raw file)")
                    run_collector = collector or st_collect.collect_rednote
                    raw_path = run_collector(destination, list(queries),
                                             n_per_query)
                    raw = st_collect.load_raw(raw_path)
                analysis = st_analyze.analyze_raw(
                    raw, destination=destination, vibe=vibe, analyzer=analyzer)
                store.update_run(run_id, raw_path=raw_path,
                                 source_mode=analysis.get("source_mode"))

            # -- validate (raises on INVALID; run marked failed below)
            st_validate.check(analysis)

            # -- geocode: fill missing lat/lng
            n_geocoded, n_missing = st_geocode.enrich_places(
                analysis, skip=skip_geocode)

            # -- persist the enriched analysis as a NEW timestamped file
            out_analysis = (paths.analysis_dir()
                            / f"{slug}_places_{_utc_ts()}.json")
            out_analysis.parent.mkdir(parents=True, exist_ok=True)
            st_analyze.save_analysis(analysis, out_analysis)
            analysis_path = str(out_analysis)

            # -- map artifacts
            artifacts = st_map.build_artifacts(
                analysis, out_dir=paths.maps_dir(), region=region)

            # -- record everything
            n_places = len(analysis.get("places", []))
            store.add_places(run_id, analysis.get("places", []))
            store.update_run(run_id, analysis_path=analysis_path,
                             source_mode=analysis.get("source_mode"))
            store.complete_run(
                run_id, n_places=n_places, n_geocoded=n_geocoded,
                kml_path=artifacts["kml_path"],
                map_html_path=artifacts["map_html_path"],
                csv_path=artifacts["csv_path"],
                started_at=started_at)

            rec = store.get_run(run_id)
            rec["duration_s"] = time.monotonic() - t0
            rec["artifacts"] = artifacts
            rec["n_missing_coords"] = n_missing
            return rec
        except Exception as e:
            store.fail_run(run_id, e)
            raise
    finally:
        store.close()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the travel-assistant research pipeline.")
    ap.add_argument("--destination",
                    help="e.g. 'Kyoto' (optional with --from-analysis)")
    ap.add_argument("--vibe", default="all")
    ap.add_argument("--dates-start", default=None)
    ap.add_argument("--dates-end", default=None)
    ap.add_argument("--budget-tier", default=None)
    ap.add_argument("--queries",
                    help="comma-separated rednote search terms for collect")
    ap.add_argument("--n", type=int, default=6, dest="n_per_query")
    ap.add_argument("--from-raw",
                    help="replay a saved data/raw/*.json (skip collect)")
    ap.add_argument("--from-analysis",
                    help="replay a saved data/analysis/*_places_*.json "
                         "(skip collect+analyze)")
    ap.add_argument("--skip-geocode", action="store_true",
                    help="do not call Nominatim; places without coords are "
                         "skipped from the KML/HTML")
    ap.add_argument("--region", default="",
                    help="region appended to CSV addresses, e.g. 'BC, Canada'")
    ap.add_argument("--db", default=None, help="run-store SQLite path")
    a = ap.parse_args(argv)

    dates = None
    if a.dates_start or a.dates_end:
        dates = {"start": a.dates_start, "end": a.dates_end}
    rec = research(
        destination=a.destination, vibe=a.vibe, dates=dates,
        budget_tier=a.budget_tier,
        queries=[q.strip() for q in a.queries.split(",")] if a.queries else None,
        n_per_query=a.n_per_query,
        from_raw=a.from_raw, from_analysis=a.from_analysis,
        skip_geocode=a.skip_geocode, region=a.region, db_path=a.db)
    art = rec["artifacts"]
    print(f"run #{rec['id']} [{rec['status']}] {rec['destination']} "
          f"({rec['n_places']} places, {rec['n_geocoded']} geocoded, "
          f"{rec['n_missing_coords']} without coords, "
          f"{rec['duration_s']:.1f}s)")
    print(f"  analysis : {rec['analysis_path']}")
    print(f"  kml      : {art['kml_path']} ({art['n_pins']} pins)")
    print(f"  map html : {art['map_html_path']}")
    print(f"  csv      : {art['csv_path']} ({art['n_csv_rows']} rows)")
    db = a.db or paths.runs_db_path()
    print(f"  run store: run #{rec['id']} recorded in {db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
