"""Write scenario versions of a GTFS feed: faster schedules and more or fewer trips per route.

`edit_feed(src, dst, time_scale, freq_ratio)`:
- time_scale[route] < 1 compresses each trip's stop times toward its first departure (a trip that
  took 40 minutes takes 40 x factor minutes); the first departure is unchanged.
- freq_ratio[route] > 1 adds trips: within each route, direction and service_id, trips are sorted
  by first departure and copies are inserted at the midpoint between consecutive departures,
  spread evenly through the day, until the trip count reaches round(n x ratio) (at most double).
  freq_ratio[route] < 1 drops trips evenly through the day.
Routes are matched on route_short_name. Other files are copied unchanged.
"""

import io
import zipfile

import numpy as np
import pandas as pd


def _to_s(hms):
    p = hms.str.split(":", expand=True).astype(int)
    return p[0] * 3600 + p[1] * 60 + p[2]


def _to_hms(sec):
    sec = sec.round().astype(int)
    return (
        (sec // 3600).astype(str).str.zfill(2)
        + ":"
        + ((sec % 3600) // 60).astype(str).str.zfill(2)
        + ":"
        + (sec % 60).astype(str).str.zfill(2)
    )


def edit_feed(src, dst, time_scale=None, freq_ratio=None):
    time_scale, freq_ratio = time_scale or {}, freq_ratio or {}
    with zipfile.ZipFile(src) as z:
        files = {n: z.read(n) for n in z.namelist()}
    routes = pd.read_csv(io.BytesIO(files["routes.txt"]), dtype=str)
    trips = pd.read_csv(io.BytesIO(files["trips.txt"]), dtype=str)
    st = pd.read_csv(io.BytesIO(files["stop_times.txt"]), dtype=str)
    name = routes.set_index("route_id").route_short_name
    trips["route"] = trips.route_id.map(name)
    st["arr"], st["dep"] = _to_s(st.arrival_time), _to_s(st.departure_time)
    st["seq"] = st.stop_sequence.astype(int)
    first = st.sort_values("seq").groupby("trip_id").dep.first()
    st["t0"] = st.trip_id.map(first)

    scale = st.trip_id.map(trips.set_index("trip_id").route.map(time_scale)).fillna(1.0)
    st["arr"] = st.t0 + (st.arr - st.t0) * scale
    st["dep"] = st.t0 + (st.dep - st.t0) * scale

    trips["start"] = trips.trip_id.map(first)
    new_trips, new_st, drop = [], [], set()
    for (route, _, _), g in trips.groupby(["route", "direction_id", "service_id"], dropna=False):
        r = freq_ratio.get(route, 1.0)
        if r == 1.0 or len(g) < 2:
            continue
        g = g.sort_values("start")
        n = len(g)
        target = int(round(n * min(r, 2.0)))
        if target < n:
            keep = set(g.trip_id.iloc[np.round(np.linspace(0, n - 1, target)).astype(int)])
            drop |= set(g.trip_id) - keep
            continue
        k = target - n
        gaps = np.round(np.linspace(0, n - 2, k)).astype(int) if k else []
        for i, j in enumerate(gaps):
            a, b = g.iloc[j], g.iloc[j + 1]
            offset = (b.start - a.start) / 2
            new_id = f"{a.trip_id}_x{i}"
            new_trips.append(a.drop(["start"]).to_dict() | {"trip_id": new_id})
            s = st[st.trip_id == a.trip_id].copy()
            s["trip_id"], s["arr"], s["dep"] = new_id, s.arr + offset, s.dep + offset
            new_st.append(s)
    trips = trips[~trips.trip_id.isin(drop)].drop(columns=["start"])
    st = st[~st.trip_id.isin(drop)]
    if new_trips:
        trips = pd.concat([trips, pd.DataFrame(new_trips)], ignore_index=True)
        st = pd.concat([st, *new_st], ignore_index=True)
    st["arrival_time"], st["departure_time"] = _to_hms(st.arr), _to_hms(st.dep)
    st = st.drop(columns=["arr", "dep", "seq", "t0"])
    files["trips.txt"] = trips.drop(columns=["route"]).to_csv(index=False).encode()
    files["stop_times.txt"] = st.to_csv(index=False).encode()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items():
            z.writestr(n, b)
    return {"trips_added": len(new_trips), "trips_dropped": len(drop)}
