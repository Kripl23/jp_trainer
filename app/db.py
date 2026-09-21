from pathlib import Path

import aiosqlite

from app import settings

# Справочники (wg_* — Wagotabi, fe_* — 基本情報技術者試験) заливаются скриптом
# scripts/seed.py и при обновлении данных пересоздаются целиком.
# Пользовательские таблицы (marks, lesson_progress, topic_progress, attempt_log)
# скрипт не трогает.
SCHEMA = """
CREATE TABLE IF NOT EXISTS wg_lesson (
    id             TEXT PRIMARY KEY,
    ord            INTEGER NOT NULL,
    kind           TEXT NOT NULL,          -- words | conjugation | topic
    chapter        TEXT NOT NULL DEFAULT '',
    chapter_index  INTEGER NOT NULL DEFAULT 0,
    location       TEXT NOT NULL DEFAULT '',
    title_ru       TEXT NOT NULL DEFAULT '',
    title_en       TEXT NOT NULL DEFAULT '',
    explanation_ru TEXT NOT NULL DEFAULT '',
    explanation_en TEXT NOT NULL DEFAULT '',
    has_grammar    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wg_word (
    id          TEXT PRIMARY KEY,
    ord         INTEGER NOT NULL,
    word        TEXT NOT NULL,
    furigana    TEXT NOT NULL DEFAULT '',
    reading     TEXT NOT NULL DEFAULT '',
    meaning_ru  TEXT NOT NULL DEFAULT '',
    note_ru     TEXT NOT NULL DEFAULT '',
    meaning_en  TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    jlpt        TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '',
    is_grammar  INTEGER NOT NULL DEFAULT 0,
    lesson_id   TEXT NOT NULL DEFAULT '',
    synonym     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wg_sentence (
    id             TEXT PRIMARY KEY,
    ord            INTEGER NOT NULL,
    japanese       TEXT NOT NULL,
    blocks         TEXT NOT NULL DEFAULT '[]',   -- JSON: [{text, word_id}]
    word_ids       TEXT NOT NULL DEFAULT '[]',   -- JSON
    anchor_word_id TEXT NOT NULL DEFAULT '',
    ru             TEXT NOT NULL DEFAULT '',
    en             TEXT NOT NULL DEFAULT '',
    politeness     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wg_kanji (
    kanji         TEXT PRIMARY KEY,
    ord           INTEGER NOT NULL,
    meaning_ru    TEXT NOT NULL DEFAULT '',
    meaning_en    TEXT NOT NULL DEFAULT '',
    on_readings   TEXT NOT NULL DEFAULT '',
    kun_readings  TEXT NOT NULL DEFAULT '',
    strokes       TEXT NOT NULL DEFAULT '',
    grade         TEXT NOT NULL DEFAULT '',
    jlpt          TEXT NOT NULL DEFAULT '',
    decomposition TEXT NOT NULL DEFAULT '',
    resembling    TEXT NOT NULL DEFAULT '',
    word_ids      TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS wg_radical (
    radical    TEXT PRIMARY KEY,
    reading    TEXT NOT NULL DEFAULT '',
    meaning_ru TEXT NOT NULL DEFAULT '',
    meaning_en TEXT NOT NULL DEFAULT '',
    strokes    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS wg_conjugation (
    id         TEXT PRIMARY KEY,
    ord        INTEGER NOT NULL,
    kind       TEXT NOT NULL,              -- verb | adjective
    word       TEXT NOT NULL,
    furigana   TEXT NOT NULL DEFAULT '',
    reading    TEXT NOT NULL DEFAULT '',
    meaning_ru TEXT NOT NULL DEFAULT '',
    word_id    TEXT NOT NULL DEFAULT '',
    category   TEXT NOT NULL DEFAULT '',   -- godan | ichidan | irregular | i | na
    forms      TEXT NOT NULL DEFAULT '{}'  -- JSON
);

CREATE TABLE IF NOT EXISTS wg_grammar (
    id         TEXT PRIMARY KEY,
    ord        INTEGER NOT NULL,
    formation  TEXT NOT NULL,
    word_id    TEXT NOT NULL DEFAULT '',
    word       TEXT NOT NULL DEFAULT '',
    meaning_ru TEXT NOT NULL DEFAULT '',
    note_ru    TEXT NOT NULL DEFAULT '',
    lesson_id  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS wg_text (
    key TEXT PRIMARY KEY,
    ru  TEXT NOT NULL DEFAULT '',
    en  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fe_topic (
    id      TEXT PRIMARY KEY,
    ord     INTEGER NOT NULL,
    area    TEXT NOT NULL,                 -- technology | management | strategy | exam
    title   TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    body    TEXT NOT NULL DEFAULT ''       -- HTML статьи
);

CREATE TABLE IF NOT EXISTS fe_question (
    id          TEXT PRIMARY KEY,
    topic_id    TEXT NOT NULL,
    ord         INTEGER NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'choice',   -- choice | open
    question    TEXT NOT NULL,
    options     TEXT NOT NULL DEFAULT '[]',       -- JSON
    answer      TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fe_term (
    id       TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    ord      INTEGER NOT NULL,
    ja       TEXT NOT NULL DEFAULT '',
    kana     TEXT NOT NULL DEFAULT '',
    en       TEXT NOT NULL DEFAULT '',
    ru       TEXT NOT NULL DEFAULT '',
    note     TEXT NOT NULL DEFAULT ''
);

-- Пользовательские отметки: статус ставится вручную, автоматика его не меняет.
CREATE TABLE IF NOT EXISTS marks (
    item_type  TEXT NOT NULL,   -- word | kanji | grammar | conjugation | sentence | fe_term
    item_id    TEXT NOT NULL,
    status     TEXT NOT NULL,   -- known | learning | hard | new
    note       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (item_type, item_id)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id    TEXT PRIMARY KEY,
    attempts     INTEGER NOT NULL DEFAULT 0,
    best_percent INTEGER NOT NULL DEFAULT 0,
    last_percent INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topic_progress (
    topic_id     TEXT PRIMARY KEY,
    attempts     INTEGER NOT NULL DEFAULT 0,
    best_percent INTEGER NOT NULL DEFAULT 0,
    last_percent INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT NOT NULL DEFAULT '',
    read_at      TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempt_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    scope     TEXT NOT NULL,             -- jp | fe
    item_type TEXT NOT NULL DEFAULT '',
    item_id   TEXT NOT NULL DEFAULT '',
    kind      TEXT NOT NULL DEFAULT '',  -- тип задания
    correct   INTEGER NOT NULL,
    answer    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_wg_word_lesson ON wg_word (lesson_id);
CREATE INDEX IF NOT EXISTS idx_wg_word_ord ON wg_word (ord);
CREATE INDEX IF NOT EXISTS idx_wg_sentence_anchor ON wg_sentence (anchor_word_id);
CREATE INDEX IF NOT EXISTS idx_fe_question_topic ON fe_question (topic_id);
CREATE INDEX IF NOT EXISTS idx_fe_term_topic ON fe_term (topic_id);
CREATE INDEX IF NOT EXISTS idx_marks_status ON marks (item_type, status);
CREATE INDEX IF NOT EXISTS idx_attempt_ts ON attempt_log (ts);
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
