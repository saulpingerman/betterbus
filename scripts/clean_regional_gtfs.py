"""Write R5-ready copies of the regional bundle's feeds (empty tables removed).

Usage (from the repository root):
    uv run scripts/clean_regional_gtfs.py

Reads data/processed/regional_bundle_v1/bundle.csv and writes each listed feed to
data/processed/regional_bundle_v1/clean/<dataset_id>.zip, with clean.csv listing the tables
removed from each.
"""

import pandas as pd

from betterbus.config import DATA, REPO
from betterbus.gtfs_edit import strip_empty_tables

BUNDLE = DATA / "processed" / "regional_bundle_v1"


def main():
    b = pd.read_csv(BUNDLE / "bundle.csv").dropna(subset=["file"])
    out = BUNDLE / "clean"
    out.mkdir(exist_ok=True)
    rows = []
    for f in sorted(set(b.file)):
        dst = out / f.split("/")[-1]
        removed = strip_empty_tables(REPO / f, dst)
        rows.append(
            {"file": f, "clean": dst.relative_to(REPO).as_posix(), "removed": ";".join(removed)}
        )
    pd.DataFrame(rows).to_csv(BUNDLE / "clean.csv", index=False)
    print(pd.DataFrame(rows)[["clean", "removed"]].to_string(index=False))


if __name__ == "__main__":
    main()
