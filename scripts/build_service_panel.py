"""Build the route-by-day and route-by-month scheduled service panel from archived WMATA GTFS.

Usage (from the repository root):
    uv run scripts/build_service_panel.py [--feed mdb-1846] [--out service_v1] [--workers 8]

Reads data/raw/gtfs/<feed>/index.csv (written by fetch_mdb_gtfs.py), decides which feed version
was in force on each date (betterbus.service.choose_versions), computes each route's scheduled
service on every date, and writes to data/processed/<out>/:
    versions.csv       each feed version, its calendar coverage and the dates it was used for
    route_day.parquet  date, version, day_type, route, trips, revenue_hours, revenue_miles, ...
    route_month.parquet  per route and month: median trips by day type, monthly revenue hours
                       and miles, weekday span and midday/evening headway
    run_meta.json      commit, dirty flag, input sha256s, creation time
The output directory is never overwritten; choose a new --out name for a rebuild.
"""

import argparse
import datetime as dt
import json
import subprocess
import zipfile
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from betterbus.config import DATA, RAW, REPO
from betterbus.service import Feed, active_dates, choose_versions


def feed_active_dates(path):
    """Dates on which a feed schedules any service (reads only the calendar files)."""
    with zipfile.ZipFile(path) as z:
        cal = pd.read_csv(z.open("calendar.txt"), dtype=str)
        cd = None
        if "calendar_dates.txt" in z.namelist():
            cd = pd.read_csv(z.open("calendar_dates.txt"), dtype=str)
            cd["date"] = pd.to_datetime(cd.date, format="%Y%m%d")
    return active_dates(cal, cd)


def day_type(d):
    return "weekday" if d.weekday() < 5 else ("saturday" if d.weekday() == 5 else "sunday")


def service_for_version(args):
    path, version, dates = args
    feed = Feed(path)
    frames = []
    for d in dates:
        df = feed.daily_route_service(d)
        if len(df):
            df.insert(0, "date", pd.Timestamp(d))
            df.insert(1, "version", version)
            df.insert(2, "day_type", day_type(d))
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def git_state():
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
    ).stdout
    return {"commit": commit, "dirty": bool(porcelain.strip()), "status_porcelain": porcelain}


def monthly(route_day):
    rd = route_day.copy()
    rd["month"] = rd.date.dt.to_period("M").dt.to_timestamp()
    by = ["route", "month"]
    out = rd.groupby(by).agg(
        days_scheduled=("date", "nunique"),
        trips_month=("trips", "sum"),
        revenue_hours_month=("revenue_hours", "sum"),
        revenue_miles_month=("revenue_miles", "sum"),
        stops_served_max=("stops_served", "max"),
    )
    for dtp in ["weekday", "saturday", "sunday"]:
        sub = rd[rd.day_type == dtp].groupby(by)
        out[f"{dtp}_trips_median"] = sub.trips.median()
        out[f"{dtp}_revenue_hours_median"] = sub.revenue_hours.median()
    wk = rd[rd.day_type == "weekday"].groupby(by)
    out["weekday_span_h_median"] = wk.span_h.median()
    out["weekday_midday_headway_min_median"] = wk.midday_headway_min.median()
    out["weekday_evening_headway_min_median"] = wk.evening_headway_min.median()
    out["versions"] = rd.groupby(by).version.agg(lambda s: ";".join(sorted(set(s))))
    return out.reset_index()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--feed", default="mdb-1846")
    p.add_argument("--out", default="service_v1")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--end", default=None, help="last date (default: today)")
    args = p.parse_args(argv)

    out = DATA / "processed" / args.out
    if out.exists():
        raise SystemExit(f"{out} exists; processed stores are immutable, pick a new --out")
    index = pd.read_csv(RAW / "gtfs" / args.feed / "index.csv")
    index["downloaded_at"] = pd.to_datetime(index.downloaded_at, utc=True)
    index["path"] = index.file.map(lambda f: REPO / f)
    index["active"] = index.path.map(feed_active_dates)
    index["first_day"] = index.active.map(min)
    index["last_day"] = index.active.map(max)
    index["version"] = index.dataset_id

    end = dt.date.fromisoformat(args.end) if args.end else dt.date.today()
    chosen = choose_versions(index, index.first_day.min(), end)
    jobs = [
        (str(index.set_index("version").path[v]), v, list(chosen[chosen == v].index))
        for v in chosen.unique()
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        frames = list(pool.map(service_for_version, jobs))
    route_day = pd.concat(frames, ignore_index=True).sort_values(["date", "route"])

    out.mkdir(parents=True)
    used = chosen.groupby(chosen).agg(lambda s: f"{min(s.index)} to {max(s.index)} ({len(s)} days)")
    versions = index[["version", "downloaded_at", "first_day", "last_day", "sha256", "file"]].copy()
    versions["used_for"] = versions.version.map(used).fillna("not used")
    versions.to_csv(out / "versions.csv", index=False)
    route_day.to_parquet(out / "route_day.parquet", index=False)
    monthly(route_day).to_parquet(out / "route_month.parquet", index=False)
    meta = {
        **git_state(),
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feed": args.feed,
        "date_range": [str(chosen.index.min()), str(chosen.index.max())],
        "inputs": versions[["version", "sha256"]].to_dict("records"),
        "command": " ".join(["scripts/build_service_panel.py", *(argv or [])]),
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    print(
        f"wrote {out}: {len(route_day):,} route-days, {route_day.route.nunique()} routes, "
        f"{chosen.index.min()} to {chosen.index.max()}"
    )
    print(versions[["version", "first_day", "last_day", "used_for"]].to_string(index=False))


if __name__ == "__main__":
    main()
