"""Build route families linking pre-redesign and post-redesign WMATA bus routes by shared stops.

Usage (from the repository root):
    uv run scripts/build_route_families.py [--out families_v1]

Reference networks: the last pre-launch GTFS version on a mid-May 2025 weekday and the launch
version on a mid-July 2025 weekday (see betterbus.families for the method). Writes to
data/processed/<out>/: membership.csv (family, side, route), pairs.csv (every old-new route pair
sharing a stop, with overlap shares and best-match flags), families.csv (per family: route
counts, containment, share of pre-launch stop events at removed stops), run_meta.json.
"""

import argparse
import datetime as dt
import json
import subprocess

from betterbus.config import DATA, RAW, REPO
from betterbus.families import build_families, stop_events

PRE = ("mdb-1846-202505020000", dt.date(2025, 5, 14))
POST = ("mdb-1846-202507250117", dt.date(2025, 7, 16))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="families_v1")
    args = p.parse_args(argv)
    out = DATA / "processed" / args.out
    if out.exists():
        raise SystemExit(f"{out} exists; processed stores are immutable, pick a new --out")

    gtfs = RAW / "gtfs" / "mdb-1846"
    pre = stop_events(gtfs / f"{PRE[0]}.zip", PRE[1])
    post = stop_events(gtfs / f"{POST[0]}.zip", POST[1])
    mem, pairs, fam = build_families(pre, post)

    out.mkdir(parents=True)
    mem.to_csv(out / "membership.csv", index=False)
    pairs.to_csv(out / "pairs.csv", index=False)
    fam.to_csv(out / "families.csv", index=False)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    meta = {
        "commit": commit,
        "created_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pre_reference": [PRE[0], str(PRE[1])],
        "post_reference": [POST[0], str(POST[1])],
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    n_old, n_new = pre.route.nunique(), post.route.nunique()
    print(f"{len(fam)} families from {n_old} old and {n_new} new routes")
    print(fam.describe().round(3).to_string())


if __name__ == "__main__":
    main()
