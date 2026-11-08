"""Download Geofabrik OpenStreetMap extracts for DC, Maryland and Virginia, pinned to one date.

Geofabrik redirects `<state>-latest.osm.pbf` to a dated file `<state>-YYMMDD.osm.pbf`. This script
resolves the redirect, saves the dated file under data/raw/osm/ together with the state's
replication `state.txt` (sequence number and data timestamp), and records both in
data/raw/osm/manifest.jsonl. The accessibility analysis must use one fixed snapshot, so pass
`--date YYMMDD` to fetch a specific dated file again (Geofabrik keeps dated files for a limited
time only).

Usage (from the repository root):
    uv run python scripts/fetch_osm.py               # newest snapshot
    uv run python scripts/fetch_osm.py --date 261106 # a given snapshot

Clip the three files to the study region with scripts/clip_osm.py.
"""

import argparse

from betterbus.config import RAW
from betterbus.download import SESSION, download

BASE = "https://download.geofabrik.de/north-america/us"
STATES = ["district-of-columbia", "maryland", "virginia"]
OUT = RAW / "osm"


def dated_url(state, date=None):
    if date:
        return f"{BASE}/{state}-{date}.osm.pbf"
    r = SESSION.head(f"{BASE}/{state}-latest.osm.pbf", allow_redirects=False, timeout=60)
    r.raise_for_status()
    loc = r.headers["Location"]
    return loc if loc.startswith("http") else f"{BASE}/{loc.rsplit('/', 1)[-1]}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="Geofabrik file date YYMMDD (default: newest)")
    args = ap.parse_args()
    for state in STATES:
        url = dated_url(state, args.date)
        name = url.rsplit("/", 1)[-1]
        print(f"{state}: {url}")
        download(url, OUT / name, timeout=600)
        if not args.date:
            download(
                f"{BASE}/{state}-updates/state.txt",
                OUT / name.replace(".osm.pbf", ".state.txt"),
            )


if __name__ == "__main__":
    main()
