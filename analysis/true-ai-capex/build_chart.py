#!/usr/bin/env python3
"""Regenerate the reported-vs-true AI capex chart from series.csv.

Usage: python3 build_chart.py [--out chart.png]
Reads analysis/true-ai-capex/series.csv (same dir) and writes the chart.
"""
import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "series.csv")


def load():
    rows = []
    with open(CSV, newline="") as f:
        for r in csv.DictReader(f):
            r["value_usd_b"] = float(r["value_usd_b"])
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "chart.png"))
    args = ap.parse_args()

    rows = load()
    by = {(r["year"], r["series"]): r for r in rows}

    # --- Panel A: Big-4 annual flow ---
    years = ["2023", "2024", "2025", "2026E"]
    reported = [by[(y, "reported_capex")]["value_usd_b"] for y in years]
    # off-BS rows use plain calendar year ("2026"), reported flow uses "2026E"
    offbs = [by[(y.replace("E", ""), "offbs_spv_estimate")]["value_usd_b"] for y in years]
    true = [r + o for r, o in zip(reported, offbs)]
    anchors = {
        "2024": "GAIIP $100B\n(MSFT/BlackRock, Sep-24)",
        "2025": "FT: $120B+ off-BS\n(ORCL/META/xAI/CRWV)",
        "2026E": "El Paso $12.3B\n(META/BlackRock SPV)",
    }

    fig = plt.figure(figsize=(13, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1], hspace=0.45, wspace=0.25)

    ax = fig.add_subplot(gs[0, :])
    x = range(len(years))
    b1 = ax.bar(x, reported, color="#1f6fb5", label="Reported capex, Big-4 (MSFT+AMZN+GOOGL+META)")
    b2 = ax.bar(x, offbs, bottom=reported, color="#f5a623", hatch="///",
                edgecolor="#b97a12", label="Off-BS SPV: newly announced commitments (estimated)")
    ax.plot(x, true, color="#2e9e4f", marker="s", linewidth=2.5, linestyle="--",
            label="True funding = reported + off-BS (estimated)")

    for i, y in enumerate(years):
        ax.text(i, reported[i] / 2, f"${reported[i]:.0f}B", ha="center", va="center",
                color="white", fontsize=10, fontweight="bold")
        if offbs[i] > 0:
            if offbs[i] >= 40:
                ax.text(i, reported[i] + offbs[i] / 2, f"+${offbs[i]:.0f}B", ha="center",
                        va="center", fontsize=10, fontweight="bold", color="#7a4d00")
            else:
                # thin sliver: label sits just left of the bar to avoid collisions
                ax.text(i - 0.44, reported[i] + offbs[i] / 2, f"+${offbs[i]:.0f}B",
                        ha="right", va="center", fontsize=10, fontweight="bold",
                        color="#7a4d00")
            # anchor box above the bar; true-value label just above the green marker
            ax.text(i, true[i] + 95, anchors[y], ha="center", va="bottom", fontsize=8.5,
                    color="#7a4d00",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#fff7e6", ec="#e8a33d"))
    for i, y in enumerate(years):
        if offbs[i] > 0:
            ax.text(i + 0.28, true[i] + 12, f"True ≈ ${true[i]:.0f}B", ha="left",
                    va="bottom", fontsize=9, fontweight="bold", color="#2e9e4f")

    ax.set_xticks(list(x))
    ax.set_xticklabels(years)
    ax.set_ylabel("Annual AI funding ($B)")
    ax.set_title("Hyperscaler AI spending: reported capex vs true funding incl. off-BS SPV — 2023–2026E")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_ylim(0, 1050)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.0f}B"))
    ax.grid(axis="y", alpha=0.3)

    # --- Panel B: Oracle (FY basis, kept separate) ---
    ax2 = fig.add_subplot(gs[1, 0])
    orcl = [by[("FY2025", "reported_capex")], by[("FY2026E", "reported_capex")]]
    ax2.bar(["FY2025", "FY2026E"], [r["value_usd_b"] for r in orcl], color="#7b61a8")
    for i, r in enumerate(orcl):
        ax2.text(i, r["value_usd_b"] + 1.5, f"${r['value_usd_b']:.0f}B", ha="center",
                 fontsize=10, fontweight="bold")
    ax2.set_ylabel("Reported capex ($B)")
    ax2.set_title("Oracle reported capex (FY basis — not in Big-4 calendar sum)")
    ax2.set_ylim(0, 95)
    ax2.text(0.98, 0.96,
             "FY2026E bar = $63B midpoint of $56–70B guidance.\n"
             "ORCL Vantage $38B off-BS package is counted in the 2025\n"
             "industry aggregate (top panel), not double-counted here.",
             transform=ax2.transAxes, ha="right", va="top", fontsize=8, color="#555",
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#ccc"))
    ax2.grid(axis="y", alpha=0.3)

    # --- Panel C: commitment STOCKS (separate axis, never mixed with flow) ---
    ax3 = fig.add_subplot(gs[1, 1])
    stocks = [r for r in rows if r["series"].endswith("_stock")]
    labels = ["~$3T off-BS\ncommitments\n(all hyperscalers,\nWSJ Jun-26)",
              "GOOGL $811B\npurchase\ncommitments",
              "META $347B\nuncommenced\nleases"]
    vals = [r["value_usd_b"] for r in stocks]
    ax3.barh(labels, vals, color="#9aa0a6")
    for i, v in enumerate(vals):
        ax3.text(v + 60, i, f"${v:,.0f}B", va="center", fontsize=10, fontweight="bold")
    ax3.set_xlabel("Commitment stock ($B) — NOT annual flow")
    ax3.set_title("Off-BS commitment STOCKS (separate axis by design)")
    ax3.grid(axis="x", alpha=0.3)

    fig.text(0.5, 0.005,
             "Methodology: off-BS layer = newly announced SPV/off-BS commitments, booked in announcement year "
             "(commitments \u2260 same-year spend). Every off-BS estimate is anchored to a named deal in series.csv \u2014 "
             "no anchor, no estimate. Oracle excluded from Big-4 bars (FY vs calendar). "
             "Regenerate: python3 build_chart.py",
             ha="center", va="bottom", fontsize=7, color="#666", wrap=True)
    fig.subplots_adjust(top=0.92, bottom=0.12, hspace=0.5, wspace=0.3)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
