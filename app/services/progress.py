"""Прогресс по урокам и темам — как в игре: урок засчитывается за тест.

Уроки не блокируются: порядок игры задаёт последовательность, но открыть можно
любой. «Текущим» считается первый незавершённый.
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

PASS_PERCENT = 80  # порог, с которого урок считается пройденным


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


async def record(conn: aiosqlite.Connection, table: str, key_column: str,
                 key: str, percent: int) -> dict:
    cur = await conn.execute(f"SELECT * FROM {table} WHERE {key_column} = ?", (key,))
    row = await cur.fetchone()
    attempts = (row["attempts"] if row else 0) + 1
    best = max(percent, row["best_percent"] if row else 0)
    completed = (row["completed_at"] if row else "") or (
        _now() if percent >= PASS_PERCENT else "")
    if row:
        await conn.execute(
            f"""UPDATE {table} SET attempts = ?, best_percent = ?, last_percent = ?,
                completed_at = ?, updated_at = ? WHERE {key_column} = ?""",
            (attempts, best, percent, completed, _now(), key))
    else:
        await conn.execute(
            f"""INSERT INTO {table} ({key_column}, attempts, best_percent, last_percent,
                completed_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)""",
            (key, attempts, best, percent, completed, _now()))
    await conn.commit()
    return {"attempts": attempts, "best_percent": best, "last_percent": percent,
            "completed": bool(completed)}


async def record_lesson(conn, lesson_id: str, percent: int) -> dict:
    return await record(conn, "lesson_progress", "lesson_id", lesson_id, percent)


async def record_topic(conn, topic_id: str, percent: int) -> dict:
    return await record(conn, "topic_progress", "topic_id", topic_id, percent)


async def mark_topic_read(conn: aiosqlite.Connection, topic_id: str) -> None:
    await conn.execute(
        """INSERT INTO topic_progress (topic_id, read_at, updated_at) VALUES (?, ?, ?)
           ON CONFLICT (topic_id) DO UPDATE SET read_at = excluded.read_at,
                                                updated_at = excluded.updated_at""",
        (topic_id, _now(), _now()))
    await conn.commit()


async def lesson_map(conn: aiosqlite.Connection) -> dict[str, dict]:
    cur = await conn.execute("SELECT * FROM lesson_progress")
    return {r["lesson_id"]: dict(r) for r in await cur.fetchall()}


async def topic_map(conn: aiosqlite.Connection) -> dict[str, dict]:
    cur = await conn.execute("SELECT * FROM topic_progress")
    return {r["topic_id"]: dict(r) for r in await cur.fetchall()}


def chapters(lessons: list[dict], progress: dict[str, dict]) -> list[dict]:
    """Группировка уроков по главам с процентом прохождения."""
    out: list[dict] = []
    for lesson in lessons:
        if not out or out[-1]["title"] != lesson["chapter"]:
            out.append({"title": lesson["chapter"], "index": lesson["chapter_index"],
                        "lessons": [], "done": 0, "words": 0})
        chapter = out[-1]
        state = progress.get(lesson["id"], {})
        done = bool(state.get("completed_at"))
        chapter["lessons"].append({**lesson, "progress": state, "done": done})
        chapter["done"] += int(done)
        chapter["words"] += lesson["word_count"]
    for chapter in out:
        total = len(chapter["lessons"])
        chapter["total"] = total
        chapter["percent"] = round(chapter["done"] / total * 100) if total else 0
    return out


def current_lesson(lessons: list[dict], progress: dict[str, dict]) -> dict | None:
    for lesson in lessons:
        if not progress.get(lesson["id"], {}).get("completed_at"):
            return lesson
    return None


def unlocked_word_ids(lessons: list[dict], progress: dict[str, dict],
                      include_current: bool = True) -> list[str]:
    """Слова уроков, которые уже пройдены (плюс текущий) — как открытый словарь."""
    ids: list[str] = []
    reached_current = False
    for lesson in lessons:
        done = bool(progress.get(lesson["id"], {}).get("completed_at"))
        if done:
            ids += lesson.get("word_ids", [])
        elif include_current and not reached_current:
            ids += lesson.get("word_ids", [])
            reached_current = True
    return ids
