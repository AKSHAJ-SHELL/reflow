"""On-disk cache for catalog responses.  OWNER: AGENT (task P-03).

A repeat search reads the stored response and does not call the network.
Only successful response bodies are stored. Failures are not cached.

Must never
----------
- write outside the cache directory it was given,
- turn a failed fetch into an empty result,
- invent part numbers (it stores bytes and does not interpret them).
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def load(cache_dir: Path, url: str) -> bytes | None:
    """Return the stored body for `url`, or None when this query is not cached."""
    path = _path(cache_dir, url)
    if not path.is_file():
        return None
    return path.read_bytes()


def store(cache_dir: Path, url: str, body: bytes) -> None:
    """Atomically store `body` under `cache_dir` for `url`."""
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = _path(directory, url)
    temporary = directory / f".{path.name}.tmp"
    temporary.write_bytes(body)
    temporary.replace(path)


def _path(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return Path(cache_dir) / digest
