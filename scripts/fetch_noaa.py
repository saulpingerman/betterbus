"""Download daily weather at Reagan National Airport from NOAA Climate Data Online.

Usage (from the repository root):
    uv run scripts/fetch_noaa.py [--start 2019-01-01]

Station GHCND:USW00013743. Elements: PRCP and SNOW (inches), SNWD (inches), TMAX and TMIN
(degrees F). The API allows one year per request and 1,000 rows per page, so the script walks
year by year. Writes data/raw/noaa/dca_daily.csv (long format: date, datatype, value,
attributes) and appends its sha256 to data/raw/noaa/manifest.jsonl. Needs NOAA_CDO_TOKEN in .env.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request

from betterbus.config import RAW, key

API = "https://www.ncei.noaa.gov/cdo-web/api/v2/data"
STATION = "GHCND:USW00013743"
ELEMENTS = ["PRCP", "SNOW", "SNWD", "TMAX", "TMIN"]
OUT = RAW / "noaa"


def get(params, token, tries=4):
    url = API + "?" + urllib.parse.urlencode(params, doseq=True)
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"token": token})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_year(start, end, token):
    rows, offset = [], 1
    while True:
        params = {
            "datasetid": "GHCND",
            "stationid": STATION,
            "datatypeid": ELEMENTS,
            "startdate": start.isoformat(),
            "enddate": end.isoformat(),
            "units": "standard",
            "limit": 1000,
            "offset": offset,
        }
        page = get(params, token)
        results = page.get("results", [])
        rows += results
        count = page.get("metadata", {}).get("resultset", {}).get("count", 0)
        offset += 1000
        time.sleep(0.25)  # the API allows five requests per second
        if offset > count or not results:
            return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--start", default="2019-01-01")
    args = p.parse_args(argv)
    token = key("NOAA_CDO_TOKEN")
    OUT.mkdir(parents=True, exist_ok=True)
    start, today = dt.date.fromisoformat(args.start), dt.date.today()
    rows = []
    for year in range(start.year, today.year + 1):
        a = max(start, dt.date(year, 1, 1))
        b = min(today, dt.date(year, 12, 31))
        got = fetch_year(a, b, token)
        print(f"{year}: {len(got)} rows")
        rows += got
    path = OUT / "dca_daily.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "datatype", "value", "attributes"])
        for r in sorted(rows, key=lambda r: (r["date"], r["datatype"])):
            w.writerow([r["date"][:10], r["datatype"], r["value"], r.get("attributes", "")])
    record = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_url": API,
        "station": STATION,
        "retrieved_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(OUT / "manifest.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
