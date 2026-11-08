"""Extract WMATA's old-to-new route crosswalk from the 2025 Route Profiles PDF.

Usage (from the repository root):
    uv run scripts/extract_wmata_crosswalk.py

Input: data/raw/route_profiles/Resource_2025-Route-Profiles_District-of-Columbia.pdf, WMATA's
"Find Your Route in the 2025 Network" crosswalk (pages 1 to 4, dated November 2024, from the
approval stage of the redesign), as posted at
https://www.popville.com/wp-content/uploads/2024/11/Resource_2025-Route-Profiles_District-of-Columbia.pdf
WMATA's note on the table: "Not all current routes have a matching route in the 2025 Network;
this crosswalk lists the closest route(s) in the area." Listed routes are in WMATA's order.

Output: data/raw/route_profiles/crosswalk_2025_network.csv with columns operator (Metrobus or
TheBus), old_route, rank (1 = listed first), new_route.
"""

import csv
import re

import pymupdf

from betterbus.config import RAW

SRC = RAW / "route_profiles" / "Resource_2025-Route-Profiles_District-of-Columbia.pdf"
OUT = RAW / "route_profiles" / "crosswalk_2025_network.csv"
SKIP = {
    "wmata.com/betterbus",
    "Find Your Route in the 2025 Network",
    "Current",
    "Route",
    "Similar 2025",
    "Network Routes",
    "Route Similar 2025",
    "Metrobus",
}
NOTE_PREFIXES = ("This crosswalk", "most useful", "crosswalk lists")
NEW = re.compile(r"^[A-Z][0-9A-Z]{1,2}$")


def parse(lines):
    rows, operator, old = [], "Metrobus", None
    for line in lines:
        line = line.strip()
        if not line or line in SKIP or line.startswith(NOTE_PREFIXES):
            continue
        if line == "TheBus":
            operator = "TheBus"
            continue
        targets = [t.strip() for t in line.split(",")]
        if old is not None and all(NEW.match(t) for t in targets):
            rows += [(operator, old, i, t) for i, t in enumerate(targets, start=1)]
            old = None
        else:
            old = line
    return rows


def main():
    doc = pymupdf.open(SRC)
    lines = []
    for page in doc.pages(0, 4):
        lines += page.get_text().splitlines()
    rows = parse(lines)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["operator", "old_route", "rank", "new_route"])
        w.writerows(rows)
    olds = {(o, r) for o, r, _, _ in rows}
    print(f"{len(rows)} links, {len(olds)} old routes, {len({r[3] for r in rows})} new routes")


if __name__ == "__main__":
    main()
