"""Regime sparkline interactions (issues #17, #19): hover annotation, timeframe
following, OLS window switch, alpha slope/acceleration sparklines and
turnaround signal markers.

Runs the template's own drawSpark / sliceRegime / effectiveRange /
renderRegime / packDefined under node with a DOM stub (no live browser in
this environment) and asserts the interactive behavior end to end.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "portfolio_analysis"
    / "templates"
    / "chart.html"
)

_FUNC_NAMES = [
    "drawSpark",
    "sliceRegime",
    "effectiveRange",
    "renderRegime",
    "yearsBefore",
    "packDefined",
]
_CONST_PREFIXES = ["const $=", "const pct=", "const dateLabel=", "const node=", "const svgNode="]

_HARNESS = r"""
// ---- minimal DOM stub ----
function stubNode(tag) {
  return {
    tag, children: [], attrs: {}, textContent: "", hidden: false, value: "",
    onpointermove: null, onpointerleave: null,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    append(...kids) { this.children.push(...kids); },
    replaceChildren() { this.children = []; },
    getBoundingClientRect() {
      return {left: 0, top: 0, width: 600, height: 120, right: 600, bottom: 120};
    },
  };
}
const __byId = {};
const document = {
  getElementById(id) { return __byId[id] || (__byId[id] = stubNode("#" + id)); },
  createElement(t) { return stubNode(t); },
  createElementNS(ns, t) { return stubNode(t); },
};

// ---- extracted template code goes here ----
__TEMPLATE_CODE__

// ---- fixture: regime windows with different point counts ----
function mkWindow(n, alpha0) {
  const dates = [], beta = [], r2 = [], alpha = [], slope = [], accel = [], signals = [];
  let d = new Date("2021-09-17T12:00:00Z");
  for (let i = 0; i < n; i++) {
    dates.push(d.toISOString().slice(0, 10));
    beta.push(1.2 - i * 0.015 + (i % 3) * 0.01);
    r2.push(Math.min(0.99, 0.35 + i * 0.004 + (i % 4) * 0.01));
    alpha.push(alpha0 - i * 0.002 + (i % 5) * 0.001);
    slope.push(i < 2 ? null : 0.001 * (1 + (i % 3) * 0.2));
    accel.push(i < 4 ? null : 0.0002 * ((i % 2) ? 1 : -1));
    signals.push(i < 4 ? null : (i % 7 === 0 ? "turnaround-strong"
      : i % 5 === 0 ? "turnaround" : i % 3 === 0 ? "early-watch" : null));
    d = new Date(d.getTime() + 21 * 86400000);
  }
  return {dates, beta, r_squared: r2, alpha_annualized: alpha,
          alpha_slope: slope, alpha_accel: accel, signals};
}
const win250 = mkWindow(87, -0.05), win125 = mkWindow(61, -0.04), win60 = mkWindow(30, -0.02);
const data = {
  ticker: "NOW", name: "ServiceNow, Inc.", benchmark: "QQQ",
  dates: ["2020-09-18", "2026-09-17"],
  regime: {default_window: "250",
           windows: {"60": win60, "125": win125, "250": win250}},
};
const regimeDates = win250.dates, regimeBeta = win250.beta,
      regimeR2 = win250.r_squared, regimeAlpha = win250.alpha_annualized,
      regimeSlope = win250.alpha_slope, regimeAccel = win250.alpha_accel,
      regimeSignals = win250.signals;
const maxDate = data.dates.at(-1);
const state = {range: "all", view: "compare", direction: "all", regimeWindow: "250",
               start: data.dates[0], end: maxDate};

const failures = [];
function check(name, cond, extra) {
  if (!cond) failures.push(name + (extra ? ": " + extra : ""));
  else console.log("ok - " + name);
}
function polyPoints(id) {
  const svg = document.getElementById(id);
  const poly = svg.children.find(c => c.tag === "polyline");
  return poly ? poly.attrs.points.split(" ").length : -1;
}
function annoGroup(id) {
  return document.getElementById(id).children.find(c => c.tag === "g");
}
function svgTexts(id) {
  return document.getElementById(id).children.filter(c => c.tag === "text").map(c => c.textContent);
}
function signalMarkers(id) {
  return document.getElementById(id).children
    .filter(c => c.tag === "circle" && c.attrs["data-signal"]);
}
const defined = arr => arr.filter(v => v !== null && v !== undefined).length;

// 1. full-range render: all five sparklines
renderRegime();
check("box unhidden", document.getElementById("regime-box").hidden === false);
check("grid shown", document.getElementById("regime-grid").hidden === false);
check("empty hidden", document.getElementById("regime-empty").hidden === true);
check("bench label", document.getElementById("regime-bench").textContent === "QQQ");
check("window label defaults to 250",
      document.getElementById("regime-window-label").textContent === "250");
check("window select synced",
      document.getElementById("regime-window").value === "250");
check("beta polyline point count", polyPoints("spark-beta") === regimeDates.length);
check("alpha polyline point count", polyPoints("spark-alpha") === regimeDates.length);
check("rsquared polyline point count", polyPoints("spark-rsquared") === regimeDates.length);
check("slope polyline skips warmup nulls",
      polyPoints("spark-slope") === defined(regimeSlope),
      String(polyPoints("spark-slope")));
check("accel polyline skips warmup nulls",
      polyPoints("spark-accel") === defined(regimeAccel));
check("annotation hidden initially", annoGroup("spark-beta").attrs.visibility === "hidden");
// R² sparkline uses a fixed 0-1 axis: labels must read 0% / 100% regardless of data range
{
  const r2texts = svgTexts("spark-rsquared");
  check("rsquared axis fixed 0-1",
        r2texts.includes("+100.00%") && r2texts.includes("+0.00%"),
        JSON.stringify(r2texts));
}

// 1b. turnaround signal markers on the alpha sparkline
{
  const marks = signalMarkers("spark-alpha");
  const expected = regimeSignals.filter(s => s !== null).length;
  check("signal marker count", marks.length === expected,
        marks.length + " vs " + expected);
  const strong = marks.find(m => m.attrs["data-signal"] === "turnaround-strong");
  check("strong marker larger", !!strong && strong.attrs.r === "5",
        JSON.stringify(strong && strong.attrs));
  const early = marks.find(m => m.attrs["data-signal"] === "early-watch");
  check("early marker hollow", !!early && early.attrs.fill === "none",
        JSON.stringify(early && early.attrs));
  const plain = marks.find(m => m.attrs["data-signal"] === "turnaround");
  check("turnaround marker filled", !!plain && plain.attrs.fill === "var(--accent)");
}

// 2. hover annotation on the beta sparkline
{
  const svg = document.getElementById("spark-beta");
  const n = regimeDates.length;
  svg.onpointermove({clientX: 310, clientY: 60});
  const expI = Math.max(0, Math.min(n - 1, Math.round((310 - 52) / (600 - 52 - 10) * (n - 1))));
  const anno = annoGroup("spark-beta");
  check("annotation visible on hover", anno.attrs.visibility === "visible");
  const [dot, tag] = anno.children;
  check("dot placed on line", dot.attrs.cx !== undefined && dot.attrs.cy !== undefined);
  const expText = `${dateLabel(regimeDates[expI])} \u00b7 \u03b2 ${regimeBeta[expI].toFixed(2)}`;
  check("annotation date+value", tag.textContent === expText,
        JSON.stringify(tag.textContent) + " vs " + JSON.stringify(expText));
  svg.onpointerleave();
  check("annotation hidden on leave", anno.attrs.visibility === "hidden");
}

// 2b. hover annotation on the slope sparkline uses pct + slope label
{
  const svg = document.getElementById("spark-slope");
  svg.onpointermove({clientX: 200, clientY: 60});
  const tag = annoGroup("spark-slope").children[1];
  check("slope annotation uses pct + slope label",
        tag.textContent.includes("slope") && tag.textContent.includes("%"), tag.textContent);
  svg.onpointerleave();
  check("slope annotation hidden on leave",
        annoGroup("spark-slope").attrs.visibility === "hidden");
}

// 3. hover annotation on the alpha sparkline uses pct formatting
{
  const svg = document.getElementById("spark-alpha");
  svg.onpointermove({clientX: 100, clientY: 60});
  const tag = annoGroup("spark-alpha").children[1];
  check("alpha annotation uses pct + \u03b1 label",
        tag.textContent.includes("\u03b1") && tag.textContent.includes("%"), tag.textContent);
  svg.onpointerleave();
}

// 3b. hover annotation on the R² sparkline: fixed-axis, pct + R² label
{
  const svg = document.getElementById("spark-rsquared");
  const n = regimeDates.length;
  svg.onpointermove({clientX: 200, clientY: 60});
  const expI = Math.max(0, Math.min(n - 1, Math.round((200 - 52) / (600 - 52 - 10) * (n - 1))));
  const anno = annoGroup("spark-rsquared");
  check("rsquared annotation visible on hover", anno.attrs.visibility === "visible");
  const tag = anno.children[1];
  const expText = `${dateLabel(regimeDates[expI])} \u00b7 R\u00b2 ${pct(regimeR2[expI])}`;
  check("rsquared annotation date+value", tag.textContent === expText,
        JSON.stringify(tag.textContent) + " vs " + JSON.stringify(expText));
  svg.onpointerleave();
  check("rsquared annotation hidden on leave", anno.attrs.visibility === "hidden");
}

// 4. 12-month window re-slices all sparklines
state.range = "1";
renderRegime();
{
  const expIdx = sliceRegime(regimeDates, yearsBefore(maxDate, 1), maxDate);
  check("12m beta point count", polyPoints("spark-beta") === expIdx.length,
        String(polyPoints("spark-beta")) + " vs " + expIdx.length);
  check("12m alpha point count", polyPoints("spark-alpha") === expIdx.length);
  check("12m rsquared point count", polyPoints("spark-rsquared") === expIdx.length);
  check("12m slope point count",
        polyPoints("spark-slope") === defined(expIdx.map(i => regimeSlope[i])));
  check("12m accel point count",
        polyPoints("spark-accel") === defined(expIdx.map(i => regimeAccel[i])));
  check("12m marker count",
        signalMarkers("spark-alpha").length ===
          expIdx.filter(i => regimeSignals[i] !== null).length);
  const r2texts = svgTexts("spark-rsquared");
  check("12m rsquared axis still fixed 0-1",
        r2texts.includes("+100.00%") && r2texts.includes("+0.00%"),
        JSON.stringify(r2texts));
  const texts = svgTexts("spark-beta");
  check("12m x-axis start label",
        texts.includes(dateLabel(regimeDates[expIdx[0]])), JSON.stringify(texts));
  check("12m x-axis end label",
        texts.some(t => t.startsWith(dateLabel(regimeDates[expIdx[expIdx.length - 1]]))),
        JSON.stringify(texts));
  check("grid still shown", document.getElementById("regime-grid").hidden === false);
}

// 5. OLS window switch re-renders from the selected window's series
state.range = "all"; state.regimeWindow = "60";
renderRegime();
check("60w beta point count", polyPoints("spark-beta") === win60.dates.length,
      String(polyPoints("spark-beta")) + " vs " + win60.dates.length);
check("60w slope point count",
      polyPoints("spark-slope") === defined(win60.alpha_slope));
check("60w marker count",
      signalMarkers("spark-alpha").length ===
        win60.signals.filter(s => s !== null).length);
check("60w window label", document.getElementById("regime-window-label").textContent === "60");
check("60w select synced", document.getElementById("regime-window").value === "60");
state.regimeWindow = "125";
renderRegime();
check("125w beta point count", polyPoints("spark-beta") === win125.dates.length);
check("125w window label", document.getElementById("regime-window-label").textContent === "125");

// 6. window with < 2 points -> empty state, no made-up numbers
state.regimeWindow = "250"; state.range = "custom";
state.start = "2026-09-10"; state.end = "2026-09-17";
renderRegime();
check("grid hidden on <2 points", document.getElementById("regime-grid").hidden === true);
check("empty shown on <2 points", document.getElementById("regime-empty").hidden === false);

// 7. sliceRegime unit checks
check("sliceRegime exact",
      JSON.stringify(sliceRegime(["2024-01-01", "2024-06-01", "2025-01-01"],
                                "2024-01-01", "2024-12-31")) === "[0,1]");
check("sliceRegime empty", sliceRegime(["2024-01-01"], "2025-01-01", "2025-12-31").length === 0);

// 7b. packDefined drops nulls/undefined, keeps alignment
check("packDefined",
      JSON.stringify(packDefined(["a", "b", "c", "d"], [1, null, undefined, 4]))
        === '[["a","d"],[1,4]]');

// 8. drawSpark defensive clear on short series
{
  const svg = document.getElementById("spark-alpha");
  drawSpark(svg, ["2024-01-01"], [0.5], v => v.toFixed(2), false, "\u03b2");
  check("short series clears svg", svg.children.length === 0);
  check("short series clears handlers", svg.onpointermove === null && svg.onpointerleave === null);
}

if (failures.length) {
  console.error("FAILURES:\n" + failures.map(f => "  - " + f).join("\n"));
  process.exit(1);
}
console.log("all sparkline interaction checks passed");
"""


def _extract_template_code() -> str:
    lines = TEMPLATE.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln == "<script>")
    end = next(i for i, ln in enumerate(lines) if ln == "</script>")
    body = lines[start + 1 : end]
    consts = [ln for ln in body if any(ln.startswith(p) for p in _CONST_PREFIXES)]
    funcs = [ln for ln in body if any(ln.startswith(f"function {n}(") for n in _FUNC_NAMES)]
    missing_c = [p for p in _CONST_PREFIXES if not any(ln.startswith(p) for ln in consts)]
    missing_f = [n for n in _FUNC_NAMES if not any(ln.startswith(f"function {n}(") for ln in funcs)]
    assert not missing_c, f"template consts not found: {missing_c}"
    assert not missing_f, f"template functions not found: {missing_f}"
    return "\n".join(consts + funcs)


@pytest.mark.unit
def test_sparkline_hover_and_timeframe(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is required for the sparkline DOM-stub smoke test")
    harness = _HARNESS.replace("__TEMPLATE_CODE__", _extract_template_code())
    script = tmp_path / "sparkline_smoke.js"
    script.write_text(harness)
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, f"node --check failed:\n{proc.stderr}"
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"sparkline smoke test failed:\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}"
    )
    assert "all sparkline interaction checks passed" in proc.stdout


@pytest.mark.unit
def test_template_carries_window_switch_and_signal_legend():
    """The window switch, the new sparklines and the not-a-buy-signal legend
    must exist in the template HTML (static check, no JS needed)."""
    html = TEMPLATE.read_text()
    assert 'id="regime-window"' in html
    assert 'id="spark-slope"' in html
    assert 'id="spark-accel"' in html
    assert 'id="regime-window-label"' in html
    assert "not buy signals" in html
    assert "Regime-change signals for later validation" in html
