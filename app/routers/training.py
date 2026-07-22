from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, settings
from app.logs import logger
from app.services import checker
from app.services.srs import SrsState, iso, now_utc, review

router = APIRouter(tags=["training"])

DIRECTIONS = ("ru_jp", "jp_ru")


class AnswerIn(BaseModel):
    word_id: int
    direction: str
    answer: str


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _new_words_used_today(conn, direction: str) -> int:
    cur = await conn.execute(
        "SELECT COUNT(*) AS c FROM srs_progress WHERE direction = ? AND first_seen = ?",
        (direction, _today()),
    )
    row = await cur.fetchone()
    return row["c"]


def _card_payload(word, direction: str, due_left: int, new_left: int) -> dict:
    if direction == "ru_jp":
        prompt = word["ru"]
    else:
        prompt = word["kanji"] or word["kana"]
    return {
        "word_id": word["id"],
        "direction": direction,
        "prompt": prompt,
        "kana_hint": word["kana"] if direction == "jp_ru" and word["kanji"] else "",
        "pos": word["pos"],
        "due_left": due_left,
        "new_left": new_left,
    }


@router.get("/session/next")
async def next_card(source: str, level: str, direction: str):
    if direction not in DIRECTIONS:
        raise HTTPException(400, "bad direction")
    conn = await db.get_db()
    now = iso(now_utc())

    cur = await conn.execute(
        """
        SELECT w.*, p.due_date FROM words w
        JOIN srs_progress p ON p.word_id = w.id AND p.direction = ?
        WHERE w.source = ? AND w.level = ? AND p.due_date <= ?
        ORDER BY p.due_date LIMIT 1
        """,
        (direction, source, level, now),
    )
    word = await cur.fetchone()

    cur = await conn.execute(
        """
        SELECT COUNT(*) AS c FROM words w
        JOIN srs_progress p ON p.word_id = w.id AND p.direction = ?
        WHERE w.source = ? AND w.level = ? AND p.due_date <= ?
        """,
        (direction, source, level, now),
    )
    due_left = (await cur.fetchone())["c"]

    used = await _new_words_used_today(conn, direction)
    new_quota = max(0, settings.NEW_WORDS_PER_DAY - used)
    new_left = 0
    if new_quota:
        cur = await conn.execute(
            """
            SELECT COUNT(*) AS c FROM words w
            WHERE w.source = ? AND w.level = ?
              AND NOT EXISTS (SELECT 1 FROM srs_progress p
                              WHERE p.word_id = w.id AND p.direction = ?)
            """,
            (source, level, direction),
        )
        new_left = min(new_quota, (await cur.fetchone())["c"])

    if word is None and new_left:
        cur = await conn.execute(
            """
            SELECT w.* FROM words w
            WHERE w.source = ? AND w.level = ?
              AND NOT EXISTS (SELECT 1 FROM srs_progress p
                              WHERE p.word_id = w.id AND p.direction = ?)
            ORDER BY w.id LIMIT 1
            """,
            (source, level, direction),
        )
        word = await cur.fetchone()

    if word is None:
        return {"done": True, "due_left": 0, "new_left": 0}
    return {"done": False, **_card_payload(word, direction, due_left, new_left)}


@router.post("/session/answer")
async def submit_answer(body: AnswerIn):
    if body.direction not in DIRECTIONS:
        raise HTTPException(400, "bad direction")
    conn = await db.get_db()

    cur = await conn.execute("SELECT * FROM words WHERE id = ?", (body.word_id,))
    word = await cur.fetchone()
    if word is None:
        raise HTTPException(404, "word not found")

    if body.direction == "jp_ru":
        correct = checker.check_jp_to_ru(body.answer, word["ru"])
    else:
        correct = checker.check_ru_to_jp(body.answer, word["kana"], word["kanji"])

    cur = await conn.execute(
        "SELECT * FROM srs_progress WHERE word_id = ? AND direction = ?",
        (body.word_id, body.direction),
    )
    prog = await cur.fetchone()
    state = SrsState(
        repetitions=prog["repetitions"] if prog else 0,
        ease_factor=prog["ease_factor"] if prog else 2.5,
        interval_days=prog["interval_days"] if prog else 0.0,
        lapses=prog["lapses"] if prog else 0,
    )
    new_state = review(state, correct)

    now = now_utc()
    if prog is None:
        await conn.execute(
            """INSERT INTO srs_progress
               (word_id, direction, repetitions, ease_factor, interval_days,
                due_date, lapses, first_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                body.word_id, body.direction, new_state.repetitions,
                new_state.ease_factor, new_state.interval_days,
                new_state.due_date, new_state.lapses, _today(),
            ),
        )
    else:
        await conn.execute(
            """UPDATE srs_progress
               SET repetitions = ?, ease_factor = ?, interval_days = ?,
                   due_date = ?, lapses = ?
               WHERE word_id = ? AND direction = ?""",
            (
                new_state.repetitions, new_state.ease_factor,
                new_state.interval_days, new_state.due_date, new_state.lapses,
                body.word_id, body.direction,
            ),
        )
    await conn.execute(
        "INSERT INTO review_log (word_id, direction, ts, correct, answer) "
        "VALUES (?, ?, ?, ?, ?)",
        (body.word_id, body.direction, iso(now), int(correct), body.answer.strip()),
    )
    await conn.commit()
    logger.info(
        "review word=%s dir=%s correct=%s", body.word_id, body.direction, correct
    )

    return {
        "correct": correct,
        "kanji": word["kanji"],
        "kana": word["kana"],
        "ru": word["ru"],
        "next_due": new_state.due_date,
    }
