"""Summarize the change in transit job access by population group (pre vs post redesign).

Usage (from the repository root):
    uv run scripts/summarize_access.py [--store access_v1] [--out access_v1]

Reads data/processed/<store>/{<a>,<b>}/access.parquet (default a=pre, b=post; columns keep the
_pre and _post suffixes for a and b) (scripts/build_access.py) and joins ACS
2020-2024 block-group counts. For each group the script reports the group-weighted mean jobs
reachable within 30, 45 and 60 minutes before and after, the change, and the share of the group
living in block groups whose 60-minute access fell. Groups: everyone (B03002 total), Black
non-Hispanic, white non-Hispanic, Hispanic, Asian non-Hispanic (B03002); people below the poverty
line (C17002 ratio under 1.00); households with no vehicle (B25044 owner plus renter); adults with
a disability (C21007, civilians 18 and over); residents of MWCOG 2022 Equity Emphasis Area tracts;
and residents of each county. Also reports the population-weighted Gini coefficient of 60-minute
access. Writes results/<out>/access_by_group.csv and summary.json.
"""

import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from betterbus.config import DATA, RAW, REPO

ACS = RAW / "acs" / "2024"
COUNTIES = {
    "11001": "District of Columbia",
    "24031": "Montgomery",
    "24033": "Prince George's",
    "51013": "Arlington",
    "51059": "Fairfax County",
    "51107": "Loudoun",
    "51510": "Alexandria",
    "51600": "Fairfax city",
    "51610": "Falls Church",
}


def acs(table, variables=None, label_contains=None):
    d = pd.read_csv(ACS / f"{table}_block_group.csv", dtype={"geoid": str})
    if variables:
        d = d[d.variable.isin(variables)]
    if label_contains:
        d = d[d.label.str.contains(label_contains, regex=False)]
    return d.groupby("geoid").estimate.sum()


def groups():
    g = pd.DataFrame(
        {
            "everyone": acs("B03002", ["B03002_001"]),
            "black_nh": acs("B03002", ["B03002_004"]),
            "white_nh": acs("B03002", ["B03002_003"]),
            "hispanic": acs("B03002", ["B03002_012"]),
            "asian_nh": acs("B03002", ["B03002_006"]),
            "below_poverty": acs("C17002", ["C17002_002", "C17002_003"]),
            "zero_vehicle_households": acs("B25044", ["B25044_003", "B25044_010"]),
            "adults_with_disability": acs("C21007", label_contains="With a disability"),
        }
    )
    eea = gpd.read_file(RAW / "mwcog_eea" / "eea2022_layer0.geojson")
    tracts = gpd.read_file(RAW / "mwcog_eea" / "eea2022_layer1.geojson")
    eea_tracts = set(tracts[tracts.Tracts.isin(eea.Tracts)].GEOID)
    g["eea_residents"] = g.everyone.where(g.index.str[:11].isin(eea_tracts), 0)
    return g, len(eea_tracts)


def gini(x, w):
    o = np.argsort(x)
    x, w = np.asarray(x)[o], np.asarray(w)[o]
    cw = np.cumsum(w) / w.sum()
    cx = np.cumsum(x * w) / (x * w).sum()
    return float(
        1 - np.sum((cw - np.concatenate([[0], cw[:-1]])) * (cx + np.concatenate([[0], cx[:-1]])))
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--store", default="access_v1")
    p.add_argument("--out", default="access_v1")
    p.add_argument("--a", default="pre", help="baseline run label (columns *_pre)")
    p.add_argument("--b", default="post", help="comparison run label (columns *_post)")
    args = p.parse_args(argv)
    store = DATA / "processed" / args.store
    pre = pd.read_parquet(store / args.a / "access.parquet").set_index("id")
    post = pd.read_parquet(store / args.b / "access.parquet").set_index("id")
    g, n_eea = groups()
    df = pre.add_suffix("_pre").join(post.add_suffix("_post")).join(g, how="inner")
    for c, name in COUNTIES.items():
        df[f"county: {name}"] = df.everyone.where(df.index.str[:5] == c, 0)

    rows = []
    for grp in [c for c in df.columns if c in g.columns or c.startswith("county: ")]:
        w = df[grp]
        if w.sum() == 0:
            continue
        r = {"group": grp, "people": float(w.sum())}
        for m in (30, 45, 60):
            a, b = (
                (df[f"jobs_{m}_pre"] * w).sum() / w.sum(),
                (df[f"jobs_{m}_post"] * w).sum() / w.sum(),
            )
            r[f"jobs_{m}_pre"], r[f"jobs_{m}_post"] = round(a), round(b)
            r[f"jobs_{m}_change"], r[f"jobs_{m}_pct"] = round(b - a), round(100 * (b / a - 1), 2)
        fell = df.jobs_60_post < df.jobs_60_pre
        r["share_where_60min_access_fell"] = round(float(w[fell].sum() / w.sum()), 3)
        rows.append(r)
    out_df = pd.DataFrame(rows)
    out = REPO / "results" / args.out
    out.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out / "access_by_group.csv", index=False)
    summary = {
        "block_groups": int(len(df)),
        "eea_tracts_matched": n_eea,
        "gini_60_pre": round(gini(df.jobs_60_pre, df.everyone), 4),
        "gini_60_post": round(gini(df.jobs_60_post, df.everyone), 4),
        "share_people_zero_jobs_60_pre": round(
            float(df.everyone[df.jobs_60_pre == 0].sum() / df.everyone.sum()), 4
        ),
        "share_people_zero_jobs_60_post": round(
            float(df.everyone[df.jobs_60_post == 0].sum() / df.everyone.sum()), 4
        ),
        "run_meta": {
            k: json.loads((store / k / "run_meta.json").read_text()) for k in (args.a, args.b)
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    cols = [
        "group",
        "people",
        "jobs_60_pre",
        "jobs_60_post",
        "jobs_60_change",
        "jobs_60_pct",
        "jobs_45_pct",
        "share_where_60min_access_fell",
    ]
    print(out_df[cols].to_string(index=False))
    print({k: v for k, v in summary.items() if k != "run_meta"})


if __name__ == "__main__":
    main()
