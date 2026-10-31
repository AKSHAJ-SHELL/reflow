"""P-04: `reflow parts update` fetches and installs the jlcparts snapshot (D-6a).

No network: the updater reads tests/data/snapshot/ (a six-part split archive
in the real format, see its README) through file:// URLs, so the real
download, join, inflate and install code runs.
"""
import json
import shutil
import sqlite3
import zipfile
import zlib
from pathlib import Path

import pytest

import reflow.cli as cli
from reflow.parts.snapshot import SnapshotError, default_db_path, update_snapshot

FIXTURE = Path(__file__).resolve().parent / "data" / "snapshot"
FIXTURE_CRC, FIXTURE_SIZE = 0x3B41B5D8, 401408
PART_NAMES = ["cache.zip", "cache.z01", "cache.z02", "cache.z03", "cache.z04", "cache.z05"]


def _url(folder: Path) -> str:
    return folder.resolve().as_uri()


def _copy_fixture(tmp_path: Path) -> Path:
    folder = tmp_path / "served"
    shutil.copytree(FIXTURE, folder)
    return folder


def _existing_db(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"previous snapshot")
    return path.read_bytes()


def _leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name not in ("cache.sqlite3", "snapshot.json"))


def _tiny_jlcparts_db(path: Path, fmt: str = "source-db-v2") -> None:
    db = sqlite3.connect(path)
    db.execute("create table meta (key text primary key not null, value text not null)")
    db.execute("insert into meta values ('format', ?)", (fmt,))
    db.execute("create table jlc_components (lcsc integer primary key, fetched_at integer not null)")
    db.execute("insert into jlc_components values (25900, 1761060000)")
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# installing
# ---------------------------------------------------------------------------

def test_installs_the_split_archive(tmp_path):
    target = tmp_path / "parts" / "cache.sqlite3"
    info = update_snapshot(target, base_url=_url(FIXTURE))

    data = target.read_bytes()
    assert (zlib.crc32(data), len(data)) == (FIXTURE_CRC, FIXTURE_SIZE)
    db = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    assert db.execute("select value from meta where key='format'").fetchone() == ("source-db-v2",)
    assert db.execute("select count(*) from jlc_components").fetchone() == (6,)

    assert info.path == target and info.components == 6
    assert sorted(info.parts) == sorted(PART_NAMES)
    assert info.oldest_row <= info.newest_row

    meta = json.loads((target.parent / "snapshot.json").read_text(encoding="utf-8"))
    assert meta["source"] == _url(FIXTURE)
    assert meta["crc32"] == f"{FIXTURE_CRC:08x}" and meta["size"] == FIXTURE_SIZE
    assert meta["components"] == 6 and meta["format"] == "source-db-v2"
    assert meta["oldest_row"] == info.oldest_row and meta["newest_row"] == info.newest_row
    assert _leftovers(target.parent) == []


def test_a_single_part_archive_installs(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    _tiny_jlcparts_db(tmp_path / "cache.sqlite3")
    with zipfile.ZipFile(served / "cache.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp_path / "cache.sqlite3", "cache.sqlite3")
    info = update_snapshot(tmp_path / "out" / "cache.sqlite3", base_url=_url(served))
    assert info.parts == ["cache.zip"] and info.components == 1


def test_a_second_update_replaces_the_first(tmp_path):
    target = tmp_path / "cache.sqlite3"
    _existing_db(target)
    update_snapshot(target, base_url=_url(FIXTURE))
    assert zlib.crc32(target.read_bytes()) == FIXTURE_CRC


# ---------------------------------------------------------------------------
# failures keep the old database and leave nothing behind
# ---------------------------------------------------------------------------

def test_a_missing_part_fails_and_keeps_the_old_database(tmp_path):
    served = _copy_fixture(tmp_path)
    (served / "cache.z05").unlink()
    target = tmp_path / "parts" / "cache.sqlite3"
    before = _existing_db(target)
    with pytest.raises(SnapshotError, match="cache.z05"):
        update_snapshot(target, base_url=_url(served))
    assert target.read_bytes() == before
    assert _leftovers(target.parent) == []


def test_a_corrupt_part_fails_and_keeps_the_old_database(tmp_path):
    served = _copy_fixture(tmp_path)
    part = bytearray((served / "cache.z03").read_bytes())
    part[1000] ^= 0xFF
    (served / "cache.z03").write_bytes(bytes(part))
    target = tmp_path / "parts" / "cache.sqlite3"
    before = _existing_db(target)
    with pytest.raises(SnapshotError):
        update_snapshot(target, base_url=_url(served))
    assert target.read_bytes() == before
    assert _leftovers(target.parent) == []


def test_a_flipped_byte_in_stored_data_is_caught_by_the_crc(tmp_path):
    """Stored (uncompressed) data decompresses fine when damaged; only the CRC check catches it."""
    served = tmp_path / "served"
    served.mkdir()
    _tiny_jlcparts_db(tmp_path / "cache.sqlite3")
    with zipfile.ZipFile(served / "cache.zip", "w", zipfile.ZIP_STORED) as z:
        z.write(tmp_path / "cache.sqlite3", "cache.sqlite3")
    archive = bytearray((served / "cache.zip").read_bytes())
    archive[30 + len("cache.sqlite3") + 2000] ^= 0xFF       # inside the stored file data
    (served / "cache.zip").write_bytes(bytes(archive))
    target = tmp_path / "out" / "cache.sqlite3"
    before = _existing_db(target)
    with pytest.raises(SnapshotError, match="CRC"):
        update_snapshot(target, base_url=_url(served))
    assert target.read_bytes() == before


def test_an_archive_without_cache_sqlite3_fails(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    _tiny_jlcparts_db(tmp_path / "other.db")
    with zipfile.ZipFile(served / "cache.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp_path / "other.db", "other.db")
    with pytest.raises(SnapshotError, match="cache.sqlite3"):
        update_snapshot(tmp_path / "out" / "cache.sqlite3", base_url=_url(served))


def test_a_database_in_another_format_fails(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    _tiny_jlcparts_db(tmp_path / "cache.sqlite3", fmt="something-else")
    with zipfile.ZipFile(served / "cache.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp_path / "cache.sqlite3", "cache.sqlite3")
    target = tmp_path / "out" / "cache.sqlite3"
    before = _existing_db(target)
    with pytest.raises(SnapshotError, match="source-db-v2"):
        update_snapshot(target, base_url=_url(served))
    assert target.read_bytes() == before
    assert _leftovers(target.parent) == []


def test_not_a_zip_fails(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    (served / "cache.zip").write_bytes(b"<html>rate limited</html>")
    with pytest.raises(SnapshotError):
        update_snapshot(tmp_path / "out" / "cache.sqlite3", base_url=_url(served))


def test_a_network_error_is_a_snapshot_error(tmp_path):
    class Down:
        def fetch(self, url, dest):
            raise OSError("network down")

    with pytest.raises(SnapshotError, match="network down"):
        update_snapshot(tmp_path / "cache.sqlite3", base_url="https://example.invalid/data", transport=Down())


# ---------------------------------------------------------------------------
# where things come from
# ---------------------------------------------------------------------------

def test_database_path_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_PARTS_DB", str(tmp_path / "x" / "cache.sqlite3"))
    assert default_db_path() == tmp_path / "x" / "cache.sqlite3"


def test_default_database_path_is_in_the_user_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("REFLOW_PARTS_DB", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_db_path() == tmp_path / ".cache" / "reflow" / "jlcparts" / "cache.sqlite3"


def test_base_url_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("REFLOW_PARTS_URL", _url(FIXTURE))
    assert update_snapshot(tmp_path / "cache.sqlite3").components == 6


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

def test_reflow_parts_update_installs_and_reports(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_PARTS_URL", _url(FIXTURE))
    target = tmp_path / "cache.sqlite3"
    assert cli.main(["parts", "update", "--db", str(target)]) == 0
    out = capsys.readouterr().out
    assert str(target) in out and "6 parts" in out
    assert target.is_file()


def test_reflow_parts_update_failure_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REFLOW_PARTS_URL", _url(tmp_path / "nothing-here"))
    assert cli.main(["parts", "update", "--db", str(tmp_path / "cache.sqlite3")]) == 2
    assert "reflow:" in capsys.readouterr().err
