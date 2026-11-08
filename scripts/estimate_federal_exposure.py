"""Test whether route families more exposed to federal employment lost more riders (federal_v1).

Usage (from the repository root):
    uv run scripts/estimate_federal_exposure.py [--out federal_v1]

Exposure per family, from its pre-launch routes' stops (May 2025 GTFS): LODES 2022 federal jobs
(JT04) over all jobs (JT00) at workplaces within 400 m, and the same ratio for residents (RAC).
Each exposure is standardized across families and interacted with month dummies (reference
2024-12) in the family panel of event_study_v1, with D_trips x post as a control. Writes
results/<out>/summary.json and event_coefficients.csv.
"""

import argparse
import datetime as dt
import json
import zipfile

import numpy as np
import pandas as pd
from linearmodels.panel import PanelOLS
from sklearn.neighbors import BallTree

from betterbus.config import DATA, RAW, REPO
from betterbus.families import stop_events
from betterbus.panel import family_month, family_service_detail

FEED = RAW / "gtfs" / "mdb-1846" / "mdb-1846-202505020000.zip"
REF = pd.Timestamp("2024-12-01")
LAUNCH = pd.Timestamp("2025-07-01")
EARTH_M = 6_371_000


def lodes(kind, jt, year=2022):
    frames = []
    for st in ("dc", "md", "va"):
        col = "w_geocode" if kind == "wac" else "h_geocode"
        f = RAW / "lodes" / st / kind / f"{st}_{kind}_S000_{jt}_{year}.csv.gz"
        d = pd.read_csv(f, usecols=[col, "C000"], dtype={col: str}).rename(columns={col: "block"})
        frames.append(d)
    return pd.concat(frames).groupby("block").C000.sum()


def exposure():
    b = pd.read_parquet(RAW / "tiger" / "tabblock20_points.parquet")
    b = b[b.STATEFP20.isin(["11", "24", "51"])].set_index("GEOID20")
    for kind in ("wac", "rac"):
        b[f"{kind}_all"] = lodes(kind, "JT00").reindex(b.index).fillna(0)
        b[f"{kind}_fed"] = lodes(kind, "JT04").reindex(b.index).fillna(0)
    pts = np.radians(b[["INTPTLAT20", "INTPTLON20"]].astype(float).to_numpy())
    tree = BallTree(pts, metric="haversine")
    with zipfile.ZipFile(FEED) as z:
        stops = pd.read_csv(z.open("stops.txt"), dtype={"stop_id": str})
    idx = tree.query_radius(np.radians(stops[["stop_lat", "stop_lon"]].to_numpy()), r=400 / EARTH_M)
    cols = ["wac_all", "wac_fed", "rac_all", "rac_fed"]
    vals = b[cols].to_numpy()
    sums = pd.DataFrame([vals[i].sum(axis=0) for i in idx], columns=cols, index=stops.stop_id)
    ev = stop_events(FEED, dt.date(2025, 5, 14))
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    ev = ev.merge(mem[mem.side == "old"], on="route")
    fam_stops = ev[["family", "stop_id"]].drop_duplicates().join(sums, on="stop_id")
    g = fam_stops.groupby("family")[cols].sum()
    out = pd.DataFrame(
        {"fed_work_share": g.wac_fed / g.wac_all, "fed_res_share": g.rac_fed / g.rac_all}
    )
    return (out - out.mean()) / out.std(), out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="federal_v1")
    args = p.parse_args(argv)
    z, raw = exposure()
    fm, _ = family_month()
    sd = family_service_detail()[["family", "D_trips"]]
    df = fm.merge(sd, on="family").merge(z, left_on="family", right_index=True).dropna()
    df = df[df.boardings > 0]
    n = df.month.nunique()
    full = df.groupby("family").month.nunique()
    df = df[df.family.isin(full[full == n].index)].copy()
    df["y"] = np.log(df.boardings)
    d = df.set_index(["family", "month"])
    months = sorted(df.month.unique())
    X = pd.DataFrame({"D_post": d.D_trips * (d.index.get_level_values("month") >= LAUNCH)})
    for e in ("fed_work_share", "fed_res_share"):
        for m in months:
            if m != REF:
                X[f"{e}|{pd.Timestamp(m):%Y-%m}"] = d[e] * (d.index.get_level_values("month") == m)
    r = PanelOLS(d.y, X, entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_entity=True
    )
    cov = r.cov
    summary = {
        "families": int(df.family.nunique()),
        "exposure_raw_mean": raw.mean().round(4).to_dict(),
        "exposure_raw_sd": raw.std().round(4).to_dict(),
        "D_post": round(float(r.params["D_post"]), 4),
    }
    rows = []
    for e in ("fed_work_share", "fed_res_share"):
        for name, (a, bnd) in {
            "2025-01 to 2025-06": ("2025-01", "2025-06"),
            "2025-07 to 2026-09": ("2025-07", "2026-09"),
        }.items():
            names = [c for c in X.columns if c.startswith(e + "|") and a <= c.split("|")[1] <= bnd]
            w = np.ones(len(names)) / len(names)
            est = float(r.params[names] @ w)
            se = float(np.sqrt(w @ cov.loc[names, names].to_numpy() @ w))
            summary[f"{e} {name}"] = {
                "mean_beta": round(est, 4),
                "se": round(se, 4),
                "ci95": [round(est - 1.96 * se, 4), round(est + 1.96 * se, 4)],
            }
        for c in [c for c in X.columns if c.startswith(e + "|")]:
            rows.append(
                {
                    "exposure": e,
                    "month": c.split("|")[1],
                    "beta": r.params[c],
                    "se": r.std_errors[c],
                }
            )
    dest = REPO / "results" / args.out
    dest.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(dest / "event_coefficients.csv", index=False)
    (dest / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
