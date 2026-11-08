"""Download WMATA's public ridership data (Metrobus by route, Metrorail by station) as raw CSVs.

Usage (from the repository root):
    uv run scripts/fetch_wmata_ridership.py            # everything
    uv run scripts/fetch_wmata_ridership.py bus        # one or more of: bus rail_daily
                                                       #   rail_periods docs

Outputs go to data/raw/wmata_ridership/ with a manifest.jsonl line per file:

- bus_route_month.csv: Metrobus boardings by route x month x service type (Weekday, Saturday,
  Sunday, Monthly Total), from the "Full Data" behind the Metrobus Ridership Summary dashboard
  (passenger counter based; July 2018 onward). Pre- and post-redesign route names both appear,
  told apart by the Network column ("Former Routes" / "Current Metro Bus Routes").
- rail_station_daily.csv: Metrorail entries, exits, tapped entries and exits and estimated
  non-tapped entries by station x service date, plus one systemwide "Bus Total Trace Adjusted" row
  per date, from the "Full Data" behind the Daily Ridership dashboard (2019 onward).
- rail_station_month_period.csv: Metrorail average daily entries by station x month x service type
  x time period (non-holiday days only, rounded to whole entries), from the Summary data of the
  "Avg Daily Entries by Station" dashboard, one request per month and service type.
- docs/: the monthly Ridership Snapshot PDFs (2023 onward), the technical-notes PDFs and the
  dashboard pages, as provenance.

The dashboards are served by a Tableau Server that allows anonymous viewing; see
betterbus.tableau for how the data are requested. The server returns at most 10,000 rows per
request, so each table is fetched in filtered pieces and every piece is checked for truncation.
Each *.csv has a *.columns.json sidecar mapping its column captions to Tableau field names and
types. Values are written as the server returns them (unformatted); an empty cell is a SQL NULL.
Re-running overwrites the CSVs and skips PDFs already downloaded.
"""

import csv
import json
import re
import sys
from datetime import date, timedelta

import requests

from betterbus.config import RAW
from betterbus.manifest import USER_AGENT, download, record, utc_now
from betterbus.tableau import TableauError, TableauView

HOST = "https://exttabanalytics.wmata.com"
SITE = "https://www.wmata.com"
OUT = RAW / "wmata_ridership"

BUS_WB = "RidershipDataPortal-MetroBusRidershipSummary"
DAILY_WB = "RidershipDataPortal-DailySummary_17782736730790"
RAIL_WB = "RidershipDataPortal-MetroRailRidershipSummary"

HUB = "/about/open-data-hub/ridership-data"
PAGES = {
    "ridership-data.html": f"{HUB}.html",
    "metrobus-ridership-summary.html": f"{HUB}/metrobus-ridership-summary.html",
    "metrorail-ridership-summary.html": f"{HUB}/metrorail-ridership-summary.html",
    "daily-ridership-dashboard.html": f"{HUB}/daily-ridership-dashboard.html",
    "bus-farebox-based-ridership-data.html": f"{HUB}/bus-farebox-based-ridership-data.html",
    "website-terms-of-use.html": "/about/public-records/website-terms-of-use.html",
}
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip


def view_url(workbook, view):
    return f"{HOST}/views/{workbook}/{view}"


def write_table(path, columns, rows, source, note):
    """Write rows (lists of server strings) as CSV with caption headers, plus a columns sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.part")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c["caption"] for c in columns])
        for r in rows:
            w.writerow(["" if v == "null" else v for v in r])
    tmp.replace(path)
    side = path.with_suffix(".columns.json")
    side.write_text(json.dumps({"source": source, "note": note, "columns": columns}, indent=1))
    when = utc_now()
    record(path, source, when, root=OUT, rows=len(rows), note=note)
    record(side, source, when, root=OUT)
    print(f"wrote {path.name}: {len(rows)} rows")


def month_starts(first, last):
    d = date(first.year, first.month, 1)
    while d <= last:
        yield d
        d = date(d.year + d.month // 12, d.month % 12 + 1, 1)


def month_end(d):
    return date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)


def same_columns(a, b):
    if [c["field"] for c in a] != [c["field"] for c in b]:
        raise TableauError("column layout changed between requests")


# Metrobus by route and month


def fetch_bus():
    """Route x month x service type, fetched one calendar year (12 month labels) at a time."""
    view = "TotalMonthlyRidershipbyRoute"
    v = TableauView(HOST, BUS_WB, view)
    ws = "Total Monthly Ridership"
    columns, rows = None, []

    def get(labels):
        nonlocal columns
        v.filter_values("Month", labels)
        try:
            cols, part = v.underlying(ws)
        except TableauError as e:
            if "truncated" not in str(e) or len(labels) == 1:
                raise
            half = len(labels) // 2
            return get(labels[:half]) + get(labels[half:])
        if columns is None:
            columns = cols
        same_columns(columns, cols)
        return part

    for year in range(2012, date.today().year + 1):
        part = get([f"{m} {year}" for m in MONTHS])
        print(f"bus {year}: {len(part)} rows")
        rows += part
    keys = [c["caption"] for c in columns]
    i_ym, i_rt, i_st = keys.index("Yearmo"), keys.index("Route"), keys.index("Service Type")
    if len({tuple(r) for r in rows}) != len(rows):
        raise TableauError("identical rows returned twice; the year pieces overlap")
    # WMATA's own table repeats some route x month x service type keys with different paid
    # boardings (June 2025, route codes used in both networks); keep them as published.
    keys_seen = {(r[i_ym], r[i_rt], r[i_st]) for r in rows}
    repeated = len(rows) - len(keys_seen)
    print(f"bus: {repeated} rows repeat a route x month x service type key")
    rows.sort(key=lambda r: tuple(r[i] for i in (i_ym, i_rt, i_st)) + tuple(r))
    write_table(
        OUT / "bus_route_month.csv",
        columns,
        rows,
        view_url(BUS_WB, view),
        f"Full Data of worksheet '{ws}', Month filter set to each calendar year in turn;"
        f" {repeated} rows repeat a Yearmo x Route x Service Type key, as published",
    )


# Metrorail by station and day


def fetch_rail_daily():
    """Station x service date (plus the systemwide bus total), one calendar month per request."""
    view = "DailyRidership-Data"
    v = TableauView(HOST, DAILY_WB, view)
    ws = "Daily Ridership - Data View"
    for caption in ("Weekday / Saturday / Sunday", "Day of Week", "Holiday"):
        v.filter_all(caption)
    date_fn = v.quick_filters["Date"]["fn"]
    first = date.fromisoformat(v.quick_filters["Date"]["range"]["rangeMin"][:10])
    columns, rows = None, []
    for m in month_starts(first, date.today()):
        v.filter_range("Date", m.isoformat(), month_end(m).isoformat(), field=date_fn)
        cols, part = v.underlying(ws)
        columns = columns or cols
        same_columns(columns, cols)
        print(f"rail daily {m:%Y-%m}: {len(part)} rows")
        rows += part
    keys = [c["caption"] for c in columns]
    i_d, i_s, i_m = keys.index("Date"), keys.index("Station Name"), keys.index("Mode")
    if len({(r[i_d], r[i_s], r[i_m]) for r in rows}) != len(rows):
        raise TableauError("duplicate date x station rows")
    rows.sort(key=lambda r: (r[i_d], r[i_m], r[i_s]))
    write_table(
        OUT / "rail_station_daily.csv",
        columns,
        rows,
        view_url(DAILY_WB, view),
        f"Full Data of worksheet '{ws}', all day types and holidays, Date filter set to each"
        " calendar month in turn",
    )


# Metrorail by station, month, service type and time period


def fetch_rail_periods(first=date(2019, 1, 1)):
    view = "AvgDailyEntriesbyStation"
    v = TableauView(HOST, RAIL_WB, view)
    ws = "Boardings by Route Table"
    for caption in ("Month", "Year", "Day of Week", "Time Period"):
        v.filter_all(caption)
    v.filter_values("Holiday", ["No"])
    date_fn = v.quick_filters["Date"]["fn"]
    last = date.fromisoformat(v.quick_filters["Date"]["range"]["rangeMax"][:10])
    columns, rows = None, []
    for m in month_starts(first, last):
        v.filter_range("Date", m.isoformat(), month_end(m).isoformat(), field=date_fn)
        for st in ("Weekday", "Saturday", "Sunday"):
            v.filter_values("Service Type", [st])
            cols, part = v.summary(ws)
            if columns is None:
                columns = [
                    {"field": "", "caption": "Month", "type": "date"},
                    {"field": "[SERVICETYPE]", "caption": "Service Type", "type": "cstring"},
                ] + cols
            same_columns(columns[2:], cols)
            rows += [[m.isoformat(), st] + r for r in part]
            print(f"rail periods {m:%Y-%m} {st}: {len(part)} rows")
    write_table(
        OUT / "rail_station_month_period.csv",
        columns,
        rows,
        view_url(RAIL_WB, view),
        f"Summary data of worksheet '{ws}' (station x time period, AGG(Avg Daily Entries))"
        " with Holiday = No, all years, months, days of week and time periods, Date filter"
        " set to each calendar month and Service Type to each value in turn; the first two"
        " columns record those filter settings",
    )


# Snapshots, technical notes and dashboard pages


def fetch_docs(first_year=2023):
    docs = OUT / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for name, path in PAGES.items():
        r = requests.get(SITE + path, headers={"User-Agent": USER_AGENT}, timeout=60)
        r.raise_for_status()
        (docs / name).write_bytes(r.content)
        record(docs / name, SITE + path, root=OUT)
    portal = (docs / "ridership-data.html").read_text()
    links = sorted(set(re.findall(r'href="(/content/dam/[^"]+\.pdf)"', portal)))
    for link in links:
        name = link.rsplit("/", 1)[1].replace("%20", "-").lower()
        is_snapshot = "snapshot" in name
        if is_snapshot:
            m = re.search(r"(20\d\d)", name)
            if not m or int(m.group(1)) < first_year:
                continue
        sub = "snapshots" if is_snapshot else "technical_notes"
        status = download(SITE + link, docs / sub / name, root=OUT)
        print(f"{status}: {sub}/{name}")


STEPS = {
    "bus": fetch_bus,
    "rail_daily": fetch_rail_daily,
    "rail_periods": fetch_rail_periods,
    "docs": fetch_docs,
}


if __name__ == "__main__":
    for step in sys.argv[1:] or list(STEPS):
        STEPS[step]()
