"""Сводная статистика по обеим частям тренажёра."""
from fastapi import APIRouter

from app import db
from app.services import content, marks, progress

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def stats(days: int = 30):
    conn = await db.get_db()

    cur = await conn.execute(
        """SELECT substr(ts, 1, 10) AS day, scope, COUNT(*) AS total,
                  COALESCE(SUM(correct), 0) AS ok
           FROM attempt_log WHERE ts >= datetime('now', ?)
           GROUP BY day, scope ORDER BY day""", (f"-{days} days",))
    daily = [dict(r) for r in await cur.fetchall()]

    cur = await conn.execute(
        """SELECT scope, COUNT(*) AS total, COALESCE(SUM(correct), 0) AS ok
           FROM attempt_log GROUP BY scope""")
    totals = {r["scope"]: {"total": r["total"], "ok": r["ok"]} for r in await cur.fetchall()}

    cur = await conn.execute(
        """SELECT kind, COUNT(*) AS total, COALESCE(SUM(correct), 0) AS ok
           FROM attempt_log WHERE scope = 'jp' GROUP BY kind ORDER BY total DESC""")
    by_kind = [dict(r) for r in await cur.fetchall()]

    lessons = await content.lessons_full(conn)
    lesson_state = await progress.lesson_map(conn)
    topics = await content.fetch(conn, "SELECT id FROM fe_topic")
    topic_state = await progress.topic_map(conn)

    total_words = (await content.fetch_one(conn, "SELECT COUNT(*) AS n FROM wg_word"))["n"]
    total_kanji = (await content.fetch_one(conn, "SELECT COUNT(*) AS n FROM wg_kanji"))["n"]
    total_grammar = (await content.fetch_one(conn, "SELECT COUNT(*) AS n FROM wg_grammar"))["n"]
    total_terms = (await content.fetch_one(conn, "SELECT COUNT(*) AS n FROM fe_term"))["n"]

    def accuracy(entry: dict) -> float:
        return round(entry["ok"] / entry["total"] * 100, 1) if entry.get("total") else 0.0

    return {
        "daily": daily,
        "totals": {k: {**v, "accuracy": accuracy(v)} for k, v in totals.items()},
        "by_kind": [{**k, "accuracy": accuracy(k)} for k in by_kind],
        "lessons": {
            "done": sum(1 for x in lessons if lesson_state.get(x["id"], {}).get("completed_at")),
            "total": len(lessons),
        },
        "topics": {
            "done": sum(1 for x in topics if topic_state.get(x["id"], {}).get("completed_at")),
            "total": len(topics),
        },
        "marks": {
            "word": await marks.counts(conn, "word", total_words),
            "kanji": await marks.counts(conn, "kanji", total_kanji),
            "grammar": await marks.counts(conn, "grammar", total_grammar),
            "fe_term": await marks.counts(conn, "fe_term", total_terms),
        },
        "chapters": [
            {"title": c["title"], "done": c["done"], "total": c["total"],
             "percent": c["percent"]}
            for c in progress.chapters(lessons, lesson_state)
        ],
    }
