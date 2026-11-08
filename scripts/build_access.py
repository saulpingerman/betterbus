"""Compute block-group transit travel times and job accessibility for one network snapshot.

Usage (from the repository root; run large jobs under a memory cap):
    systemd-run --user --scope -p MemoryMax=64G \\
      uv run scripts/build_access.py --label pre --date 2025-05-14 \\
        --bus mdb-1846-202505020000 --rail mdb-1847-202505140012 [--sample 200]

Builds an R5 network from the fixed study-region OSM snapshot plus the given WMATA bus and rail
GTFS versions (WMATA only: this isolates the Better Bus change), then computes the median
transit-plus-walk travel time (percentile 50 over departures each minute in the window) from
every Compact block group to every block group in the Compact and buffer counties, capped at
--max-min minutes. Writes data/processed/<out>/<label>/: points.parquet, ttm.parquet
(from_id, to_id, travel_time), access.parquet (jobs and low-wage jobs reachable within 30, 45
and 60 minutes per origin block group) and run_meta.json.
"""

import argparse
import datetime as dt
import json
import subprocess
import sys
import time

from betterbus.config import DATA, RAW, REPO

OSM = RAW / "osm" / "dmv-study-region-261106.osm.pbf"
THRESHOLDS = [30, 45, 60]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--label", required=True)
    p.add_argument("--date", required=True, help="service date, YYYY-MM-DD (a weekday)")
    p.add_argument("--bus", required=True, help="Mobility Database dataset id of the bus feed")
    p.add_argument("--rail", required=True, help="Mobility Database dataset id of the rail feed")
    p.add_argument("--start", default="07:00")
    p.add_argument("--window-min", type=int, default=120)
    p.add_argument("--max-min", type=int, default=60)
    p.add_argument("--sample", type=int, default=0, help="origins to sample (0 = all)")
    p.add_argument("--memory", default="48G", help="Java heap for R5")
    p.add_argument("--out", default="access_v1")
    args = p.parse_args(argv)

    sys.argv[1:] = ["--max-memory", args.memory]  # r5py reads its options from argv at import
    import r5py

    from betterbus.access import block_group_points

    out = DATA / "processed" / args.out / args.label
    if out.exists():
        raise SystemExit(f"{out} exists; processed stores are immutable, pick a new --out")

    pts = block_group_points()
    origins = pts[pts.compact]
    if args.sample:
        origins = origins.sample(args.sample, random_state=0)
    gtfs = [
        RAW / "gtfs" / "mdb-1846" / f"{args.bus}.zip",
        RAW / "gtfs" / "mdb-1847" / f"{args.rail}.zip",
    ]
    t0 = time.time()
    network = r5py.TransportNetwork(OSM, [str(g) for g in gtfs])
    t_net = time.time() - t0
    departure = dt.datetime.fromisoformat(f"{args.date}T{args.start}")
    ttm = r5py.TravelTimeMatrix(
        network,
        origins=origins[["id", "geometry"]],
        destinations=pts[["id", "geometry"]],
        departure=departure,
        departure_time_window=dt.timedelta(minutes=args.window_min),
        transport_modes=[r5py.TransportMode.TRANSIT, r5py.TransportMode.WALK],
        max_time=dt.timedelta(minutes=args.max_min),
        percentiles=[50],
    )
    t_ttm = time.time() - t0 - t_net
    ttm = ttm.rename(columns={c: "travel_time" for c in ttm.columns if c.startswith("travel_time")})

    reach = ttm.dropna(subset=["travel_time"]).merge(
        pts[["id", "jobs", "jobs_low_wage"]], left_on="to_id", right_on="id"
    )
    acc = origins[["id", "pop20"]].set_index("id")
    for m in THRESHOLDS:
        within = reach[reach.travel_time <= m].groupby("from_id")
        acc[f"jobs_{m}"] = within.jobs.sum()
        acc[f"jobs_low_wage_{m}"] = within.jobs_low_wage.sum()
    acc = acc.fillna(0).reset_index()

    out.mkdir(parents=True)
    pts.drop(columns="geometry").to_parquet(out / "points.parquet", index=False)
    ttm.to_parquet(out / "ttm.parquet", index=False)
    acc.to_parquet(out / "access.parquet", index=False)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    meta = {
        **vars(args),
        "commit": commit,
        "osm": OSM.name,
        "gtfs": [g.name for g in gtfs],
        "r5py": r5py.__version__,
        "origins": len(origins),
        "destinations": len(pts),
        "seconds_network": round(t_net),
        "seconds_matrix": round(t_ttm),
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    w = acc.pop20
    summary = {f"jobs_{m}": round((acc[f"jobs_{m}"] * w).sum() / w.sum()) for m in THRESHOLDS}
    print(f"{args.label}: network {t_net:.0f}s, matrix {t_ttm:.0f}s, {len(origins)} origins")
    print("population-weighted mean jobs reachable:", summary)


if __name__ == "__main__":
    main()
