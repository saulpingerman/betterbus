"""Scheduled bus service by route and day, computed from archived GTFS feeds.

`Feed` loads one GTFS zip into a per-trip table (route, service, first departure, last arrival,
scheduled minutes, shape miles). `daily_route_service` counts each route's trips, revenue
hours, revenue miles, span and headways on a given date. `choose_versions` decides which archived
feed version was in force on each date.

Definitions (scheduled, not delivered, service):
- revenue hours: sum over trips of last scheduled arrival minus first scheduled departure. This
  excludes layover and recovery time, so it is smaller than NTD vehicle revenue hours.
- revenue miles: length of the trip's shape, measured by haversine over the shape points (WMATA
  leaves shape_dist_traveled empty).
- midday headway: 300 minutes divided by the trips departing 10:00 to 15:00 in the busier
  direction; evening headway: 180 minutes over trips departing 19:00 to 22:00.
"""

import datetime as dt
import zipfile

import numpy as np
import pandas as pd

EARTH_MI = 3958.8


def _seconds(hms):
    """GTFS HH:MM:SS (hours may exceed 24) to seconds after midnight of the service day."""
    parts = hms.str.split(":", expand=True).astype(int)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def shape_miles(shapes):
    """Length in miles of each shape_id, by haversine over consecutive shape points."""
    sh = shapes.sort_values(["shape_id", "shape_pt_sequence"])
    lat = np.radians(sh.shape_pt_lat.to_numpy())
    lon = np.radians(sh.shape_pt_lon.to_numpy())
    ids = sh.shape_id.to_numpy()
    a = (
        np.sin((lat[1:] - lat[:-1]) / 2) ** 2
        + np.cos(lat[1:]) * np.cos(lat[:-1]) * np.sin((lon[1:] - lon[:-1]) / 2) ** 2
    )
    d = 2 * EARTH_MI * np.arcsin(np.sqrt(a))
    d[ids[1:] != ids[:-1]] = 0.0
    seg = pd.Series(np.concatenate([[0.0], d]), index=sh.index)
    return seg.groupby(sh.shape_id.to_numpy()).sum()


class Feed:
    """One GTFS feed version reduced to the tables the service measures need."""

    def __init__(self, path):
        self.path = path
        with zipfile.ZipFile(path) as z:

            def read(name, **kw):
                return pd.read_csv(z.open(name), dtype=str, **kw)

            self.routes = read("routes.txt")
            trips = read("trips.txt")
            cal = read("calendar.txt")
            self.calendar_dates = (
                read("calendar_dates.txt") if "calendar_dates.txt" in z.namelist() else None
            )
            shapes = pd.read_csv(z.open("shapes.txt"), dtype={"shape_id": str})
            st = read(
                "stop_times.txt",
                usecols=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
            )
        st["seq"] = st.stop_sequence.astype(int)
        st = st.sort_values(["trip_id", "seq"])
        g = st.groupby("trip_id", sort=False)
        first, last = g.head(1).set_index("trip_id"), g.tail(1).set_index("trip_id")
        tt = pd.DataFrame(
            {
                "start_s": _seconds(first.departure_time),
                "end_s": _seconds(last.arrival_time),
                "n_stops": g.size(),
            }
        )
        miles = shape_miles(shapes)
        trips = trips.set_index("trip_id").join(tt, how="inner")
        trips["miles"] = trips.shape_id.map(miles)
        trips["minutes"] = (trips.end_s - trips.start_s) / 60
        names = self.routes.set_index("route_id").route_short_name
        trips["route"] = trips.route_id.map(names).fillna(trips.route_id)
        self.trips = trips.reset_index()
        self.stop_routes = (
            st[["trip_id", "stop_id"]]
            .merge(self.trips[["trip_id", "route", "service_id"]], on="trip_id")[
                ["route", "service_id", "stop_id"]
            ]
            .drop_duplicates()
        )

        cal["start"] = pd.to_datetime(cal.start_date, format="%Y%m%d")
        cal["end"] = pd.to_datetime(cal.end_date, format="%Y%m%d")
        self.calendar = cal
        days = list(cal.start) + list(cal.end)
        if self.calendar_dates is not None and len(self.calendar_dates):
            self.calendar_dates["d"] = pd.to_datetime(self.calendar_dates.date, format="%Y%m%d")
            days += list(self.calendar_dates.d)
        self.first_day, self.last_day = min(days).date(), max(days).date()

    def services_on(self, date):
        """Service IDs active on `date` (calendar plus calendar_dates exceptions)."""
        ts = pd.Timestamp(date)
        dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][
            date.weekday()
        ]
        c = self.calendar
        active = set(c.service_id[(c.start <= ts) & (c.end >= ts) & (c[dow] == "1")])
        if self.calendar_dates is not None and len(self.calendar_dates):
            cd = self.calendar_dates[self.calendar_dates.d == ts]
            active |= set(cd.service_id[cd.exception_type == "1"])
            active -= set(cd.service_id[cd.exception_type == "2"])
        return active

    def daily_route_service(self, date):
        """Per-route scheduled service on `date`, or an empty frame if nothing runs."""
        services = self.services_on(date)
        t = self.trips[self.trips.service_id.isin(services)]
        if t.empty:
            return pd.DataFrame()
        g = t.groupby("route")
        out = pd.DataFrame(
            {
                "trips": g.size(),
                "revenue_hours": g.minutes.sum() / 60,
                "revenue_miles": g.miles.sum(),
                "first_departure_h": g.start_s.min() / 3600,
                "last_arrival_h": g.end_s.max() / 3600,
            }
        )
        out["span_h"] = out.last_arrival_h - out.first_departure_h
        for name, lo, hi in [("midday", 10, 15), ("evening", 19, 22)]:
            w = t[(t.start_s >= lo * 3600) & (t.start_s < hi * 3600)]
            peak_dir = w.groupby(["route", "direction_id"]).size().groupby("route").max()
            out[f"{name}_trips_peak_dir"] = peak_dir.reindex(out.index).fillna(0)
            out[f"{name}_headway_min"] = (
                (hi - lo) * 60 / out[f"{name}_trips_peak_dir"].replace(0, np.nan)
            )
        stops = self.stop_routes[self.stop_routes.service_id.isin(services)]
        out["stops_served"] = stops.groupby("route").stop_id.nunique().reindex(out.index)
        out.index.name = "route"
        return out.reset_index()


def active_dates(calendar, calendar_dates):
    """Dates on which at least one service_id runs, from calendar.txt and calendar_dates.txt."""
    cal = calendar.copy()
    cal["start"] = pd.to_datetime(cal.start_date, format="%Y%m%d")
    cal["end"] = pd.to_datetime(cal.end_date, format="%Y%m%d")
    dows = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    runs = {}  # date -> set of service_ids
    for row in cal.itertuples():
        for d in pd.date_range(row.start, row.end):
            if getattr(row, dows[d.weekday()]) == "1":
                runs.setdefault(d.date(), set()).add(row.service_id)
    if calendar_dates is not None:
        for row in calendar_dates.itertuples():
            d = pd.Timestamp(row.date).date()
            if row.exception_type == "1":
                runs.setdefault(d, set()).add(row.service_id)
            elif row.exception_type == "2":
                runs.get(d, set()).discard(row.service_id)
    return frozenset(d for d, s in runs.items() if s)


def choose_versions(versions, start, end):
    """For each date in [start, end], the feed version in force.

    `versions` is a DataFrame with columns version, downloaded_at (datetime) and active (the set
    of dates on which the version schedules any service, from `active_dates`). On each date the
    rule takes, among versions with service that day, the most recently downloaded one that was
    already published (downloaded on or before that date); if none was published yet, the
    earliest-downloaded one. Returns a Series indexed by date.
    """
    v = versions.sort_values("downloaded_at")
    out = {}
    day = start
    while day <= end:
        cover = v[v.active.map(lambda s, d=day: d in s)]
        if len(cover):
            published = cover[cover.downloaded_at.dt.date <= day]
            pick = published.iloc[-1] if len(published) else cover.iloc[0]
            out[day] = pick.version
        day += dt.timedelta(days=1)
    return pd.Series(out, name="version")
