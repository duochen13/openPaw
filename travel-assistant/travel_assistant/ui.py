"""Local dashboard: `travel-assistant ui` — MLflow-style map renderer over the run store.

Stdlib only (http.server). The server reads the SQLite run store and renders
past research runs as maps; it takes no API keys and starts no network
service of its own.

Map rendering is deliberately self-contained SVG (equirectangular projection
with a cos(lat0) aspect correction), NOT the Google Maps embeds produced by
scripts/build_gmap_html.py: those need GOOGLE_MAPS_API_KEY in the viewer's
browser and render nothing without one. The dashboard is keyless by design
(per issue #78's scope), so it draws its own pins/popups/legend and works
fully offline. Per-type pin colors match build_gmap_html.py's legend.

Routes:
    GET /                    index: all runs + a compare picker
    GET /runs/<id>           run detail: map, quotes, cost rollup, place list
    GET /compare?a=<id>&b=<id>
                             side-by-side comparison of two runs
"""
import argparse
import json
import math
from html import escape as _escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import paths
from . import store as store_mod

# Pin colors / labels, kept identical to scripts/build_gmap_html.py's legend.
CATS = {
    "restaurant": ("#E8453C", "Food"),
    "cafe":       ("#F5A623", "Caf\u00e9 / bakery"),
    "bar":        ("#8E44AD", "Bar / brewery"),
    "sight":      ("#2E9E4F", "Outdoors / sights"),
    "shop":       ("#2D7DD2", "Shop / market"),
    "other":      ("#7F8C8D", "Other"),
}

MAP_W, MAP_H = 640, 440


def esc(s):
    return _escape("" if s is None else str(s), quote=True)


def cat_of(place):
    t = (place.get("category") or place.get("type") or "other")
    return t if t in CATS else "other"


def safe_js(obj):
    """json.dumps safe to embed inside an inline <script> tag."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# --------------------------------------------------------------------------
# Cost rollup.
#
# COST MODEL (issue #78 defines none — this is the interpretation):
# the run store reserves a `price_hint` TEXT column per place, but the v1
# analyzer never emits price hints, so every v1 run has NULL price_hint.
# The rollup is therefore a pure aggregation of the recorded per-place
# price hints: how many places carry one, how many don't, and the hint list
# itself — always labeled as an estimate. It does NOT invent prices, parse
# currencies, or call any pricing backend. If a future stage fills
# price_hint (schema.py reserves it), this rollup picks it up unchanged.
# --------------------------------------------------------------------------
def cost_rollup(places):
    hints = [(p.get("name"), p.get("price_hint"))
             for p in places if p.get("price_hint")]
    return {
        "n_total": len(places),
        "n_with_hint": len(hints),
        "n_without_hint": len(places) - len(hints),
        "hints": hints,
    }


# --------------------------------------------------------------------------
# Map fragment: SVG pins + category legend + click popups.
# --------------------------------------------------------------------------
def _geocoded(places):
    out = []
    for p in places:
        lat, lng = p.get("lat"), p.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            out.append(p)
    return out


def _project(geo):
    """Equirectangular projection of geocoded places into MAP_W x MAP_H."""
    lats = [p["lat"] for p in geo]
    lngs = [p["lng"] for p in geo]
    lat0 = sum(lats) / len(lats)
    kx = math.cos(math.radians(lat0)) or 0.01
    xs = [(g - min(lngs)) * kx for g in lngs]
    ys = [(max(lats) - g) for g in lats]
    xspan = (max(xs) - min(xs)) or 0.02 * kx
    yspan = (max(ys) - min(ys)) or 0.02
    pad = 52
    s = min((MAP_W - 2 * pad) / xspan, (MAP_H - 2 * pad) / yspan)
    ox = (MAP_W - xspan * s) / 2 - min(xs) * s
    oy = (MAP_H - yspan * s) / 2 - min(ys) * s
    return [(x * s + ox, y * s + oy) for x, y in zip(xs, ys)], \
        (min(lngs), max(lngs)), (min(lats), max(lats))


def map_fragment(run, prefix):
    """Self-contained map HTML for one run's places. `prefix` keeps multi-map
    pages (compare view) collision-free."""
    places = run.get("places") or []
    geo = _geocoded(places)
    if not geo:
        return ('<div class="ta-map ta-empty">No geocoded places in this run.</div>',
                [])

    coords, (lo_lng, hi_lng), (lo_lat, hi_lat) = _project(geo)

    # graticule
    grid = []
    for i in range(5):
        x = 8 + i * (MAP_W - 16) / 4
        grid.append(
            f'<line x1="{x:.0f}" y1="8" x2="{x:.0f}" y2="{MAP_H - 8}" class="ta-grid"/>')
        grid.append(
            f'<text x="{x:.0f}" y="{MAP_H - 12}" class="ta-gridlbl">'
            f'{lo_lng + i * (hi_lng - lo_lng) / 4:.2f}\u00b0</text>')
    for i in range(4):
        y = 8 + i * (MAP_H - 16) / 3
        grid.append(
            f'<line x1="8" y1="{y:.0f}" x2="{MAP_W - 8}" y2="{y:.0f}" class="ta-grid"/>')
        grid.append(
            f'<text x="14" y="{y - 5:.0f}" class="ta-gridlbl">'
            f'{hi_lat - i * (hi_lat - lo_lat) / 3:.2f}\u00b0</text>')

    pins_svg, js_places, present = [], [], {}
    for idx, (p, (x, y)) in enumerate(zip(geo, coords)):
        cat = cat_of(p)
        color = CATS[cat][0]
        present[cat] = present.get(cat, 0) + 1
        pins_svg.append(
            f'<circle class="ta-pin" data-cat="{cat}" data-i="{idx}" '
            f'cx="{x:.1f}" cy="{y:.1f}" r="7.5" fill="{color}" '
            f'stroke="#fff" stroke-width="1.6" '
            f'onclick="taPop(\'{prefix}\',{idx})">'
            f'<title>{esc(p.get("name"))}</title></circle>')
        urls = p.get("source_urls") or []
        url = urls[0] if urls else (p.get("map_link") or "")
        js_places.append({
            "x": round(x, 1), "y": round(y, 1),
            "name": p.get("name") or "", "type": cat,
            "area": p.get("area") or "",
            "rating": p.get("rating"),
            "why": p.get("why_loved") or "",
            "url": url,
            "price": p.get("price_hint") or "",
        })

    legend_rows = []
    for cat, n in present.items():
        color, label = CATS[cat]
        legend_rows.append(
            f'<span class="ta-lgrow" data-cat="{cat}" '
            f'onclick="taToggleCat(\'{prefix}\',\'{cat}\')">'
            f'<span class="ta-dot" style="background:{color}"></span>'
            f'{esc(label)} <span class="ta-n">{n}</span></span>')

    skipped = len(places) - len(geo)
    note = (f'<div class="ta-skip">{skipped} place(s) without coordinates '
            f'are listed below the map.</div>' if skipped else "")

    html = f"""
<div class="ta-mapwrap">
  <div class="ta-map" id="map-{prefix}">
    <svg viewBox="0 0 {MAP_W} {MAP_H}" width="100%" role="img"
         aria-label="map of {esc(run.get('destination'))}">
      <rect x="0" y="0" width="{MAP_W}" height="{MAP_H}" class="ta-bg"/>
      {''.join(grid)}
      {''.join(pins_svg)}
    </svg>
    <div class="ta-pop" id="pop-{prefix}" hidden></div>
  </div>
  <div class="ta-legend">{"".join(legend_rows)}</div>
  {note}
</div>
<script>TA_MAPS["{prefix}"] = {safe_js(js_places)};</script>"""
    return html, geo


# --------------------------------------------------------------------------
# Page builders (pure functions of run records — easy to test offline).
# --------------------------------------------------------------------------
def _shell(title, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — travel-assistant</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; margin: 0;
         color: #222; background: #fafafa; }}
  .ta-head {{ background: #1a73e8; color: #fff; padding: 14px 22px; }}
  .ta-head a {{ color: #fff; }}
  .ta-head h1 {{ margin: 0; font-size: 20px; }}
  .ta-body {{ padding: 18px 22px; max-width: 1100px; }}
  .ta-meta {{ color: #555; font-size: 13px; margin: 6px 0 14px; }}
  .ta-meta b {{ color: #222; }}
  table.ta-runs {{ border-collapse: collapse; width: 100%; background: #fff; }}
  table.ta-runs th, table.ta-runs td {{
    border: 1px solid #e0e0e0; padding: 8px 10px; font-size: 14px; text-align: left; }}
  table.ta-runs th {{ background: #f0f4f9; }}
  .st-complete {{ color: #2E9E4F; font-weight: 600; }}
  .st-failed {{ color: #E8453C; font-weight: 600; }}
  .st-running {{ color: #F5A623; font-weight: 600; }}
  .ta-compare {{ margin: 16px 0; background: #fff; border: 1px solid #e0e0e0;
                padding: 12px 14px; border-radius: 8px; }}
  .ta-compare select, .ta-compare button {{ font-size: 14px; padding: 5px 8px; }}
  /* map */
  .ta-mapwrap {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
                 padding: 10px; margin: 12px 0; }}
  .ta-map {{ position: relative; }}
  .ta-empty {{ padding: 40px; text-align: center; color: #888; }}
  .ta-bg {{ fill: #f6f3ec; }}
  .ta-grid {{ stroke: #ddd6c4; stroke-width: 1; }}
  .ta-gridlbl {{ fill: #a09a8a; font-size: 10px; }}
  .ta-pin {{ cursor: pointer; }}
  .ta-legend {{ margin-top: 8px; font-size: 13px; }}
  .ta-lgrow {{ display: inline-flex; align-items: center; margin: 0 14px 4px 0;
               cursor: pointer; user-select: none; }}
  .ta-lgrow.off {{ opacity: .35; text-decoration: line-through; }}
  .ta-dot {{ width: 11px; height: 11px; border-radius: 50%; margin-right: 6px;
             border: 1px solid rgba(0,0,0,.25); display: inline-block; }}
  .ta-n {{ color: #888; margin-left: 4px; }}
  .ta-skip {{ font-size: 12px; color: #888; margin-top: 6px; }}
  .ta-pop {{ position: absolute; z-index: 5; width: 270px; background: #fff;
             border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,.3);
             padding: 12px 14px; transform: translate(-50%, calc(-100% - 14px));
             font-size: 13px; }}
  .ta-pop h3 {{ margin: 0 0 2px; font-size: 15px; }}
  .ta-pop .ta-pmeta {{ color: #666; font-size: 12px; margin-bottom: 6px; }}
  .ta-pop blockquote {{ margin: 6px 0; padding-left: 10px; font-style: italic;
                        border-left: 3px solid #1a73e8; color: #333; }}
  .ta-pop .ta-x {{ position: absolute; top: 6px; right: 10px; cursor: pointer;
                   color: #999; font-size: 15px; }}
  .ta-pop .ta-price {{ color: #2E9E4F; font-weight: 600; }}
  /* cost rollup */
  .ta-cost {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
              padding: 12px 14px; margin: 12px 0; font-size: 14px; }}
  .ta-cost h2 {{ margin: 0 0 6px; font-size: 16px; }}
  .ta-cost .ta-fine {{ color: #777; font-size: 12px; }}
  /* place list */
  .ta-places {{ margin: 12px 0; }}
  .ta-place {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
                padding: 10px 14px; margin-bottom: 8px; font-size: 14px; }}
  .ta-place .ta-pname {{ font-weight: 600; }}
  .ta-place .ta-ptype {{ display: inline-block; font-size: 11px; color: #fff;
                         border-radius: 10px; padding: 1px 8px; margin-left: 8px;
                         vertical-align: 1px; }}
  .ta-place .ta-pwhy {{ font-style: italic; color: #444; margin: 4px 0 0; }}
  .ta-place .ta-pmeta {{ color: #777; font-size: 12px; }}
  .ta-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  .ta-scroll {{ max-height: 520px; overflow-y: auto; }}
  @media (max-width: 800px) {{ .ta-cols {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="ta-head"><h1><a href="/">&#x1f5fa;&#xfe0f; travel-assistant</a>
 &nbsp;·&nbsp; {esc(title)}</h1></div>
<div class="ta-body">
{body}
</div>
<script>
var TA_MAPS = {{}};
var TA_CAT = {{}};
function taPop(prefix, i) {{
  var m = TA_MAPS[prefix][i];
  var pop = document.getElementById("pop-" + prefix);
  var rating = (typeof m.rating === "number") ? " \\u2b50 " + m.rating : "";
  var price = m.price ? '<div class="ta-price">\\u{{1F4B2}} ' + esc(m.price) + "</div>" : "";
  pop.innerHTML =
    '<span class="ta-x" onclick="this.parentNode.hidden=true">\\u00d7</span>' +
    "<h3>" + esc(m.name) + "</h3>" +
    '<div class="ta-pmeta">' + esc(m.type) + (m.area ? " \\u00b7 " + esc(m.area) : "") +
    rating + "</div>" +
    (m.why ? "<blockquote>\\u201c" + esc(m.why) + "\\u201d</blockquote>" : "") +
    price +
    (m.url ? '<div><a href="' + encodeURI(m.url) +
      '" target="_blank" rel="noopener">source</a></div>' : "");
  pop.style.left = (m.x / {MAP_W} * 100) + "%";
  pop.style.top = (m.y / {MAP_H} * 100) + "%";
  pop.hidden = false;
}}
function esc(s) {{
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}}
function taToggleCat(prefix, cat) {{
  var sel = TA_CAT[prefix] || (TA_CAT[prefix] = {{}});
  sel[cat] = !(sel[cat] === false);
  var wrap = document.getElementById("map-" + prefix).parentNode;
  wrap.querySelectorAll("circle.ta-pin").forEach(function (c) {{
    if (c.getAttribute("data-cat") === cat)
      c.style.display = sel[cat] ? "" : "none";
  }});
  wrap.querySelectorAll(".ta-lgrow").forEach(function (r) {{
    if (r.getAttribute("data-cat") === cat)
      r.classList.toggle("off", !sel[cat]);
  }});
}}
</script>
</body>
</html>"""


def _run_meta(rec):
    dates = " / ".join(d for d in (rec.get("date_start"), rec.get("date_end")) if d)
    parts = [
        f"vibe <b>{esc(rec.get('vibe'))}</b>",
        f"status <b class=\"st-{esc(rec.get('status'))}\">{esc(rec.get('status'))}</b>",
    ]
    if dates:
        parts.append(f"dates <b>{esc(dates)}</b>")
    if rec.get("budget_tier"):
        parts.append(f"budget <b>{esc(rec.get('budget_tier'))}</b>")
    if rec.get("source_mode"):
        parts.append(f"source <b>{esc(rec.get('source_mode'))}</b>")
    parts.append(f"places <b>{rec.get('n_places')}</b> "
                 f"({rec.get('n_geocoded') or 0} geocoded)")
    parts.append(f"started <b>{esc((rec.get('started_at') or '')[:16].replace('T', ' '))}</b>")
    return " · ".join(parts)


def _cost_box(places):
    r = cost_rollup(places)
    fine = ("Estimate from per-place <i>price_hint</i> values recorded in the "
            "run store. No pricing backend — v1 runs have no price hints, so "
            "no totals are invented.")
    if r["n_with_hint"]:
        rows = "".join(
            f"<tr><td>{esc(n)}</td><td>{esc(h)}</td></tr>"
            for n, h in r["hints"])
        body = (f"{r['n_with_hint']} of {r['n_total']} places carry a price hint:"
                f"<table class='ta-runs' style='margin-top:8px'>"
                f"<tr><th>Place</th><th>Price hint</th></tr>{rows}</table>")
    else:
        body = (f"No price hints recorded for this run "
                f"({r['n_total']} places) — cost rollup unavailable.")
    return (f"<div class='ta-cost'><h2>&#x1f4b0; Cost rollup (estimate)</h2>"
            f"{body}<div class='ta-fine'>{fine}</div></div>")


def _place_card(p):
    cat = cat_of(p)
    color, label = CATS[cat]
    rating = f" \u2b50 {p['rating']}" if isinstance(p.get("rating"), (int, float)) else ""
    urls = p.get("source_urls") or []
    url = urls[0] if urls else (p.get("map_link") or "")
    meta_bits = [b for b in (
        p.get("area"),
        f"{p.get('mention_count')} mentions" if p.get("mention_count") else "",
        (p.get("sentiment") or ""),
    ) if b]
    meta = " · ".join(meta_bits) + rating
    why = (f"<p class='ta-pwhy'>\u201c{esc(p.get('why_loved'))}\u201d</p>"
           if p.get("why_loved") else "")
    link = (f" <a href='{esc(url)}' target='_blank' rel='noopener'>source</a>"
            if url else "")
    return (f"<div class='ta-place' data-cat='{cat}'>"
            f"<span class='ta-pname'>{esc(p.get('name'))}</span>"
            f"<span class='ta-ptype' style='background:{color}'>{esc(label)}</span>"
            f"<div class='ta-pmeta'>{esc(meta)}{link}</div>{why}</div>")


def index_page(runs):
    rows = []
    for r in runs:
        rows.append(
            f"<tr><td>#{r['id']}</td>"
            f"<td><a href='/runs/{r['id']}'>{esc(r.get('destination'))}</a></td>"
            f"<td>{esc(r.get('vibe'))}</td>"
            f"<td>{esc(r.get('started_at', '')[:10])}</td>"
            f"<td>{r.get('n_places')}</td>"
            f"<td class='st-{esc(r.get('status'))}'>{esc(r.get('status'))}</td></tr>")
    table = ("<table class='ta-runs'><tr><th>#</th><th>Destination</th><th>Vibe</th>"
             "<th>Date</th><th>Places</th><th>Status</th></tr>"
             + "".join(rows) + "</table>") if rows else \
            "<p>No runs in the store yet.</p>"

    opts = "".join(
        f"<option value='{r['id']}'>#{r['id']} {esc(r.get('destination'))}</option>"
        for r in runs)
    cmp_form = ""
    if len(runs) >= 2:
        cmp_form = (f"<form class='ta-compare' action='/compare' method='get'>"
                    f"<b>Compare trips:</b> <select name='a'>{opts}</select>"
                    f" <select name='b'>{opts}</select>"
                    f" <button type='submit'>Compare</button></form>")
    return _shell("All runs",
                  f"<p class='ta-meta'>{len(runs)} run(s) in the store.</p>"
                  f"{cmp_form}{table}")


def run_page(rec):
    places = rec.get("places") or []
    map_html, geo = map_fragment(rec, f"r{rec['id']}")
    by_id = {id(p): p for p in places}
    missing = [p for p in places if id(p) not in {id(g) for g in geo}]
    miss_list = ("<div class='ta-cost'><h2>Places without coordinates "
                 f"({len(missing)})</h2>" +
                 "".join(f"<div class='ta-pmeta'>\u00b7 {esc(p.get('name'))} "
                         f"({esc(p.get('area') or '')})</div>" for p in missing) +
                 "</div>") if missing else ""
    cards = "".join(_place_card(p) for p in places)
    return _shell(f"{rec.get('destination')} (run #{rec['id']})",
                  f"<p class='ta-meta'>{_run_meta(rec)}</p>"
                  f"{_cost_box(places)}"
                  f"{map_html}{miss_list}"
                  f"<h2>Places ({len(places)})</h2>"
                  f"<div class='ta-places'>{cards}</div>")


def compare_page(rec_a, rec_b, runs):
    def col(rec, prefix):
        places = rec.get("places") or []
        map_html, _ = map_fragment(rec, prefix)
        cards = "".join(_place_card(p) for p in places)
        return (f"<h2><a href='/runs/{rec['id']}'>{esc(rec.get('destination'))}</a> "
                f"<span class='ta-pmeta'>run #{rec['id']}</span></h2>"
                f"<p class='ta-meta'>{_run_meta(rec)}</p>"
                f"{_cost_box(places)}{map_html}"
                f"<h3>Places ({len(places)})</h3>"
                f"<div class='ta-places ta-scroll'>{cards}</div>")

    def sel(name, current):
        opts = "".join(
            f"<option value='{r['id']}'"
            f"{' selected' if r['id'] == current else ''}>"
            f"#{r['id']} {esc(r.get('destination'))}</option>" for r in runs)
        return f"<select name='{name}'>{opts}</select>"

    form = (f"<form class='ta-compare' action='/compare' method='get'>"
            f"<b>Compare:</b> {sel('a', rec_a['id'])} vs {sel('b', rec_b['id'])} "
            f"<button type='submit'>Compare</button></form>")
    return _shell(f"Compare: {rec_a.get('destination')} vs {rec_b.get('destination')}",
                  f"{form}<div class='ta-cols'>"
                  f"<div>{col(rec_a, 'cmpA')}</div>"
                  f"<div>{col(rec_b, 'cmpB')}</div></div>")


# --------------------------------------------------------------------------
# HTTP server.
# --------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_version = "travel-assistant-ui/0.1"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _store(self):
        return store_mod.RunStore(self.server.db_path)

    def do_GET(self):  # noqa: N802 (http.server naming)
        u = urlparse(self.path)
        st = self._store()
        try:
            if u.path in ("/", ""):
                return self._send(200, index_page(st.list_runs(limit=100)))
            if u.path == "/compare":
                q = parse_qs(u.query)
                try:
                    a = int((q.get("a") or [""])[0])
                    b = int((q.get("b") or [""])[0])
                except ValueError:
                    return self._send(400, _shell("Bad request",
                                                  "<p>Compare needs ?a=&lt;id&gt;&amp;b=&lt;id&gt;.</p>"))
                ra, rb = st.get_run(a), st.get_run(b)
                if ra is None or rb is None:
                    return self._send(404, _shell("Not found",
                                                  "<p>One of the runs does not exist.</p>"))
                return self._send(200, compare_page(ra, rb, st.list_runs(limit=100)))
            if u.path.startswith("/runs/"):
                try:
                    run_id = int(u.path.split("/runs/", 1)[1].split("/")[0])
                except ValueError:
                    return self._send(404, _shell("Not found", "<p>Bad run id.</p>"))
                rec = st.get_run(run_id)
                if rec is None:
                    return self._send(404, _shell("Not found",
                                                  f"<p>No run #{run_id}.</p>"))
                return self._send(200, run_page(rec))
            return self._send(404, _shell("Not found", "<p>Unknown path.</p>"))
        finally:
            st.close()

    def log_message(self, fmt, *args):  # quieter than the default
        pass


def make_server(host, port, db_path):
    srv = ThreadingHTTPServer((host, port), _Handler)
    srv.db_path = str(db_path)
    return srv


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Local dashboard over the travel run store "
                    "(no API keys, no network service).")
    ap.add_argument("--db", default=None, help="run-store SQLite path")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args(argv)
    db = a.db or paths.runs_db_path()
    srv = make_server(a.host, a.port, db)
    addr = f"http://{a.host}:{srv.server_address[1]}"
    print(f"travel-assistant ui — serving {db}")
    print(f"open {addr}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
