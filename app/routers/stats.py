from fastapi import APIRouter

from app import db
from app.services.decks import list_decks

router = APIRouter(tags=["stats"])

LEARNED_REPETITIONS = 3  # слово считается выученным после 3 верных подряд


@router.get("/decks")
async def decks(direction: str = "jp_ru"):
    conn = await db.get_db()
    return await list_decks(conn, direction)


@router.get("/stats")
async def stats(days: int = 30):
    conn = await db.get_db()

    cur = await conn.execute(
        """
        SELECT substr(ts, 1, 10) AS day,
               COUNT(*) AS reviews,
               SUM(correct) AS correct
        FROM review_log
        WHERE ts >= datetime('now', ?)
        GROUP BY day ORDER BY day
        """,
        (f"-{days} days",),
    )
    daily = [dict(r) for r in await cur.fetchall()]

    cur = await conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(correct), 0) AS ok FROM review_log"
    )
    totals = await cur.fetchone()

    cur = await conn.execute(
        "SELECT direction, COUNT(*) AS c FROM srs_progress "
        "WHERE repetitions >= ? GROUP BY direction",
        (LEARNED_REPETITIONS,),
    )
    learned = {r["direction"]: r["c"] for r in await cur.fetchall()}

    cur = await conn.execute("SELECT COUNT(*) AS c FROM words")
    total_words = (await cur.fetchone())["c"]

    return {
        "daily": daily,
        "total_reviews": totals["c"],
        "total_correct": totals["ok"],
        "accuracy": round(totals["ok"] / totals["c"] * 100, 1) if totals["c"] else 0,
        "learned": learned,
        "total_words": total_words,
    }
