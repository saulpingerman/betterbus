"""Choose and download the archived GTFS feed in force on each reference date for every non-WMATA
operator in the study region, and write the regional bundle definition.

Usage (from the repository root):
    uv run python scripts/fetch_regional_gtfs.py [--only mdb-477,tld-61]

Selection rule, per operator and reference date D (pre = 2025-05-14, post = 2025-10-22):
  1. Pool the datasets of every Mobility Database feed record listed for the operator (an operator
     can have an old, deprecated record and a current one).
  2. Walk the datasets downloaded on or before D, latest first. The first one whose own
     calendar.txt and calendar_dates.txt give at least one service_id active on D is chosen.
  3. If none qualifies, walk the datasets downloaded after D, earliest first, and take the first
     one active on D (noted as "downloaded after date"). The same happens when the dataset found
     in step 2 was downloaded more than MAX_AGE days before D: some feeds carry perpetual
     calendars (for example 2000 to 2099), so an old file can look active on D long after its
     network was replaced. If no later dataset is active on D, the old one is kept, noted STALE.
  4. If still none, the date is a gap: the inspected dataset whose nearest active date is closest
     to D is recorded with the gap in days, but no file is attached in the bundle.
  The catalog's service range is not used to skip candidates: for some feeds it is far narrower
  than the file (Frederick TransIT datasets of October 2025 are listed as ending 2025-05-27 but
  their calendar.txt runs to 2026-12-31), so every candidate is downloaded and checked in the file.

Chosen datasets are saved as data/raw/gtfs/<feed_id>/<dataset_id>.zip, verified against the
catalog SHA-256 and appended to data/raw/gtfs/<feed_id>/index.csv (the columns written by
fetch_mdb_gtfs.py). Candidates inspected but not chosen are deleted. Output:
data/processed/regional_bundle_v1/bundle.csv (one row per operator and date) and checks.csv
(per chosen file: required files present, share of stops inside the study bounding box).
"""

import argparse
import csv
import io
import shutil
import tempfile
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from betterbus.config import DATA, RAW, REPO
from betterbus.mobilitydb import access_token, api_get, list_datasets, sha256

DATES = {"pre": date(2025, 5, 14), "post": date(2025, 10, 22)}
BBOX = (-78.062, 38.071, -76.249, 39.820)  # west, south, east, north; same as scripts/clip_osm.py
MAX_INSPECT = 12  # downloads per direction (before / after D) per operator and date
MAX_AGE = 365  # days; an earlier dataset older than this yields to a later one active on D
OUT = DATA / "processed" / "regional_bundle_v1"
INDEX_FIELDS = [
    "dataset_id",
    "downloaded_at",
    "service_start",
    "service_end",
    "sha256",
    "file",
    "status",
]

# (operator, Mobility Database feed ids pooled for it). WMATA (mdb-1846, mdb-1847) is handled
# elsewhere. Excluded on purpose: intercity carriers (Amtrak mdb-11, mdb-2297; Megabus mdb-2321;
# Flixbus mdb-593; Peter Pan mdb-496; Coach USA tld-5741; Trailways ntd-20177; Virginia Breeze
# mdb-1328, mdb-3506), GTFS-Flex demand-response feeds that r5py cannot route (ART mdb-2434,
# Loudoun mdb-2411, Virginia Regional Transit mdb-2445, Bay Transit mdb-2439, City of Alexandria
# mdb-2936), and feeds with no stop inside the bounding box (WinTran mdb-608, Cecil Transit,
# Shore Transit, Delaware and Richmond-area operators).
OPERATORS = [
    ("Prince George's County TheBus", ["mdb-477"]),
    ("Montgomery County Ride On", ["mdb-488"]),
    ("Fairfax Connector", ["mdb-483"]),
    ("Alexandria DASH", ["mdb-482"]),
    ("Arlington Transit ART", ["mdb-485"]),
    ("Fairfax City CUE", ["mdb-2885", "mdb-2862", "mdb-2609", "mdb-484"]),
    ("Loudoun County Transit", ["mdb-1053"]),
    ("OmniRide (PRTC)", ["mdb-1156", "mdb-481"]),
    ("MTA Maryland Local Bus", ["mdb-466"]),
    ("MTA Maryland Commuter Bus", ["mdb-467"]),
    ("MTA Maryland MARC Train", ["mdb-468"]),
    ("MTA Maryland Light Rail", ["mdb-469"]),
    ("MTA Maryland Metro Subway", ["mdb-470"]),
    ("Virginia Railway Express", ["tld-61", "mdb-478"]),
    ("DC Streetcar", ["mdb-2223", "mdb-487"]),
    ("DC Circulator", ["mdb-486"]),
    ("Bethesda Circulator", ["mdb-231"]),
    ("Howard County RTA of Central Maryland", ["mdb-489"]),
    ("Charles County VanGO", ["mdb-479"]),
    ("Frederick County TransIT", ["mdb-2432", "mdb-498"]),
    ("Annapolis Transit", ["mdb-2285", "mdb-491"]),
    ("Anne Arundel County Transit", ["ntd-30129"]),
    ("Charm City Circulator", ["tld-288_1", "ntd-30201", "mdb-493"]),
    ("Harbor Connector", ["mdb-618"]),
    ("Baltimore Water Taxi", ["tld-984"]),
    ("Towson Loop", ["mdb-1784"]),
    ("BWI Airport Shuttle", ["mdb-490"]),
    ("Fredericksburg Regional Transit", ["mdb-3433", "mdb-2430", "mdb-1299"]),
    ("Virginia Regional Transit", ["mdb-621"]),
    ("Washington County Transit", ["mdb-2286", "mdb-497"]),
    ("Eastern Panhandle Transit Authority", ["tld-4459"]),
    ("Harpers Ferry NHP Shuttle", ["tld-6678"]),
    ("Calvert County Public Transportation", ["mdb-480"]),
    ("St. Mary's Transit System", ["mdb-2268", "mdb-1203", "mdb-476"]),
    ("Carroll Transit System", ["mdb-500"]),
    ("Harford Transit LINK", ["mdb-501"]),
    ("Queen Anne's County Ride", ["mdb-492"]),
    ("Bay Transit", ["mdb-224"]),
    ("rabbittransit", ["tld-223", "mdb-499"]),
]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def read_table(zf, name):
    """Rows of `name` in the zip (searched at any folder depth) as dicts, or None if absent."""
    hits = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == name]
    if not hits:
        return None
    with zf.open(hits[0]) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace")
        return [
            {k.strip(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(text)
        ]


def parse_day(s):
    return datetime.strptime(s, "%Y%m%d").date()


def active_dates(zf, lo=date(2010, 1, 1), hi=date(2028, 12, 31)):
    """Map service_id -> set of dates it runs, within [lo, hi], from calendar and calendar_dates."""
    out = {}
    for r in read_table(zf, "calendar.txt") or []:
        try:
            start, end = max(parse_day(r["start_date"]), lo), min(parse_day(r["end_date"]), hi)
        except (KeyError, ValueError):
            continue
        days = {i for i, w in enumerate(WEEKDAYS) if r.get(w) == "1"}
        s = out.setdefault(r["service_id"], set())
        d = start
        while d <= end:
            if d.weekday() in days:
                s.add(d)
            d += timedelta(days=1)
    for r in read_table(zf, "calendar_dates.txt") or []:
        try:
            d = parse_day(r["date"])
        except (KeyError, ValueError):
            continue
        s = out.setdefault(r["service_id"], set())
        if r.get("exception_type") == "1":
            s.add(d)
        elif r.get("exception_type") == "2":
            s.discard(d)
    return out


def inspect(path, day):
    """Service counts on `day` and the nearest active date in the file."""
    with zipfile.ZipFile(path) as zf:
        svc = active_dates(zf)
        on = {sid for sid, ds in svc.items() if day in ds}
        trips = read_table(zf, "trips.txt") or []
    run = [t for t in trips if t.get("service_id") in on]
    every = set().union(*svc.values()) if svc else set()
    nearest = min(every, key=lambda d: abs((d - day).days)) if every else None
    return {
        "services": len(on),
        "trips": len(run),
        "routes": len({t.get("route_id") for t in run}),
        "nearest": nearest,
    }


def sanity(path):
    """Required files and the share of physical stops inside BBOX."""
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        names = {n.rsplit("/", 1)[-1] for n in zf.namelist()}
        missing = [n for n in ("stops.txt", "stop_times.txt", "trips.txt") if n not in names]
        n_st = 0
        if "stop_times.txt" not in missing:
            with zf.open([n for n in zf.namelist() if n.endswith("stop_times.txt")][0]) as f:
                n_st = sum(1 for _ in f) - 1
        stops = read_table(zf, "stops.txt") or []
    pts = []
    for s in stops:
        if s.get("location_type", "") not in ("", "0"):
            continue
        try:
            pts.append((float(s["stop_lon"]), float(s["stop_lat"])))
        except (KeyError, ValueError):
            pass
    inside = sum(BBOX[0] <= x <= BBOX[2] and BBOX[1] <= y <= BBOX[3] for x, y in pts)
    return {
        "zip_ok": bad is None,
        "missing": ";".join(missing),
        "stops": len(pts),
        "stops_in_bbox": inside,
        "share_in_bbox": round(inside / len(pts), 3) if pts else 0.0,
        "stop_times_rows": n_st,
    }


class Fetcher:
    """Downloads candidates once per run; keeps chosen files, deletes the rest at the end."""

    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.paths = {}

    def get(self, d):
        if d["id"] in self.paths:
            return self.paths[d["id"]]
        final = RAW / "gtfs" / d["feed_id"] / f"{d['id']}.zip"
        if final.exists() and (not d.get("hash") or sha256(final) == d["hash"]):
            self.paths[d["id"]] = final
            return final
        path = self.tmp / f"{d['id']}.zip"
        urllib.request.urlretrieve(d["hosted_url"], path)
        if d.get("hash") and sha256(path) != d["hash"]:
            raise RuntimeError(f"{d['id']}: SHA-256 does not match the catalog")
        self.paths[d["id"]] = path
        return path

    def keep(self, d):
        """Move a chosen dataset into data/raw/gtfs/<feed_id>/ and append it to index.csv."""
        dest = RAW / "gtfs" / d["feed_id"]
        dest.mkdir(parents=True, exist_ok=True)
        final = dest / f"{d['id']}.zip"
        src = self.paths[d["id"]]
        status = "cached" if src == final else "ok"
        if src != final:
            shutil.move(src, final)
            self.paths[d["id"]] = final
        index = dest / "index.csv"
        rows = list(csv.DictReader(open(index))) if index.exists() else []
        if not any(r["dataset_id"] == d["id"] for r in rows):
            rows.append(
                {
                    "dataset_id": d["id"],
                    "downloaded_at": d["downloaded_at"],
                    "service_start": d.get("service_date_range_start"),
                    "service_end": d.get("service_date_range_end"),
                    "sha256": d.get("hash"),
                    "file": final.relative_to(REPO).as_posix(),
                    "status": status,
                }
            )
            with open(index, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
                w.writeheader()
                w.writerows(rows)
        return final


def choose(datasets, day, fetch):
    """Apply the selection rule; return (dataset, inspection, note, chosen)."""
    before = [d for d in datasets if date.fromisoformat(d["downloaded_at"][:10]) <= day][::-1]
    after = [d for d in datasets if date.fromisoformat(d["downloaded_at"][:10]) > day]
    seen, stale = [], None
    for direction, pool in (("before", before), ("after", after)):
        for d in pool[:MAX_INSPECT]:
            info = inspect(fetch.get(d), day)
            seen.append((d, info))
            if info["services"] == 0:
                continue
            age = (day - date.fromisoformat(d["downloaded_at"][:10])).days
            if direction == "before" and age > MAX_AGE:
                stale = (d, info, age)  # perpetual calendars make old files look active; look later
                break
            if direction == "before":
                return d, info, "", True
            if stale:
                note = (
                    "downloaded after date; the latest earlier dataset active on the date,"
                    f" {stale[0]['id']},"
                    f" was downloaded {stale[2]} days before it and is treated as superseded"
                )
            else:
                note = "downloaded after date; no earlier dataset is active on it"
            return d, info, note, True
    if stale:
        d, info, age = stale
        return (
            d,
            info,
            f"STALE: downloaded {age} days before date and no later dataset is active on it",
            True,
        )
    # Gap: distance to the nearest active date, from the file if inspected, else the catalog range.
    gaps = {}
    for d in datasets:
        s, e = d.get("service_date_range_start"), d.get("service_date_range_end")
        if s and e:
            s, e = date.fromisoformat(s[:10]), date.fromisoformat(e[:10])
            gaps[d["id"]] = (
                min(abs((s - day).days), abs((e - day).days)),
                d,
                "catalog service range",
            )
    for d, info in seen:
        if info["nearest"]:
            gaps[d["id"]] = (abs((info["nearest"] - day).days), d, "nearest active date in file")
    if not datasets:
        return None, None, "GAP: the feed record has no archived dataset", False
    if not gaps:
        return None, None, "GAP: no archived dataset has service dates in 2010 to 2028", False
    gap, d, how = min(gaps.values(), key=lambda g: (g[0], g[1]["downloaded_at"]))
    return (
        d,
        None,
        "GAP: no archived dataset is active on this date;"
        f" nearest {d['id']} ({how}), {gap} days away",
        False,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated feed ids; restrict to operators using them")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    token = access_token()
    OUT.mkdir(parents=True, exist_ok=True)
    bundle, checks = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        fetch = Fetcher(tmp)
        for operator, feed_ids in OPERATORS:
            if only and not only & set(feed_ids):
                continue
            datasets, status = [], {}
            for fid in feed_ids:
                status[fid] = api_get(f"/gtfs_feeds/{fid}", token)["status"]
                for d in list_datasets(fid, token):
                    d["feed_id"] = fid
                    datasets.append(d)
            datasets.sort(key=lambda d: d["downloaded_at"])
            for label, day in DATES.items():
                d, info, note, ok = choose(datasets, day, fetch)
                row = {
                    "date_label": label,
                    "date": day.isoformat(),
                    "operator": operator,
                    "feed_id": d["feed_id"] if d else "",
                    "dataset_id": d["id"] if d else "",
                    "file": "",
                    "active_services_on_date": info["services"] if info else 0,
                    "trips_on_date": info["trips"] if info else 0,
                    "routes_on_date": info["routes"] if info else 0,
                    "note": note,
                }
                if ok and status[d["feed_id"]] != "active":
                    if d is [x for x in datasets if x["feed_id"] == d["feed_id"]][-1]:
                        last = (
                            f"last archived dataset of {d['feed_id']},"
                            f" a feed now marked {status[d['feed_id']]};"
                            " the archive cannot confirm the file was still current on the date"
                        )
                        row["note"] = "; ".join(x for x in (row["note"], last) if x)
                if ok:
                    final = fetch.keep(d)
                    row["file"] = final.relative_to(REPO).as_posix()
                    if d["id"] not in checks:
                        checks[d["id"]] = {
                            "dataset_id": d["id"],
                            "file": row["file"],
                            **sanity(final),
                        }
                    c = checks[d["id"]]
                    if not c["zip_ok"] or c["missing"] or c["share_in_bbox"] < 0.5:
                        defect = (
                            f"check: zip_ok={c['zip_ok']} missing={c['missing'] or 'none'}"
                            f" share_in_bbox={c['share_in_bbox']}"
                        )
                        row["note"] = "; ".join(x for x in (row["note"], defect) if x)
                print(
                    f"{label} {operator}: {row['dataset_id']}"
                    f" trips={row['trips_on_date']} {row['note']}"
                )
                bundle.append(row)
    if only:  # merge into the existing bundle instead of replacing it
        old = OUT / "bundle.csv"
        done = {(r["date_label"], r["operator"]) for r in bundle}
        prior = (
            [r for r in csv.DictReader(open(old)) if (r["date_label"], r["operator"]) not in done]
            if old.exists()
            else []
        )
        bundle = prior + bundle
        oldc = OUT / "checks.csv"
        if oldc.exists():
            for r in csv.DictReader(open(oldc)):
                checks.setdefault(r["dataset_id"], r)
    order = {op: i for i, (op, _) in enumerate(OPERATORS)}
    bundle.sort(key=lambda r: (r["date_label"] != "pre", order.get(r["operator"], 999)))
    with open(OUT / "bundle.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bundle[0]))
        w.writeheader()
        w.writerows(bundle)
    with open(OUT / "checks.csv", "w", newline="") as f:
        rows = list(checks.values())
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
