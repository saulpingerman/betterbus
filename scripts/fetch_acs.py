"""Download ACS 5-year detailed tables for the study region from the Census API.

For every county in COUNTIES (the WMATA Compact area plus the buffer counties) and every table in
TABLES, the script requests `group(<table>)` at block-group and tract level and saves:

  data/raw/acs/<vintage>/json/<table>_<level>_<state><county>.json   raw API response
  data/raw/acs/<vintage>/meta/<table>.json                           variable labels
  data/raw/acs/<vintage>/<table>_<level>.csv                         tidy long table

The tidy CSV has one row per geography and variable: geoid, state, county, tract, block_group,
name, variable (e.g. B19001_002), label, estimate, moe, estimate_annotation, moe_annotation.
Census sentinel values (for example -666666666 = not computable) are kept as published.

Some tables are published only at tract level; a block-group request then returns nulls in every
cell. Such block-group files are still saved, and the tidy CSV for that table and level is
skipped with a message.

The vintage is the newest of CANDIDATE_VINTAGES that the API serves. The API key is read from
CENSUS_API_KEY in .env.

Usage (from the repository root):
    uv run python scripts/fetch_acs.py              # newest vintage
    uv run python scripts/fetch_acs.py --vintage 2023
"""

import argparse
import csv
import json
import time

import requests

from betterbus.config import RAW, key
from betterbus.download import SESSION, get_json, record

API = "https://api.census.gov/data/{vintage}/acs/acs5"
CANDIDATE_VINTAGES = [2025, 2024, 2023]

COMPACT = {
    "11": ["001"],  # District of Columbia
    "24": ["031", "033"],  # Montgomery, Prince George's
    "51": ["013", "059", "107", "510", "600", "610"],
    # Arlington, Fairfax County, Loudoun, Alexandria city, Fairfax city, Falls Church city
}
BUFFER = {
    "24": ["027", "003", "017", "021"],  # Howard, Anne Arundel, Charles, Frederick
    "51": ["153", "683", "685"],  # Prince William, Manassas city, Manassas Park city
}
COUNTIES = [(s, c) for d in (COMPACT, BUFFER) for s, cs in d.items() for c in cs]

TABLES = {
    "B01003": "Total population",
    "B03002": "Hispanic or Latino origin by race",
    "B19013": "Median household income",
    "B19001": "Household income in the past 12 months",
    "B25044": "Tenure by vehicles available",
    "B08301": "Means of transportation to work",
    "C17002": "Ratio of income to poverty level",
    "B11001": "Household type (households)",
    "C21007": "Age by veteran status by poverty status by disability status",
    "B18101": "Sex by age by disability status",
}
LEVELS = {"block_group": "block group:*", "tract": "tract:*"}


def newest_vintage():
    """The newest vintage the API serves. Only a 404 moves on to an older vintage; any other
    failure (for example a 503 while the API is busy) stops the script rather than silently
    falling back to an older vintage."""
    for v in CANDIDATE_VINTAGES:
        for attempt in range(3):
            try:
                r = SESSION.get(API.format(vintage=v) + ".json", timeout=60)
                break
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(15)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("application/json"):
            return v
        raise SystemExit(f"unexpected response for ACS {v}: {r.headers.get('content-type')}")
    raise SystemExit("no ACS 5-year vintage found")


def fetch_meta(vintage, table, out):
    url = f"{API.format(vintage=vintage)}/groups/{table}.json"
    dest = out / "meta" / f"{table}.json"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(get_json(url), indent=1))
        record(dest, url, manifest=out / "manifest.jsonl")
    return json.loads(dest.read_text())["variables"]


def fetch_county(vintage, table, level, state, county, out, api_key):
    dest = out / "json" / f"{table}_{level}_{state}{county}.json"
    if dest.exists():
        return json.loads(dest.read_text())
    params = {
        "get": f"group({table})",
        "for": LEVELS[level],
        "in": f"state:{state} county:{county}",
    }
    rows = get_json(API.format(vintage=vintage), params={**params, "key": api_key})
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(rows))
    url = requests.Request("GET", API.format(vintage=vintage), params=params).prepare().url
    record(dest, url + "&key=REDACTED", manifest=out / "manifest.jsonl")
    return rows


def tidy(rows, variables, table):
    head, body = rows[0], rows[1:]
    idx = {h: i for i, h in enumerate(head)}
    names = sorted(
        h[:-1]
        for h in head
        if h.startswith(table + "_") and h.endswith("E") and h[:-1] + "M" in idx
    )
    out = []
    for r in body:
        geo = r[idx["GEO_ID"]].split("US")[-1]
        for v in names:
            out.append(
                {
                    "geoid": geo,
                    "state": r[idx["state"]],
                    "county": r[idx["county"]],
                    "tract": r[idx["tract"]],
                    "block_group": r[idx["block group"]] if "block group" in idx else "",
                    "name": r[idx["NAME"]],
                    "variable": v,
                    "label": variables.get(v + "E", {}).get("label", ""),
                    "estimate": r[idx[v + "E"]],
                    "moe": r[idx[v + "M"]],
                    "estimate_annotation": r[idx[v + "EA"]] if v + "EA" in idx else "",
                    "moe_annotation": r[idx[v + "MA"]] if v + "MA" in idx else "",
                }
            )
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--vintage", type=int)
    args = ap.parse_args()
    vintage = args.vintage or newest_vintage()
    out = RAW / "acs" / str(vintage)
    api_key = key("CENSUS_API_KEY")
    print(f"ACS 5-year {vintage}, {len(COUNTIES)} counties")
    for table in TABLES:
        variables = fetch_meta(vintage, table, out)
        for level in LEVELS:
            rows = []
            for state, county in COUNTIES:
                rows += tidy(
                    fetch_county(vintage, table, level, state, county, out, api_key),
                    variables,
                    table,
                )
            if not rows or all(r["estimate"] is None for r in rows):
                print(f"  {table} {level}: all estimates null (not published at this level)")
                continue
            dest = out / f"{table}_{level}.csv"
            with open(dest, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            record(
                dest,
                API.format(vintage=vintage) + " (derived from json/)",
                manifest=out / "manifest.jsonl",
            )
            ngeo = len({r["geoid"] for r in rows})
            print(f"  {table} {level}: {ngeo} geographies, {len(rows)} rows")


if __name__ == "__main__":
    main()
