"""Collect job-access comparisons into one table for the paper.

Usage (from the repository root, after the access runs exist):
    uv run scripts/collect_access.py

Runs scripts/summarize_access.py for each comparison below (writing results/access_<a>_vs_<b>/)
and gathers the 60-minute change by group into results/access_comparisons.csv.
"""

import pandas as pd

from betterbus.config import DATA, REPO

STORE = DATA / "processed" / "access_v1"
PAIRS = [
    ("pre", "post"),
    ("pre_regional", "post_regional"),
    ("post", "S1"),
    ("post", "S2b"),
    ("post", "S3b"),
    ("post", "S2h"),
    ("post", "S3h"),
    ("post_regional", "S1_regional"),
    ("post_regional", "S2b_regional"),
    ("post_regional", "S3b_regional"),
    ("post_regional", "S2h_regional"),
    ("post_regional", "S3h_regional"),
]
GROUPS = [
    "everyone",
    "black_nh",
    "white_nh",
    "hispanic",
    "asian_nh",
    "below_poverty",
    "zero_vehicle_households",
    "adults_with_disability",
    "eea_residents",
    "county: Prince George's",
    "county: District of Columbia",
]


def main():
    import summarize_access

    rows = []
    for a, b in PAIRS:
        if not (
            (STORE / a / "access.parquet").exists() and (STORE / b / "access.parquet").exists()
        ):
            print(f"skip {a} vs {b}: run missing")
            continue
        out = f"access_{a}_vs_{b}"
        summarize_access.main(["--a", a, "--b", b, "--out", out])
        t = pd.read_csv(REPO / "results" / out / "access_by_group.csv").set_index("group")
        for g in GROUPS:
            if g in t.index:
                r = t.loc[g]
                rows.append(
                    {
                        "a": a,
                        "b": b,
                        "group": g,
                        "jobs_60_a": r.jobs_60_pre,
                        "jobs_60_b": r.jobs_60_post,
                        "change": r.jobs_60_change,
                        "pct": r.jobs_60_pct,
                        "share_fell": r.share_where_60min_access_fell,
                    }
                )
    df = pd.DataFrame(rows)
    df.to_csv(REPO / "results" / "access_comparisons.csv", index=False)
    print(df.pivot_table(index="group", columns="b", values="pct").round(2).to_string())


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    main()
