"""Build the H3 cell x month Metrobus boardings panel and cell treatments (ledger: area_panel_v1).

Usage (from the repository root):
    uv run scripts/build_area_panel.py [--out area_v1]

For each month from 2024-08, takes the GTFS version in force on the 15th (service_v1), finds each
route's served stops, and apportions the route's portal boardings (Monthly Total) to those stops
in proportion to the static demand weight of betterbus.area.stop_weights. Stop boardings are
summed to H3 resolution-8 cells. Treatments per cell: weekday scheduled stop visits and served
stops on 2025-05-14 (pre) and 2025-10-22 (post). Writes data/processed/<out>/cell_month.parquet,
cell_treatment.parquet, route_match.csv (share of boardings on routes found in GTFS) and
run_meta.json.
"""

import argparse
import datetime as dt
import json
import subprocess

import numpy as np
import pandas as pd

from betterbus.area import cell_of, feed_stops, stop_weights
from betterbus.config import DATA, RAW, REPO
from betterbus.families import stop_events
from betterbus.panel import route_boardings

GTFS = RAW / "gtfs" / "mdb-1846"
PRE = ("mdb-1846-202505020000", dt.date(2025, 5, 14))
POST = ("mdb-1846-202510160132", dt.date(2025, 10, 22))
LAUNCH = pd.Timestamp("2025-07-01")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="area_v1")
    p.add_argument("--start", default="2024-08-01")
    args = p.parse_args(argv)
    out = DATA / "processed" / args.out
    if out.exists():
        raise SystemExit(f"{out} exists; processed stores are immutable, pick a new --out")

    rd = pd.read_parquet(
        DATA / "processed" / "service_v1" / "route_day.parquet", columns=["date", "version"]
    )
    by_date = rd.drop_duplicates("date").set_index("date").version
    rb = route_boardings()
    rb = rb[rb.month >= args.start]
    months = sorted(rb.month.unique())
    version_of = {m: by_date[pd.Timestamp(m) + pd.Timedelta(days=14)] for m in months}

    stops_all, route_stops = [], {}
    for v in sorted(set(version_of.values())):
        s, rs = feed_stops(GTFS / f"{v}.zip")
        stops_all.append(s.assign(version=v))
        route_stops[v] = rs
    stops = pd.concat(stops_all).drop_duplicates("stop_id", keep="last")
    stops["cell"] = cell_of(stops.stop_lat, stops.stop_lon)
    w = stop_weights(stops)
    stops["w"] = stops.stop_id.map(w)

    rows, match = [], []
    for m in months:
        v = version_of[m]
        side = "old" if pd.Timestamp(m) < LAUNCH else "new"
        b = rb[(rb.month == m) & (rb.side == side)]
        rs = route_stops[v].merge(stops[["stop_id", "cell", "w"]], on="stop_id")
        rs["share"] = rs.w / rs.groupby("route").w.transform("sum")
        j = b.merge(rs, on="route")
        match.append(
            {
                "month": str(pd.Timestamp(m).date()),
                "version": v,
                "boardings_matched_share": float(
                    j.drop_duplicates("route").boardings.sum() / b.boardings.sum()
                ),
            }
        )
        j["b"] = j.boardings * j.share
        rows.append(j.groupby("cell", as_index=False).b.sum().assign(month=m))
    cm = pd.concat(rows).rename(columns={"b": "boardings"})

    ev = []
    for label, (v, day) in {"pre": PRE, "post": POST}.items():
        e = stop_events(GTFS / f"{v}.zip", day).merge(stops[["stop_id", "cell"]], on="stop_id")
        g = e.groupby("cell").agg(visits=("n", "sum"), stops=("stop_id", "nunique"))
        ev.append(g.add_suffix(f"_{label}"))
    tr = pd.concat(ev, axis=1).fillna(0)
    tr["D_visits"] = np.log(tr.visits_post / tr.visits_pre)
    tr["D_stops"] = np.log(tr.stops_post / tr.stops_pre)

    out.mkdir(parents=True)
    cm.to_parquet(out / "cell_month.parquet", index=False)
    tr.reset_index().rename(columns={"index": "cell"}).to_parquet(
        out / "cell_treatment.parquet", index=False
    )
    pd.DataFrame(match).to_csv(out / "route_match.csv", index=False)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    meta = {
        "commit": commit,
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pre": [PRE[0], str(PRE[1])],
        "post": [POST[0], str(POST[1])],
        "h3_resolution": 8,
        "weight": "residents 2020 plus LODES 2024 jobs within 400 m",
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    mm = pd.DataFrame(match)
    lo = mm.boardings_matched_share.min()
    print(f"{cm.cell.nunique()} cells, {len(months)} months; matched share min {lo:.3f}")
    print(
        tr[["visits_pre", "visits_post", "D_visits", "D_stops"]]
        .replace([np.inf, -np.inf], np.nan)
        .describe()
        .round(3)
        .to_string()
    )


if __name__ == "__main__":
    main()
