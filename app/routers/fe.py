"""API подготовки к 基本情報技術者試験: тесты по темам и термины."""
from __future__ import annotations

import random
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import db, settings
from app.logs import logger
from app.services import content, marks, progress

router = APIRouter(tags=["fe"])

DEFAULT_COUNT = settings.QUIZ_QUESTIONS
MAX_COUNT = 60


class AnswerIn(BaseModel):
    kind: str = "choice"
    item_id: str
    answer: str = ""
    direction: str = "ja_ru"


class CompleteIn(BaseModel):
    correct: int = 0
    total: int = 0


def _normalize(text: str) -> str:
    text = (text or "").strip().lower().replace("ё", "е")
    text = re.sub(r"[^\w\s%.,/+-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _term_question(rng: random.Random, term: dict, pool: list[dict], direction: str) -> dict:
    """Вопрос по термину: японское слово -> русское значение или наоборот."""
    if direction == "ru_ja":
        prompt, correct, others = term["ru"], term["ja"], [t["ja"] for t in pool]
    else:
        prompt, correct, others = term["ja"], term["ru"], [t["ru"] for t in pool]
    if not prompt or not correct:
        return {}
    wrong = [o for o in dict.fromkeys(others) if o and o != correct]
    rng.shuffle(wrong)
    wrong = wrong[:3]
    if len(wrong) < 2:
        return {}
    options = [correct] + wrong
    rng.shuffle(options)
    return {
        "kind": "term",
        "item_id": term["id"],
        "direction": direction,
        "question": prompt,
        "sub": term["kana"] if direction == "ja_ru" else "",
        "options": options,
        "topic_id": term["topic_id"],
    }


@router.get("/fe/quiz")
async def build_quiz(topic: str = "", mode: str = "topic", count: int = DEFAULT_COUNT,
                     statuses: str = "", direction: str = "ja_ru"):
    conn = await db.get_db()
    rng = random.Random()
    count = min(max(count, 1), MAX_COUNT)

    if mode == "terms":
        terms = await content.fetch(
            conn, "SELECT * FROM fe_term WHERE (? = '' OR topic_id = ?) ORDER BY ord",
            (topic, topic))
        wanted = [s for s in statuses.split(",") if s]
        if wanted:
            allowed = set(await marks.ids_with_status(conn, "fe_term", wanted))
            terms = [t for t in terms if t["id"] in allowed]
        everything = await content.fetch(conn, "SELECT * FROM fe_term")
        rng.shuffle(terms)
        questions = []
        for term in terms:
            if len(questions) >= count:
                break
            q = _term_question(rng, term, everything, direction)
            if q:
                q["n"] = len(questions) + 1
                questions.append(q)
        return {"questions": questions, "mode": "terms"}

    rows = await content.fetch(
        conn,
        "SELECT * FROM fe_question WHERE (? = '' OR topic_id = ?) ORDER BY ord",
        (topic, topic))
    if topic:
        questions = rows[:count]
    else:
        rng.shuffle(rows)
        questions = rows[:count]
    out = []
    for n, row in enumerate(questions, 1):
        options = list(row["options"])
        rng.shuffle(options)
        out.append({"kind": row["kind"], "item_id": row["id"], "n": n,
                    "question": row["question"], "options": options,
                    "topic_id": row["topic_id"]})
    return {"questions": out, "mode": "topic"}


@router.post("/fe/answer")
async def check_answer(body: AnswerIn):
    conn = await db.get_db()
    if body.kind == "term":
        term = await content.fetch_one(conn, "SELECT * FROM fe_term WHERE id = ?", (body.item_id,))
        if not term:
            raise HTTPException(404, "термин не найден")
        expected = term["ja"] if body.direction == "ru_ja" else term["ru"]
        correct = _normalize(body.answer) == _normalize(expected)
        explanation = " · ".join(x for x in [term["ja"], term["kana"], term["en"],
                                             term["ru"], term["note"]] if x)
        item_type, topic_id = "fe_term", term["topic_id"]
    else:
        row = await content.fetch_one(
            conn, "SELECT * FROM fe_question WHERE id = ?", (body.item_id,))
        if not row:
            raise HTTPException(404, "вопрос не найден")
        expected = row["answer"]
        correct = _normalize(body.answer) == _normalize(expected)
        explanation = row["explanation"]
        item_type, topic_id = "fe_question", row["topic_id"]

    await conn.execute(
        """INSERT INTO attempt_log (ts, scope, item_type, item_id, kind, correct, answer)
           VALUES (datetime('now'), 'fe', ?, ?, ?, ?, ?)""",
        (item_type, body.item_id, body.kind, int(correct), body.answer.strip()[:200]))
    await conn.commit()
    return {"correct": correct, "expected": expected, "explanation": explanation,
            "topic_id": topic_id,
            "mark": (await marks.get_map(conn, "fe_term")).get(body.item_id, {})}


@router.post("/fe/topic/{topic_id}/complete")
async def complete_topic(topic_id: str, body: CompleteIn):
    conn = await db.get_db()
    if not await content.fetch_one(conn, "SELECT id FROM fe_topic WHERE id = ?", (topic_id,)):
        raise HTTPException(404, "тема не найдена")
    percent = round(body.correct / body.total * 100) if body.total else 0
    result = await progress.record_topic(conn, topic_id, percent)
    logger.info("fe topic %s: %s%%", topic_id, percent)
    return {"percent": percent, **result, "pass_percent": progress.PASS_PERCENT}


@router.get("/fe/terms")
async def list_terms(q: str = "", topic: str = "", status: str = "", limit: int = 500):
    conn = await db.get_db()
    terms = await content.fetch(
        conn, "SELECT * FROM fe_term WHERE (? = '' OR topic_id = ?) ORDER BY ord", (topic, topic))
    mark_map = await marks.get_map(conn, "fe_term")
    needle = q.strip().lower()
    out = []
    for term in terms:
        mark = mark_map.get(term["id"], {"status": "new", "note": ""})
        if status and mark["status"] != status:
            continue
        if needle and needle not in (
                f'{term["ja"]}{term["kana"]}{term["en"]}{term["ru"]}'.lower()):
            continue
        out.append({**term, "mark": mark})
        if len(out) >= limit:
            break
    return out
