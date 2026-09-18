"""Cross-stock factor dashboard (issue #24): data builder, rendering, CLI wiring.

Covers the daily trailing-250 OLS beta / annualized alpha series per ticker:
shape and warmup, agreement with the single-stock pipeline, no-look-ahead,
degenerate windows as gaps, the shared date axis, and the factors.html page
itself (no iframes, dashboard link). The template's interactive JS gets its
own node DOM-stub smoke test below.
"""

import random
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from portfolio_analysis import cli
from portfolio_analysis.config import MoveParams, Portfolio, PortfolioEntry
from portfolio_analysis.dashboard import render_dashboard
from portfolio_analysis.factor_dashboard import (
    FACTOR_WINDOW,
    factor_dashboard_data,
    render_factor_dashboard,
)
from portfolio_analysis.moves import (
    aligned_returns,
    annualize_alpha,
    ols_regression,
)
from portfolio_analysis.render import _trailing_factor
from portfolio_analysis.store import Store

SYMBOLS = ("AAA", "BBB", "CCC")
BENCH = "QQQ"
N_BARS = 320  # 319 returns; warmup is 249, so 70 defined points per ticker


def _portfolio(symbols=SYMBOLS, benchmark=BENCH) -> Portfolio:
    return Portfolio(
        entries=tuple(
            PortfolioEntry(s, 1000 + i, f"{s} Inc.", ()) for i, s in enumerate(symbols)
        ),
        benchmark=benchmark,
        price_years=6,
        move_params=MoveParams(beta_window=250, sigma_window=20, z_threshold=2.5),
        news_coverage_start="2020-01-01",
        paths={},
    )


def _gen_bench(seed: int, n: int):
    """One shared benchmark: dates, price dict, and its return list."""
    rng = random.Random(seed)
    dates = [(date(2021, 1, 4) + timedelta(days=i)).isoformat() for i in range(n)]
    px = 100.0
    bench, rets = {}, []
    for i, d in enumerate(dates):
        if i:
            br = (rng.random() - 0.5) * 0.02
            px *= 1 + br
            rets.append(br)
        bench[d] = px
    return dates, bench, rets


def _gen_asset(seed: int, dates, bench_rets, beta_true: float):
    """Asset prices with a known beta to the given benchmark returns.

    Noise is iid - never a function of the benchmark return - so it cannot
    load onto beta (see the collinear-noise note on the shared ``_series``
    fixture in test_moves_compute).
    """
    rng = random.Random(seed)
    px = 100.0
    asset = {dates[0]: px}
    for d, br in zip(dates[1:], bench_rets, strict=True):
        ar = beta_true * br + (rng.random() - 0.5) * 0.004
        px *= 1 + ar
        asset[d] = px
    return asset


def _bars(ticker: str, prices: dict[str, float]):
    return [
        {
            "ticker": ticker,
            "date": d,
            "open": p,
            "high": p,
            "low": p,
            "close": p,
            "adj_close": p,
            "volume": 1000,
            "source": "test",
        }
        for d, p in prices.items()
    ]


def _seed(tmp_path: Path, betas=(1.5, 0.5, 1.0), n: int = N_BARS) -> Store:
    """Three tickers with distinct true betas against one shared benchmark."""
    store = Store.open(tmp_path / "t.sqlite")
    dates, bench, bench_rets = _gen_bench(4242, n)
    for i, (sym, b) in enumerate(zip(SYMBOLS, betas, strict=True)):
        asset = _gen_asset(1000 + i, dates, bench_rets, b)
        store.upsert_price_bars(_bars(sym, asset))
    store.upsert_price_bars(_bars(BENCH, bench))
    return store


@pytest.mark.unit
def test_series_shape_and_warmup(tmp_path):
    store = _seed(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
    finally:
        store.close()
    assert data["window"] == FACTOR_WINDOW
    assert data["benchmark"] == BENCH
    assert len(data["dates"]) == N_BARS - 1  # one return per consecutive pair
    assert list(data["stocks"]) == list(SYMBOLS)
    colors = [s["color"] for s in data["stocks"].values()]
    assert len(set(colors)) == len(SYMBOLS)  # distinct lines
    for sym in SYMBOLS:
        s = data["stocks"][sym]
        assert len(s["beta"]) == len(data["dates"])
        assert len(s["alpha"]) == len(data["dates"])
        assert all(v is None for v in s["beta"][: FACTOR_WINDOW - 1])
        assert all(v is None for v in s["alpha"][: FACTOR_WINDOW - 1])
        assert all(isinstance(v, float) for v in s["beta"][FACTOR_WINDOW - 1 :])
        assert all(isinstance(v, float) for v in s["alpha"][FACTOR_WINDOW - 1 :])
    assert data["asof"] == data["dates"][-1]


@pytest.mark.unit
def test_trailing_matches_single_stock_pipeline(tmp_path):
    """The last point must equal _trailing_factor on the same observations -
    the number the single-stock chart shows in its header."""
    store = _seed(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
        asset = store.adjusted_series("AAA")
        bench = store.adjusted_series(BENCH)
    finally:
        store.close()
    expected = _trailing_factor(asset, bench, FACTOR_WINDOW, BENCH)
    assert expected is not None
    got = data["stocks"]["AAA"]
    # Payload rounds to 4dp/5dp by design; compare within that.
    assert got["beta"][-1] == pytest.approx(expected["beta"], abs=1e-4)
    assert got["alpha"][-1] == pytest.approx(expected["alpha_annualized"], abs=1e-5)
    # Sanity: the synthetic true beta is 1.5, so the estimate must be near it.
    assert got["beta"][-1] == pytest.approx(1.5, abs=0.15)


@pytest.mark.unit
def test_each_point_uses_trailing_data_only(tmp_path):
    """No look-ahead: series[i] == manual OLS over returns[i-249, i]."""
    store = _seed(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
        asset = store.adjusted_series("BBB")
        bench = store.adjusted_series(BENCH)
    finally:
        store.close()
    _, aret, bret = aligned_returns(asset, bench)
    series = data["stocks"]["BBB"]
    for i in (FACTOR_WINDOW - 1, 300, len(aret) - 1):
        b, a = ols_regression(aret[i - FACTOR_WINDOW + 1 : i + 1],
                              bret[i - FACTOR_WINDOW + 1 : i + 1])
        # Payload rounds beta to 4dp and alpha to 5dp by design.
        assert series["beta"][i] == pytest.approx(b, abs=1e-4)
        assert series["alpha"][i] == pytest.approx(annualize_alpha(a), abs=1e-5)


@pytest.mark.unit
def test_degenerate_window_is_a_gap_not_a_number(tmp_path):
    """A flat benchmark has zero variance: every window must stay None."""
    store = Store.open(tmp_path / "t.sqlite")
    try:
        dates, _, bench_rets = _gen_bench(7, N_BARS)
        flat = {d: 100.0 for d in dates}
        asset = _gen_asset(9, dates, bench_rets, 1.2)  # real variance
        store.upsert_price_bars(_bars(BENCH, flat))  # zero variance
        store.upsert_price_bars(_bars("AAA", asset))
        data = factor_dashboard_data(_portfolio(("AAA",)), store)
    finally:
        store.close()
    s = data["stocks"]["AAA"]
    assert all(v is None for v in s["beta"])
    assert all(v is None for v in s["alpha"])


@pytest.mark.unit
def test_shared_date_axis_is_a_union(tmp_path):
    """A ticker missing early dates keeps its slot as None on the union axis."""
    store = Store.open(tmp_path / "t.sqlite")
    try:
        dates, bench, bench_rets = _gen_bench(4242, N_BARS)
        for i, (sym, b) in enumerate(zip(SYMBOLS, (1.5, 0.5, 1.0), strict=True)):
            asset = _gen_asset(1000 + i, dates, bench_rets, b)
            if sym == "CCC":
                asset = dict(list(asset.items())[50:])  # late start
            store.upsert_price_bars(_bars(sym, asset))
        store.upsert_price_bars(_bars(BENCH, bench))
        data = factor_dashboard_data(_portfolio(), store)
    finally:
        store.close()
    assert len(data["dates"]) == N_BARS - 1
    ccc = data["stocks"]["CCC"]["beta"]
    assert len(ccc) == N_BARS - 1
    assert all(v is None for v in ccc[:50])
    assert any(v is not None for v in ccc[FACTOR_WINDOW:])


@pytest.mark.unit
def test_missing_prices_raise(tmp_path):
    store = Store.open(tmp_path / "t.sqlite")
    try:
        with pytest.raises(ValueError, match="no prices for benchmark"):
            factor_dashboard_data(_portfolio(benchmark="XXX"), store)
        _, bench, _ = _gen_bench(7, N_BARS)
        store.upsert_price_bars(_bars(BENCH, bench))
        with pytest.raises(ValueError, match="no prices for AAA"):
            factor_dashboard_data(_portfolio(("AAA",)), store)
    finally:
        store.close()


@pytest.mark.unit
def test_render_writes_self_contained_page(tmp_path):
    store = _seed(tmp_path)
    try:
        data = factor_dashboard_data(_portfolio(), store)
    finally:
        store.close()
    target = render_factor_dashboard(data, tmp_path / "out")
    assert target.name == "factors.html"
    html = target.read_text()
    assert "<iframe" not in html
    for token in ("id=\"chips\"", "id=\"slider\"", "id=\"betaSvg\"",
                  "id=\"alphaSvg\"", "const DATA ="):
        assert token in html, token
    for sym in SYMBOLS:
        assert sym in html


@pytest.mark.unit
def test_dashboard_index_links_factors_page(tmp_path):
    target = render_dashboard(_portfolio(), tmp_path / "out")
    assert 'href="factors.html"' in target.read_text()


@pytest.mark.unit
def test_cli_factor_dashboard_end_to_end(tmp_path):
    """The CLI command wires db/out-dir through to factors.html."""
    from portfolio_analysis.config import load_portfolio

    real = load_portfolio()
    store = Store.open(tmp_path / "t.sqlite")
    try:
        dates, bench, bench_rets = _gen_bench(9999, N_BARS)
        store.upsert_price_bars(_bars(real.benchmark, bench))
        for i, sym in enumerate(real.symbols):
            asset = _gen_asset(5000 + i, dates, bench_rets, 1.0)
            store.upsert_price_bars(_bars(sym, asset))
    finally:
        store.close()
    out = tmp_path / "out"
    rc = cli.main(["factor-dashboard", "--db", str(tmp_path / "t.sqlite"),
                   "--out-dir", str(out)])
    assert rc == 0
    page = out / "factors.html"
    assert page.exists()
    for sym in real.symbols:
        assert sym in page.read_text()


# ---------------------------------------------------------------------------
# Template interaction smoke test (node + DOM stub, no live browser)
# ---------------------------------------------------------------------------

_HARNESS = r"""
// ---- minimal DOM stub ----
function mkClassList() {
  const s = new Set();
  return {
    add(c) { s.add(c); }, remove(c) { s.delete(c); },
    toggle(c, force) {
      if (force === undefined) { if (s.has(c)) s.delete(c); else s.add(c); }
      else if (force) s.add(c); else s.delete(c);
    },
    contains(c) { return s.has(c); },
  };
}
function stubNode(tag) {
  return {
    tag, children: [], attrs: {}, textContent: "", innerHTML: "",
    style: {}, dataset: {}, classList: mkClassList(), _handlers: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    append(...kids) { this.children.push(...kids); },
    appendChild(k) { this.children.push(k); return k; },
    addEventListener(t, fn) { (this._handlers[t] = this._handlers[t] || []).push(fn); },
    removeEventListener(t, fn) {
      const a = this._handlers[t] || [], i = a.indexOf(fn);
      if (i >= 0) a.splice(i, 1);
    },
    _fire(t, ev) { for (const fn of (this._handlers[t] || [])) fn(ev || {}); },
    querySelector(sel) {
      if (sel[0] === ".") {
        const want = sel.slice(1);
        const walk = n => {
          for (const k of n.children) {
            if (k.attrs && k.attrs.class === want) return k;
            const f = walk(k); if (f) return f;
          }
          return null;
        };
        return walk(this);
      }
      return null;
    },
    querySelectorAll() { return []; },
    getBoundingClientRect() {
      return { left: 0, top: 0, width: 1000, height: 340, right: 1000, bottom: 340 };
    },
    remove() {},
    setPointerCapture() {},
  };
}
const __byId = {};
const __presetButtons = ["all", "756", "252", "126"].map(n => {
  const b = stubNode("button"); b.dataset.n = n; return b;
});
const document = {
  getElementById(id) { return __byId[id] || (__byId[id] = stubNode("#" + id)); },
  createElement(t) { return stubNode(t); },
  createElementNS(ns, t) { return stubNode(t); },
  querySelectorAll(sel) { return sel === "#presets button" ? __presetButtons : []; },
};

// ---- template code under test ----
__TEMPLATE_CODE__

// ---- checks ----
let nPass = 0;
function check(name, cond, extra) {
  if (!cond) {
    console.log("FAIL: " + name + (extra ? " :: " + extra : ""));
    process.exitCode = 1;
  } else { nPass++; }
}

check("chip count", chipsEl.children.length === 5, chipsEl.children.length);
const chipB = chipsEl.children[1];
chipB.onclick();
check("chip toggles stock off", !visible.has("BBB") && chipB.classList.contains("off"));
check("beta svg drops toggled stock",
      !$("betaSvg").innerHTML.includes("#1f6feb"));
check("alpha svg drops toggled stock",
      !$("alphaSvg").innerHTML.includes("#1f6feb"));
chipB.onclick();
check("chip toggles stock back on",
      visible.has("BBB") && !chipB.classList.contains("off"));

setRange(10, 40);
check("slider start label", $("d0").textContent === fmtDate(DATA.dates[10]),
      $("d0").textContent);
check("slider end label", $("d1").textContent === fmtDate(DATA.dates[40]),
      $("d1").textContent);
check("slider window width", i1 - i0 === 30, (i1 - i0));
setRange(10, 20);
check("sub-30d window widened gracefully", i1 - i0 >= 30, (i1 - i0));

__presetButtons[2].onclick();  // 1Y preset on a 90-day fixture -> full range
check("preset restores full range",
      $("d0").textContent === fmtDate(DATA.dates[0]) &&
      $("d1").textContent === fmtDate(DATA.dates[DATA.dates.length - 1]));
check("preset marked active", __presetButtons[2].classList.contains("on"));

// hover: clientX=500 on a 1000-wide svg
const expI = Math.round((500 - 52) / (1000 - 52 - 8) * (DATA.dates.length - 1));
$("betaBox")._fire("pointermove", { clientX: 500 });
const tip = $("betaTip");
check("tooltip visible on hover", tip.style.display === "block");
check("tooltip shows hovered date", tip.innerHTML.includes(fmtDate(DATA.dates[expI])),
      tip.innerHTML.slice(0, 80));
check("tooltip shows stock values",
      tip.innerHTML.includes("AAA") && tip.innerHTML.includes("CCC"));
check("tooltip beta formatted",
      tip.innerHTML.includes(DATA.stocks.AAA.beta[expI].toFixed(2)));
check("crosshair guide drawn",
      $("betaSvg").children.some(c => c.tag === "line"));
$("betaBox")._fire("pointerleave", {});
check("tooltip hidden on leave", tip.style.display === "none");

console.log("all factor-dashboard interaction checks passed (" + nPass + ")");
"""


def _fixture_payload():
    from datetime import date, timedelta

    dates = [(date(2021, 1, 4) + timedelta(days=i)).isoformat() for i in range(90)]
    colors = {"AAA": "#955424", "BBB": "#1f6feb", "CCC": "#d97706"}
    stocks = {}
    for t, b0, a0 in (("AAA", 1.5, 0.05), ("BBB", 0.5, -0.02), ("CCC", 1.0, 0.01)):
        beta = [round(b0 + i * 0.001, 4) for i in range(90)]
        alpha = [round(a0 - i * 0.0002, 5) for i in range(90)]
        beta[10] = None  # exercise gap-splitting in the path builder
        stocks[t] = {"color": colors[t], "name": f"{t} Inc.",
                     "beta": beta, "alpha": alpha}
    return {"dates": dates, "stocks": stocks, "window": 250,
            "benchmark": "QQQ", "asof": dates[-1]}


def _template_js(html: str) -> str:
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>")
    return html[start:end]


@pytest.mark.unit
def test_template_interactions(tmp_path):
    if shutil.which("node") is None:
        pytest.skip("node is required for the factor-dashboard DOM-stub smoke test")
    target = render_factor_dashboard(_fixture_payload(), tmp_path / "out")
    harness = _HARNESS.replace("__TEMPLATE_CODE__", _template_js(target.read_text()))
    script = tmp_path / "factor_dashboard_smoke.js"
    script.write_text(harness)
    proc = subprocess.run(["node", "--check", str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"node --check failed:\n{proc.stderr}"
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"factor-dashboard smoke test failed:\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}"
    )
    assert "all factor-dashboard interaction checks passed" in proc.stdout
