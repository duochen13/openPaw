"""Regime sparkline interactions (issues #17, #19, #39-#42): hover annotation,
timeframe following, OLS window switch, alpha slope sparkline, turnaround
signal markers with tooltips, adaptive daily/weekly/monthly granularity, and
the no-overlap axis labels.

Runs the template's own drawSpark / sliceRegime / effectiveRange /
renderRegime / packDefined / granularityForDays under node with a DOM stub
(no live browser in this environment) and asserts the interactive behavior
end to end.
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
    "granularityForDays",
    "label",
    "moveTipLines",
    "placeTip",
]
_CONST_PREFIXES = [
    "const $=",
    "const pct=",
    "const dateLabel=",
    "const node=",
    "const svgNode=",
    "const SIGNAL_TEXT=",
]

_HARNESS = r"""
// ---- minimal DOM stub ----
function stubNode(tag) {
  return {
    tag, children: [], attrs: {}, textContent: "", hidden: false, value: "",
    handlers: {}, onpointermove: null, onpointerleave: null,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    addEventListener(ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); },
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
// Trailing-average helper mirroring signals.smooth_display (span 5).
function trailAvg(vals, span) {
  const out = new Array(vals.length).fill(null), run = [];
  for (let i = 0; i < vals.length; i++) {
    const v = vals[i];
    if (v === null || v === undefined) { run.length = 0; continue; }
    run.push(v);
    if (run.length > span) run.shift();
    if (run.length === span) out[i] = run.reduce((a, b) => a + b, 0) / span;
  }
  return out;
}
function mkWindow(n, alpha0, endDate) {
  const dates = [], beta = [], r2 = [], alpha = [], slope = [], signals = [];
  const end = new Date(endDate + "T12:00:00Z").getTime();
  for (let i = 0; i < n; i++) {
    const d = new Date(end - (n - 1 - i) * 21 * 86400000);
    dates.push(d.toISOString().slice(0, 10));
    beta.push(1.2 - i * 0.015 + (i % 3) * 0.01);
    r2.push(Math.min(0.99, 0.35 + i * 0.004 + (i % 4) * 0.01));
    alpha.push(alpha0 - i * 0.002 + (i % 5) * 0.001);
    slope.push(i < 2 ? null : 0.001 * (1 + (i % 3) * 0.2));
    signals.push(i < 4 ? null : (i % 5 === 0 ? "turnaround" : null));
  }
  return {dates, beta, r_squared: r2, alpha_annualized: alpha,
          alpha_slope: slope, alpha_slope_display: trailAvg(slope, 5), signals};
}
// Daily-resolution tail for zoomed-in views (issue #41), ending on the same
// session as the monthly series.
function mkFine(endDate, n) {
  const dates = [], beta = [], r2 = [], alpha = [], slope = [], signals = [];
  const end = new Date(endDate + "T12:00:00Z").getTime();
  for (let i = 0; i < n; i++) {
    const d = new Date(end - (n - 1 - i) * 86400000);
    dates.push(d.toISOString().slice(0, 10));
    const k = n - 1 - i;
    beta.push(1.15 + (k % 9) * 0.01);
    r2.push(Math.min(0.99, 0.4 + (k % 20) * 0.01));
    alpha.push(-0.06 + (k % 30) * 0.001);
    slope.push(k < 2 ? null : 0.0008 * ((k % 2) ? 1 : -1));
    signals.push(k % 25 === 0 ? "turnaround" : null);
  }
  return {dates, beta, r_squared: r2, alpha_annualized: alpha,
          alpha_slope: slope, alpha_slope_display: trailAvg(slope, 5), signals};
}
const win250 = mkWindow(87, -0.05, "2026-09-17"),
      win125 = mkWindow(61, -0.04, "2026-09-17"),
      win60 = mkWindow(30, -0.02, "2026-09-17");
const fineWin = mkFine(win250.dates.at(-1), 400);
const data = {
  ticker: "NOW", name: "ServiceNow, Inc.", benchmark: "QQQ",
  dates: ["2020-09-18", "2026-09-17"],
  regime: {default_window: "250",
           windows: {"60": win60, "125": win125, "250": win250},
           fine_tail_sessions: 400,
           fine: {"60": fineWin, "125": fineWin, "250": fineWin}},
};
const regimeDates = win250.dates, regimeBeta = win250.beta,
      regimeR2 = win250.r_squared, regimeAlpha = win250.alpha_annualized,
      regimeSlope = win250.alpha_slope, regimeSlopeD = win250.alpha_slope_display,
      regimeSignals = win250.signals;
const maxDate = data.dates.at(-1);
const state = {range: "all", view: "compare", direction: "all", kind: "all",
               regimeWindow: "250", start: data.dates[0], end: maxDate};

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
function sigTipGroup(id) {
  return document.getElementById(id).children
    .find(c => c.tag === "g" && c.attrs.class === "sig-tip");
}
function svgTexts(id) {
  return document.getElementById(id).children.filter(c => c.tag === "text").map(c => c.textContent);
}
function signalMarkers(id) {
  return document.getElementById(id).children
    .filter(c => c.tag === "circle" && c.attrs["data-signal"]);
}
const defined = arr => arr.filter(v => v !== null && v !== undefined).length;

// 1. full-range render: all four sparklines, monthly granularity
renderRegime();
check("box unhidden", document.getElementById("regime-box").hidden === false);
check("grid shown", document.getElementById("regime-grid").hidden === false);
check("empty hidden", document.getElementById("regime-empty").hidden === true);
check("bench label", document.getElementById("regime-bench").textContent === "QQQ");
check("window label defaults to 250",
      document.getElementById("regime-window-label").textContent === "250");
check("window select synced",
      document.getElementById("regime-window").value === "250");
check("granularity caption monthly on full range",
      document.getElementById("regime-gran").textContent.startsWith("monthly resolution"),
      document.getElementById("regime-gran").textContent);
check("beta polyline point count", polyPoints("spark-beta") === regimeDates.length);
check("alpha polyline point count", polyPoints("spark-alpha") === regimeDates.length);
check("rsquared polyline point count", polyPoints("spark-rsquared") === regimeDates.length);
check("slope polyline draws the smoothed display series",
      polyPoints("spark-slope") === defined(regimeSlopeD),
      String(polyPoints("spark-slope")));
check("annotation hidden initially", annoGroup("spark-beta").attrs.visibility === "hidden");
// R² sparkline uses a fixed 0-1 axis: labels must read 0% / 100% regardless of data range
{
  const r2texts = svgTexts("spark-rsquared");
  check("rsquared axis fixed 0-1",
        r2texts.includes("+100.00%") && !r2texts.includes("+0.00%"),
        JSON.stringify(r2texts));
}
// Reference threshold lines: beta = 1.0 (market-neutral); R² = 0.70/0.85
{
  const isHline = c => c.tag === "line" && c.attrs["stroke-dasharray"] === "5 3";
  const betaH = document.getElementById("spark-beta").children.filter(isHline);
  check("beta market-neutral line drawn", betaH.length === 1, String(betaH.length));
  check("beta line labeled",
        svgTexts("spark-beta").includes("β = 1.0"),
        JSON.stringify(svgTexts("spark-beta")));
  const r2H = document.getElementById("spark-rsquared").children.filter(isHline);
  check("rsquared two threshold lines", r2H.length === 2, String(r2H.length));
  const r2t = svgTexts("spark-rsquared");
  check("rsquared lines labeled",
        r2t.includes("0.70") && r2t.includes("0.85"), JSON.stringify(r2t));
  // the slope sparkline draws the display series, not the raw slope
  const slopeSvg = document.getElementById("spark-slope");
  check("slope sparkline has no threshold lines",
        slopeSvg.children.filter(isHline).length === 0);
}
// Issue #39: the standalone min-value label is gone, so the bottom-right
// date/value caption can never collide with it; the max label stays.
{
  const texts = svgTexts("spark-alpha");
  const standalonePct = texts.filter(t => /^[+-][\d.]+%$/.test(t));
  check("only the max value label remains",
        standalonePct.length === 1 && standalonePct[0] === pct(Math.max(0, ...regimeAlpha)),
        JSON.stringify(texts));
}

// 1b. turnaround signal markers: one filled kind, hover tooltip (issue #40)
{
  const marks = signalMarkers("spark-alpha");
  const expected = regimeSignals.filter(s => s !== null).length;
  check("signal marker count", marks.length === expected,
        marks.length + " vs " + expected);
  check("single signal kind",
        marks.every(m => m.attrs["data-signal"] === "turnaround"));
  const m0 = marks[0];
  check("marker filled", m0.attrs.fill === "var(--accent)");
  check("marker keyboard-focusable",
        m0.attrs.tabindex === "0" && m0.attrs.role === "img");
  check("marker aria-label names the signal",
        (m0.attrs["aria-label"] || "").includes("Turnaround watch"),
        m0.attrs["aria-label"]);
  // hover the last marker: exercises the right-edge clamp of the tooltip
  const svg = document.getElementById("spark-alpha");
  const last = marks[marks.length - 1];
  last.handlers.pointerenter[0]();
  const tip = sigTipGroup("spark-alpha");
  check("signal tooltip visible on hover", tip && tip.attrs.visibility === "visible");
  const [r, t1, t2, t3] = tip.children;
  check("tooltip title has date + meaning",
        t1.textContent.includes("Turnaround watch") && /\d{4}/.test(t1.textContent),
        t1.textContent);
  check("tooltip shows backing alpha and slope values",
        t2.textContent.includes("\u03b1") && t2.textContent.includes("%")
          && t2.textContent.includes("slope"), t2.textContent);
  check("tooltip cites the backing computation",
        t3.textContent.includes("trailing 250-session OLS"), t3.textContent);
  check("tooltip clamped inside the chart",
        +r.attrs.x >= 52 && +r.attrs.x + +r.attrs.width <= 600 - 10
          && +r.attrs.y >= 0 && +r.attrs.y + +r.attrs.height <= 120,
        JSON.stringify(r.attrs));
  // the generic hover annotation stays out of the way while a signal tooltip is up
  svg.onpointermove({target: last});
  check("generic anno suppressed on signal hover",
        annoGroup("spark-alpha").attrs.visibility === "hidden");
  last.handlers.pointerleave[0]();
  check("signal tooltip hidden on leave", tip.attrs.visibility === "hidden");
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

// 4. adaptive granularity (issue #41): 12 months -> weekly from the daily tail
state.range = "1";
renderRegime();
{
  const fIdx = sliceRegime(fineWin.dates, yearsBefore(maxDate, 1), maxDate);
  let expWeekly = fIdx.filter((_, k) => k % 5 === 0);
  if (expWeekly[expWeekly.length - 1] !== fIdx[fIdx.length - 1])
    expWeekly = [...expWeekly, fIdx[fIdx.length - 1]];
  check("granularity caption weekly",
        document.getElementById("regime-gran").textContent.startsWith("weekly resolution"),
        document.getElementById("regime-gran").textContent);
  check("12m beta point count (weekly)", polyPoints("spark-beta") === expWeekly.length,
        String(polyPoints("spark-beta")) + " vs " + expWeekly.length);
  check("12m alpha point count (weekly)", polyPoints("spark-alpha") === expWeekly.length);
  check("12m rsquared point count (weekly)", polyPoints("spark-rsquared") === expWeekly.length);
  check("12m slope point count (weekly)",
        polyPoints("spark-slope") === defined(expWeekly.map(i => fineWin.alpha_slope_display[i])));
  check("12m marker count (weekly)",
        signalMarkers("spark-alpha").length ===
          expWeekly.filter(i => fineWin.signals[i] !== null).length);
  const r2texts = svgTexts("spark-rsquared");
  check("12m rsquared axis still fixed 0-1",
        r2texts.includes("+100.00%") && !r2texts.includes("+0.00%"),
        JSON.stringify(r2texts));
  check("grid still shown", document.getElementById("regime-grid").hidden === false);
}

// 4b. custom range under a month -> daily
state.range = "custom"; state.start = "2026-09-01"; state.end = "2026-09-17";
renderRegime();
{
  const fIdx = sliceRegime(fineWin.dates, state.start, state.end);
  const granText = document.getElementById("regime-gran").textContent;
  check("granularity caption daily",
        granText === `daily resolution \u00b7 ${fIdx.length} points`, granText);
  check("daily beta point count", polyPoints("spark-beta") === fIdx.length);
  const texts = svgTexts("spark-beta");
  check("daily x-axis start label",
        texts.includes(dateLabel(fineWin.dates[fIdx[0]])), JSON.stringify(texts));
}

// 4c. zoomed range with no fine-tail coverage falls back to monthly
{
  const savedFine = data.regime.fine;
  delete data.regime.fine;
  state.range = "1";
  renderRegime();
  const expIdx = sliceRegime(regimeDates, yearsBefore(maxDate, 1), maxDate);
  check("fallback granularity caption monthly",
        document.getElementById("regime-gran").textContent.startsWith("monthly resolution"),
        document.getElementById("regime-gran").textContent);
  check("fallback beta point count", polyPoints("spark-beta") === expIdx.length);
  data.regime.fine = savedFine;
}

// 5. OLS window switch re-renders from the selected window's series
state.range = "all"; state.regimeWindow = "60";
renderRegime();
check("60w beta point count", polyPoints("spark-beta") === win60.dates.length,
      String(polyPoints("spark-beta")) + " vs " + win60.dates.length);
check("60w slope point count",
      polyPoints("spark-slope") === defined(win60.alpha_slope_display));
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
state.start = "2026-09-17"; state.end = "2026-09-17";
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

// 7c. granularity thresholds (issue #41)
check("granularity daily", granularityForDays(31) === "daily");
check("granularity weekly low", granularityForDays(32) === "weekly");
check("granularity weekly high", granularityForDays(365) === "weekly");
check("granularity monthly", granularityForDays(366) === "monthly");

// 8. drawSpark defensive clear on short series
{
  const svg = document.getElementById("spark-alpha");
  drawSpark(svg, ["2024-01-01"], [0.5], v => v.toFixed(2), false, "\u03b2");
  check("short series clears svg", svg.children.length === 0);
  check("short series clears handlers", svg.onpointermove === null && svg.onpointerleave === null);
}

// 9. price-chart move marker tooltip content (issue #40): date, direction,
// event description from collected facts, relevant values; missing backing
// data is stated plainly, never invented.
{
  const evidenced = {
    date: "2025-03-28", return: -0.092, idiosyncratic_component: -0.1151,
    z: -19.58, beta: 1.55,
    facts: [{label: "Quarterly earnings reported", date: "2025-03-28"}],
    evidence_status: "available",
  };
  const missing = {
    date: "2024-10-01", return: 0.0357, idiosyncratic_component: 0.028,
    z: 2.5, beta: 0.9, facts: [], evidence_status: "missing",
  };
  const eLines = moveTipLines(evidenced);
  check("move tip date+direction+return", eLines[0].includes("Mar 28, 2025") &&
        eLines[0].includes("Price fell") && eLines[0].includes("-9.20%"), eLines[0]);
  check("move tip event from facts", eLines[1] === "Quarterly earnings reported", eLines[1]);
  check("move tip values", eLines[2].includes("abnormal -11.51%") &&
        eLines[2].includes("z -19.58") && eLines[2].includes("β 1.55"), eLines[2]);
  const mLines = moveTipLines(missing);
  check("move tip missing evidence plain", mLines[1] === "Evidence not collected", mLines[1]);
  check("move tip up direction", moveTipLines(missing)[0].includes("Price rose"));
  // Dated-event marker (no unusual move): return and abnormal move still
  // shown, z omitted instead of crashing.
  const eventOnly = {
    date: "2025-04-30", return: 0.012, idiosyncratic_component: 0.004,
    z: null, beta: 1.1, kind: "event",
    facts: [{label: "Quarterly earnings reported", date: "2025-04-30"}],
    evidence_status: "event_only",
  };
  const vLines = moveTipLines(eventOnly);
  check("event tip date+direction+return", vLines[0].includes("Apr 30, 2025") &&
        vLines[0].includes("Price rose") && vLines[0].includes("+1.20%"), vLines[0]);
  check("event tip event from facts", vLines[1] === "Quarterly earnings reported", vLines[1]);
  check("event tip shows abnormal, no z",
        vLines[2].includes("abnormal +0.40%") && !vLines[2].includes("z ") &&
        vLines[2].includes("dated event"), vLines[2]);
  // Tooltip placement clamps inside the chart near every edge.
  const W = 900, H = 370, L = 45, R = 24, T = 32, B = 32, tw = 330, th = 76;
  const inside = ([tx, ty]) =>
    tx >= L && tx + tw <= W - R && ty >= T && ty + th <= H - B;
  check("tip clamps at right edge", inside(placeTip(W - 30, 200, W, H, L, R, T, B, tw, th)));
  check("tip clamps at left edge", inside(placeTip(L + 5, 200, W, H, L, R, T, B, tw, th)));
  check("tip flips below near top", inside(placeTip(400, T + 8, W, H, L, R, T, B, tw, th)));
  check("tip clamps near bottom", inside(placeTip(400, H - B - 8, W, H, L, R, T, B, tw, th)));
  check("tip centered case", inside(placeTip(450, 200, W, H, L, R, T, B, tw, th)));
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
    """The window switch, the slope sparkline, the single-kind signal legend,
    the granularity caption, and the TLDR block must exist in the template
    HTML (static check, no JS needed)."""
    html = TEMPLATE.read_text()
    assert 'id="regime-window"' in html
    assert 'id="spark-slope"' in html
    assert 'id="spark-accel"' not in html
    assert 'id="regime-window-label"' in html
    assert 'id="regime-gran"' in html
    assert 'id="tldr-box"' in html and 'id="tldr-text"' in html
    assert "not buy signals" in html
    assert "Regime-change signals for later validation" in html
    assert "turnaround-strong" not in html
    assert "early-watch" not in html
    # One filled signal kind remains: alpha < 0 and slope > 0.
    assert "\u03b1 &lt; 0 and slope &gt; 0" in html
