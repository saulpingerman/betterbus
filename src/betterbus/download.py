"""Shared helpers for fetching raw files: streamed download, SHA-256 and a per-directory manifest.

Every raw-data directory gets a `manifest.jsonl` with one JSON object per file:
{"path", "bytes", "sha256", "url", "retrieved_at"}. `path` is relative to the repository root.
Re-recording a file replaces its earlier manifest line.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from betterbus.config import REPO

USER_AGENT = "betterbus-research/0.1 (public-data transit evaluation)"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT


def utcnow():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def relpath(path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def record(path, url, retrieved_at=None, manifest=None):
    """Add or replace the manifest line for `path` in `manifest` (default: its directory's)."""
    path = Path(path)
    manifest = Path(manifest) if manifest else path.parent / "manifest.jsonl"
    entry = {
        "path": relpath(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "url": url,
        "retrieved_at": retrieved_at or utcnow(),
    }
    rows = []
    if manifest.exists():
        rows = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
        rows = [r for r in rows if r["path"] != entry["path"]]
    rows.append(entry)
    manifest.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return entry


def download(url, dest, manifest=None, overwrite=False, params=None, timeout=120, retries=3):
    """Stream `url` to `dest` (via a .part file), record it in the manifest and return the entry.

    An existing `dest` is kept unless `overwrite`; its manifest line is still (re)written
    if missing. Returns None when the server answers 404 or when `dest` already exists and is
    already in the manifest.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    manifest = Path(manifest) if manifest else dest.parent / "manifest.jsonl"
    if dest.exists() and not overwrite:
        if manifest.exists() and f'"{relpath(dest)}"' in manifest.read_text():
            return None
        return record(dest, url, manifest=manifest)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(retries):
        try:
            with SESSION.get(url, params=params, stream=True, timeout=timeout) as r:
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            break
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    part.rename(dest)
    full_url = url if not params else requests.Request("GET", url, params=params).prepare().url
    return record(dest, full_url, manifest=manifest)


def get_json(url, params=None, timeout=120, retries=4, pause=0.3, secret_params=("key",)):
    """GET a JSON document politely (short pause after each request, retry on 429/5xx).

    Values of `secret_params` (API keys) are left out of any error message.
    """
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(10 * (attempt + 1))
                continue
            if not r.ok:
                shown = {k: v for k, v in (params or {}).items() if k not in secret_params}
                raise requests.HTTPError(f"{r.status_code} {r.reason} for {url} {shown}")
            time.sleep(pause)
            return r.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))


def arcgis_layer(layer_url, dest, page=1000):
    """Export every feature of an ArcGIS REST MapServer/FeatureServer layer to GeoJSON (WGS84).

    Writes `dest` (GeoJSON FeatureCollection) and `dest` with suffix `.layer.json` (the layer's
    metadata: fields, description, editing info), records both in the directory's manifest and
    returns (feature_count, metadata). Pages through the layer with resultOffset, ordered by its
    object-id field. Existing files are reused.
    """
    dest = Path(dest)
    meta_path = dest.with_suffix(".layer.json")
    if dest.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return len(json.loads(dest.read_text())["features"]), meta
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = get_json(layer_url, params={"f": "json"})
    if "error" in meta:
        raise RuntimeError(f"{layer_url}: {meta['error']}")
    meta_path.write_text(json.dumps(meta, indent=1))
    record(meta_path, f"{layer_url}?f=json")
    oid = meta.get("objectIdField") or next(
        (f["name"] for f in meta.get("fields", []) if f["type"] == "esriFieldTypeOID"), None
    )
    total = get_json(
        f"{layer_url}/query", params={"where": "1=1", "returnCountOnly": "true", "f": "json"}
    )["count"]
    page = min(page, meta.get("maxRecordCount") or page)
    paginates = meta.get("advancedQueryCapabilities", {}).get("supportsPagination", False)
    base = {"outFields": "*", "outSR": 4326, "f": "geojson"}
    if paginates or not oid:
        # Ordinary offset paging (or a single request when the layer has no object id).
        windows = [None] * ((total + page - 1) // page if paginates else 1)
    else:
        # No pagination support: query object-id ranges of at most `page` ids.
        ids = sorted(
            get_json(
                f"{layer_url}/query", params={"where": "1=1", "returnIdsOnly": "true", "f": "json"}
            )["objectIds"]
        )
        windows = [(ids[i], ids[min(i + page, len(ids)) - 1]) for i in range(0, len(ids), page)]
    features = []
    for i, window in enumerate(windows):
        if window is None:
            params = {**base, "where": "1=1"}
            if paginates:
                params.update(resultOffset=i * page, resultRecordCount=page)
                if oid:
                    params["orderByFields"] = oid
        else:
            params = {**base, "where": f"{oid} >= {window[0]} AND {oid} <= {window[1]}"}
        chunk = get_json(f"{layer_url}/query", params=params)
        if "error" in chunk:
            raise RuntimeError(f"{layer_url}: {chunk['error']}")
        features += chunk.get("features", [])
    if len(features) != total:
        raise RuntimeError(f"{layer_url}: got {len(features)} of {total} features")
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    record(dest, f"{layer_url}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson")
    return total, meta
