"""The links and their click counts, kept in SQLite."""

import sqlite3

from shorty import config

_db = sqlite3.connect(config.DATABASE, check_same_thread=False)
_db.execute("CREATE TABLE IF NOT EXISTS links (code TEXT PRIMARY KEY, url TEXT NOT NULL, clicks INTEGER DEFAULT 0)")


def save(code: str, url: str) -> None:
    with _db:
        _db.execute("INSERT INTO links (code, url) VALUES (?, ?)", (code, url))


def find(code: str) -> str | None:
    row = _db.execute("SELECT url FROM links WHERE code = ?", (code,)).fetchone()
    return row[0] if row else None


def add_clicks(counts: dict[str, int]) -> None:
    with _db:
        _db.executemany("UPDATE links SET clicks = clicks + ? WHERE code = ?",
                        [(n, code) for code, n in counts.items()])
