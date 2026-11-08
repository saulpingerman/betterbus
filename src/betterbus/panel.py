"""Family-by-month ridership panel joined to each family's change in scheduled service.

Ridership is WMATA's APC Metrobus boardings by route and month (Ridership Data Portal). Routes
are assigned to route families (data/processed/families_v*/membership.csv): pre-launch routes
("Former Routes" in the portal, through June 2025) by their old-side membership and launched
routes ("Current Metro Bus Routes", from July 2025) by their new-side membership. Family
boardings are the sum over member routes, so riders moving between routes of one family net out.

Treatment intensity is each family's log change in median weekday scheduled trips (and revenue
hours) between a pre-launch month (old members) and a post-launch month (new members), from the
service panel (data/processed/service_v*/route_month.parquet).
"""

import numpy as np
import pandas as pd

from betterbus.config import DATA, RAW

NETWORK_SIDE = {"Former Routes": "old", "Current Metro Bus Routes": "new"}


def route_boardings(service_type="Monthly Total"):
    """Portal boardings by side, route and month (duplicate keys averaged, Route None dropped)."""
    b = pd.read_csv(
        RAW / "wmata_ridership" / "bus_route_month.csv", dtype={"Route": str, "Yearmo": str}
    )
    b = b[(b["Service Type"] == service_type) & b.Route.notna() & (b.Route != "None")]
    b = b.assign(side=b.Network.map(NETWORK_SIDE), month=pd.to_datetime(b.Yearmo, format="%Y%m"))
    b = b.rename(columns={"Route": "route", "Monthly Boardings": "boardings", "Num Dates": "days"})
    return b.groupby(["side", "route", "month"], as_index=False)[["boardings", "days"]].mean()


def family_service_change(
    families="families_v1", service="service_v1", pre="2025-05", post="2025-10"
):
    """Per family: weekday trips and revenue hours before and after, and their log changes."""
    mem = pd.read_csv(DATA / "processed" / families / "membership.csv")
    rm = pd.read_parquet(DATA / "processed" / service / "route_month.parquet")
    rm["ym"] = rm.month.dt.strftime("%Y-%m")
    cols = ["weekday_trips_median", "weekday_revenue_hours_median"]
    before = mem[mem.side == "old"].merge(
        rm[rm.ym == pre][["route", *cols]], on="route", how="left"
    )
    after = mem[mem.side == "new"].merge(
        rm[rm.ym == post][["route", *cols]], on="route", how="left"
    )
    out = pd.DataFrame(
        {
            "trips_pre": before.groupby("family").weekday_trips_median.sum(min_count=1),
            "hours_pre": before.groupby("family").weekday_revenue_hours_median.sum(min_count=1),
            "trips_post": after.groupby("family").weekday_trips_median.sum(min_count=1),
            "hours_post": after.groupby("family").weekday_revenue_hours_median.sum(min_count=1),
        }
    )
    out["dlog_trips"] = np.log(out.trips_post / out.trips_pre)
    out["dlog_hours"] = np.log(out.hours_post / out.hours_pre)
    return out.reset_index()


def family_month(families="families_v1", start="2023-01-01", end=None):
    """Family x month boardings; also returns the share of boardings on routes in no family."""
    mem = pd.read_csv(DATA / "processed" / families / "membership.csv")
    rb = route_boardings()
    rb = rb[rb.month >= start]
    if end:
        rb = rb[rb.month <= end]
    rb = rb.merge(mem, on=["side", "route"], how="left")
    unmatched = (
        rb[rb.family.isna()].groupby("month").boardings.sum() / rb.groupby("month").boardings.sum()
    )
    fm = rb.dropna(subset=["family"]).groupby(["family", "month"], as_index=False).boardings.sum()
    return fm, unmatched.fillna(0)


def family_service_detail(
    families="families_v1", service="service_v1", pre="2025-05", post="2025-10"
):
    """Per family: weekday trips, hours, miles, speed, miles per trip and midday headway, before
    (old members, month `pre`) and after (new members, month `post`), with log changes.

    Route values are medians over the month's weekdays; family values are sums over members
    (midday headway = 300 minutes over the summed peak-direction midday trips).
    """
    mem = pd.read_csv(DATA / "processed" / families / "membership.csv")
    rd = pd.read_parquet(DATA / "processed" / service / "route_day.parquet")
    rd = rd[rd.day_type == "weekday"].assign(ym=rd.date.dt.strftime("%Y-%m"))
    cols = ["trips", "revenue_hours", "revenue_miles", "midday_trips_peak_dir"]
    med = rd.groupby(["ym", "route"])[cols].median().reset_index()
    parts = {}
    for label, side, ym in [("pre", "old", pre), ("post", "new", post)]:
        m = mem[mem.side == side].merge(med[med.ym == ym], on="route", how="left")
        parts[label] = m.groupby("family")[cols].sum(min_count=1)
    out = parts["pre"].add_suffix("_pre").join(parts["post"].add_suffix("_post"), how="outer")
    for s in ("pre", "post"):
        out[f"speed_{s}"] = out[f"revenue_miles_{s}"] / out[f"revenue_hours_{s}"]
        out[f"miles_per_trip_{s}"] = out[f"revenue_miles_{s}"] / out[f"trips_{s}"]
        out[f"midday_headway_{s}"] = 300 / out[f"midday_trips_peak_dir_{s}"].replace(0, np.nan)
    out["D_trips"] = np.log(out.trips_post / out.trips_pre)
    out["D_hours"] = np.log(out.revenue_hours_post / out.revenue_hours_pre)
    out["D_speed"] = np.log(out.speed_post / out.speed_pre)
    out["D_length"] = np.log(out.miles_per_trip_post / out.miles_per_trip_pre)
    return out.reset_index()
