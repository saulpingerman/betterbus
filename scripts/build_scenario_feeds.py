"""Write the alternative-allocation scenario versions of the October 2025 WMATA bus GTFS.

Usage (from the repository root):
    uv run scripts/build_scenario_feeds.py [--out scenario_feeds_v1]

Scenarios (ledger: alternatives_v1, corrected in alternatives_v2), applied to every new route
of each route family:
  S1 speed held: trip durations scale by speed after / speed before (pre-launch scheduled speed)
     and trip counts by the inverse, so each family's weekday hours stay fixed.
  S2 frequency where it pays: trip counts scale by the family's hours ratio in
     results/<alt>/s2_reallocation.csv (--alt, default alternatives_v1).
  S3: S1 then S2.
Writes data/processed/<out>/{S1,S2,S3}.zip and edits.json (trips added and dropped).
"""

import argparse
import json

import pandas as pd

from betterbus.config import DATA, RAW, REPO
from betterbus.gtfs_edit import edit_feed
from betterbus.panel import family_service_detail

BASE = RAW / "gtfs" / "mdb-1846" / "mdb-1846-202510160132.zip"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="scenario_feeds_v1")
    p.add_argument("--alt", default="alternatives_v1", help="folder with s2_reallocation.csv")
    args = p.parse_args(argv)
    out = DATA / "processed" / args.out
    if out.exists():
        raise SystemExit(f"{out} exists; processed stores are immutable, pick a new --out")
    mem = pd.read_csv(DATA / "processed" / "families_v1" / "membership.csv")
    new = mem[mem.side == "new"]
    sd = family_service_detail().set_index("family").dropna(subset=["speed_pre", "speed_post"])
    f = (sd.speed_post / sd.speed_pre).rename("f")
    s2 = pd.read_csv(REPO / "results" / args.alt / "s2_reallocation.csv", index_col=0).hours_ratio
    fam_of = new.set_index("route").family
    s1_time = {r: float(f[fam]) for r, fam in fam_of.items() if fam in f.index}
    s1_freq = {r: 1 / v for r, v in s1_time.items()}
    s2_freq = {r: float(s2[fam]) for r, fam in fam_of.items() if fam in s2.index}
    s3_freq = {r: s1_freq.get(r, 1.0) * s2_freq.get(r, 1.0) for r in set(s1_freq) | set(s2_freq)}
    out.mkdir(parents=True)
    edits = {
        "S1": edit_feed(BASE, out / "S1.zip", time_scale=s1_time, freq_ratio=s1_freq),
        "S2": edit_feed(BASE, out / "S2.zip", freq_ratio=s2_freq),
        "S3": edit_feed(BASE, out / "S3.zip", time_scale=s1_time, freq_ratio=s3_freq),
    }
    (out / "edits.json").write_text(json.dumps({"base": BASE.name, **edits}, indent=1))
    print(json.dumps(edits))


if __name__ == "__main__":
    main()
