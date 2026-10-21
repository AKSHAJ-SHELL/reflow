"""Fetch and install the jlcparts parts snapshot.  OWNER: AGENT (task P-04, DECISIONS D-6a).

Contract
--------
    update_snapshot(db_path=None, *, base_url=None, transport=None, on_part=None) -> SnapshotInfo
    default_db_path() -> Path

jlcparts publishes its database as a split zip: `cache.zip` plus
`cache.z01`…`cache.zNN`, holding one entry, `cache.sqlite3`. This module:

1. downloads `cache.zip` and reads its end record, which says how many parts
   there are (the central directory sits on the last disk), then downloads
   the rest;
2. inflates `cache.sqlite3` straight across the parts (macOS `unzip` and
   `zip -s 0` cannot join this archive) and checks its CRC-32 and size;
3. opens the result read-only and checks `meta.format == "source-db-v2"` and a
   `jlc_components` table;
4. replaces the installed database atomically and writes `snapshot.json`
   beside it: source URL, parts, CRC, size, row count, and the oldest and
   newest per-row `fetched_at` (as UTC dates).

On any failure the installed database is left as it was, and temporary files
are removed. Zip64 archives are refused, not guessed at.

Locations: `db_path`, else REFLOW_PARTS_DB, else
~/.cache/reflow/jlcparts/cache.sqlite3. Source: `base_url`, else
REFLOW_PARTS_URL, else DEFAULT_BASE_URL. Per-part timeout: REFLOW_PARTS_TIMEOUT
(seconds, default 300).

Must never
----------
- write inside the repository, or redistribute the database,
- install a database whose CRC, size or format does not check out,
- leave a half-written database at the install path.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import struct
import tempfile
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

DEFAULT_BASE_URL = "https://yaqwsx.github.io/jlcparts/data"
ENTRY = "cache.sqlite3"
FORMAT = "source-db-v2"

_EOCD = b"PK\x05\x06"
_CENTRAL = b"PK\x01\x02"
_LOCAL = b"PK\x03\x04"
_CHUNK = 1 << 20


class SnapshotError(RuntimeError):
    """The snapshot could not be fetched, read, or verified."""


class Transport(Protocol):
    def fetch(self, url: str, dest: Path) -> None: ...


class UrlLibTransport:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def fetch(self, url: str, dest: Path) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": "reflow-parts-update"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response, open(dest, "wb") as out:
            shutil.copyfileobj(response, out, _CHUNK)


@dataclass
class SnapshotInfo:
    path: Path
    parts: list[str]        # in download order: cache.zip first
    components: int
    oldest_row: str         # UTC date of the oldest per-row fetched_at
    newest_row: str
    crc32: int
    size: int


def default_db_path() -> Path:
    env = os.environ.get("REFLOW_PARTS_DB", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".cache" / "reflow" / "jlcparts" / ENTRY


def update_snapshot(db_path=None, *, base_url: str | None = None, transport: Transport | None = None,
                    on_part: Callable[[str], None] | None = None) -> SnapshotInfo:
    target = Path(db_path) if db_path is not None else default_db_path()
    base = (base_url or os.environ.get("REFLOW_PARTS_URL", "").strip() or DEFAULT_BASE_URL).rstrip("/")
    transport = transport or UrlLibTransport(_timeout())
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".reflow-download-", dir=target.parent))
    fd, tmp_name = tempfile.mkstemp(prefix=f".{ENTRY}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    staged = Path(tmp_name)
    try:
        names = ["cache.zip"]
        _fetch(transport, base, "cache.zip", work, on_part)
        last_disk = _end_record(work / "cache.zip")[0]
        for index in range(1, last_disk + 1):
            name = f"cache.z{index:02d}"
            _fetch(transport, base, name, work, on_part)
            names.append(name)
        parts = [work / n for n in names[1:]] + [work / "cache.zip"]
        crc, size = _inflate(parts, staged)
        components, oldest, newest = _check_database(staged)
        os.replace(staged, target)
        info = SnapshotInfo(target, names, components, oldest, newest, crc, size)
        _write_meta(target.parent / "snapshot.json", info, base)
        return info
    finally:
        shutil.rmtree(work, ignore_errors=True)
        staged.unlink(missing_ok=True)


def _fetch(transport: Transport, base: str, name: str, work: Path, on_part) -> None:
    if on_part is not None:
        on_part(name)
    try:
        transport.fetch(f"{base}/{name}", work / name)
    except (urllib.error.URLError, OSError) as exc:
        raise SnapshotError(f"could not fetch {name}: {getattr(exc, 'reason', None) or exc}") from exc


def _timeout() -> float:
    raw = os.environ.get("REFLOW_PARTS_TIMEOUT", "300")
    try:
        value = float(raw)
    except ValueError as exc:
        raise SnapshotError(f"REFLOW_PARTS_TIMEOUT is not a number: {raw!r}") from exc
    if value <= 0:
        raise SnapshotError("REFLOW_PARTS_TIMEOUT must be positive")
    return value


# ---------------------------------------------------------------------------
# reading the split archive
# ---------------------------------------------------------------------------

def _end_record(last_part: Path) -> tuple[int, int, int, int, int]:
    """(this disk, central-directory disk, entries, cd size, cd offset) from the EOCD."""
    with open(last_part, "rb") as f:
        f.seek(0, os.SEEK_END)
        length = f.tell()
        f.seek(max(0, length - 65557))
        tail = f.read()
    at = tail.rfind(_EOCD)
    if at == -1 or len(tail) - at < 22:
        raise SnapshotError("cache.zip is not a zip archive (no end record)")
    disk, cd_disk, _, entries, cd_size, cd_offset, _ = struct.unpack("<HHHHIIH", tail[at + 4:at + 22])
    if 0xFFFF in (disk, cd_disk, entries) or 0xFFFFFFFF in (cd_size, cd_offset):
        raise SnapshotError("zip64 snapshot archives are not supported")
    return disk, cd_disk, entries, cd_size, cd_offset


class _Parts:
    """The parts read as one byte stream: disk k starts at starts[k]."""

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        self.starts = []
        total = 0
        for path in paths:
            self.starts.append(total)
            total += path.stat().st_size
        self.length = total

    def read(self, offset: int, count: int) -> bytes:
        return b"".join(self.stream(offset, count))

    def stream(self, offset: int, count: int) -> Iterator[bytes]:
        if offset < 0 or offset + count > self.length:
            raise SnapshotError("archive is shorter than its directory says")
        for index, path in enumerate(self.paths):
            start, end = self.starts[index], self.starts[index] + path.stat().st_size
            if count == 0:
                return
            if offset >= end:
                continue
            with open(path, "rb") as f:
                f.seek(offset - start)
                while count and offset < end:
                    chunk = f.read(min(_CHUNK, count, end - offset))
                    if not chunk:
                        raise SnapshotError(f"{path.name} ended early")
                    yield chunk
                    offset += len(chunk)
                    count -= len(chunk)


def _inflate(paths: list[Path], dest: Path) -> tuple[int, int]:
    parts = _Parts(paths)
    _, cd_disk, entries, cd_size, cd_offset = _end_record(paths[-1])
    if entries != 1:
        raise SnapshotError(f"expected one entry ({ENTRY}), found {entries}")
    if cd_disk >= len(paths):
        raise SnapshotError("central directory is on a part that was not downloaded")
    central = parts.read(parts.starts[cd_disk] + cd_offset, cd_size)
    if len(central) < 46 or central[:4] != _CENTRAL:
        raise SnapshotError("archive central directory is unreadable")
    (_, _, _, flags, method, _, _, crc, csize, usize, name_len, _, _,
     disk_start, _, _, local_offset) = struct.unpack("<IHHHHHHIIIHHHHHII", central[:46])
    name = central[46:46 + name_len].decode("utf-8", "replace")
    if name != ENTRY:
        raise SnapshotError(f"archive holds {name!r}, expected {ENTRY}")
    if flags & 0x1:
        raise SnapshotError("archive is encrypted")
    if 0xFFFFFFFF in (csize, usize, local_offset):
        raise SnapshotError("zip64 snapshot archives are not supported")
    if method not in (0, 8):
        raise SnapshotError(f"unsupported compression method {method}")
    if disk_start >= len(paths):
        raise SnapshotError("entry starts on a part that was not downloaded")
    header_at = parts.starts[disk_start] + local_offset
    header = parts.read(header_at, 30)
    if header[:4] != _LOCAL:
        raise SnapshotError("archive local header is unreadable")
    local_name_len, local_extra_len = struct.unpack("<HH", header[26:30])
    data_at = header_at + 30 + local_name_len + local_extra_len

    inflater = zlib.decompressobj(-15) if method == 8 else None
    got_crc, written = 0, 0
    try:
        with open(dest, "wb") as out:
            for chunk in parts.stream(data_at, csize):
                plain = inflater.decompress(chunk) if inflater else chunk
                got_crc, written = zlib.crc32(plain, got_crc), written + len(plain)
                out.write(plain)
            if inflater:
                plain = inflater.flush()
                got_crc, written = zlib.crc32(plain, got_crc), written + len(plain)
                out.write(plain)
    except zlib.error as exc:
        raise SnapshotError(f"{ENTRY} does not decompress: {exc}") from exc
    if (got_crc, written) != (crc, usize):
        raise SnapshotError(f"{ENTRY} failed its check: CRC {got_crc:08x}/{written} bytes, "
                            f"archive says {crc:08x}/{usize} bytes")
    return crc, usize


# ---------------------------------------------------------------------------
# checking and recording the database
# ---------------------------------------------------------------------------

def _check_database(path: Path) -> tuple[int, str, str]:
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = db.execute("select value from meta where key = 'format'").fetchone()
            if row is None or row[0] != FORMAT:
                raise SnapshotError(f"database format is {row[0] if row else 'missing'!r}, expected {FORMAT}")
            count, oldest, newest = db.execute(
                "select count(*), min(fetched_at), max(fetched_at) from jlc_components"
            ).fetchone()
        finally:
            db.close()
    except sqlite3.Error as exc:
        raise SnapshotError(f"{ENTRY} is not a jlcparts {FORMAT} database: {exc}") from exc
    if not count:
        raise SnapshotError(f"{ENTRY} has no components")
    return count, _date(oldest), _date(newest)


def _date(stamp: int) -> str:
    return datetime.fromtimestamp(int(stamp), timezone.utc).strftime("%Y-%m-%d")


def _write_meta(path: Path, info: SnapshotInfo, base: str) -> None:
    meta = {
        "source": base,
        "parts": info.parts,
        "crc32": f"{info.crc32:08x}",
        "size": info.size,
        "format": FORMAT,
        "components": info.components,
        "oldest_row": info.oldest_row,
        "newest_row": info.newest_row,
        "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    fd, tmp = tempfile.mkstemp(prefix=".snapshot.", suffix=".tmp", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
