"""Estimate the pre-registered family-level event study of ridership on redesign service change.

Usage (from the repository root):
    uv run scripts/estimate_event_study.py [--out event_study_v1]

Specification (ledger entry "event_study_v1 | prereg"): log monthly boardings of route family f
in month t on family and month fixed effects plus D_f x month dummies (reference 2025-05), where
D_f is the family's log change in median weekday scheduled trips from 2025-05 (old routes) to
2025-10 (new routes). Standard errors are clustered by family. Also estimates the pooled
post-launch coefficient (2025-06 dropped) and the pre-registered secondary variants.

Writes results/<out>/: event_coefficients.csv, summary.json and event_study.png.
"""

import argparse
import json
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS

from betterbus.config import DATA, REPO
from betterbus.panel import family_month, family_service_change

REF = pd.Timestamp("2025-05-01")
LAUNCH = pd.Timestamp("2025-07-01")
PRE_END = pd.Timestamp("2025-04-01")


def load(treatment="dlog_trips"):
    fm, _ = family_month()
    sc = family_service_change()
    fam = pd.read_csv(DATA / "processed" / "families_v1" / "families.csv")
    df = fm.merge(sc[["family", "dlog_trips", "dlog_hours"]], on="family").merge(
        fam[["family", "containment"]], on="family"
    )
    df = df.dropna(subset=[treatment])
    df = df[df.boardings > 0]
    # balanced on months: keep families observed in every month
    n_months = df.month.nunique()
    keep = df.groupby("family").month.nunique()
    df = df[df.family.isin(keep[keep == n_months].index)].copy()
    df["y"] = np.log(df.boardings)
    df["D"] = df[treatment]
    w24 = df[df.month.dt.year == 2024].groupby("family").boardings.sum()
    df["w2024"] = df.family.map(w24)
    return df


def event_study(df, weights=None):
    months = sorted(df.month.unique())
    X = pd.DataFrame(index=df.index)
    names = []
    for m in months:
        if m == REF:
            continue
        name = f"ev_{pd.Timestamp(m):%Y_%m}"
        X[name] = df.D * (df.month == m)
        names.append(name)
    data = pd.concat([df[["family", "month", "y"]], X], axis=1).set_index(["family", "month"])
    w = None if weights is None else df.set_index(["family", "month"])[weights]
    res = PanelOLS(data.y, data[names], entity_effects=True, time_effects=True, weights=w).fit(
        cov_type="clustered", cluster_entity=True
    )
    coefs = pd.DataFrame({"beta": res.params, "se": res.std_errors})
    coefs["month"] = [pd.Timestamp(n[3:].replace("_", "-") + "-01") for n in coefs.index]
    pre = [n for n in names if pd.Timestamp(n[3:].replace("_", "-") + "-01") <= PRE_END]
    ftest = res.wald_test(formula=" = ".join(pre) + " = 0") if pre else None
    return res, coefs.reset_index(drop=True), ftest, pre


def pooled(df, weights=None):
    d = df[df.month != pd.Timestamp("2025-06-01")].copy()
    d["post_D"] = d.D * (d.month >= LAUNCH)
    data = d.set_index(["family", "month"])
    w = None if weights is None else data[weights]
    res = PanelOLS(data.y, data[["post_D"]], entity_effects=True, time_effects=True, weights=w).fit(
        cov_type="clustered", cluster_entity=True
    )
    return {
        "beta": float(res.params["post_D"]),
        "se": float(res.std_errors["post_D"]),
        "ci95": [float(x) for x in res.conf_int().loc["post_D"]],
        "families": int(d.family.nunique()),
        "obs": int(res.nobs),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="event_study_v1")
    args = p.parse_args(argv)
    out = REPO / "results" / args.out
    out.mkdir(parents=True, exist_ok=True)

    df = load("dlog_trips")
    res, coefs, ftest, pre = event_study(df)
    coefs.to_csv(out / "event_coefficients.csv", index=False)
    pre_coefs = coefs[coefs.month <= PRE_END]
    summary = {
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
        ).stdout.strip(),
        "families": int(df.family.nunique()),
        "months": [str(df.month.min().date()), str(df.month.max().date())],
        "treatment_sd": float(df.groupby("family").D.first().std()),
        "pretrend_wald": {
            "stat": float(ftest.stat),
            "df": int(ftest.df),
            "pval": float(ftest.pval),
        },
        "pre_beta_mean": float(pre_coefs.beta.mean()),
        "primary_pooled": pooled(df),
        "secondary": {},
    }
    sec = summary["secondary"]
    sec["a_weighted_2024_boardings"] = pooled(df, weights="w2024")
    sec["b_treatment_revenue_hours"] = pooled(load("dlog_hours"))
    sec["c_containment_ge_0.6"] = pooled(df[df.containment >= 0.6])
    sec["d_abs_D_le_1"] = pooled(df[df.D.abs() <= 1])
    sec["e_poisson_ppml"] = "not run: needs a PPML implementation with two-way fixed effects"
    (out / "summary.json").write_text(json.dumps(summary, indent=1))

    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.axhline(0, color="0.6", lw=0.8)
    ax.axvline(LAUNCH, color="0.6", lw=0.8, ls="--")
    ax.errorbar(
        coefs.month,
        coefs.beta,
        yerr=1.96 * coefs.se,
        fmt="o",
        ms=3,
        color="black",
        ecolor="0.55",
        elinewidth=0.8,
        capsize=0,
    )
    ax.set_ylabel("coefficient on log change\nin weekday trips")
    ax.set_title("Monthly boardings by route family, relative to May 2025", fontsize=10, loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "event_study.png", dpi=150)
    print(json.dumps({k: v for k, v in summary.items() if k != "commit"}, indent=1))


if __name__ == "__main__":
    main()
