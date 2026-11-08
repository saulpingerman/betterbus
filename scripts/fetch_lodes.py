"""Download LODES 8 job counts (WAC, RAC, OD) and geography crosswalks for DC, Maryland, Virginia.

Files come from https://lehd.ces.census.gov/data/lodes/LODES8/ and are saved unchanged
(gzipped CSV) under data/raw/lodes/<state>/{wac,rac,od}/. Each file is checked against the
`.sha256sum` file the Census Bureau publishes next to it. Also saved: each state's `version.txt`
(data vintage), the `<st>_xwalk.csv.gz` block crosswalk, and the technical documentation PDF.

What is fetched:
  WAC and RAC, segment S000, job types JT00 (all jobs), JT04 (all federal jobs),
  JT05 (federal primary jobs), for the years in YEARS;
  OD main and aux, JT00, for OD_YEAR only.

Usage (from the repository root):
    uv run python scripts/fetch_lodes.py
Re-running skips files already present.
"""

import gzip
import hashlib

from betterbus.config import RAW
from betterbus.download import SESSION, download, sha256

BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"
STATES = ["dc", "md", "va"]
JOB_TYPES = ["JT00", "JT04", "JT05"]
YEARS = [2019, 2022, 2023, 2024]
OD_YEAR = 2024
TECH_DOC = "LODESTechDoc8.5.pdf"
OUT = RAW / "lodes"
MANIFEST = OUT / "manifest.jsonl"


def published_sha(url):
    r = SESSION.get(url.removesuffix(".gz") + ".sha256sum", timeout=60)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text.split()[0].lower()


def fetch(url, dest):
    download(url, dest, manifest=MANIFEST, timeout=600)
    if not dest.exists():
        print(f"  missing on server: {url}")
        return
    if url.endswith(".gz"):
        want = published_sha(url)
        status = "no checksum" if want is None else "MISMATCH"
        if want == sha256(dest):
            status = "ok (gz)"
        elif want is not None:
            # Some .sha256sum files name the uncompressed CSV; check that too.
            h = hashlib.sha256()
            with gzip.open(dest, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            if h.hexdigest() == want:
                status = "ok (csv)"
        print(f"  {dest.name}: {dest.stat().st_size:,} bytes, sha256 {status}")
        if status == "MISMATCH":
            raise SystemExit(f"checksum mismatch for {dest}")


def main():
    fetch(f"{BASE}/{TECH_DOC}", OUT / TECH_DOC)
    for st in STATES:
        print(st)
        fetch(f"{BASE}/{st}/version.txt", OUT / st / "version.txt")
        fetch(f"{BASE}/{st}/{st}_xwalk.csv.gz", OUT / st / f"{st}_xwalk.csv.gz")
        for kind in ("wac", "rac"):
            for jt in JOB_TYPES:
                for year in YEARS:
                    name = f"{st}_{kind}_S000_{jt}_{year}.csv.gz"
                    fetch(f"{BASE}/{st}/{kind}/{name}", OUT / st / kind / name)
        for part in ("main", "aux"):
            name = f"{st}_od_{part}_JT00_{OD_YEAR}.csv.gz"
            fetch(f"{BASE}/{st}/od/{name}", OUT / st / "od" / name)


if __name__ == "__main__":
    main()
