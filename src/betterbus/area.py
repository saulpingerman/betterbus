"""Place-level (H3 cell) ridership panel that holds geography fixed (ledger: area_panel_v1).

Route boardings are apportioned to the route's stops in proportion to a static demand weight
(residents plus jobs within 400 m of the stop), so the apportionment does not depend on how
often buses call. Stops are grouped into H3 resolution-8 cells.
"""

import zipfile

import h3
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from betterbus.access import jobs_by_block
from betterbus.config import RAW

EARTH_M = 6_371_000
RES = 8


def feed_stops(path):
    """stop_id, lat, lon and the set of routes serving each stop in one GTFS version."""
    with zipfile.ZipFile(path) as z:
        stops = pd.read_csv(z.open("stops.txt"), dtype={"stop_id": str})
        trips = pd.read_csv(z.open("trips.txt"), dtype=str, usecols=["route_id", "trip_id"])
        routes = pd.read_csv(
            z.open("routes.txt"), dtype=str, usecols=["route_id", "route_short_name"]
        )
        st = pd.read_csv(z.open("stop_times.txt"), dtype=str, usecols=["trip_id", "stop_id"])
    trips = trips.merge(routes, on="route_id")
    rs = st.merge(trips[["trip_id", "route_short_name"]], on="trip_id")
    rs = (
        rs[["route_short_name", "stop_id"]]
        .drop_duplicates()
        .rename(columns={"route_short_name": "route"})
    )
    return stops[["stop_id", "stop_lat", "stop_lon"]], rs


def stop_weights(stops, radius_m=400):
    """Residents (2020) plus jobs (LODES 2024) within radius_m of each stop."""
    b = pd.read_parquet(RAW / "tiger" / "tabblock20_points.parquet")
    b = b[b.STATEFP20.isin(["11", "24", "51"])].copy()
    b = b.join(jobs_by_block(), on="GEOID20").fillna({"jobs": 0})
    b["w"] = b.POP20 + b.jobs
    b = b[b.w > 0]
    pts = np.radians(b[["INTPTLAT20", "INTPTLON20"]].astype(float).to_numpy())
    tree = BallTree(pts, metric="haversine")
    q = np.radians(stops[["stop_lat", "stop_lon"]].to_numpy())
    idx = tree.query_radius(q, r=radius_m / EARTH_M)
    w = b.w.to_numpy()
    return pd.Series([w[i].sum() for i in idx], index=stops.stop_id.to_numpy())


def cell_of(lat, lon):
    return [h3.latlng_to_cell(a, b, RES) for a, b in zip(lat, lon, strict=True)]
