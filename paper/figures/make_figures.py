"""Draw the paper's figures from results/ and the processed stores.

Usage (from the repository root):
    uv run paper/figures/make_figures.py

Writes paper/figures/<name>.pdf and .png. Every label comes from NAMES; an unknown key fails.
"""

import json
import sys

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.text import Text

from betterbus.config import DATA, REPO
from betterbus.panel import route_boardings

OUT = REPO / "paper" / "figures"
RES = REPO / "results"
WIDTH = 6.5  # TRB single-column text width (in)
LAUNCH = pd.Timestamp("2025-06-29")
BLACK, BLUE, VERMILLION, GRAY, GREEN = "#000000", "#0072B2", "#D55E00", "#999999", "#009E73"

mpl.rcParams.update(
    {
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "legend.fontsize": 8,
        "legend.frameon": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "lines.linewidth": 1.5,
        "lines.markersize": 4,
        "errorbar.capsize": 0,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

NAMES = {
    "riders": "Boardings",
    "trips": "Scheduled trips",
    "hours": "Scheduled hours",
    "transfer": "Routes handed to other operators",
    "realloc": "WMATA trip reallocation",
    "common": "Common to all routes",
    "pooled": "All families",
    "stable": "Unchanged alignment",
    "stable11": "One old to one new route",
    "lowfreq": "Infrequent routes",
    "highfreq": "Frequent routes",
}


def name(k):
    if k not in NAMES:
        raise KeyError(f"no paper name for {k!r}")
    return NAMES[k]


def word_count(fig):
    return sum(
        any(c.isalpha() for c in w)
        for t in fig.findobj(Text)
        if t.get_visible()
        for w in t.get_text().split()
    )


def save(fig, stem):
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.png", dpi=200)
    print(f"{stem}: {word_count(fig)} words")
    plt.close(fig)


def fig_system():
    rb = route_boardings()
    tot = rb.groupby("month").boardings.sum()
    m = ((tot / tot.shift(12) - 1) * 100).loc["2024-01-01":]
    rd = pd.read_parquet(DATA / "processed" / "service_v1" / "route_day.parquet")
    wk = rd[rd.day_type == "weekday"].groupby("date")[["trips", "revenue_hours"]].sum()
    wk = wk.groupby(wk.index.to_period("M")).median()
    wk.index = wk.index.to_timestamp()
    wk = wk.loc["2024-08-01":"2026-10-01"]
    base = wk.loc["2025-05-01"]
    idx = wk / base * 100
    fig, (a, b) = plt.subplots(1, 2, figsize=(WIDTH, 2.5), gridspec_kw={"width_ratios": [1.25, 1]})
    a.axhline(0, color=GRAY, lw=0.6)
    a.plot(m.index, m.values, color=BLACK, marker="o", ms=2.5, lw=1.2)
    a.set_ylabel("Boardings, change from\nsame month a year earlier (%)")
    for ax in (a, b):
        ax.axvline(LAUNCH, color=GRAY, lw=0.8, ls="--")
        ax.xaxis.set_major_locator(mpl.dates.YearLocator())
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%Y"))
    series = [
        b.plot(idx.index, idx.trips, color=BLUE, label="trips")[0],
        b.plot(idx.index, idx.revenue_hours, color=VERMILLION, label="hours")[0],
    ]
    b.set_ylabel("Weekday service (May 2025 = 100)")
    for line in series:
        b.annotate(
            name(line.get_label()),
            (line.get_xdata()[-1], line.get_ydata()[-1]),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            color=line.get_color(),
            fontsize=8,
            annotation_clip=False,
        )
    a.text(-0.16, 1.02, "a", transform=a.transAxes, fontweight="bold")
    b.text(-0.2, 1.02, "b", transform=b.transAxes, fontweight="bold")
    fig.tight_layout()
    save(fig, "fig1_system")


def fig_event():
    c = pd.read_csv(RES / "event_study_v1" / "event_coefficients.csv", parse_dates=["month"])
    fig, ax = plt.subplots(figsize=(WIDTH, 2.6))
    ax.axhline(0, color=GRAY, lw=0.6)
    ax.axvline(LAUNCH, color=GRAY, lw=0.8, ls="--")
    ax.errorbar(
        c.month, c.beta, yerr=1.96 * c.se, fmt="o", ms=3, color=BLACK, ecolor=GRAY, elinewidth=0.8
    )
    ax.set_ylabel("Boardings response to\nlog change in trips")
    ax.xaxis.set_major_locator(mpl.dates.YearLocator())
    ax.xaxis.set_major_formatter(mpl.dates.DateFormatter("%Y"))
    fig.tight_layout()
    save(fig, "fig2_event_study")


def fig_decomposition():
    d = json.loads((RES / "decomposition_v1" / "summary.json").read_text())[
        "components_pct_of_before"
    ]
    keys = [
        ("transfer", "routes_handed_to_other_operators"),
        ("realloc", "wmata_trip_reallocation"),
        ("common", "common_to_all_families"),
    ]
    fig, ax = plt.subplots(figsize=(WIDTH, 1.7))
    for i, (_, j) in enumerate(keys):
        v = d[j]
        ax.barh(i, v["mean"], color=[VERMILLION, BLUE, GRAY][i], height=0.55)
        ax.errorbar(
            v["mean"],
            i,
            xerr=[[v["mean"] - v["p05"]], [v["p95"] - v["mean"]]],
            fmt="none",
            ecolor=BLACK,
            elinewidth=0.8,
        )
    ax.set_yticks(range(3), [name(k) for k, _ in keys])
    ax.invert_yaxis()
    ax.axvline(0, color=BLACK, lw=0.6)
    ax.set_xlabel("Change in boardings (percentage points)")
    fig.tight_layout()
    save(fig, "fig3_decomposition")


def fig_elasticities():
    mech = json.loads((RES / "mechanisms_v1" / "summary.json").read_text())
    es = json.loads((RES / "event_study_v1" / "summary.json").read_text())["primary_pooled"]
    rows = [
        ("pooled", es["beta"], es["ci95"]),
        ("stable", 0.7092, [0.5237, 0.8947]),
        ("stable11", 0.7603, [0.5546, 0.9661]),
        (
            "lowfreq",
            mech["headway_split"]["D_trips_lowfreq"]["beta"],
            mech["headway_split"]["D_trips_lowfreq"]["ci95"],
        ),
        (
            "highfreq",
            mech["headway_split"]["D_trips_highfreq"]["beta"],
            mech["headway_split"]["D_trips_highfreq"]["ci95"],
        ),
    ]
    fig, ax = plt.subplots(figsize=(WIDTH, 2.0))
    for i, (k, b, ci) in enumerate(rows):
        col = BLACK if i < 3 else (GREEN if k == "lowfreq" else VERMILLION)
        ax.errorbar(
            b, i, xerr=[[b - ci[0]], [ci[1] - b]], fmt="o", color=col, ecolor=col, elinewidth=1.0
        )
    ax.set_yticks(range(len(rows)), [name(r[0]) for r in rows])
    ax.invert_yaxis()
    ax.axvline(0, color=GRAY, lw=0.6)
    ax.set_xlim(0, 1.2)
    ax.set_xlabel("Elasticity of boardings with respect to weekday trips")
    fig.tight_layout()
    save(fig, "fig4_elasticities")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    which = sys.argv[1:] or ["system", "event", "decomposition", "elasticities"]
    for w in which:
        globals()[f"fig_{w}"]()


if __name__ == "__main__":
    main()
