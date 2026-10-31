# jlcparts-format snapshot fixture (P-04)

A tiny stand-in for the jlcparts `cache.zip` + `cache.zNN` download, in the
same format: one `cache.sqlite3` entry, split with `zip -s 64k` (so it starts
with the `PK\x07\x08` spanning marker, like the real archive).

Built 2026-10-21 from the real snapshot (`meta.format = source-db-v2`):
- the real table schema;
- 6 real `jlc_components` rows: C25900, C1525, C129490, C94847, C194710, C492412;
- a `padding` table of random bytes so the archive spans six 64 KiB parts.

Uncompressed `cache.sqlite3`: 401408 bytes. The CRC is stored in the archive.
The jlcparts project is MIT-licensed; its parts data is scraped from JLCPCB's
public catalogue, with no separate licence stated.
