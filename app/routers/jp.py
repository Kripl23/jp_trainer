"""API японской части: подбор заданий, проверка ответов, отметки, прогресс."""
from __future__ import annotations

import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db, settings
from app.logs import logger
from app.services import content, marks, progress, quiz
from app.services.wagotabi_text import Context, render

router = APIRouter(tags=["japanese"])

DEFAULT_COUNT = settings.QUIZ_QUESTIONS
MAX_COUNT = 60


class AnswerIn(BaseModel):
    kind: str
    item_type: str
    item_id: str
    answer: str = ""
    slot: int | None = None
    form: str = ""


class CompleteIn(BaseModel):
    correct: int = 0
    total: int = 0


class MarkIn(BaseModel):
    item_type: str
    item_id: str
    status: str
    note: str = Field(default="", max_length=500)


async def _pool(conn, lesson_id: str, mode: str, statuses: list[str]) -> quiz.Pool:
    lessons = await content.lessons_full(conn)
    all_words = await content.words(conn)

    if lesson_id:
        words = [w for w in all_words if w["lesson_id"] == lesson_id]
    elif mode == "marked":
        wanted = set(await marks.ids_with_status(conn, "word", statuses or ["hard", "learning"]))
        words = [w for w in all_words if w["id"] in wanted]
    else:
        state = await progress.lesson_map(conn)
        ids = set(progress.unlocked_word_ids(lessons, state))
        words = [w for w in all_words if w["id"] in ids] or all_words

    if not words:
        return quiz.Pool([], [], [], [], all_words)

    horizon = max(w["ord"] for w in words)
    seen = [w for w in all_words if w["ord"] <= horizon] or all_words
    seen_ids = [w["id"] for w in seen]
    target_ids = [w["id"] for w in words]

    # предложения берём только из уже пройденной лексики, но с оглядкой на набор
    sentences = [s for s in await content.sentences_within(conn, seen_ids, limit=400)
                 if set(s["word_ids"]) & set(target_ids)]
    kanji = [k for k in await content.kanji_for_words(conn, target_ids)]
    conjugations = await content.conjugations_for_words(conn, target_ids)
    return quiz.Pool(words=words, sentences=sentences, conjugations=conjugations,
                     kanji=kanji, all_words=seen)


@router.get("/jp/quiz")
async def build_quiz(lesson_id: str = "", mode: str = "lesson", kinds: str = "",
                     count: int = DEFAULT_COUNT, statuses: str = ""):
    conn = await db.get_db()
    pool = await _pool(conn, lesson_id, mode,
                       [s for s in statuses.split(",") if s])
    selected = [k for k in kinds.split(",") if k in quiz.KINDS]
    questions = quiz.build(pool, selected, min(max(count, 1), MAX_COUNT),
                           seed=random.randrange(1 << 30))
    return {
        "questions": questions,
        "pool": {"words": len(pool.words), "sentences": len(pool.sentences),
                 "kanji": len(pool.kanji), "conjugations": len(pool.conjugations)},
    }


@router.post("/jp/answer")
async def check_answer(body: AnswerIn):
    if body.kind not in quiz.KINDS:
        raise HTTPException(400, "неизвестный тип задания")
    conn = await db.get_db()
    item = await content.item(conn, body.item_type, body.item_id)
    if item is None:
        raise HTTPException(404, "элемент не найден")

    extra = {"slot": body.slot if body.slot is not None else -1, "form": body.form}
    correct, expected = quiz.check(body.kind, item, body.answer, extra)

    await conn.execute(
        """INSERT INTO attempt_log (ts, scope, item_type, item_id, kind, correct, answer)
           VALUES (datetime('now'), 'jp', ?, ?, ?, ?, ?)""",
        (body.item_type, body.item_id, body.kind, int(correct), body.answer.strip()[:200]))
    await conn.commit()

    ctx = Context(words={item["id"]: item} if body.item_type == "word" else {},
                  texts=await content.text_map(conn))
    return {
        "correct": correct,
        "expected": expected,
        "explanation": quiz.explain(body.kind, item),
        "note": render(item.get("note_ru", ""), ctx) if body.item_type == "word" else "",
        "mark": (await marks.get_map(conn, body.item_type)).get(body.item_id, {}),
    }


@router.post("/jp/lesson/{lesson_id}/complete")
async def complete_lesson(lesson_id: str, body: CompleteIn):
    conn = await db.get_db()
    if not await content.lesson(conn, lesson_id):
        raise HTTPException(404, "урок не найден")
    percent = round(body.correct / body.total * 100) if body.total else 0
    result = await progress.record_lesson(conn, lesson_id, percent)
    logger.info("lesson %s: %s%% (%s/%s)", lesson_id, percent, body.correct, body.total)
    return {"percent": percent, **result, "pass_percent": progress.PASS_PERCENT}


@router.post("/marks")
async def set_mark(body: MarkIn):
    conn = await db.get_db()
    try:
        return await marks.set_mark(conn, body.item_type, body.item_id, body.status, body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/jp/words")
async def list_words(q: str = "", category: str = "", status: str = "",
                     lesson_id: str = "", limit: int = 500):
    conn = await db.get_db()
    words = await content.words(conn, lesson_id)
    mark_map = await marks.get_map(conn, "word")
    needle = q.strip().lower()
    result = []
    for word in words:
        if category and word["category"] != category:
            continue
        mark = mark_map.get(word["id"], {"status": "new", "note": ""})
        if status and mark["status"] != status:
            continue
        if needle and needle not in (
                f'{word["word"]}{word["reading"]}{word["meaning_ru"]}'.lower()):
            continue
        result.append({**word, "mark": mark})
        if len(result) >= limit:
            break
    return result
