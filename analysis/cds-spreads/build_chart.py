#!/usr/bin/env python3
"""Regenerate the hyperscaler CDS-spread chart from series.csv + annotations.csv.

Usage: python3 build_chart.py [--out chart.png]
Reads analysis/cds-spreads/series.csv and annotations.csv (same dir).
PROXY RULE: bond spreads / loan quotes / rating actions are NEVER plotted as CDS
prints - they live in the separate proxy panel with their own labels.
"""
import argparse
import csv
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = os.path.dirname(os.path.abspath(__file__))
SERIES = os.path.join(HERE, "series.csv")
ANNOT = os.path.join(HERE, "annotations.csv")

COLORS = {
    "ORCL": "#c0392b", "CRWV": "#7b2d8b", "GOOGL": "#1f6fb5", "META": "#2e9e4f",
    "AMZN": "#e67e22", "MSFT": "#16a3a3", "NVDA": "#7f8c8d",
}
MARKERS = {"ORCL": "o", "CRWV": "D", "GOOGL": "s", "META": "^", "AMZN": "v",
           "MSFT": "P", "NVDA": "X"}


def parse(d):
    return datetime.strptime(d, "%Y-%m-%d")


def load_series():
    rows = []
    with open(SERIES, newline="") as f:
        for r in csv.DictReader(f):
            r["value_num"] = float(r["value_num"]) if r["value_num"] else None
            r["date"] = parse(r["date"])
            rows.append(r)
    return rows


def load_annot():
    rows = []
    with open(ANNOT, newline="") as f:
        for r in csv.DictReader(f):
            r["date"] = parse(r["date"])
            rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "chart.png"))
    args = ap.parse_args()

    rows = load_series()
    cds = [r for r in rows if r["proxy_type"] == "cds_print"]
    ratings = [r for r in rows if r["proxy_type"] == "rating_action"]
    spreads = [r for r in rows if r["proxy_type"] == "bond_spread"]
    loans = [r for r in rows if r["proxy_type"] == "loan_quote"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 10), sharex=False,
                                   gridspec_kw={"height_ratios": [1.5, 1], "hspace": 0.35})

    # ---------- Panel 1: 5Y CDS prints only ----------
    for co in ["ORCL", "CRWV", "GOOGL", "META", "AMZN", "MSFT", "NVDA"]:
        pts = sorted([r for r in cds if r["company"] == co], key=lambda r: r["date"])
        if not pts:
            continue
        xs = [r["date"] for r in pts]
        ys = [r["value_num"] for r in pts]
        ax1.plot(xs, ys, color=COLORS[co], linewidth=1.2, alpha=0.7)
        ax1.scatter(xs, ys, color=COLORS[co], marker=MARKERS[co], s=55,
                    label=f"{co} 5Y CDS (print)", zorder=3, edgecolors="white")

    # rating actions as vertical lines
    for r in ratings:
        if r["company"] == "ORCL" and "BBB-" in r["value_text"]:
            ax1.axvline(r["date"], color="#c0392b", linestyle=":", linewidth=1.5)
            ax1.text(r["date"], 30, " S&P: ORCL \u2192 BBB-\n (1 notch above junk)",
                     fontsize=8.5, color="#c0392b", va="bottom", ha="left")

    # key widening-episode annotations
    annots = [
        (parse("2025-12-12"), 147, "FT: $120B+ off-BS via SPVs\nCDS 147, widest since '08",
         "left", parse("2025-12-12"), 175),
        (parse("2026-07-28"), 212, ">200bps — widest\nsince 2008 GFC",
         "right", parse("2026-06-05"), 300),
        (parse("2026-09-24"), 227.5, "Jupiter loans 89\u201391c\nCDS record 227.5",
         "center", parse("2026-09-24"), 520),
    ]
    for d, y, label, ha, xd, yoff in annots:
        ax1.annotate(label, xy=(d, y), xytext=(xd, yoff),
                     fontsize=8, color="#333", ha=ha, va="center",
                     arrowprops=dict(arrowstyle="->", color="#666", lw=1),
                     bbox=dict(boxstyle="round,pad=0.3", fc="#fffbe6", ec="#d9c66a"))

    ax1.set_yscale("log")
    ax1.set_ylim(25, 1300)
    ax1.set_ylabel("5Y CDS spread (bps, log scale)")
    ax1.set_title("Hyperscaler 5Y CDS spreads — news-reported prints only (no interpolation, no proxies)")
    ax1.legend(loc="upper left", fontsize=8.5, ncol=2)
    ax1.grid(True, which="both", alpha=0.25)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax1.text(0.01, 0.02,
             "Each marker = one verified news-reported print (source in series.csv).\n"
             "Continuous weekly history is paywalled (Bloomberg/ICE) — gaps are real gaps.",
             transform=ax1.transAxes, ha="left", va="bottom", fontsize=7.5, color="#666")

    # ---------- Panel 2: proxies — never presented as CDS ----------
    tenors = [("2-4yr", "bond_spread_bps_2_4yr"), ("5-7yr", "bond_spread_bps_5_7yr"),
              ("20yr+", "bond_spread_bps_20yr_plus")]
    x = list(range(len(tenors)))
    base = [next(r["value_num"] for r in spreads
                 if r["metric"] == m and r["date"].year == 2025) for _, m in tenors]
    jul = [next(r["value_num"] for r in spreads
                if r["metric"] == m and r["date"].year == 2026) for _, m in tenors]
    w = 0.35
    ax2.bar([i - w / 2 for i in x], base, width=w, color="#b9c6d3",
            label="Median bond spread, 2025 (LSEG via Reuters)")
    ax2.bar([i + w / 2 for i in x], jul, width=w, color="#34495e",
            label="Median bond spread, Jul-2026 (LSEG via Reuters)")
    for i in x:
        ax2.text(i - w / 2, base[i] + 1.5, f"{base[i]:g}", ha="center", fontsize=9)
        ax2.text(i + w / 2, jul[i] + 1.5, f"{jul[i]:g}", ha="center", fontsize=9,
                 fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels([t for t, _ in tenors])
    ax2.set_ylabel("bps over Treasuries")
    ax2.set_title("Credit PROXIES — not CDS prints (bond Z-spread medians, loan quote, rating actions)")
    ax2.legend(fontsize=8.5, loc="upper left")
    ax2.set_ylim(0, 165)
    ax2.grid(axis="y", alpha=0.3)

    # loan quote + rating actions as annotated facts (not plotted as spreads)
    loan = loans[0]
    ax2.text(0.98, 0.96,
             f"ORCL Project Jupiter $18B loans: {loan['value_text']}c (Sep-2026, FT via Reuters) — stressed\n"
             "S&P: ORCL \u2192 BBB- Jul 9 '26 (1 notch above junk) | Moody's: ORCL negative outlook\n"
             "S&P: CRWV B+ affirmed Apr 9 '26 (positive outlook) — yet CDS prices ~40-45% 5Y default prob",
             transform=ax2.transAxes, ha="right", va="top", fontsize=8.5, color="#333",
             bbox=dict(boxstyle="round,pad=0.4", fc="#f4f6f8", ec="#999"))

    fig.suptitle("Hyperscaler credit stress: 5Y CDS + documented proxies — 2024 → Sep 2026",
                 fontsize=13, fontweight="bold", y=0.98)
    fig.text(0.5, 0.01,
             "Proxy rule: nothing in the lower panel is a CDS print. Bond spreads, loan quotes and rating actions "
             "are labeled as what they are. Regenerate: python3 build_chart.py",
             ha="center", va="bottom", fontsize=7.5, color="#666", wrap=True)
    fig.subplots_adjust(top=0.93, bottom=0.09)
    fig.savefig(args.out, dpi=150)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
