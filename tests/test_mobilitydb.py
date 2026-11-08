"""Unit tests for the Mobility Database helpers that need no network."""

import hashlib

from betterbus.mobilitydb import sha256


def test_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "f.bin"
    payload = b"gtfs" * 300_000  # larger than one read chunk
    path.write_bytes(payload)
    assert sha256(path) == hashlib.sha256(payload).hexdigest()
