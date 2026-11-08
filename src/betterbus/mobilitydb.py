"""Client for the Mobility Database API: list and download archived GTFS datasets.

Each dataset is saved as data/raw/gtfs/<feed_id>/<dataset_id>.zip, verified against the
catalog's SHA-256, and listed in data/raw/gtfs/<feed_id>/index.csv with its service dates.
"""

import csv
import hashlib
import json
import urllib.parse
import urllib.request

from betterbus.config import RAW, REPO, key

API = "https://api.mobilitydatabase.org/v1"


def access_token():
    """Exchange the refresh token in .env for a short-lived access token."""
    req = urllib.request.Request(
        f"{API}/tokens",
        method="POST",
        data=json.dumps({"refresh_token": key("MOBILITY_DB_REFRESH_TOKEN")}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["access_token"]


def api_get(path, token, **params):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def list_datasets(feed_id, token):
    """Every archived dataset of a GTFS feed, oldest download first."""
    out, offset = [], 0
    while True:
        page = api_get(f"/gtfs_feeds/{feed_id}/datasets", token, limit=100, offset=offset)
        out += page
        if len(page) < 100:
            return sorted(out, key=lambda d: d["downloaded_at"])
        offset += 100


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_feed(feed_id, token, dest_root=RAW / "gtfs"):
    """Download every dataset of `feed_id` not already present; write and return the index rows."""
    dest = dest_root / feed_id
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in list_datasets(feed_id, token):
        path = dest / f"{d['id']}.zip"
        if path.exists() and d.get("hash") and sha256(path) == d["hash"]:
            status = "cached"
        else:
            urllib.request.urlretrieve(d["hosted_url"], path)
            ok = not d.get("hash") or sha256(path) == d["hash"]
            status = "ok" if ok else "HASH MISMATCH"
        rows.append(
            {
                "dataset_id": d["id"],
                "downloaded_at": d["downloaded_at"],
                "service_start": d.get("service_date_range_start"),
                "service_end": d.get("service_date_range_end"),
                "sha256": d.get("hash"),
                "file": path.relative_to(REPO).as_posix(),
                "status": status,
            }
        )
    with open(dest / "index.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows
