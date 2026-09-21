"""Заливка справочников в БД: Wagotabi (data/wagotabi) и FE-экзамен (data/fe).

    .venv/bin/python scripts/seed.py

Справочные таблицы (wg_*, fe_*) пересоздаются целиком, пользовательские
(marks, lesson_progress, topic_progress, attempt_log) не трогаются.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app import settings  # noqa: E402
from app.db import SCHEMA  # noqa: E402

WAGOTABI = BASE / "data" / "wagotabi"
FE = BASE / "data" / "fe"


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def seed_wagotabi(conn: sqlite3.Connection) -> None:
    lessons = load(WAGOTABI / "lessons.json")
    if lessons is None:
        print("data/wagotabi/lessons.json не найден — пропускаю японскую часть")
        return

    conn.executescript("DELETE FROM wg_lesson; DELETE FROM wg_word; DELETE FROM wg_sentence;"
                       "DELETE FROM wg_kanji; DELETE FROM wg_radical;"
                       "DELETE FROM wg_conjugation; DELETE FROM wg_grammar; DELETE FROM wg_text;")

    conn.executemany(
        """INSERT INTO wg_lesson (id, ord, kind, chapter, chapter_index, location,
               title_ru, title_en, explanation_ru, explanation_en, has_grammar)
           VALUES (:id, :order, :kind, :chapter, :chapter_index, :location,
               :title_ru, :title_en, :explanation_ru, :explanation_en, :has_grammar)""",
        [{**x, "has_grammar": int(x["has_grammar"])} for x in lessons])
    print(f"  уроки: {len(lessons)}")

    words = load(WAGOTABI / "words.json") or []
    conn.executemany(
        """INSERT INTO wg_word (id, ord, word, furigana, reading, meaning_ru, note_ru,
               meaning_en, category, jlpt, tags, is_grammar, lesson_id, synonym)
           VALUES (:id, :order, :word, :furigana, :reading, :meaning_ru, :note_ru,
               :meaning_en, :category, :jlpt, :tags, :is_grammar, :lesson_id, :synonym)""",
        [{**x, "tags": ",".join(x["tags"]), "is_grammar": int(x["is_grammar"])} for x in words])
    print(f"  слова: {len(words)}")

    sentences = load(WAGOTABI / "sentences.json") or []
    conn.executemany(
        """INSERT INTO wg_sentence (id, ord, japanese, blocks, word_ids, anchor_word_id,
               ru, en, politeness)
           VALUES (:id, :order, :japanese, :blocks, :word_ids, :anchor_word_id,
               :ru, :en, :politeness)""",
        [{**x, "blocks": json.dumps(x["blocks"], ensure_ascii=False),
          "word_ids": json.dumps(x["word_ids"], ensure_ascii=False)} for x in sentences])
    print(f"  предложения: {len(sentences)}")

    kanji = load(WAGOTABI / "kanji.json") or []
    conn.executemany(
        """INSERT INTO wg_kanji (kanji, ord, meaning_ru, meaning_en, on_readings,
               kun_readings, strokes, grade, jlpt, decomposition, resembling, word_ids)
           VALUES (:kanji, :order, :meaning_ru, :meaning_en, :on_readings,
               :kun_readings, :strokes, :grade, :jlpt, :decomposition, :resembling,
               :word_ids)""",
        [{**x, "on_readings": "、".join(x["on"]), "kun_readings": "、".join(x["kun"]),
          "word_ids": json.dumps(x["word_ids"], ensure_ascii=False)} for x in kanji])
    print(f"  кандзи: {len(kanji)}")

    radicals = load(WAGOTABI / "radicals.json") or []
    conn.executemany(
        """INSERT INTO wg_radical (radical, reading, meaning_ru, meaning_en, strokes)
           VALUES (:radical, :reading, :meaning_ru, :meaning_en, :strokes)""", radicals)
    print(f"  ключи: {len(radicals)}")

    conjugations = load(WAGOTABI / "conjugations.json") or []
    conn.executemany(
        """INSERT INTO wg_conjugation (id, ord, kind, word, furigana, reading, meaning_ru,
               word_id, category, forms)
           VALUES (:id, :order, :kind, :word, :furigana, :reading, :meaning_ru,
               :word_id, :category, :forms)""",
        [{**x, "forms": json.dumps(x["forms"], ensure_ascii=False)} for x in conjugations])
    print(f"  спряжения: {len(conjugations)}")

    grammar = load(WAGOTABI / "grammar.json") or []
    conn.executemany(
        """INSERT INTO wg_grammar (id, ord, formation, word_id, word, meaning_ru,
               note_ru, lesson_id)
           VALUES (:id, :order, :formation, :word_id, :word, :meaning_ru,
               :note_ru, :lesson_id)""", grammar)
    print(f"  грамматика: {len(grammar)}")

    texts = load(WAGOTABI / "localization.json") or {}
    conn.executemany("INSERT INTO wg_text (key, ru, en) VALUES (?, ?, ?)",
                     [(k, v["ru"], v["en"]) for k, v in texts.items()])
    print(f"  тексты: {len(texts)}")


def seed_fe(conn: sqlite3.Connection) -> None:
    topics = load(FE / "topics.json")
    if topics is None:
        print("data/fe/topics.json не найден — пропускаю FE-часть")
        return
    conn.executescript("DELETE FROM fe_topic; DELETE FROM fe_question; DELETE FROM fe_term;")

    rows = []
    for topic in topics:
        body = topic.get("body")
        if body is None:
            article = FE / "articles" / f"{topic['id']}.html"
            body = article.read_text(encoding="utf-8") if article.exists() else ""
            if not body:
                print(f"    ! нет статьи для темы {topic['id']}")
        rows.append({**topic, "body": body})
    conn.executemany(
        """INSERT INTO fe_topic (id, ord, area, title, summary, body)
           VALUES (:id, :order, :area, :title, :summary, :body)""", rows)
    print(f"  темы: {len(rows)}")

    questions = load(FE / "questions.json") or []
    conn.executemany(
        """INSERT INTO fe_question (id, topic_id, ord, kind, question, options, answer,
               explanation)
           VALUES (:id, :topic_id, :order, :kind, :question, :options, :answer,
               :explanation)""",
        [{"kind": "choice", "explanation": "", **q,
          "options": json.dumps(q.get("options", []), ensure_ascii=False)}
         for q in questions])
    print(f"  вопросы: {len(questions)}")

    terms = load(FE / "terms.json") or []
    conn.executemany(
        """INSERT INTO fe_term (id, topic_id, ord, ja, kana, en, ru, note)
           VALUES (:id, :topic_id, :order, :ja, :kana, :en, :ru, :note)""",
        [{"kana": "", "note": "", "en": "", **t} for t in terms])
    print(f"  термины: {len(terms)}")


def main() -> None:
    db_path = Path(settings.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    print(f"БД: {db_path}")
    print("Wagotabi:")
    seed_wagotabi(conn)
    print("FE-экзамен:")
    seed_fe(conn)
    conn.commit()
    conn.close()
    print("готово")


if __name__ == "__main__":
    main()
