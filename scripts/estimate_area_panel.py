"""Estimate the place-level (H3 cell) ridership response to scheduled stop visits (area_panel_v1).

Usage (from the repository root):
    uv run scripts/estimate_area_panel.py [--store area_v1] [--out area_panel_v1]

Log cell boardings on cell and month fixed effects plus post x D_visits and post x D_stops
(2025-06 dropped), clustered by cell; an event-study version with D_visits x month dummies
(reference 2025-05); a split of the visits coefficient by pre-launch weekday visits (below vs
above the median cell); and counts of cells that lost all service. Writes results/<out>/.
"""

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from betterbus.config import DATA, REPO

LAUNCH, REF, TRANSITION = (pd.Timestamp(x) for x in ("2025-07-01", "2025-05-01", "2025-06-01"))


def fit(df, terms):
    d = df.set_index(["cell", "month"])
    X = pd.DataFrame({t: d.post * d[t] for t in terms})
    r = PanelOLS(d.y, X, entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_entity=True
    )
    ci = r.conf_int()
    res = {
        t: {
            "beta": round(float(r.params[t]), 4),
            "se": round(float(r.std_errors[t]), 4),
            "ci95": [round(float(ci.loc[t, "lower"]), 4), round(float(ci.loc[t, "upper"]), 4)],
        }
        for t in terms
    }
    return res | {"cells": int(df.cell.nunique()), "obs": int(r.nobs)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--store", default="area_v1")
    p.add_argument("--out", default="area_panel_v1")
    args = p.parse_args(argv)
    store = DATA / "processed" / args.store
    cm = pd.read_parquet(store / "cell_month.parquet")
    tr = pd.read_parquet(store / "cell_treatment.parquet")
    lost = tr[(tr.visits_pre > 0) & (tr.visits_post == 0)]
    pre_b = cm[(cm.month >= "2024-08-01") & (cm.month < LAUNCH)].groupby("cell").boardings.sum()
    df = cm.merge(tr, on="cell")
    df = df[np.isfinite(df.D_visits) & np.isfinite(df.D_stops) & (df.boardings > 0)]
    n = df.month.nunique()
    full = df.groupby("cell").month.nunique()
    df = df[df.cell.isin(full[full == n].index)].copy()
    df["y"] = np.log(df.boardings)
    df["post"] = (df.month >= LAUNCH).astype(float)
    pooled_df = df[df.month != TRANSITION]
    med = tr.loc[tr.cell.isin(df.cell), "visits_pre"].median()
    pooled_df = pooled_df.assign(
        D_visits_low=pooled_df.D_visits * (pooled_df.visits_pre <= med),
        D_visits_high=pooled_df.D_visits * (pooled_df.visits_pre > med),
    )
    out = {
        "visits_only": fit(pooled_df, ["D_visits"]),
        "visits_and_stops": fit(pooled_df, ["D_visits", "D_stops"]),
        "visits_split_by_baseline": fit(pooled_df, ["D_visits_low", "D_visits_high"])
        | {"median_visits_pre": float(med)},
        "cells_lost_all_service": int(len(lost)),
        "share_pre_boardings_in_cells_lost": round(
            float(pre_b.reindex(lost.cell).sum() / pre_b.sum()), 4
        ),
        "treatment_sd": round(float(df.groupby("cell").D_visits.first().std()), 4),
    }
    # event study
    d = df.set_index(["cell", "month"])
    X = pd.DataFrame(
        {
            f"m{pd.Timestamp(m):%Y%m}": d.D_visits * (d.index.get_level_values("month") == m)
            for m in sorted(df.month.unique())
            if m != REF
        }
    )
    r = PanelOLS(d.y, X, entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_entity=True
    )
    ev = pd.DataFrame({"beta": r.params, "se": r.std_errors})
    ev["month"] = [pd.Timestamp(c[1:5] + "-" + c[5:] + "-01") for c in ev.index]
    pre = ev[ev.month < TRANSITION]
    out["event_pre_mean"] = round(float(pre.beta.mean()), 4)
    out["event_pre_max_abs_t"] = round(float((pre.beta / pre.se).abs().max()), 2)
    dest = REPO / "results" / args.out
    dest.mkdir(parents=True, exist_ok=True)
    ev.reset_index(drop=True).to_csv(dest / "event_coefficients.csv", index=False)
    (dest / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.axhline(0, color="0.6", lw=0.8)
    ax.axvline(LAUNCH, color="0.6", lw=0.8, ls="--")
    ax.errorbar(
        ev.month,
        ev.beta,
        yerr=1.96 * ev.se,
        fmt="o",
        ms=3,
        color="black",
        ecolor="0.55",
        elinewidth=0.8,
    )
    ax.set_ylabel("coefficient on log change\nin weekday stop visits")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(dest / "event_study.png", dpi=150)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
