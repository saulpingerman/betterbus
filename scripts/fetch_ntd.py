"""Download the NTD "Complete Monthly Ridership (with Adjustments and Estimates)" file.

Usage (from the repository root):
    uv run scripts/fetch_ntd.py

Saves the full national file (every agency, mode and type of service, January 2002 onward:
unlinked passenger trips, vehicle revenue hours and miles, vehicles in maximum service) from
data.transportation.gov dataset 8bui-9xvu to data/raw/ntd/, named by the dataset's last update
date, with its sha256 in data/raw/ntd/manifest.jsonl. WMATA is NTD ID 30030.
"""

import datetime as dt
import hashlib
import json
import urllib.request

from betterbus.config import RAW

DATASET = "8bui-9xvu"
META_URL = f"https://data.transportation.gov/api/views/{DATASET}.json"
CSV_URL = f"https://data.transportation.gov/api/views/{DATASET}/rows.csv?accessType=DOWNLOAD"
OUT = RAW / "ntd"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(META_URL, timeout=60) as resp:
        meta = json.load(resp)
    updated = dt.datetime.fromtimestamp(meta["rowsUpdatedAt"], dt.UTC)
    path = OUT / f"ntd_monthly_adjusted_{updated:%Y%m%d}.csv"
    if not path.exists():
        urllib.request.urlretrieve(CSV_URL, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest,
        "source_url": CSV_URL,
        "dataset_updated": updated.isoformat(),
        "retrieved_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(OUT / "manifest.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
