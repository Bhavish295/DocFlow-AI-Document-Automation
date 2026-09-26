"""Tests for deterministic SHA-256 document hashing."""

from pathlib import Path

from app.services.document_hashing import sha256_bytes, sha256_file, sha256_stream


def test_sha256_bytes_deterministic():
    left = sha256_bytes(b"invoice-content")
    right = sha256_bytes(b"invoice-content")
    assert left == right
    assert len(left) == 64


def test_sha256_bytes_different_content():
    assert sha256_bytes(b"alpha") != sha256_bytes(b"beta")


def test_sha256_file_matches_bytes(tmp_path: Path):
    path = tmp_path / "doc.bin"
    payload = b"pdf-bytes-" + (b"x" * 2048)
    path.write_bytes(payload)
    assert sha256_file(path) == sha256_bytes(payload)


def test_sha256_stream_matches_bytes():
    chunks = [b"one", b"two", b"three"]
    assert sha256_stream(chunks) == sha256_bytes(b"".join(chunks))


def test_sha256_file_chunked_large(tmp_path: Path):
    path = tmp_path / "large.bin"
    payload = b"A" * (1024 * 1024 + 17)
    path.write_bytes(payload)
    assert sha256_file(path, chunk_size=4096) == sha256_bytes(payload)
