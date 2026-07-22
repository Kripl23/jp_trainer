"""Колоды: уровни JLPT, уроки Minna no Nihongo, свои слова."""
from datetime import datetime, timezone

import aiosqlite

JLPT_ORDER = ["N5", "N4", "N3", "N2", "N1"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


async def list_decks(db: aiosqlite.Connection, direction: str) -> list[dict]:
    """Все колоды с количеством слов, due-карточек и новых слов."""
    now = _now_iso()
    cur = await db.execute(
        """
        SELECT w.source, w.level,
               COUNT(*) AS total,
               SUM(CASE WHEN p.word_id IS NOT NULL AND p.due_date <= ?
                        THEN 1 ELSE 0 END) AS due,
               SUM(CASE WHEN p.word_id IS NULL THEN 1 ELSE 0 END) AS new
        FROM words w
        LEFT JOIN srs_progress p
               ON p.word_id = w.id AND p.direction = ?
        GROUP BY w.source, w.level
        """,
        (now, direction),
    )
    rows = await cur.fetchall()

    def sort_key(r):
        if r["source"] == "jlpt":
            return (0, JLPT_ORDER.index(r["level"]) if r["level"] in JLPT_ORDER else 9)
        if r["source"] == "minna":
            return (1, int(r["level"]) if str(r["level"]).isdigit() else 999)
        return (2, 0)

    return [
        {
            "source": r["source"],
            "level": r["level"],
            "total": r["total"],
            "due": r["due"] or 0,
            "new": r["new"] or 0,
        }
        for r in sorted(rows, key=sort_key)
    ]
