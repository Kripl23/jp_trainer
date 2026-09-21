"""Доступ к учебным данным Wagotabi в БД."""
from __future__ import annotations

import json

import aiosqlite

JSON_FIELDS = {"blocks", "word_ids", "forms", "options"}


def row_to_dict(row: aiosqlite.Row) -> dict:
    data = dict(row)
    for key in JSON_FIELDS & data.keys():
        try:
            data[key] = json.loads(data[key] or "[]")
        except (TypeError, json.JSONDecodeError):
            data[key] = []
    if "tags" in data and isinstance(data["tags"], str):
        data["tags"] = [t for t in data["tags"].split(",") if t]
    if "on_readings" in data:
        data["on"] = [r for r in (data.pop("on_readings") or "").split("、") if r]
        data["kun"] = [r for r in (data.pop("kun_readings") or "").split("、") if r]
    return data


async def fetch(conn: aiosqlite.Connection, sql: str, params=()) -> list[dict]:
    cur = await conn.execute(sql, params)
    return [row_to_dict(r) for r in await cur.fetchall()]


async def fetch_one(conn: aiosqlite.Connection, sql: str, params=()) -> dict | None:
    rows = await fetch(conn, sql, params)
    return rows[0] if rows else None


async def lessons(conn) -> list[dict]:
    return await fetch(conn, "SELECT * FROM wg_lesson ORDER BY ord")


async def lesson(conn, lesson_id: str) -> dict | None:
    return await fetch_one(conn, "SELECT * FROM wg_lesson WHERE id = ?", (lesson_id,))


async def lessons_full(conn) -> list[dict]:
    """Уроки со списком слов — основа для прогресса и подбора заданий."""
    rows = await lessons(conn)
    cur = await conn.execute("SELECT id, lesson_id FROM wg_word ORDER BY ord")
    by_lesson: dict[str, list[str]] = {}
    for r in await cur.fetchall():
        by_lesson.setdefault(r["lesson_id"], []).append(r["id"])
    for row in rows:
        row["word_ids"] = by_lesson.get(row["id"], [])
        row["word_count"] = len(row["word_ids"])
    return rows


async def words(conn, lesson_id: str = "") -> list[dict]:
    if lesson_id:
        return await fetch(conn, "SELECT * FROM wg_word WHERE lesson_id = ? ORDER BY ord",
                           (lesson_id,))
    return await fetch(conn, "SELECT * FROM wg_word ORDER BY ord")


async def words_by_ids(conn, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return await fetch(conn, f"SELECT * FROM wg_word WHERE id IN ({marks}) ORDER BY ord", ids)


async def sentences_for_words(conn, ids: list[str], limit: int = 200) -> list[dict]:
    """Примеры, в которых встречаются указанные слова."""
    if not ids:
        return []
    rows = await fetch(conn, "SELECT * FROM wg_sentence ORDER BY ord")
    wanted = set(ids)
    return [s for s in rows if wanted & set(s["word_ids"])][:limit]


async def sentences_within(conn, allowed_ids: list[str], limit: int = 200) -> list[dict]:
    """Примеры, вся лексика которых входит в переданный набор слов."""
    if not allowed_ids:
        return []
    allowed = set(allowed_ids)
    rows = await fetch(conn, "SELECT * FROM wg_sentence ORDER BY ord")
    return [s for s in rows if s["word_ids"] and set(s["word_ids"]) <= allowed][:limit]


async def kanji_for_words(conn, ids: list[str]) -> list[dict]:
    rows = await fetch(conn, "SELECT * FROM wg_kanji ORDER BY ord")
    wanted = set(ids)
    return [k for k in rows if wanted & set(k["word_ids"])]


async def conjugations_for_words(conn, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return await fetch(
        conn, f"SELECT * FROM wg_conjugation WHERE word_id IN ({marks}) ORDER BY ord", ids)


async def grammar_for_lesson(conn, lesson_id: str) -> list[dict]:
    return await fetch(conn, "SELECT * FROM wg_grammar WHERE lesson_id = ? ORDER BY ord",
                       (lesson_id,))


async def text_map(conn) -> dict[str, dict]:
    cur = await conn.execute("SELECT key, ru, en FROM wg_text")
    return {r["key"]: {"ru": r["ru"], "en": r["en"]} for r in await cur.fetchall()}


async def item(conn, item_type: str, item_id: str) -> dict | None:
    """Элемент любого типа по идентификатору — для проверки ответов."""
    table = {
        "word": ("wg_word", "id"),
        "sentence": ("wg_sentence", "id"),
        "kanji": ("wg_kanji", "kanji"),
        "conjugation": ("wg_conjugation", "id"),
        "grammar": ("wg_grammar", "id"),
        "fe_term": ("fe_term", "id"),
    }.get(item_type)
    if not table:
        return None
    name, key = table
    return await fetch_one(conn, f"SELECT * FROM {name} WHERE {key} = ?", (item_id,))
