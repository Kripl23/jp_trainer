from pathlib import Path

import aiosqlite

from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kanji   TEXT NOT NULL DEFAULT '',
    kana    TEXT NOT NULL,
    ru      TEXT NOT NULL,
    source  TEXT NOT NULL DEFAULT 'custom',   -- jlpt | minna | custom
    level   TEXT NOT NULL DEFAULT '',          -- N5..N1 или номер урока
    pos     TEXT NOT NULL DEFAULT '',
    UNIQUE (kana, kanji, source, level)
);

CREATE TABLE IF NOT EXISTS srs_progress (
    word_id      INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    direction    TEXT NOT NULL,                -- ru_jp | jp_ru
    repetitions  INTEGER NOT NULL DEFAULT 0,
    ease_factor  REAL NOT NULL DEFAULT 2.5,
    interval_days REAL NOT NULL DEFAULT 0,
    due_date     TEXT NOT NULL,                -- ISO datetime UTC
    lapses       INTEGER NOT NULL DEFAULT 0,
    first_seen   TEXT NOT NULL,                -- ISO date, для лимита новых слов
    PRIMARY KEY (word_id, direction)
);

CREATE TABLE IF NOT EXISTS review_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id   INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
    direction TEXT NOT NULL,
    ts        TEXT NOT NULL,
    correct   INTEGER NOT NULL,
    answer    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_srs_due ON srs_progress (direction, due_date);
CREATE INDEX IF NOT EXISTS idx_words_deck ON words (source, level);
CREATE INDEX IF NOT EXISTS idx_log_ts ON review_log (ts);
"""

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(settings.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.executescript(SCHEMA)
        await _db.commit()
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None
