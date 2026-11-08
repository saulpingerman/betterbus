"""Rank route families by rider-hours lost to slower schedules, and list the S2 hour transfers.

Usage (from the repository root):
    uv run scripts/rank_priority_corridors.py

For each family: scheduled speed before (May 2025) and after (October 2025), weekday riders
(after window, ten months, divided by weekdays-equivalent is not attempted; boardings are the
ten-month total), and the rider-minutes added per weekday by slower schedules, approximated as
boardings per weekday trip x weekday trips x (minutes per trip after - minutes per trip at the
pre-launch speed). Writes results/alternatives_v2/priority_corridors.csv and
s2_routes.csv (new route names and long names for the families that give or receive hours).
"""

import zipfile

import pandas as pd

from betterbus.config import DATA, RAW, REPO
from betterbus.panel import family_service_detail, route_boardings

OUT = REPO / "results" / "alternatives_v2"
FEED = RAW / "gtfs" / "mdb-1846" / "mdb-1846-202510160132.zip"


def main():
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    new = mem[mem.side == "new"]
    with zipfile.ZipFile(FEED) as z:
        names = (
            pd.read_csv(z.open("routes.txt"), dtype=str)
            .set_index("route_short_name")
            .route_long_name
        )
    sd = family_service_detail().set_index("family")
    rb = route_boardings()
    after = rb[(rb.side == "new") & (rb.month >= "2025-08-01") & (rb.month <= "2026-05-01")]
    after = after.merge(new, on="route").groupby("family").boardings.sum()
    df = sd.join(after.rename("boardings_after"))
    df["routes"] = new.groupby("family").route.apply(lambda s: " ".join(sorted(s)))
    df["names"] = new.groupby("family").route.apply(
        lambda s: "; ".join(names.get(r, r) for r in sorted(s))
    )
    mpt = df.miles_per_trip_post
    df["min_per_trip_post"] = mpt / df.speed_post * 60
    df["min_per_trip_at_pre_speed"] = mpt / df.speed_pre * 60
    per_weekday_riders = df.boardings_after / 210  # about 210 weekday-equivalents in ten months
    riders_per_trip = per_weekday_riders / df.trips_post
    df["extra_rider_minutes_per_weekday"] = (
        riders_per_trip * df.trips_post * (df.min_per_trip_post - df.min_per_trip_at_pre_speed)
    )
    df["speed_change_pct"] = (df.speed_post / df.speed_pre - 1) * 100
    cols = [
        "routes",
        "names",
        "speed_pre",
        "speed_post",
        "speed_change_pct",
        "boardings_after",
        "extra_rider_minutes_per_weekday",
    ]
    top = df.sort_values("extra_rider_minutes_per_weekday", ascending=False)[cols]
    top.round(3).to_csv(OUT / "priority_corridors.csv")
    s2 = pd.read_csv(OUT / "s2_reallocation.csv", index_col=0)
    s2 = s2.drop(columns=["midday_headway_pre"]).join(
        df[["routes", "names", "trips_post", "midday_headway_pre"]]
    )
    s2.round(3).sort_values("hours_change").to_csv(OUT / "s2_routes.csv")
    print(top.head(12).round(2).to_string())
    print(
        s2[["routes", "hours_change", "hours_ratio", "midday_headway_pre", "eea_share"]]
        .round(2)
        .to_string()
    )


if __name__ == "__main__":
    main()
