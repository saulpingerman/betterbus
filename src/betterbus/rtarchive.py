"""Archive WMATA's GTFS-Realtime feeds to local disk.

Run from the repository root:
    .venv/bin/python -m betterbus.rtarchive [--interval 30] [--min-free-gb 25]

Every `interval` seconds, each feed in FEEDS is fetched once. A response that differs from the
previous one for that feed is appended to an hourly file

    data/raw/gtfs-rt/<feed>/<YYYY-MM-DD>/<feed>_<YYYYMMDDTHH>Z.rtz   (UTC)

as one independent zstd frame holding: fetch time (int64 ms since epoch, big-endian), payload
length (uint32), payload (the protobuf bytes as served). Each frame is flushed and fsynced, so a
crash loses at most the frame being written. `iter_records` reads a file back.

Live state is written atomically to data/raw/gtfs-rt/status.json every cycle. When free disk
space falls below --min-free-gb the archiver stops writing, sets phase "disk_low" and rechecks
every ten minutes.
"""

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import signal
import struct
import sys
import time
import urllib.error
import urllib.request

import zstandard

from betterbus.config import RAW, key

BASE = "https://api.wmata.com/gtfs"
FEEDS = {
    "bus-vp": f"{BASE}/bus-gtfsrt-vehiclepositions.pb",
    "bus-tu": f"{BASE}/bus-gtfsrt-tripupdates.pb",
    "bus-alerts": f"{BASE}/bus-gtfsrt-alerts.pb",
    "rail-vp": f"{BASE}/rail-gtfsrt-vehiclepositions.pb",
    "rail-tu": f"{BASE}/rail-gtfsrt-tripupdates.pb",
    "rail-alerts": f"{BASE}/rail-gtfsrt-alerts.pb",
}
OUT = RAW / "gtfs-rt"
HEADER = struct.Struct(">qI")  # fetch time in ms, payload length


def hour_path(root, feed, t_ms):
    """Path of the hourly file that a record fetched at `t_ms` belongs to."""
    t = dt.datetime.fromtimestamp(t_ms / 1000, dt.UTC)
    return root / feed / f"{t:%Y-%m-%d}" / f"{feed}_{t:%Y%m%dT%H}Z.rtz"


def append_record(path, t_ms, payload, compressor):
    """Append one record to `path` as its own zstd frame, flushed to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = compressor.compress(HEADER.pack(t_ms, len(payload)) + payload)
    with open(path, "ab") as f:
        f.write(frame)
        f.flush()
        os.fsync(f.fileno())
    return len(frame)


def iter_records(path):
    """Yield (fetch_time_ms, payload) for every complete record in an .rtz file."""
    with open(path, "rb") as f:
        reader = zstandard.ZstdDecompressor().stream_reader(f, read_across_frames=True)
        data = io.BufferedReader(reader)
        while True:
            head = data.read(HEADER.size)
            if len(head) < HEADER.size:
                return
            t_ms, n = HEADER.unpack(head)
            payload = data.read(n)
            if len(payload) < n:
                return  # truncated final record
            yield t_ms, payload


def fetch(url, api_key, timeout=20):
    req = urllib.request.Request(url, headers={"api_key": api_key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def write_status(path, status):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=1, sort_keys=True))
    os.replace(tmp, path)


def now_iso():
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(interval, min_free_gb, root=OUT):
    root.mkdir(parents=True, exist_ok=True)
    api_keys = [key("WMATA_API_KEY")]
    if os.environ.get("WMATA_API_KEY_SECONDARY"):
        api_keys.append(os.environ["WMATA_API_KEY_SECONDARY"])
    compressor = zstandard.ZstdCompressor(level=10)
    last_hash = {}
    stop = False

    def on_signal(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    feeds = {name: {"ok": 0, "dup": 0, "err": 0, "bytes": 0} for name in FEEDS}
    status = {"started_at": now_iso(), "interval_s": interval, "phase": "running", "feeds": feeds}
    status_path = root / "status.json"
    print(f"{now_iso()} archiving {len(FEEDS)} feeds every {interval}s to {root}", flush=True)

    while not stop:
        cycle_start = time.time()
        free_gb = shutil.disk_usage(root).free / 1e9
        status["disk_free_gb"] = round(free_gb, 1)
        if free_gb < min_free_gb:
            status["phase"] = "disk_low"
            write_status(status_path, status)
            print(f"{now_iso()} disk_low: {free_gb:.1f} GB free < {min_free_gb} GB", flush=True)
            for _ in range(600):
                if stop:
                    break
                time.sleep(1)
            continue
        status["phase"] = "running"

        for name, url in FEEDS.items():
            st = feeds[name]
            t_ms = int(time.time() * 1000)
            payload, error = None, None
            for api_key in api_keys:
                try:
                    payload = fetch(url, api_key)
                    break
                except urllib.error.HTTPError as e:
                    error = f"HTTP {e.code}"
                    if e.code not in (401, 403):
                        break  # only an auth failure is worth retrying with the other key
                except Exception as e:  # network errors, timeouts
                    error = f"{type(e).__name__}: {e}"
                    break
            if payload is None:
                st["err"] += 1
                st["last_error"] = f"{now_iso()} {error}"
                print(f"{now_iso()} {name} {error}", flush=True)
                continue
            digest = hashlib.sha256(payload).digest()
            if last_hash.get(name) == digest:
                st["dup"] += 1
            else:
                st["bytes"] += append_record(hour_path(root, name, t_ms), t_ms, payload, compressor)
                st["ok"] += 1
                last_hash[name] = digest
            st["last_ok"] = now_iso()

        status["last_cycle"] = now_iso()
        status["last_cycle_s"] = round(time.time() - cycle_start, 2)
        write_status(status_path, status)
        # sleep to the next multiple of `interval`, in short steps so a stop signal is prompt
        wake = (int(time.time()) // interval + 1) * interval
        while not stop and time.time() < wake:
            time.sleep(min(1.0, wake - time.time()))

    status["phase"] = "stopped"
    status["stopped_at"] = now_iso()
    write_status(status_path, status)
    print(f"{now_iso()} stopped", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--interval", type=int, default=30, help="seconds between polls")
    p.add_argument("--min-free-gb", type=float, default=25, help="stop writing below this")
    args = p.parse_args(argv)
    run(args.interval, args.min_free_gb)


if __name__ == "__main__":
    sys.exit(main())
