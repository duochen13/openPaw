"""End-to-end research run: collect -> analyze -> validate -> geocode -> map.

Every run is recorded in the SQLite run store (see store.py). Analysis inputs
are never mutated: the enriched (geocoded) analysis is written to a new
timestamped file under data/analysis/.

Offline / test usage: replay a saved analysis file
    python -m travel_assistant.research --from-analysis data/analysis/vancouver_places_20260709_030913.json --skip-geocode
Live usage (needs the browse browser + logged-in xiaohongshu session).
The analyze step is the LLM subagent pass (SKILL.md Step 3) — the package
ships no default analyzer, so collect only, analyze via the travel-research
agent skill, then replay the saved analysis:
    python -m travel_assistant.research --destination "Kyoto" --vibe food \\
        --queries "京都美食,京都必去,Kyoto food" --no-analyze
    python -m travel_assistant.research --from-analysis data/analysis/kyoto_places_<ts>.json
"""
import argparse
import sys
import time
from datetime import datetime, timezone

from . import collectors as collectors_mod
from . import paths
from . import store as store_mod
from .stages import collect as st_collect
from .stages import analyze as st_analyze
from .stages import validate as st_validate
from .stages import geocode as st_geocode
from .stages import map as st_map


def _utc_ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _collector_source_label(run_collector, raw):
    """Best-effort source label for the places of one run.

    Collector instance identity wins; otherwise the raw file's own
    "source" field (the rednote script writes "source": "rednote"). Returns
    None when nothing trustworthy is available — replayed analyses then keep
    the labels the analyzer already emitted.
    """
    if isinstance(run_collector, collectors_mod.Collector):
        return run_collector.source
    return (raw or {}).get("source")


def research(destination=None, *, vibe="all", dates=None, budget_tier=None,
             queries=None, n_per_query=6,
             from_raw=None, from_analysis=None, analyzer=None,
             collector=None, skip_geocode=False, region="", db_path=None,
             no_analyze=False):
    """Run the full pipeline and record it. Returns the completed run record.

    dates: optional {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}.
    collector: a Collector instance (travel_assistant.collectors) or any
        callable with the signature collector(destination, queries,
        n_per_query=6) -> raw_path. Defaults to the rednote collector.
        A Collector's `source` label ("rednote" / "websearch") is stamped
        onto every place that does not already carry one.
    no_analyze: stop after the collect stage (the analyze step needs an
        analyzer callable for the LLM subagent pass — see stages/analyze.py —
        or research(..., from_analysis=<path>)). The run is recorded as
        complete with n_places=0 and the record carries raw_path.
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
            ran_collector = None
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
                    ran_collector = run_collector
                n_discussions = len((raw or {}).get("discussions", []))
                # Record raw_path before analyze: analyze_raw may raise
                # (no analyzer configured) and the failed run should still
                # point at the collected output.
                store.update_run(run_id, raw_path=raw_path)
                if n_discussions == 0:
                    # Deliberately a warning, not an early exit: per SKILL.md
                    # Step 2 the analyzer (LLM subagent) is expected to fall
                    # back to web search when collection comes back empty.
                    print(
                        f"WARNING: collection yielded 0 posts ({raw_path}). "
                        f"The analyze step may fall back to web search "
                        f"(SKILL.md Step 2); if rednote was expected, check "
                        f"the logged-in xiaohongshu session.",
                        file=sys.stderr)
                if no_analyze:
                    store.complete_run(run_id, n_places=0, n_geocoded=0,
                                       started_at=started_at)
                    rec = store.get_run(run_id)
                    rec["duration_s"] = time.monotonic() - t0
                    rec["raw_path"] = raw_path
                    rec["no_analyze"] = True
                    return rec
                analysis = st_analyze.analyze_raw(
                    raw, destination=destination, vibe=vibe, analyzer=analyzer)
                store.update_run(run_id,
                                 source_mode=analysis.get("source_mode"))
            else:
                raw = None

            # -- per-place source label: the collector that produced the raw
            #    file stamps its label; replays keep the analyzer's own.
            collectors_mod.label_places(
                analysis, _collector_source_label(ran_collector, raw))

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


def _failed_run_raw_path(db_path):
    """Best-effort raw_path of the most recent run (the one that just failed
    in analyze). Returns None when the store is unreachable."""
    try:
        store = store_mod.RunStore(db_path)
        try:
            latest = store.latest_run()
            return (latest or {}).get("raw_path")
        finally:
            store.close()
    except Exception:
        return None


def _no_analyzer_message(raw_path):
    where = (f"\n\n  Collection output was saved to: {raw_path}"
             if raw_path else "")
    return (
        "ERROR: the analyze step is the LLM subagent pass (SKILL.md Step 3) "
        "and this CLI ships no default analyzer.\n"
        "  Run the full workflow via the travel-research agent skill, or "
        "re-run with:\n"
        "    python -m travel_assistant.research "
        "--from-analysis <data/analysis/*_places_*.json>" + where
    )


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
    ap.add_argument("--collector", default="rednote",
                    choices=["rednote", "websearch"],
                    help="which source collector to run (default: rednote); "
                         "websearch needs a configured search backend and "
                         "will fail loudly without one")
    ap.add_argument("--from-raw",
                    help="replay a saved data/raw/*.json (skip collect)")
    ap.add_argument("--from-analysis",
                    help="replay a saved data/analysis/*_places_*.json "
                         "(skip collect+analyze)")
    ap.add_argument("--no-analyze", action="store_true",
                    help="stop after collection and print the raw output "
                         "path (the analyze step needs the LLM subagent "
                         "pass — SKILL.md Step 3 — or --from-analysis)")
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
    try:
        rec = research(
            destination=a.destination, vibe=a.vibe, dates=dates,
            budget_tier=a.budget_tier,
            queries=[q.strip() for q in a.queries.split(",")] if a.queries else None,
            n_per_query=a.n_per_query,
            from_raw=a.from_raw, from_analysis=a.from_analysis,
            collector=collectors_mod.collector_for(a.collector)(),
            skip_geocode=a.skip_geocode, region=a.region, db_path=a.db,
            no_analyze=a.no_analyze)
    except NotImplementedError as e:
        # analyze_raw deliberately raises when no analyzer is configured
        # (the LLM subagent pass); translate it into a clean CLI error.
        if "No analyzer configured" not in str(e):
            raise
        print(_no_analyzer_message(_failed_run_raw_path(a.db)),
              file=sys.stderr)
        return 2
    if rec.get("no_analyze"):
        print(f"run #{rec['id']} [{rec['status']}] {rec['destination']} "
              f"-- collection only (--no-analyze), "
              f"{rec['duration_s']:.1f}s")
        print(f"  raw      : {rec['raw_path']}")
        db = a.db or paths.runs_db_path()
        print(f"  run store: run #{rec['id']} recorded in {db}")
        return 0
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
