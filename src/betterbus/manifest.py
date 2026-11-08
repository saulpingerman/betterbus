"""Download helpers that keep a `manifest.jsonl` of every raw file in a directory.

Each manifest line records one file: its path relative to the repository, size, SHA-256, source
URL (or a description of the request that produced it) and the UTC retrieval time. Re-recording a
path replaces its earlier line.
"""

import hashlib
import json
import time
from datetime import UTC, datetime

import requests

from betterbus.config import REPO

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) betterbus-research-download"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(path, source, retrieved_at=None, root=None, **extra):
    """Add or replace the manifest line for `path` in `root / "manifest.jsonl"`.

    `root` defaults to the file's own directory; pass the dataset directory for files in
    subdirectories so that one manifest lists them all.
    """
    manifest = (root or path.parent) / "manifest.jsonl"
    rel = path.relative_to(REPO).as_posix()
    lines = []
    if manifest.exists():
        lines = [json.loads(x) for x in manifest.read_text().splitlines() if x.strip()]
    lines = [x for x in lines if x["path"] != rel]
    entry = {
        "path": rel,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "source": source,
        "retrieved_at": retrieved_at or utc_now(),
        **extra,
    }
    lines.append(entry)
    lines.sort(key=lambda x: x["path"])
    manifest.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return entry


def download(url, dest, overwrite=False, delay=0.5, root=None):
    """Fetch `url` to `dest` and record it; skip a file that already exists."""
    if dest.exists() and not overwrite:
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(delay)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    record(dest, url, root=root)
    return "ok"
