import csv
import io

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app import db
from app.logs import logger

router = APIRouter(tags=["words"])


class WordIn(BaseModel):
    kanji: str = ""
    kana: str
    ru: str
    source: str = "custom"
    level: str = ""
    pos: str = ""


@router.get("/words")
async def list_words(q: str = "", source: str = "", level: str = "", limit: int = 200):
    conn = await db.get_db()
    sql = "SELECT * FROM words WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (kanji LIKE ? OR kana LIKE ? OR ru LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if source:
        sql += " AND source = ?"
        params.append(source)
    if level:
        sql += " AND level = ?"
        params.append(level)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(min(limit, 1000))
    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("/words")
async def add_word(body: WordIn):
    if not body.kana.strip() or not body.ru.strip():
        raise HTTPException(400, "kana и ru обязательны")
    conn = await db.get_db()
    cur = await conn.execute(
        """INSERT OR IGNORE INTO words (kanji, kana, ru, source, level, pos)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (body.kanji.strip(), body.kana.strip(), body.ru.strip(),
         body.source, body.level, body.pos),
    )
    await conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(409, "такое слово уже есть")
    return {"id": cur.lastrowid}


@router.delete("/words/{word_id}")
async def delete_word(word_id: int):
    conn = await db.get_db()
    cur = await conn.execute("DELETE FROM words WHERE id = ?", (word_id,))
    await conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "word not found")
    return {"deleted": word_id}


@router.post("/words/import")
async def import_csv(file: UploadFile, source: str = "custom", level: str = ""):
    """CSV с заголовком: kanji,kana,ru[,pos][,level]. Разделитель — запятая.

    Колонка level в файле имеет приоритет над query-параметром.
    """
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    required = {"kana", "ru"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise HTTPException(400, "нужны колонки kana и ru (плюс опционально kanji, pos, level)")

    conn = await db.get_db()
    added = skipped = 0
    for row in reader:
        kana = (row.get("kana") or "").strip()
        ru = (row.get("ru") or "").strip()
        if not kana or not ru:
            skipped += 1
            continue
        cur = await conn.execute(
            """INSERT OR IGNORE INTO words (kanji, kana, ru, source, level, pos)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (row.get("kanji") or "").strip(),
                kana, ru, source,
                (row.get("level") or level).strip(),
                (row.get("pos") or "").strip(),
            ),
        )
        if cur.rowcount:
            added += 1
        else:
            skipped += 1
    await conn.commit()
    logger.info("csv import: added=%s skipped=%s", added, skipped)
    return {"added": added, "skipped": skipped}
