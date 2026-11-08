"""Download every archived GTFS dataset for one or more Mobility Database feeds.

Usage (from the repository root):
    uv run scripts/fetch_mdb_gtfs.py mdb-1846 [mdb-1847 ...]

mdb-1846 is WMATA bus, mdb-1847 is WMATA rail. Re-running skips files already downloaded.
"""

import sys

from betterbus.mobilitydb import access_token, fetch_feed


def main(feed_ids):
    token = access_token()
    for fid in feed_ids:
        rows = fetch_feed(fid, token)
        bad = [r for r in rows if r["status"] == "HASH MISMATCH"]
        print(f"{fid}: {len(rows)} datasets, {len(bad)} hash mismatches")
        if bad:
            sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:] or ["mdb-1846"])
