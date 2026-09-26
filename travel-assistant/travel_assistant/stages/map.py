"""Map stage: places object -> KML + interactive HTML + My Maps CSV.

Wraps build_map.build_kml, build_gmap_html.write_map_html, and
build_mymaps_csv.write_csv (unchanged). Unlike build_map.enrich_and_build,
this stage never mutates the caller's analysis object on disk — the
orchestrator writes the enriched analysis to its own timestamped file.
"""
import os
from pathlib import Path

from . import ensure_scripts_on_path
from .. import paths

ensure_scripts_on_path()
import build_map as _bm
import build_gmap_html as _bg
import build_mymaps_csv as _bc


def build_artifacts(obj, *, out_dir=None, region=""):
    """Write {slug}.kml, {slug}_map.html, {slug}_mymaps.csv.

    Returns a dict of artifact paths plus pin/row counts.
    """
    out_dir = Path(out_dir) if out_dir else paths.maps_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = obj.get("destination", "")
    slug = paths.slugify(dest)
    places = obj.get("places", [])

    kml, n_pins = _bm.build_kml(dest, places)
    kml_path = out_dir / f"{slug}.kml"
    kml_path.write_text(kml, encoding="utf-8")

    html_path, n_kept, n_skipped = _bg.write_map_html(obj, out_dir=str(out_dir))

    csv_path = out_dir / f"{slug}_mymaps.csv"
    n_rows = _bc.write_csv(obj, str(csv_path), region)

    return {
        "kml_path": str(kml_path),
        "map_html_path": str(html_path),
        "csv_path": str(csv_path),
        "n_pins": n_pins,
        "n_html_kept": n_kept,
        "n_html_skipped": n_skipped,
        "n_csv_rows": n_rows,
    }
