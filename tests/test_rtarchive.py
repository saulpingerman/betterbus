"""Round-trip and file-layout tests for the GTFS-Realtime archive format."""

import zstandard

from betterbus.rtarchive import append_record, hour_path, iter_records


def test_records_round_trip(tmp_path):
    comp = zstandard.ZstdCompressor(level=3)
    path = tmp_path / "f.rtz"
    records = [(1_794_103_542_000 + i, bytes([i]) * (i * 1000)) for i in range(5)]
    for t, payload in records:
        append_record(path, t, payload, comp)
    assert list(iter_records(path)) == records


def test_truncated_final_record_is_dropped(tmp_path):
    comp = zstandard.ZstdCompressor(level=3)
    path = tmp_path / "f.rtz"
    append_record(path, 1, b"a" * 500, comp)
    append_record(path, 2, b"b" * 500, comp)
    whole = path.read_bytes()
    path.write_bytes(whole[:-5])  # simulate a crash while writing the last frame
    got = list(iter_records(path))
    assert got[0] == (1, b"a" * 500)
    assert len(got) <= 2


def test_hour_path_uses_utc(tmp_path):
    # 2026-11-08 02:05:42 UTC
    p = hour_path(tmp_path, "bus-vp", 1_794_103_542_000)
    assert p == tmp_path / "bus-vp" / "2026-11-08" / "bus-vp_20261108T02Z.rtz"
