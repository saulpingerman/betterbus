"""Download WMATA's Better Bus old-route to new-route crosswalk and save it as CSV.

Usage (from the repository root; pdfplumber is needed only here, so it is added for this run):
    uv run --with pdfplumber scripts/fetch_wmata_crosswalk.py              # sources 2 and 3
    uv run --with pdfplumber scripts/fetch_wmata_crosswalk.py --profiles   # also source 1

Status: source 1 (about 126 Wayback requests) has not been run to completion; the project's
primary crosswalk comes from the "2025 Route Profiles" PDFs kept elsewhere under data/raw/.

WMATA's interactive "Find Your New Route" tool (wmata.com/betterbus before the site moved in 2025)
queried an endpoint that no longer exists, so the crosswalk is rebuilt from two WMATA sources:

1. Route profiles of the launched network (June 29, 2025). Each new route had a page saying
   "Compare the <new route> to these old routes: Metrobus ..., TheBus ...". Those pages are gone
   from wmata.com; they are read from the Internet Archive's Wayback Machine (raw captures, `id_`
   URLs) and saved under wayback/. Output: route_profiles.csv (one row per new route) and
   crosswalk_route_profiles.csv (one row per new route x old route).
2. "Proposed 2025 Network Comment and Response Summary" (WMATA, final version published with the
   Board's November 2024 approval), whose tables list for each new route the proposed number, the
   final number, the name and the "Similar Current Routes". Output: the PDF itself,
   comment_response_routes.csv (one row per table row, all six columns) and
   crosswalk_comment_response.csv (one row per new route x old route).

It also saves the archived Better Bus home page that hosted the tool, and old_routes.csv, the list
of pre-redesign routes (code and line name) embedded in that page for the tool's autocomplete.

Outputs go to data/raw/wmata_crosswalk/ with a manifest.jsonl line per file. Archived pages
already downloaded are reused; delete wayback/ to fetch them again.
"""

import csv
import json
import re
import sys
import time
from html import unescape

import requests

from betterbus.config import RAW
from betterbus.manifest import USER_AGENT, download, record

OUT = RAW / "wmata_crosswalk"
WAYBACK = OUT / "wayback"
ARCHIVE = "https://web.archive.org"
OLD_SITE = "wmata.com/initiatives/plans/Better-Bus"
COMMENT_PDF = (
    "https://www.wmata.com/content/dam/wmata-com/migrated-assets/initiatives/plans/better-bus/"
    "upload/reports_proposed-2025-network-comment-and-response-summary_final.pdf"
)
# A capture of the Better Bus home page from two days before launch, with the route finder.
HOME_CAPTURE = (
    "20250627053316",
    "https://www.wmata.com/initiatives/plans/Better-Bus/index.cfm?emci=a1d93963-6c50-f011-8f7c-"
    "6045bdfe8e9c&emdi=ea000000-0000-0000-0000-000000000001&ceid=%7B%7BContactsEmailID%7D%7D",
)
OPERATORS = ("Metrobus", "TheBus", "Ride On", "DASH", "ART", "Fairfax Connector", "CUE")


def wayback_get(url, tries=6, pause=3.0):
    """GET from the Wayback Machine politely, retrying its frequent transient failures."""
    for i in range(tries):
        time.sleep(pause * (i + 1))
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
        except requests.RequestException as e:
            print(f"  retry {i + 1}: {e.__class__.__name__}")
            continue
        if r.status_code == 200 and "Temporarily Offline" not in r.text[:2000]:
            return r
        print(f"  retry {i + 1}: HTTP {r.status_code}")
    raise RuntimeError(f"Wayback Machine did not answer for {url}")


def capture(timestamp, original, dest):
    """Save the raw archived bytes of `original` captured at `timestamp` (or the nearest one)."""
    url = f"{ARCHIVE}/web/{timestamp}id_/{original}"
    if not dest.exists():
        r = wayback_get(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        record(dest, url, root=OUT, original=original, final_url=r.url)
    return dest.read_text(errors="replace")


def text(fragment):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def split_routes(cell):
    """'A8, A4, P6 TheBus 35' -> [('Metrobus','A8'), ('Metrobus','A4'), ('Metrobus','P6'),
    ('TheBus','35')]. A bare list counts as Metrobus; an operator name applies to what follows."""
    out, operator = [], "Metrobus"
    pattern = "|".join(re.escape(o) for o in sorted(OPERATORS, key=len, reverse=True))
    for piece in re.split(f"({pattern})", cell):
        piece = piece.strip(" ,;")
        if not piece:
            continue
        if piece in OPERATORS:
            operator = piece
            continue
        for code in re.split(r"[,\s]+", piece):
            if code and code.upper() != "N/A":
                out.append((operator, code))
    return out


def write_csv(path, header, rows, source):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    record(path, source, root=OUT, rows=len(rows))
    print(f"wrote {path.name}: {len(rows)} rows")


# 1. Archived home page and the old route list


def fetch_home():
    ts, original = HOME_CAPTURE
    page = capture(ts, original, WAYBACK / "better_bus_index_20250627.html")
    m = re.search(r"alertsWidgetBusRoutesJSON\s*=\s*eval\((\[.*?\])\);", page, re.S)
    routes = json.loads(m.group(1))
    rows = [(r["VALUE"], r["LABEL"], r.get("DIRECTIONS", "")) for r in routes]
    write_csv(
        OUT / "old_routes.csv",
        ["old_route", "label", "directions"],
        rows,
        f"{ARCHIVE}/web/{ts}id_/{original} (alertsWidgetBusRoutesJSON)",
    )


# 2. Archived route profiles of the launched network


def list_profile_captures(launch="20250629"):
    """One successful capture of each route-profile.cfm?route=<code> page, keyed by code: the
    earliest one on or after the launch date, else the latest one before it."""
    cdx = (
        f"{ARCHIVE}/cdx/search/cdx?url={OLD_SITE}/route-profile.cfm&matchType=prefix"
        "&output=json&fl=timestamp,original,statuscode&filter=statuscode:200"
    )
    rows = wayback_get(cdx).json()[1:]
    best = {}
    for ts, original, _ in rows:
        m = re.search(r"[?&]route=([A-Za-z0-9]+)$", original)
        if not m:
            continue
        code = m.group(1).upper()
        old = best.get(code)
        if old is None:
            best[code] = (ts, original)
        elif ts >= launch:
            if old[0] < launch or ts < old[0]:
                best[code] = (ts, original)
        elif old[0] < launch and ts > old[0]:
            best[code] = (ts, original)
    return best


def parse_profile(page):
    h2 = re.search(r"<h2[^>]*>(.*?)</h2>", page, re.S)
    heading = text(h2.group(1)) if h2 else ""
    code, _, name = heading.partition(" ")
    body = page[h2.end() :] if h2 else page
    comp = re.search(
        r"<strong>\s*Compare the [^<]*?th(?:is|ese) old routes?:\s*</strong>(.*?)</p>", body, re.S
    )
    freq = re.search(r"<strong>Frequency</strong>:(.*?)Click", body, re.S)
    end = comp.start() if comp else (freq.start() if freq else 0)
    return {
        "new_route": code,
        "new_route_name": name,
        "old_routes": text(comp.group(1)) if comp else "",
        "frequency": text(freq.group(1)).rstrip(". ") if freq else "",
        "description": text(body[:end]),
    }


def fetch_profiles():
    captures = list_profile_captures()
    print(f"{len(captures)} route profile pages archived")
    profiles, missing = [], []
    for code in sorted(captures):
        ts, original = captures[code]
        try:
            page = capture(ts, original, WAYBACK / "route_profiles" / f"{code}.html")
        except RuntimeError as e:
            print(f"  {code}: {e}")
            missing.append(code)
            continue
        p = parse_profile(page)
        if p["new_route"].upper() != code:
            print(f"  {code}: heading reads {p['new_route']!r}; kept as {code}")
        archived = f"{ARCHIVE}/web/{ts}/{original}"
        p.update(new_route=code, capture_timestamp=ts, archived_url=archived)
        profiles.append(p)
    if missing:
        print(f"not fetched (re-run to retry): {' '.join(missing)}")
    cols = [
        "new_route",
        "new_route_name",
        "old_routes",
        "frequency",
        "description",
        "capture_timestamp",
        "archived_url",
    ]
    src = f"{ARCHIVE}/web/*/{OLD_SITE}/route-profile.cfm?route=*"
    write_csv(OUT / "route_profiles.csv", cols, [[p[c] for c in cols] for p in profiles], src)
    long = [
        [p["new_route"], op, old, p["capture_timestamp"]]
        for p in profiles
        for op, old in split_routes(p["old_routes"])
    ]
    write_csv(
        OUT / "crosswalk_route_profiles.csv",
        ["new_route", "old_operator", "old_route", "capture_timestamp"],
        long,
        src,
    )


# 3. Comment and response summary tables


def fetch_comment_response():
    import pdfplumber

    pdf_path = OUT / "proposed-2025-network-comment-and-response-summary_final.pdf"
    download(COMMENT_PDF, pdf_path, root=OUT)
    rows, region = [], ""
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables():
                if not table or not (table[0][0] or "").startswith("Route Number"):
                    continue
                for raw in table[1:]:
                    cells = [re.sub(r"\s+", " ", c or "").strip() for c in raw]
                    if not any(cells):
                        continue
                    if cells[0] in ("DISTRICT OF COLUMBIA", "MARYLAND", "VIRGINIA"):
                        region = cells[0]  # section header row
                        continue
                    if not any(cells[:4]) and rows:  # continuation of the previous row
                        prev = rows[-1][6:]
                        rows[-1][6:] = [
                            f"{a} {b}".strip() for a, b in zip(prev, cells[4:], strict=True)
                        ]
                        continue
                    rows.append([page_no, region] + cells)
    header = [
        "pdf_page",
        "region",
        "proposed_route",
        "new_route",
        "new_route_name",
        "similar_current_routes",
        "comment_summary",
        "service_planning_changes",
    ]
    write_csv(OUT / "comment_response_routes.csv", header, rows, COMMENT_PDF)
    long = [
        [r[3], r[2], op, old, r[0]]
        for r in rows
        if r[3] and not r[3].upper().startswith("N/A")
        for op, old in split_routes(r[5])
    ]
    write_csv(
        OUT / "crosswalk_comment_response.csv",
        ["new_route", "proposed_route", "old_operator", "old_route", "pdf_page"],
        long,
        COMMENT_PDF,
    )


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fetch_comment_response()
    fetch_home()
    if "--profiles" in sys.argv[1:]:
        fetch_profiles()
