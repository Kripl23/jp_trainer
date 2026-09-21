"""Ручные отметки «знаю / учу / трудное».

Статус ставит только пользователь: результаты тестов его не меняют, они лишь
копятся в attempt_log и показываются рядом как справка.
"""
from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite

STATUSES = ("new", "learning", "known", "hard")
STATUS_LABELS = {
    "new": "не отмечено",
    "learning": "учу",
    "known": "знаю",
    "hard": "трудное",
}
ITEM_TYPES = ("word", "kanji", "grammar", "conjugation", "sentence", "fe_term")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


async def set_mark(conn: aiosqlite.Connection, item_type: str, item_id: str,
                   status: str, note: str = "") -> dict:
    if item_type not in ITEM_TYPES:
        raise ValueError(f"неизвестный тип элемента: {item_type}")
    if status not in STATUSES:
        raise ValueError(f"неизвестный статус: {status}")
    if status == "new" and not note:
        await conn.execute("DELETE FROM marks WHERE item_type = ? AND item_id = ?",
                           (item_type, item_id))
        await conn.commit()
        return {"item_type": item_type, "item_id": item_id, "status": "new", "note": ""}
    await conn.execute(
        """INSERT INTO marks (item_type, item_id, status, note, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (item_type, item_id)
           DO UPDATE SET status = excluded.status, note = excluded.note,
                         updated_at = excluded.updated_at""",
        (item_type, item_id, status, note, _now()),
    )
    await conn.commit()
    return {"item_type": item_type, "item_id": item_id, "status": status, "note": note}


async def get_map(conn: aiosqlite.Connection, item_type: str) -> dict[str, dict]:
    cur = await conn.execute(
        "SELECT item_id, status, note FROM marks WHERE item_type = ?", (item_type,))
    return {r["item_id"]: {"status": r["status"], "note": r["note"]}
            for r in await cur.fetchall()}


async def counts(conn: aiosqlite.Connection, item_type: str, total: int) -> dict[str, int]:
    cur = await conn.execute(
        "SELECT status, COUNT(*) AS c FROM marks WHERE item_type = ? GROUP BY status",
        (item_type,))
    result = {s: 0 for s in STATUSES}
    for row in await cur.fetchall():
        result[row["status"]] = row["c"]
    result["new"] = max(0, total - sum(v for k, v in result.items() if k != "new"))
    return result


async def ids_with_status(conn: aiosqlite.Connection, item_type: str,
                          statuses: list[str]) -> list[str]:
    statuses = [s for s in statuses if s in STATUSES and s != "new"]
    if not statuses:
        return []
    marks = ",".join("?" * len(statuses))
    cur = await conn.execute(
        f"SELECT item_id FROM marks WHERE item_type = ? AND status IN ({marks})",
        [item_type, *statuses])
    return [r["item_id"] for r in await cur.fetchall()]


async def attempt_stats(conn: aiosqlite.Connection, item_type: str) -> dict[str, dict]:
    """Сколько раз элемент встречался в тестах и сколько раз был верным."""
    cur = await conn.execute(
        """SELECT item_id, COUNT(*) AS total, COALESCE(SUM(correct), 0) AS ok
           FROM attempt_log WHERE item_type = ? GROUP BY item_id""", (item_type,))
    return {r["item_id"]: {"total": r["total"], "ok": r["ok"]} for r in await cur.fetchall()}
