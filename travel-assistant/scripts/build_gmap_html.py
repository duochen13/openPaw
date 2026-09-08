#!/usr/bin/env python3
"""Render a places JSON as a self-contained Google Maps HTML viewer (v1: pins + popups).

Usage:
    GOOGLE_MAPS_API_KEY=... python3 build_gmap_html.py [places.json]

If no path is given, the latest data/analysis/*_places_*.json is used.
Output: data/maps/{slug}_map.html  (open by double-click; no server needed).

The Maps JS API key is read from the GOOGLE_MAPS_API_KEY env var and injected into
the output. If unset, a "YOUR_API_KEY" placeholder is written instead so the file is
still generated. The key is NOT stored in this script. Note: a Maps JS key is always
visible in client-side HTML -- protect it with an HTTP-referrer restriction in the
Google Cloud console rather than relying on secrecy.
"""
import json, os, sys, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
ANALYSIS_DIR = os.path.join(BASE, "data", "analysis")
MAPS_DIR = os.path.join(BASE, "data", "maps")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "_", (text or "trip").lower()).strip("_")
    return s or "trip"


def filter_places(places):
    """Split places into (kept_with_coords, skipped_without_coords)."""
    kept, skipped = [], []
    for p in places or []:
        lat, lng = p.get("lat"), p.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            kept.append(p)
        else:
            skipped.append(p)
    return kept, skipped


def safe_json(obj):
    """json.dumps that is safe to embed inside an inline <script> tag."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html, body {{ height: 100%; margin: 0; font-family: -apple-system, system-ui, sans-serif; }}
  #map {{ height: calc(100% - 34px); width: 100%; }}
  #footer {{ height: 34px; line-height: 34px; padding: 0 12px; font-size: 13px;
             color: #444; background: #f5f5f5; border-top: 1px solid #ddd;
             box-sizing: border-box; overflow: hidden; white-space: nowrap; }}
  .iw-title {{ font-weight: 600; font-size: 15px; margin: 0 0 2px; }}
  .iw-meta {{ color: #666; font-size: 12px; margin: 0 0 6px; }}
  .iw-why {{ margin: 0 0 6px; max-width: 260px; }}
  .iw-link {{ font-size: 12px; }}
  #legend {{ position: absolute; bottom: 44px; left: 10px; z-index: 5; background: #fff;
             border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.3); padding: 8px 11px;
             font-size: 12px; line-height: 1.7; }}
  #legend .lg-hd {{ font-weight: 600; margin-bottom: 3px; }}
  .lg-row {{ display: flex; align-items: center; white-space: nowrap;
             cursor: pointer; user-select: none; padding: 1px 4px; margin: 0 -4px;
             border-radius: 4px; }}
  .lg-row:hover {{ background: #f0f0f0; }}
  .lg-off {{ opacity: .4; }}
  .lg-off .lg-lbl {{ text-decoration: line-through; }}
  .lg-dot {{ width: 11px; height: 11px; border-radius: 50%; margin-right: 7px;
             border: 1px solid rgba(0,0,0,.25); flex: 0 0 auto; }}
  #legend .lg-hint {{ font-size: 10px; color: #999; margin-top: 5px; }}
  #routebox {{ position: absolute; bottom: 44px; left: 50%; transform: translateX(-50%); z-index: 5;
               display: none; background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.3);
               padding: 6px 12px; font-size: 13px; max-width: 90%; }}
  #searchbox {{ position: absolute; top: 10px; left: 50%; transform: translateX(-50%); z-index: 6;
                width: min(340px, 82%); }}
  #searchbox gmp-place-autocomplete {{ width: 100%; box-shadow: 0 1px 4px rgba(0,0,0,.3);
                border-radius: 8px; background: #fff; }}
  .rb {{ cursor: pointer; user-select: none; }}
  .rb-note {{ color: #999; font-size: 11px; }}
  .route-label {{ position: absolute; transform: translate(-50%, -50%); background: #1a73e8; color: #fff;
                  font-size: 11px; font-weight: 600; padding: 1px 7px; border-radius: 10px;
                  white-space: nowrap; box-shadow: 0 1px 2px rgba(0,0,0,.35); pointer-events: none; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="searchbox"></div>
<div id="legend"></div>
<div id="routebox"></div>
<div id="footer">{footer}</div>
<script>
const PLACES = {places_json};
let MAP = null;
let INFO = null;

// Category -> pin color + legend label. Unknown types fall back to "other".
const CATS = {{
  restaurant: {{ color: "#E8453C", label: "Food" }},
  cafe:       {{ color: "#F5A623", label: "Caf\\u00e9 / bakery" }},
  bar:        {{ color: "#8E44AD", label: "Bar / brewery" }},
  sight:      {{ color: "#2E9E4F", label: "Outdoors / sights" }},
  shop:       {{ color: "#2D7DD2", label: "Shop / market" }},
  other:      {{ color: "#7F8C8D", label: "Other" }},
  added:      {{ color: "#D81B8C", label: "Added by you" }}
}};
function catFor(t) {{ return CATS[t] ? t : "other"; }}

// Filter state: markers grouped by category, which categories are shown, and which exist.
const MARKERS_BY_CAT = {{}};
const SELECTED = {{}};
let PRESENT = new Set();

// A Material "place" teardrop, tip anchored at the location.
const PIN_PATH = "M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z";
function pinIcon(color) {{
  return {{ path: PIN_PATH, fillColor: color, fillOpacity: 1,
            strokeColor: "#ffffff", strokeWeight: 1.2, scale: 1.7,
            anchor: new google.maps.Point(12, 22) }};
}}

function buildLegend(present) {{
  const el = document.getElementById("legend");
  const rows = ['<div class="lg-hd">Categories</div>'];
  Object.keys(CATS).forEach(function (k) {{
    if (!present.has(k)) return;
    const off = SELECTED[k] ? "" : " lg-off";
    rows.push('<div class="lg-row' + off + '" data-cat="' + k + '">' +
      '<span class="lg-dot" style="background:' + CATS[k].color + '"></span>' +
      '<span class="lg-lbl">' + CATS[k].label + '</span></div>');
  }});
  rows.push('<div class="lg-hint">click to filter</div>');
  el.innerHTML = rows.join("");
  el.querySelectorAll(".lg-row").forEach(function (row) {{
    row.addEventListener("click", function () {{ toggleCat(row.getAttribute("data-cat")); }});
  }});
}}

function toggleCat(cat) {{
  SELECTED[cat] = !SELECTED[cat];
  (MARKERS_BY_CAT[cat] || []).forEach(function (m) {{ m.setVisible(SELECTED[cat]); }});
  buildLegend(PRESENT);
  rebuildRoute();  // route follows the filter: legs to hidden pins disappear
}}

function escapeHtml(s) {{
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}}

function infoContent(p) {{
  const meta = [p.type, p.area].filter(Boolean).map(escapeHtml).join(" \\u00b7 ");
  const rating = (typeof p.rating === "number") ? ' \\u2b50 ' + p.rating : '';
  const url = (p.source_urls && p.source_urls.length) ? p.source_urls[0] : (p.map_link || null);
  const link = url ? '<div class="iw-link"><a href="' + encodeURI(url) +
      '" target="_blank" rel="noopener">source</a></div>' : '';
  const rm = '<div class="iw-link"><a href="#" class="iw-remove" data-id="' +
      escapeHtml(p.id) + '">remove</a></div>';
  return '<div class="iw-title">' + escapeHtml(p.name) + '</div>' +
         '<div class="iw-meta">' + meta + rating + '</div>' +
         (p.why_loved ? '<div class="iw-why">' + escapeHtml(p.why_loved) + '</div>' : '') +
         link + rm;
}}

function initMap() {{
  const map = new google.maps.Map(document.getElementById("map"), {{
    mapTypeControl: true, streetViewControl: false
  }});
  MAP = map;
  INFO = new google.maps.InfoWindow();
  const bounds = new google.maps.LatLngBounds();
  PLACES.forEach(function (p, i) {{
    p.id = p.id || ("p" + i);
    const cat = catFor(p.type);
    PRESENT.add(cat);
    if (SELECTED[cat] === undefined) SELECTED[cat] = true;
    addMarker(p);
    bounds.extend({{ lat: p.lat, lng: p.lng }});
  }});
  buildLegend(PRESENT);
  if (PLACES.length === 1) {{ map.setCenter(PLACES[0]); map.setZoom(14); }}
  else if (PLACES.length > 1) {{ map.fitBounds(bounds); }}
  else {{ map.setCenter({{ lat: 20, lng: 0 }}); map.setZoom(2); }}
  rebuildRoute();
  initSearch();
}}
//__ROUTE_JS__
//__SEARCH_JS__
</script>
<script async
  src="https://maps.googleapis.com/maps/api/js?key={api_key}&libraries=routes,places&callback=initMap">
</script>
</body>
</html>
"""


# Driving-route layer (Google Directions). Injected verbatim after .format() so its
# single braces don't collide with the template's str.format placeholders.
ROUTE_JS = r"""
// --- Driving route via the Google Routes API. Follows the category filter and is
//     recomputed whenever the visible set changes. Legs under MIN_LEG_MIN are not drawn.
var ROUTE = {polylines: [], labels: [], visible: true, mode: null, hours: "0", gen: 0, legCache: {}};
var RouteLabel = null;
var EST_SPEED_KMH = 55;   // fallback road speed if the Routes API is unavailable
var MIN_LEG_MIN = 10;     // do not draw a connector for legs shorter than this many minutes

function _fmtDur(h) {
  var m = h * 60;
  if (m < 60) return "~" + Math.round(m) + " min";
  return "~" + h.toFixed(1) + " h";
}

function _haversine(a, b) {
  var R = 6371, toRad = Math.PI / 180;
  var dLat = (b.lat - a.lat) * toRad, dLng = (b.lng - a.lng) * toRad;
  var la1 = a.lat * toRad, la2 = b.lat * toRad;
  var x = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
          Math.cos(la1) * Math.cos(la2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return 2 * R * Math.asin(Math.sqrt(x));
}

// Greedy nearest-neighbour chain, starting from the south-easternmost pin.
function orderPins(pins) {
  if (pins.length <= 2) return pins.slice();
  var rest = pins.slice(), start = 0;
  for (var i = 1; i < rest.length; i++) { if (rest[i].lng > rest[start].lng) start = i; }
  var ordered = [rest.splice(start, 1)[0]];
  while (rest.length) {
    var last = ordered[ordered.length - 1], best = 0, bd = Infinity;
    for (var j = 0; j < rest.length; j++) {
      var d = _haversine(last, rest[j]);
      if (d < bd) { bd = d; best = j; }
    }
    ordered.push(rest.splice(best, 1)[0]);
  }
  return ordered;
}

function defineRouteLabel() {
  if (RouteLabel) return;
  RouteLabel = function (pos, text) { this.pos = pos; this.text = text; this.div = null; };
  RouteLabel.prototype = Object.create(google.maps.OverlayView.prototype);
  RouteLabel.prototype.onAdd = function () {
    var d = document.createElement("div");
    d.className = "route-label"; d.textContent = this.text;
    this.div = d; this.getPanes().floatPane.appendChild(d);
  };
  RouteLabel.prototype.draw = function () {
    if (!this.div) return;
    var p = this.getProjection().fromLatLngToDivPixel(this.pos);
    this.div.style.left = p.x + "px"; this.div.style.top = p.y + "px";
  };
  RouteLabel.prototype.onRemove = function () {
    if (this.div && this.div.parentNode) this.div.parentNode.removeChild(this.div);
    this.div = null;
  };
}

function _toLL(p) { return {lat: p.lat, lng: p.lng}; }
function _mid(path) {
  var p = path[Math.floor(path.length / 2)];
  return new google.maps.LatLng(p.lat, p.lng);
}

// Pins that are geocoded AND belong to a currently-selected category.
function visiblePlaced() {
  return PLACES.filter(function (p) {
    return typeof p.lat === "number" && typeof p.lng === "number" &&
           SELECTED[catFor(p.type)] !== false;
  });
}

function clearRouteGraphics() {
  ROUTE.polylines.forEach(function (pl) { pl.setMap(null); });
  ROUTE.labels.forEach(function (l) { l.setMap(null); });
  ROUTE.polylines = []; ROUTE.labels = [];
}

// One real road leg via the Routes API (cached by coordinate pair). Throws if the
// Routes API is disabled/unavailable so the caller can fall back to estimates.
async function realLeg(o, d) {
  var key = o.lat.toFixed(4) + "," + o.lng.toFixed(4) + ">" + d.lat.toFixed(4) + "," + d.lng.toFixed(4);
  if (key in ROUTE.legCache) return ROUTE.legCache[key];
  var lib = await google.maps.importLibrary("routes");
  var res = await lib.Route.computeRoutes({
    origin: {lat: o.lat, lng: o.lng},
    destination: {lat: d.lat, lng: d.lng},
    travelMode: "DRIVING",
    fields: ["durationMillis", "path"]
  });
  var r = res && res.routes && res.routes[0];
  var leg = r ? {sec: (r.durationMillis || 0) / 1000, path: (r.path || []).map(_toLL)} : null;
  ROUTE.legCache[key] = leg;
  return leg;
}

// Recompute the whole route over the currently-visible pins. A generation counter
// discards a run that a newer filter change has superseded.
async function rebuildRoute() {
  var gen = ++ROUTE.gen;
  clearRouteGraphics();
  ROUTE.hours = "0";
  var pins = visiblePlaced();
  if (pins.length < 2) { updateRouteBox(); return; }
  defineRouteLabel();
  var order = orderPins(pins);
  var totalSec = 0, useEst = false;
  for (var i = 0; i < order.length - 1; i++) {
    if (gen !== ROUTE.gen) return;
    var o = order[i], d = order[i + 1], leg = null;
    if (!useEst) {
      try { leg = await realLeg(o, d); }
      catch (e) { useEst = true; }   // Routes API disabled -> estimate the rest
    }
    if (gen !== ROUTE.gen) return;
    if (!leg) {
      var h = _haversine(o, d) / EST_SPEED_KMH;
      leg = {sec: h * 3600, path: [_toLL(o), _toLL(d)], est: true};
    }
    totalSec += leg.sec;
    if (leg.sec / 60 >= MIN_LEG_MIN && leg.path.length >= 2) {
      var est = !!leg.est;
      ROUTE.polylines.push(new google.maps.Polyline({
        path: leg.path, map: ROUTE.visible ? MAP : null,
        strokeColor: "#1a73e8", strokeWeight: 4, strokeOpacity: est ? 0 : 0.7,
        icons: est ? [{icon: {path: "M 0,-1 0,1", strokeOpacity: 0.7, strokeWeight: 3, scale: 3},
                       offset: "0", repeat: "12px"}] : null
      }));
      var lbl = new RouteLabel(_mid(leg.path), _fmtDur(leg.sec / 3600));
      lbl.setMap(ROUTE.visible ? MAP : null);
      ROUTE.labels.push(lbl);
    }
  }
  if (gen !== ROUTE.gen) return;
  ROUTE.mode = useEst ? "est" : "real";
  ROUTE.hours = (totalSec / 3600).toFixed(1);
  updateRouteBox();
}

function updateRouteBox() {
  var box = document.getElementById("routebox");
  if (visiblePlaced().length < 2 || ROUTE.hours === "0" || ROUTE.hours === "0.0") {
    box.style.display = "none"; return;
  }
  var note = ROUTE.mode === "est"
    ? ' <span class="rb-note">(estimated — enable the Routes API for real road times)</span>'
    : ' <span class="rb-note">(legs under ' + MIN_LEG_MIN + ' min hidden)</span>';
  box.innerHTML = '<label class="rb"><input type="checkbox" id="rbchk"' +
    (ROUTE.visible ? " checked" : "") + "> 🚗 Driving route · ~" + ROUTE.hours +
    " h total" + note + "</label>";
  box.style.display = "block";
  document.getElementById("rbchk").addEventListener("change", function (e) {
    toggleRoute(e.target.checked);
  });
}

function toggleRoute(on) {
  ROUTE.visible = on;
  ROUTE.polylines.forEach(function (pl) { pl.setMap(on ? MAP : null); });
  ROUTE.labels.forEach(function (l) { l.setMap(on ? MAP : null); });
}
"""

# Native Places search box: lets the user add their own "intended" pins. Injected
# after .format() (single braces) alongside ROUTE_JS.
SEARCH_JS = r"""
var ADDED_SEQ = 0;

// Delegated handler for the "remove" link inside any pin's popup.
document.addEventListener("click", function (e) {
  var a = e.target.closest ? e.target.closest(".iw-remove") : null;
  if (a) { e.preventDefault(); removePlace(a.getAttribute("data-id")); }
});

// Shared marker factory (used for both collected and user-added pins).
function addMarker(p) {
  var cat = catFor(p.type);
  if (!MARKERS_BY_CAT[cat]) MARKERS_BY_CAT[cat] = [];
  var marker = new google.maps.Marker({
    position: {lat: p.lat, lng: p.lng}, title: p.name,
    map: (SELECTED[cat] !== false) ? MAP : null,
    icon: pinIcon(CATS[cat].color)
  });
  p.__marker = marker;
  MARKERS_BY_CAT[cat].push(marker);
  marker.addListener("click", function () { INFO.setContent(infoContent(p)); INFO.open(MAP, marker); });
  return marker;
}

// Google Places Autocomplete search box (Places API New). Degrades to hidden if unavailable.
async function initSearch() {
  try {
    var places = await google.maps.importLibrary("places");
    var pac = new places.PlaceAutocompleteElement();
    document.getElementById("searchbox").appendChild(pac);
    pac.addEventListener("gmp-select", async function (e) {
      try {
        var place = e.placePrediction.toPlace();
        await place.fetchFields({fields: ["displayName", "location", "formattedAddress"]});
        addPlace(place.displayName || "Added place",
                 place.formattedAddress || "", place.location.lat(), place.location.lng());
      } catch (err) { /* ignore a single failed selection */ }
    });
  } catch (e) {
    var sb = document.getElementById("searchbox");
    if (sb) sb.style.display = "none";  // Places API not enabled -> no search box
  }
}

// Add a user-chosen pin; it behaves like any collected pin (filterable + routed).
function addPlace(name, area, lat, lng) {
  var id = "added-" + (++ADDED_SEQ);
  var p = {name: name, type: "added", area: area || "", why_loved: "Added by you",
           source_urls: [], map_link: null, rating: null, lat: lat, lng: lng, added: true, id: id};
  PLACES.push(p);
  if (SELECTED["added"] === undefined) SELECTED["added"] = true;
  PRESENT.add("added");
  var marker = addMarker(p);
  MAP.panTo({lat: lat, lng: lng});
  if (MAP.getZoom() < 12) MAP.setZoom(13);
  INFO.setContent(infoContent(p));
  INFO.open(MAP, marker);
  buildLegend(PRESENT);
  rebuildRoute();
}

// Remove any pin (collected or user-added) via its popup's "remove" link.
function removePlace(id) {
  var cat = null;
  for (var i = 0; i < PLACES.length; i++) {
    if (PLACES[i].id === id) {
      var p = PLACES[i];
      cat = catFor(p.type);
      if (p.__marker) p.__marker.setMap(null);
      var arr = MARKERS_BY_CAT[cat] || [];
      var mi = arr.indexOf(p.__marker);
      if (mi >= 0) arr.splice(mi, 1);
      PLACES.splice(i, 1);
      break;
    }
  }
  if (cat && !(MARKERS_BY_CAT[cat] || []).length) PRESENT.delete(cat);
  INFO.close();
  buildLegend(PRESENT);
  rebuildRoute();
}
"""


def build_html(data, api_key):
    places = data.get("places", [])
    kept, skipped = filter_places(places)
    dest = data.get("destination", "Trip")
    footer = "{} places shown".format(len(kept))
    if skipped:
        footer += "  ·  {} skipped (no coordinates)".format(len(skipped))
    if api_key == "YOUR_API_KEY":
        footer += "  ·  ⚠️ add your Google Maps API key to render the map"
    html = HTML_TEMPLATE.format(
        title="Map — " + dest,
        footer=footer,
        places_json=safe_json(kept),
        api_key=api_key,
    ).replace("//__ROUTE_JS__", ROUTE_JS).replace("//__SEARCH_JS__", SEARCH_JS)
    return html, kept, skipped


def write_map_html(data, out_dir=MAPS_DIR):
    """Build and write {slug}_map.html from a places dict. Returns (out_path, n_kept, n_skipped).

    Reusable entry point (also called by build_map.py). Reads the Maps key from
    GOOGLE_MAPS_API_KEY; falls back to a YOUR_API_KEY placeholder if unset.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip() or "YOUR_API_KEY"
    html, kept, skipped = build_html(data, api_key)
    os.makedirs(out_dir, exist_ok=True)
    slug = slugify(data.get("destination"))
    out = os.path.join(out_dir, slug + "_map.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    if api_key == "YOUR_API_KEY":
        print("NOTE: GOOGLE_MAPS_API_KEY not set -- wrote YOUR_API_KEY placeholder.")
    return out, len(kept), len(skipped)


def main(argv):
    if len(argv) > 1:
        path = argv[1]
    else:
        cands = sorted(glob.glob(os.path.join(ANALYSIS_DIR, "*_places_*.json")))
        if not cands:
            print("No places JSON found in", ANALYSIS_DIR)
            return 2
        path = cands[-1]

    data = json.load(open(path, encoding="utf-8"))
    out, kept, skipped = write_map_html(data)
    print("wrote", out, "({} places, {} skipped)".format(kept, skipped))
    print("open it:  open", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
