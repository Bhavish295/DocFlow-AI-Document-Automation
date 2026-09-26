"""Deterministic SHA-256 hashing for uploaded document files."""

from __future__ import annotations

import hashlib
from pathlib import Path


CHUNK_SIZE = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = CHUNK_SIZE) -> str:
    """Compute SHA-256 of a file without loading it entirely into memory."""
    digest = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(chunks: list[bytes] | tuple[bytes, ...]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()
