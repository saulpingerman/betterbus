"""Clip the Geofabrik DC, Maryland and Virginia extracts to one study-region .osm.pbf.

Needs the pyosmium library, which is not a project dependency; run it as a one-off with:
    uv run --with osmium python scripts/clip_osm.py [--date 261106]

Input: data/raw/osm/{district-of-columbia,maryland,virginia}-<date>.osm.pbf (scripts/fetch_osm.py).
Output: data/raw/osm/dmv-study-region-<date>.osm.pbf, recorded in data/raw/osm/manifest.jsonl.

Method (equivalent to `osmium extract --strategy complete_ways` on the merged states):
  1. Stream the three files merged and de-duplicated (objects on state borders appear in more
     than one extract). Keep every node inside BBOX and every way with at least one kept node.
  2. Add all nodes of kept ways, so ways that leave the box stay complete and routable.
  3. Keep every relation with at least one kept node or way as a member (turn restrictions,
     routes, multipolygons). Relation members outside the clip are not added, so long relations
     are reference-incomplete, as with `osmium extract`.
  4. Write the kept objects, sorted, with the Geofabrik replication timestamp in the file header.

BBOX is the extent of the WMATA Compact counties plus the buffer counties (Howard, Anne Arundel,
Charles, Frederick, Prince William, Manassas, Manassas Park) from TIGER 2024 tracts,
(-77.962, 38.171, -76.349, 39.720), widened by 0.1 degree on each side. It reaches a little into
West Virginia and Pennsylvania, which are not in the source extracts: there the clip holds only
ways that cross in from Maryland or Virginia.
"""

import argparse
import re

import osmium

from betterbus.config import RAW
from betterbus.download import record

STATES = ["district-of-columbia", "maryland", "virginia"]
BBOX = (-78.062, 38.071, -76.249, 39.820)  # west, south, east, north (WGS84)
OSM = RAW / "osm"


class Select(osmium.SimpleHandler):
    def __init__(self, tracker, relations):
        super().__init__()
        self.t = tracker
        self.relations = relations
        self.counts = [0, 0, 0]

    def node(self, n):
        if self.relations:
            return
        loc = n.location
        if loc.valid() and BBOX[0] <= loc.lon <= BBOX[2] and BBOX[1] <= loc.lat <= BBOX[3]:
            self.t.add_node(n.id)
            self.counts[0] += 1

    def way(self, w):
        if not self.relations and self.t.contains_any_references(w):
            self.t.add_way(w.id)
            self.counts[1] += 1

    def relation(self, r):
        if self.relations and self.t.contains_any_references(r):
            self.t.add_relation(r.id)
            self.counts[2] += 1


def merged(files):
    reader = osmium.MergeInputReader()
    for f in files:
        reader.add_file(str(f))
    return reader


def timestamp(date):
    text = (OSM / f"{STATES[0]}-{date}.state.txt").read_text()
    return re.search(r"timestamp=(\S+)", text).group(1).replace("\\:", ":")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", help="Geofabrik file date YYMMDD (default: newest present)")
    args = ap.parse_args()
    date = (
        args.date
        or sorted(p.name.split("-")[-1].split(".")[0] for p in OSM.glob(f"{STATES[0]}-*.osm.pbf"))[
            -1
        ]
    )
    files = [OSM / f"{s}-{date}.osm.pbf" for s in STATES]
    dest = OSM / f"dmv-study-region-{date}.osm.pbf"

    tracker = osmium.IdTracker()
    sel = Select(tracker, relations=False)
    merged(files).apply(sel, simplify=True)
    for f in files:
        tracker.complete_backward_references(str(f), relation_depth=0)
    rel = Select(tracker, relations=True)
    merged(files).apply(rel, simplify=True)
    print(
        f"kept {sel.counts[0]:,} nodes in box, {sel.counts[1]:,} ways, {rel.counts[2]:,} relations"
    )

    header = osmium.io.Header()
    header.add_box(
        osmium.osm.Box(osmium.osm.Location(BBOX[0], BBOX[1]), osmium.osm.Location(BBOX[2], BBOX[3]))
    )
    header.set("generator", "betterbus scripts/clip_osm.py (pyosmium)")
    header.set("osmosis_replication_timestamp", timestamp(date))
    tmp = dest.with_name(dest.name + ".part.osm.pbf")
    writer = osmium.SimpleWriter(str(tmp), header=header, overwrite=True)
    try:
        merged(files).apply(tracker.id_filter(), writer, simplify=True)
    finally:
        writer.close()
    tmp.rename(dest)
    record(dest, "derived: " + ", ".join(f.name for f in files) + f" clipped to bbox {BBOX}")
    print(f"wrote {dest} ({dest.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
