"""Regime sparkline interactions (issue #17): hover annotation + timeframe following.

Runs the template's own drawSpark / sliceRegime / effectiveRange / renderRegime
under node with a DOM stub (no live browser in this environment) and asserts the
interactive behavior end to end.
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

_FUNC_NAMES = ["drawSpark", "sliceRegime", "effectiveRange", "renderRegime", "yearsBefore"]
_CONST_PREFIXES = ["const $=", "const pct=", "const dateLabel=", "const node=", "const svgNode="]

_HARNESS = r"""
// ---- minimal DOM stub ----
function stubNode(tag) {
  return {
    tag, children: [], attrs: {}, textContent: "", hidden: false,
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

// ---- fixture: 21-session sampled regime series, 2021-09-17 .. 2026-09-17 ----
const regimeDates = [], regimeBeta = [], regimeAlpha = [];
{
  let d = new Date("2021-09-17T12:00:00Z");
  const end = new Date("2026-09-17T12:00:00Z");
  let i = 0;
  while (d <= end) {
    regimeDates.push(d.toISOString().slice(0, 10));
    regimeBeta.push(1.2 - i * 0.015 + (i % 3) * 0.01);
    regimeAlpha.push(-0.05 - i * 0.002 + (i % 5) * 0.001);
    d = new Date(d.getTime() + 21 * 86400000);
    i++;
  }
}
const data = {
  ticker: "NOW", name: "ServiceNow, Inc.", benchmark: "QQQ",
  dates: ["2020-09-18", "2026-09-17"],
  regime: {dates: regimeDates, beta: regimeBeta, alpha_annualized: regimeAlpha},
};
const maxDate = data.dates.at(-1);
const state = {range: "all", view: "compare", direction: "all", start: data.dates[0], end: maxDate};

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

// 1. full-range render
renderRegime();
check("box unhidden", document.getElementById("regime-box").hidden === false);
check("grid shown", document.getElementById("regime-grid").hidden === false);
check("empty hidden", document.getElementById("regime-empty").hidden === true);
check("bench label", document.getElementById("regime-bench").textContent === "QQQ");
check("beta polyline point count", polyPoints("spark-beta") === regimeDates.length);
check("alpha polyline point count", polyPoints("spark-alpha") === regimeDates.length);
check("annotation hidden initially", annoGroup("spark-beta").attrs.visibility === "hidden");

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

// 3. hover annotation on the alpha sparkline uses pct formatting
{
  const svg = document.getElementById("spark-alpha");
  svg.onpointermove({clientX: 100, clientY: 60});
  const tag = annoGroup("spark-alpha").children[1];
  check("alpha annotation uses pct + \u03b1 label",
        tag.textContent.includes("\u03b1") && tag.textContent.includes("%"), tag.textContent);
  svg.onpointerleave();
}

// 4. 12-month window re-slices both sparklines
state.range = "1";
renderRegime();
{
  const expIdx = sliceRegime(regimeDates, yearsBefore(maxDate, 1), maxDate);
  check("12m beta point count", polyPoints("spark-beta") === expIdx.length,
        String(polyPoints("spark-beta")) + " vs " + expIdx.length);
  check("12m alpha point count", polyPoints("spark-alpha") === expIdx.length);
  const texts = svgTexts("spark-beta");
  check("12m x-axis start label",
        texts.includes(dateLabel(regimeDates[expIdx[0]])), JSON.stringify(texts));
  check("12m x-axis end label",
        texts.some(t => t.startsWith(dateLabel(regimeDates[expIdx[expIdx.length - 1]]))),
        JSON.stringify(texts));
  check("grid still shown", document.getElementById("regime-grid").hidden === false);
}

// 5. 3-year window
state.range = "3";
renderRegime();
{
  const expIdx = sliceRegime(regimeDates, yearsBefore(maxDate, 3), maxDate);
  check("3y beta point count", polyPoints("spark-beta") === expIdx.length);
}

// 6. window with < 2 points -> empty state, no made-up numbers
state.range = "custom"; state.start = "2026-09-10"; state.end = "2026-09-17";
renderRegime();
check("grid hidden on <2 points", document.getElementById("regime-grid").hidden === true);
check("empty shown on <2 points", document.getElementById("regime-empty").hidden === false);

// 7. sliceRegime unit checks
check("sliceRegime exact",
      JSON.stringify(sliceRegime(["2024-01-01", "2024-06-01", "2025-01-01"],
                                "2024-01-01", "2024-12-31")) === "[0,1]");
check("sliceRegime empty", sliceRegime(["2024-01-01"], "2025-01-01", "2025-12-31").length === 0);

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
