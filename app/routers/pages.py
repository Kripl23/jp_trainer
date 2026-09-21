"""HTML-страницы."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app import db
from app.services import content, marks, progress, quiz
from app.services.wagotabi_text import Context, furigana_html, plain, render

router = APIRouter(tags=["pages"])

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")
templates.env.filters["furigana"] = furigana_html
templates.env.filters["game_text"] = render
templates.env.filters["plain"] = plain


def plural(number: int, one: str, few: str, many: str) -> str:
    """1 слово, 2 слова, 5 слов."""
    number = abs(int(number))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


templates.env.filters["plural"] = plural

AREAS = {
    "exam": "Об экзамене",
    "technology": "Технологии (テクノロジ系)",
    "management": "Менеджмент (マネジメント系)",
    "strategy": "Стратегия (ストラテジ系)",
}


async def _render_context(conn) -> Context:
    """Справочники для подстановок внутри игровых текстов."""
    words = {w["id"]: w for w in await content.words(conn)}
    sentences = {s["id"]: s for s in await content.fetch(conn, "SELECT * FROM wg_sentence")}
    return Context(words=words, sentences=sentences, texts=await content.text_map(conn))


@router.get("/")
async def index(request: Request):
    conn = await db.get_db()
    lessons = await content.lessons_full(conn)
    lesson_progress = await progress.lesson_map(conn)
    chapters = progress.chapters(lessons, lesson_progress)
    current = progress.current_lesson(lessons, lesson_progress)
    total_words = (await content.fetch_one(conn, "SELECT COUNT(*) AS n FROM wg_word"))["n"]
    word_marks = await marks.counts(conn, "word", total_words)
    return templates.TemplateResponse(request, "index.html", {
        "chapters": chapters,
        "current": current,
        "done": sum(1 for x in lessons if lesson_progress.get(x["id"], {}).get("completed_at")),
        "total": len(lessons),
        "word_marks": word_marks,
        "total_words": total_words,
    })


@router.get("/lesson/{lesson_id}")
async def lesson_page(request: Request, lesson_id: str):
    conn = await db.get_db()
    lesson = await content.lesson(conn, lesson_id)
    if not lesson:
        raise HTTPException(404, "урок не найден")
    words = await content.words(conn, lesson_id)
    ids = [w["id"] for w in words]
    ctx = await _render_context(conn)
    state = (await progress.lesson_map(conn)).get(lesson_id, {})
    return templates.TemplateResponse(request, "lesson.html", {
        "lesson": lesson,
        "explanation": render(lesson["explanation_ru"] or lesson["explanation_en"], ctx),
        "words": words,
        "notes": {w["id"]: render(w["note_ru"], ctx) for w in words if w["note_ru"]},
        "grammar": [{**g, "note_html": render(g["note_ru"], ctx)}
                    for g in await content.grammar_for_lesson(conn, lesson_id)],
        "sentences": await content.sentences_for_words(conn, ids, limit=12),
        "conjugations": await content.conjugations_for_words(conn, ids),
        "kanji": await content.kanji_for_words(conn, ids),
        "marks": await marks.get_map(conn, "word"),
        "statuses": marks.STATUS_LABELS,
        "state": state,
        "form_names": quiz.FORM_NAMES,
    })


@router.get("/quiz")
async def quiz_page(request: Request, lesson: str = "", mode: str = "lesson"):
    conn = await db.get_db()
    title = "Тренировка"
    if lesson:
        row = await content.lesson(conn, lesson)
        if not row:
            raise HTTPException(404, "урок не найден")
        title = f'{row["id"]} · {row["title_ru"]}'
    elif mode == "marked":
        title = "Повторение отмеченного"
    elif mode == "all":
        title = "Всё пройденное"
    return templates.TemplateResponse(request, "quiz.html", {
        "lesson_id": lesson, "mode": mode, "title": title, "kinds": quiz.KINDS,
    })


@router.get("/dictionary")
async def dictionary_page(request: Request, word: str = ""):
    conn = await db.get_db()
    ctx = await _render_context(conn)
    words = await content.words(conn)
    return templates.TemplateResponse(request, "dictionary.html", {
        "words": words,
        "notes": {w["id"]: render(w["note_ru"], ctx) for w in words if w["note_ru"]},
        "marks": await marks.get_map(conn, "word"),
        "stats": await marks.attempt_stats(conn, "word"),
        "statuses": marks.STATUS_LABELS,
        "categories": sorted({w["category"] for w in words if w["category"]}),
        "focus": word,
    })


@router.get("/kanji")
async def kanji_page(request: Request):
    conn = await db.get_db()
    kanji = await content.fetch(conn, "SELECT * FROM wg_kanji ORDER BY ord")
    words = {w["id"]: w for w in await content.words(conn)}
    return templates.TemplateResponse(request, "kanji.html", {
        "kanji": kanji,
        "words": words,
        "marks": await marks.get_map(conn, "kanji"),
        "statuses": marks.STATUS_LABELS,
        "radicals": await content.fetch(conn, "SELECT * FROM wg_radical ORDER BY strokes"),
    })


@router.get("/grammar")
async def grammar_page(request: Request):
    conn = await db.get_db()
    ctx = await _render_context(conn)
    rows = await content.fetch(conn, "SELECT * FROM wg_grammar ORDER BY ord")
    lessons = {x["id"]: x for x in await content.lessons(conn)}
    explained = await content.fetch(
        conn, "SELECT * FROM wg_lesson WHERE explanation_ru <> '' ORDER BY ord")
    return templates.TemplateResponse(request, "grammar.html", {
        "rows": [{**g, "note_html": render(g["note_ru"], ctx),
                  "lesson": lessons.get(g["lesson_id"])} for g in rows],
        "explained": [{**x, "html": render(x["explanation_ru"] or x["explanation_en"], ctx)}
                      for x in explained],
        "marks": await marks.get_map(conn, "grammar"),
        "statuses": marks.STATUS_LABELS,
    })


@router.get("/stats")
async def stats_page(request: Request):
    return templates.TemplateResponse(request, "stats.html", {})


# ---------------------------------------------------------------- FE-экзамен


@router.get("/fe")
async def fe_index(request: Request):
    conn = await db.get_db()
    topics = await content.fetch(conn, "SELECT * FROM fe_topic ORDER BY ord")
    state = await progress.topic_map(conn)
    counts = await content.fetch(
        conn, "SELECT topic_id, COUNT(*) AS n FROM fe_question GROUP BY topic_id")
    question_count = {r["topic_id"]: r["n"] for r in counts}
    term_counts = await content.fetch(
        conn, "SELECT topic_id, COUNT(*) AS n FROM fe_term GROUP BY topic_id")
    terms_count = {r["topic_id"]: r["n"] for r in term_counts}

    areas: list[dict] = []
    for topic in topics:
        if not areas or areas[-1]["id"] != topic["area"]:
            areas.append({"id": topic["area"], "title": AREAS.get(topic["area"], topic["area"]),
                          "topics": []})
        areas[-1]["topics"].append({**topic, "state": state.get(topic["id"], {}),
                                    "questions": question_count.get(topic["id"], 0),
                                    "terms": terms_count.get(topic["id"], 0)})
    total_terms = sum(terms_count.values())
    return templates.TemplateResponse(request, "fe/index.html", {
        "areas": areas,
        "done": sum(1 for t in topics if state.get(t["id"], {}).get("completed_at")),
        "total": len(topics),
        "term_marks": await marks.counts(conn, "fe_term", total_terms),
        "total_terms": total_terms,
    })


@router.get("/fe/terms")
async def fe_terms(request: Request):
    conn = await db.get_db()
    terms = await content.fetch(conn, "SELECT * FROM fe_term ORDER BY ord")
    topics = {t["id"]: t for t in await content.fetch(conn, "SELECT * FROM fe_topic")}
    return templates.TemplateResponse(request, "fe/terms.html", {
        "terms": terms, "topics": topics,
        "marks": await marks.get_map(conn, "fe_term"),
        "statuses": marks.STATUS_LABELS,
    })


@router.get("/fe/quiz")
async def fe_quiz_page(request: Request, topic: str = "", mode: str = "topic"):
    conn = await db.get_db()
    title = "Тест"
    if topic:
        row = await content.fetch_one(conn, "SELECT * FROM fe_topic WHERE id = ?", (topic,))
        if not row:
            raise HTTPException(404, "тема не найдена")
        title = row["title"]
    elif mode == "terms":
        title = "Термины"
    elif mode == "all":
        title = "Все темы"
    return templates.TemplateResponse(request, "fe/quiz.html", {
        "topic_id": topic, "mode": mode, "title": title,
    })


@router.get("/fe/{topic_id}")
async def fe_topic(request: Request, topic_id: str):
    conn = await db.get_db()
    topic = await content.fetch_one(conn, "SELECT * FROM fe_topic WHERE id = ?", (topic_id,))
    if not topic:
        raise HTTPException(404, "тема не найдена")
    await progress.mark_topic_read(conn, topic_id)
    topics = await content.fetch(conn, "SELECT id, ord, title FROM fe_topic ORDER BY ord")
    position = next((i for i, t in enumerate(topics) if t["id"] == topic_id), 0)
    return templates.TemplateResponse(request, "fe/article.html", {
        "topic": topic,
        "area_title": AREAS.get(topic["area"], topic["area"]),
        "terms": await content.fetch(
            conn, "SELECT * FROM fe_term WHERE topic_id = ? ORDER BY ord", (topic_id,)),
        "questions": await content.fetch(
            conn, "SELECT COUNT(*) AS n FROM fe_question WHERE topic_id = ?", (topic_id,)),
        "marks": await marks.get_map(conn, "fe_term"),
        "statuses": marks.STATUS_LABELS,
        "state": (await progress.topic_map(conn)).get(topic_id, {}),
        "prev": topics[position - 1] if position > 0 else None,
        "next": topics[position + 1] if position + 1 < len(topics) else None,
    })
