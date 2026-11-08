"""Download Census TIGER/Line and cartographic boundary files for DC, Maryland and Virginia.

Saved under data/raw/tiger/ (zipped shapefiles, unchanged):
  tl_2020_<fips>_bg.zip, tl_2020_<fips>_tract.zip     2020 TIGER/Line (matches LODES 8 blocks)
  tl_2020_<fips>_tabblock20.zip                       2020 blocks, with INTPTLAT20/INTPTLON20
  tl_2024_<fips>_bg.zip, tl_2024_<fips>_tract.zip     2024 TIGER/Line (geography of ACS 2020-2024)
  cb_2024_<fips>_bg_500k.zip, cb_2024_<fips>_tract_500k.zip
                                                      2024 cartographic boundaries (shoreline
                                                      clipped, generalized; for maps)

It then writes tabblock20_points.parquet: one row per 2020 block in the three states with
GEOID20, STATEFP20, COUNTYFP20, INTPTLAT20, INTPTLON20, ALAND20, AWATER20, POP20, HOUSING20
(no polygons). These points can serve as r5py origins/destinations for LODES block counts.

Usage (from the repository root):
    uv run python scripts/fetch_tiger.py
Re-running skips files already present.
"""

import geopandas as gpd
import pandas as pd

from betterbus.config import RAW
from betterbus.download import download, record

BASE = "https://www2.census.gov/geo/tiger"
STATES = ["11", "24", "51"]
OUT = RAW / "tiger"


def files(fips):
    return [
        f"TIGER2020/BG/tl_2020_{fips}_bg.zip",
        f"TIGER2020/TRACT/tl_2020_{fips}_tract.zip",
        f"TIGER2020/TABBLOCK20/tl_2020_{fips}_tabblock20.zip",
        f"TIGER2024/BG/tl_2024_{fips}_bg.zip",
        f"TIGER2024/TRACT/tl_2024_{fips}_tract.zip",
        f"GENZ2024/shp/cb_2024_{fips}_bg_500k.zip",
        f"GENZ2024/shp/cb_2024_{fips}_tract_500k.zip",
    ]


def block_points():
    dest = OUT / "tabblock20_points.parquet"
    if dest.exists():
        return
    cols = [
        "GEOID20",
        "STATEFP20",
        "COUNTYFP20",
        "INTPTLAT20",
        "INTPTLON20",
        "ALAND20",
        "AWATER20",
        "POP20",
        "HOUSING20",
    ]
    parts = []
    for fips in STATES:
        df = gpd.read_file(
            OUT / f"tl_2020_{fips}_tabblock20.zip", columns=cols, ignore_geometry=True
        )
        df["INTPTLAT20"] = df["INTPTLAT20"].astype(float)
        df["INTPTLON20"] = df["INTPTLON20"].astype(float)
        parts.append(df)
    pd.concat(parts, ignore_index=True).to_parquet(dest, index=False)
    record(dest, "derived from tl_2020_{11,24,51}_tabblock20.zip")


def main():
    for fips in STATES:
        for f in files(fips):
            dest = OUT / f.rsplit("/", 1)[-1]
            download(f"{BASE}/{f}", dest, timeout=600)
            print(f, "ok" if dest.exists() else "missing on server")
    block_points()


if __name__ == "__main__":
    main()
