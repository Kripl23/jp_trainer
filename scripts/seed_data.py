"""Заливка словарей из data/*.csv в БД. Идемпотентен (INSERT OR IGNORE).

Использование:
    .venv/bin/python scripts/seed_data.py
"""
import csv
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app import settings  # noqa: E402
from app.db import SCHEMA  # noqa: E402

# файл -> (source, level по умолчанию); level из колонки csv имеет приоритет
SEED_FILES = {
    "jlpt_n5.csv": ("jlpt", "N5"),
    "jlpt_n4.csv": ("jlpt", "N4"),
    "jlpt_n3.csv": ("jlpt", "N3"),
    "jlpt_n2.csv": ("jlpt", "N2"),
    "jlpt_n1.csv": ("jlpt", "N1"),
    "minna_lessons.csv": ("minna", ""),
}


def seed() -> None:
    db_path = Path(settings.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    total_added = 0
    for fname, (source, default_level) in SEED_FILES.items():
        path = BASE / "data" / fname
        if not path.exists():
            continue
        added = 0
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kana = (row.get("kana") or "").strip()
                ru = (row.get("ru") or "").strip()
                if not kana or not ru:
                    continue
                kanji = (row.get("kanji") or "").strip()
                if kanji == kana:  # катакана/хирагана без кандзи
                    kanji = ""
                level = (row.get("level") or default_level).strip()
                cur = conn.execute(
                    """INSERT OR IGNORE INTO words
                       (kanji, kana, ru, source, level, pos)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (kanji, kana, ru, source, level,
                     (row.get("pos") or "").strip()),
                )
                added += cur.rowcount
        conn.commit()
        total_added += added
        print(f"{fname}: +{added}")

    cur = conn.execute("SELECT COUNT(*) FROM words")
    print(f"добавлено: {total_added}, всего слов в БД: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    seed()
