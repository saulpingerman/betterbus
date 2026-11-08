"""Estimate which part of the redesign's service change moved ridership (ledger: mechanisms_v1).

Usage (from the repository root):
    uv run scripts/estimate_mechanisms.py [--out mechanisms_v1]

Same family-month panel, fixed effects, clustering and sample as the pooled event study
(scripts/estimate_event_study.py): log boardings on post-launch interactions with each family's
change in log weekday trips, log scheduled speed and log miles per trip (jointly), then adding
the share of pre-launch stop events at removed stops, then a split of the trips coefficient by
pre-launch midday headway (above or below the median family). Writes results/<out>/summary.json.
"""

import argparse
import json

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from betterbus.config import DATA, REPO
from betterbus.panel import family_month, family_service_detail

LAUNCH = pd.Timestamp("2025-07-01")
TRANSITION = pd.Timestamp("2025-06-01")


def panel():
    fm, _ = family_month()
    sd = family_service_detail()
    fam = pd.read_csv(DATA / "processed" / "families_v1" / "families.csv")
    df = fm.merge(sd, on="family").merge(
        fam[["family", "containment", "share_events_at_removed_stops"]], on="family"
    )
    df = df.dropna(subset=["D_trips", "D_speed", "D_length"])
    df = df[df.boardings > 0]
    n = df.month.nunique()
    full = df.groupby("family").month.nunique()
    df = df[df.family.isin(full[full == n].index) & (df.month != TRANSITION)].copy()
    df["y"] = np.log(df.boardings)
    df["post"] = (df.month >= LAUNCH).astype(float)
    return df


def fit(df, terms):
    d = df.set_index(["family", "month"])
    X = pd.DataFrame({t: d.post * d[t] for t in terms})
    res = PanelOLS(d.y, X, entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_entity=True
    )
    ci = res.conf_int()
    return {
        t: {
            "beta": round(float(res.params[t]), 4),
            "se": round(float(res.std_errors[t]), 4),
            "ci95": [round(float(ci.loc[t, "lower"]), 4), round(float(ci.loc[t, "upper"]), 4)],
        }
        for t in terms
    } | {"families": int(df.family.nunique()), "obs": int(res.nobs)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="mechanisms_v1")
    args = p.parse_args(argv)
    df = panel()
    fam = df.groupby("family").first()
    med_hw = fam.midday_headway_pre.median()
    df["D_trips_lowfreq"] = df.D_trips * (df.midday_headway_pre > med_hw)
    df["D_trips_highfreq"] = df.D_trips * (df.midday_headway_pre <= med_hw)
    hw = df.dropna(subset=["midday_headway_pre"])
    out = {
        "joint_trips_speed_length": fit(df, ["D_trips", "D_speed", "D_length"]),
        "plus_removed_stops": fit(
            df, ["D_trips", "D_speed", "D_length", "share_events_at_removed_stops"]
        ),
        "trips_only_same_sample": fit(df, ["D_trips"]),
        "headway_split": fit(hw, ["D_trips_lowfreq", "D_trips_highfreq"])
        | {"median_midday_headway_min": float(med_hw)},
        "treatment_sd": {
            k: round(float(fam[k].std()), 4) for k in ["D_trips", "D_speed", "D_length"]
        },
    }
    dest = REPO / "results" / args.out
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
