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
    classList: {toggle() {}, add() {}, remove() {}},
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
// Issue #47 fixtures: time-weighted (WLS) regime series keyed by half-life.
const wls20 = mkWindow(40, -0.03, "2026-09-17"),
      wls60 = mkWindow(55, -0.025, "2026-09-17"),
      wls120 = mkWindow(70, -0.035, "2026-09-17");
const wlsFine = mkFine(win250.dates.at(-1), 300);
// Issue #50 fixtures: WLS-regression slope series per (half-life, span).
const wlsSlope = {}, wlsSlopeFine = {};
for (const h of ["20", "60", "120"]) {
  wlsSlope[h] = {}; wlsSlopeFine[h] = {};
  for (const s of ["10", "20", "30"]) {
    const w = mkWindow(40, -0.03, "2026-09-17");
    const k = Number(s) / 20;  // keep spans distinguishable
    w.alpha_slope = w.alpha_slope.map(v => v === null ? null : v * k);
    w.alpha_slope_display = trailAvg(w.alpha_slope, 5);
    wlsSlope[h][s] = w;
    wlsSlopeFine[h][s] = mkFine(win250.dates.at(-1), 300);
  }
}
const data = {
  ticker: "NOW", name: "ServiceNow, Inc.", benchmark: "QQQ",
  dates: ["2020-09-18", "2026-09-17"],
  tldr: "TLDR fixture sentence.",
  regime: {default_window: "250",
           windows: {"60": win60, "125": win125, "250": win250},
           fine_tail_sessions: 400,
           fine: {"60": fineWin, "125": fineWin, "250": fineWin},
           wls_half_lives: ["20", "60", "120"], wls_default: "60",
           wls: {"20": wls20, "60": wls60, "120": wls120},
           wls_fine: {"20": wlsFine, "60": wlsFine, "120": wlsFine},
           slope_spans: ["10", "20", "30"], slope_default: "20",
           wls_slope: wlsSlope, wls_slope_fine: wlsSlopeFine},
};
const regimeDates = win250.dates, regimeBeta = win250.beta,
      regimeR2 = win250.r_squared, regimeAlpha = win250.alpha_annualized,
      regimeSlope = win250.alpha_slope, regimeSlopeD = win250.alpha_slope_display,
      regimeSignals = win250.signals;
const maxDate = data.dates.at(-1);
const state = {range: "all", view: "compare", direction: "all", kind: "all",
               regimeWindow: "250", regimeMode: "fixed", wlsHalfLife: "60",
               wlsSlopeHalfLife: "60", wlsSlopeSpan: "20",
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
check("mode label defaults to fixed 250-session OLS",
      document.getElementById("regime-mode-label").textContent === "Trailing 250-session OLS",
      document.getElementById("regime-mode-label").textContent);
check("factor strip states active fixed mode",
      document.getElementById("factor-mode").textContent === "Regime panel: fixed time weight",
      document.getElementById("factor-mode").textContent);
check("tldr unmodified in fixed mode",
      document.getElementById("tldr-text").textContent === "TLDR fixture sentence.",
      document.getElementById("tldr-text").textContent);
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
check("60w mode label",
      document.getElementById("regime-mode-label").textContent === "Trailing 60-session OLS",
      document.getElementById("regime-mode-label").textContent);
check("60w select synced", document.getElementById("regime-window").value === "60");
state.regimeWindow = "125";
renderRegime();
check("125w beta point count", polyPoints("spark-beta") === win125.dates.length);
check("125w mode label",
      document.getElementById("regime-mode-label").textContent === "Trailing 125-session OLS",
      document.getElementById("regime-mode-label").textContent);

// 5b. issue #47: WLS tab renders the half-life series and says so
state.regimeMode = "wls"; state.wlsHalfLife = "20"; state.range = "all";
renderRegime();
check("wls 20h beta point count", polyPoints("spark-beta") === wls20.dates.length,
      String(polyPoints("spark-beta")) + " vs " + wls20.dates.length);
check("wls mode label",
      document.getElementById("regime-mode-label").textContent ===
        "Trailing WLS, half-life 20 sessions (recent sessions weigh more)",
      document.getElementById("regime-mode-label").textContent);
check("wls half-life select synced", document.getElementById("regime-half-life").value === "20");
check("wls tab marked selected",
      document.getElementById("regime-tab-wls").attrs["aria-selected"] === "true");
check("fixed tab deselected in wls mode",
      document.getElementById("regime-tab-fixed").attrs["aria-selected"] === "false");
check("wls signal note names WLS computation",
      document.getElementById("regime-signal-note").textContent ===
        "time-weighted (WLS) computation",
      document.getElementById("regime-signal-note").textContent);
check("factor strip states active wls mode",
      document.getElementById("factor-mode").textContent ===
        "Regime panel: enable time weight (half-life 20 sessions)",
      document.getElementById("factor-mode").textContent);
check("tldr names the active wls mode",
      document.getElementById("tldr-text").textContent ===
        "TLDR fixture sentence. Regime panel below is showing enable time weight " +
        "(half-life 20 sessions).",
      document.getElementById("tldr-text").textContent);
{
  const wmarks = signalMarkers("spark-alpha");
  check("wls marker count",
        wmarks.length === wls20.signals.filter(s => s !== null).length);
  const wlast = wmarks[wmarks.length - 1];
  wlast.handlers.pointerenter[0]();
  const wtip = sigTipGroup("spark-alpha");
  check("wls signal tooltip cites WLS",
        wtip.children[3].textContent.includes("trailing WLS, half-life 20 sessions"),
        wtip.children[3].textContent);
  wlast.handlers.pointerleave[0]();
}
// 5c. issue #50: "enable time weight (alpha slope)" tab
state.regimeMode = "wls-slope"; state.wlsSlopeHalfLife = "60";
state.wlsSlopeSpan = "30"; state.range = "all";
renderRegime();
check("slope tab marked selected",
      document.getElementById("regime-tab-wls-slope").attrs["aria-selected"] === "true");
check("other tabs deselected in slope mode",
      document.getElementById("regime-tab-fixed").attrs["aria-selected"] === "false" &&
      document.getElementById("regime-tab-wls").attrs["aria-selected"] === "false");
check("slope controls visible, sibling controls hidden",
      document.getElementById("regime-wls-slope-controls").hidden === false &&
      document.getElementById("regime-wls-controls").hidden === true &&
      document.getElementById("regime-fixed-controls").hidden === true);
check("slope half-life + span selects synced",
      document.getElementById("regime-slope-half-life").value === "60" &&
      document.getElementById("regime-slope-span").value === "30");
check("slope mode label names WLS-regression estimator and span",
      document.getElementById("regime-mode-label").textContent.includes("WLS-regression") &&
      document.getElementById("regime-mode-label").textContent.includes("span 30"),
      document.getElementById("regime-mode-label").textContent);
check("slope note names WLS regression",
      document.getElementById("regime-slope-note").textContent.includes("WLS regression"),
      document.getElementById("regime-slope-note").textContent);
check("slope tab beta still from the wls half-life series",
      polyPoints("spark-beta") === wls60.dates.length,
      String(polyPoints("spark-beta")) + " vs " + wls60.dates.length);
{
  const sd30 = wlsSlope["60"]["30"].alpha_slope_display;
  check("slope sparkline draws the span-30 display series",
        polyPoints("spark-slope") === defined(sd30),
        String(polyPoints("spark-slope")) + " vs " + defined(sd30));
  const smarks = signalMarkers("spark-alpha");
  const slast = smarks[smarks.length - 1];
  slast.handlers.pointerenter[0]();
  const stip = sigTipGroup("spark-alpha");
  check("slope tab tooltip cites WLS-regression slope and span",
        stip.children[3].textContent.includes("WLS-regression slope (span 30)"),
        stip.children[3].textContent);
  slast.handlers.pointerleave[0]();
}
check("factor strip states slope mode",
      document.getElementById("factor-mode").textContent.includes(
        "enable time weight (alpha slope)"),
      document.getElementById("factor-mode").textContent);
check("tldr names the slope mode",
      document.getElementById("tldr-text").textContent.includes("enable time weight (alpha slope)"),
      document.getElementById("tldr-text").textContent);
state.regimeMode = "fixed"; state.wlsHalfLife = "60";

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
    assert 'id="regime-gran"' in html
    assert 'id="tldr-box"' in html and 'id="tldr-text"' in html
    assert "not buy signals" in html
    assert "Regime-change signals for later validation" in html
    assert "turnaround-strong" not in html
    assert "early-watch" not in html
    # One filled signal kind remains: alpha < 0 and slope > 0.
    assert "\u03b1 &lt; 0 and slope &gt; 0" in html


@pytest.mark.unit
def test_template_carries_weighting_mode_tabs():
    """Issue #47: the regime panel has fixed-time-weight / enable-time-weight
    tabs, a half-life selector for the WLS tab, and a dynamic mode label."""
    html = TEMPLATE.read_text()
    assert 'id="regime-tab-fixed"' in html
    assert 'id="regime-tab-wls"' in html
    assert ">fixed time weight<" in html
    assert ">enable time weight<" in html
    assert 'id="regime-half-life"' in html
    assert 'id="regime-mode-label"' in html
    assert 'id="regime-signal-note"' in html
    assert 'id="factor-mode"' in html
    assert "fixed time weight" in html
    # The old static window label is gone; the label is mode-aware now.
    assert 'id="regime-window-label"' not in html


@pytest.mark.unit
def test_template_carries_alpha_slope_tab():
    """Issue #50: the regime panel's third tab - "enable time weight (alpha
    slope)" - with its own half-life and slope-span selectors, and a dynamic
    slope note naming the active estimator."""
    html = TEMPLATE.read_text()
    assert 'id="regime-tab-wls-slope"' in html
    assert ">enable time weight (alpha slope)<" in html
    assert 'id="regime-wls-slope-controls"' in html
    assert 'id="regime-slope-half-life"' in html
    assert 'id="regime-slope-span"' in html
    assert 'id="regime-slope-note"' in html
    assert "WLS-regression" in html


@pytest.mark.unit
def test_preset_date_helpers(tmp_path):
    """Issue #52: monthsBefore/daysBefore do calendar-correct arithmetic.

    Regression guard: sixMonthStart previously used yearsBefore(x, 0.5),
    whose fractional year truncated to a whole year (12 months, not 6).
    """
    if shutil.which("node") is None:
        pytest.skip("node is required for the date-helper check")
    lines = TEMPLATE.read_text().splitlines()
    funcs = [
        ln
        for ln in lines
        if ln.startswith("function monthsBefore(") or ln.startswith("function daysBefore(")
    ]
    assert len(funcs) == 2, "preset date helpers not found in template"
    script = tmp_path / "preset_dates.js"
    script.write_text(
        "\n".join(funcs)
        + """
const assert = require("assert");
assert.strictEqual(monthsBefore("2026-09-17", 6), "2026-03-17");
assert.strictEqual(monthsBefore("2026-09-17", 3), "2026-06-17");
assert.strictEqual(monthsBefore("2026-09-17", 1), "2026-08-17");
assert.strictEqual(monthsBefore("2026-03-31", 1), "2026-02-28");  // month-end clamp
assert.strictEqual(daysBefore("2026-09-17", 7), "2026-09-10");
assert.strictEqual(daysBefore("2026-01-05", 10), "2025-12-26");  // year boundary
console.log("preset date helper checks passed");
"""
    )
    proc = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, f"node --check failed:\n{proc.stderr}"
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, f"date helper check failed:\n{proc.stderr}"
    assert "preset date helper checks passed" in proc.stdout
