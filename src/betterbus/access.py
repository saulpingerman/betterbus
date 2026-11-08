"""Inputs for the transit job-accessibility analysis: block-group points, people and jobs.

Each block group is represented by one point: the population-weighted mean of its 2020 census
block internal points; block groups with no residents use the job-weighted mean, and those with
neither use the plain mean. Jobs are LODES 8 workplace counts (WAC, all jobs JT00, segment S000)
summed from blocks to block groups (block-group GEOID = first 12 digits of the block GEOID;
LODES 8 uses 2020 blocks, and 2020 and 2024 block-group GEOIDs are identical in DC, MD and VA).
"""

import geopandas as gpd
import pandas as pd

from betterbus.config import RAW

COMPACT = ["11001", "24031", "24033", "51013", "51059", "51107", "51510", "51600", "51610"]
BUFFER = ["24027", "24003", "24017", "24021", "51153", "51683", "51685"]
STATES = {"11": "dc", "24": "md", "51": "va"}


def jobs_by_block(year=2024):
    """LODES WAC jobs per 2020 block: total (C000) and earning $1,250/month or less (CE01)."""
    frames = []
    for abbr in STATES.values():
        path = RAW / "lodes" / abbr / "wac" / f"{abbr}_wac_S000_JT00_{year}.csv.gz"
        w = pd.read_csv(path, usecols=["w_geocode", "C000", "CE01"], dtype={"w_geocode": str})
        frames.append(w)
    w = pd.concat(frames).rename(
        columns={"w_geocode": "block", "C000": "jobs", "CE01": "jobs_low_wage"}
    )
    return w.groupby("block")[["jobs", "jobs_low_wage"]].sum()


def block_group_points(counties=COMPACT + BUFFER, year=2024):
    """Block groups in `counties` as points (EPSG:4326): id, pop20, jobs, jobs_low_wage."""
    b = pd.read_parquet(RAW / "tiger" / "tabblock20_points.parquet")
    b = b[(b.STATEFP20 + b.COUNTYFP20).isin(counties)].copy()
    b["lat"], b["lon"] = b.INTPTLAT20.astype(float), b.INTPTLON20.astype(float)
    b = b.join(jobs_by_block(year), on="GEOID20").fillna({"jobs": 0, "jobs_low_wage": 0})
    b["bg"] = b.GEOID20.str[:12]

    def weighted(group):
        for weight in ("POP20", "jobs"):
            w = group[weight]
            if w.sum() > 0:
                return pd.Series(
                    {"lat": (group.lat * w).sum() / w.sum(), "lon": (group.lon * w).sum() / w.sum()}
                )
        return pd.Series({"lat": group.lat.mean(), "lon": group.lon.mean()})

    pts = b.groupby("bg")[["lat", "lon", "POP20", "jobs"]].apply(weighted)
    tot = b.groupby("bg")[["POP20", "jobs", "jobs_low_wage"]].sum()
    df = pts.join(tot).reset_index().rename(columns={"bg": "id", "POP20": "pop20"})
    df["county"] = df.id.str[:5]
    df["compact"] = df.county.isin(COMPACT)
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.lon, df.lat), crs="EPSG:4326")
