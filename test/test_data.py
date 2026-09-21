"""Проверки целостности данных в data/ — ловят ошибки при правке контента."""
import json
from collections import Counter
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
WAGOTABI = BASE / "data" / "wagotabi"
FE = BASE / "data" / "fe"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


needs_wagotabi = pytest.mark.skipif(
    not (WAGOTABI / "words.json").exists(),
    reason="данные Wagotabi не выгружены (scripts/extract_wagotabi.py)")


@needs_wagotabi
def test_wagotabi_files_present():
    for name in ("lessons", "words", "sentences", "kanji", "radicals",
                 "conjugations", "grammar", "localization"):
        assert (WAGOTABI / f"{name}.json").exists(), name


@needs_wagotabi
def test_word_ids_are_unique_and_ordered():
    words = load(WAGOTABI / "words.json")
    ids = [w["id"] for w in words]
    assert len(ids) == len(set(ids))
    assert [w["order"] for w in words] == list(range(1, len(words) + 1))


@needs_wagotabi
def test_every_lesson_word_exists():
    words = {w["id"] for w in load(WAGOTABI / "words.json")}
    for lesson in load(WAGOTABI / "lessons.json"):
        for word_id in lesson["word_ids"]:
            assert word_id in words, f"{lesson['id']} ссылается на {word_id}"


@needs_wagotabi
def test_lessons_are_numbered_without_gaps():
    lessons = load(WAGOTABI / "lessons.json")
    assert [x["order"] for x in lessons] == list(range(1, len(lessons) + 1))
    assert len({x["id"] for x in lessons}) == len(lessons)


@needs_wagotabi
def test_sentence_blocks_rebuild_the_sentence():
    for sentence in load(WAGOTABI / "sentences.json"):
        joined = "".join(block["text"] for block in sentence["blocks"])
        assert joined == sentence["japanese"], sentence["id"]


@needs_wagotabi
def test_words_without_translation_stay_rare():
    """В данных игры есть записи вообще без перевода — их должно быть немного.

    Такие слова не попадают в задания «значение слова»: генератор их пропускает.
    """
    words = load(WAGOTABI / "words.json")
    without = [w["id"] for w in words if not (w["meaning_ru"] or w["meaning_en"])]
    assert len(without) <= 25, f"внезапно много слов без перевода: {len(without)}"


@needs_wagotabi
def test_untranslated_words_are_skipped_in_meaning_questions():
    import random

    from app.services import quiz

    words = load(WAGOTABI / "words.json")
    without = [w for w in words if not (w["meaning_ru"] or w["meaning_en"])]
    if not without:
        pytest.skip("все слова переведены")
    pool = quiz.Pool(words=without, sentences=[], conjugations=[], kanji=[],
                     all_words=words)
    for word in without:
        assert quiz.q_word_meaning(random.Random(0), word, pool) is None
        assert quiz.q_meaning_word(random.Random(0), word, pool) is None


# ---------------------------------------------------------------- FE

def test_fe_topics_are_consistent():
    topics = load(FE / "topics.json")
    assert [t["order"] for t in topics] == list(range(1, len(topics) + 1))
    assert len({t["id"] for t in topics}) == len(topics)
    assert all(t["area"] in {"exam", "technology", "management", "strategy"} for t in topics)
    assert all(t["title"] and t["summary"] for t in topics)


def test_every_topic_has_an_article():
    for topic in load(FE / "topics.json"):
        article = FE / "articles" / f"{topic['id']}.html"
        assert article.exists(), topic["id"]
        assert len(article.read_text(encoding="utf-8")) > 500, topic["id"]


def test_fe_questions_are_answerable():
    topics = {t["id"] for t in load(FE / "topics.json")}
    questions = load(FE / "questions.json")
    assert len({q["id"] for q in questions}) == len(questions)
    for question in questions:
        assert question["topic_id"] in topics, question["id"]
        assert question["answer"] in question["options"], question["id"]
        assert len(question["options"]) >= 3, question["id"]
        assert len(set(question["options"])) == len(question["options"]), question["id"]
        assert question["explanation"], question["id"]


def test_every_topic_has_questions_and_terms():
    topics = [t["id"] for t in load(FE / "topics.json")]
    by_question = Counter(q["topic_id"] for q in load(FE / "questions.json"))
    by_term = Counter(t["topic_id"] for t in load(FE / "terms.json"))
    for topic_id in topics:
        assert by_question[topic_id] >= 5, f"мало вопросов: {topic_id}"
        assert by_term[topic_id] >= 5, f"мало терминов: {topic_id}"


def test_fe_terms_are_filled():
    topics = {t["id"] for t in load(FE / "topics.json")}
    terms = load(FE / "terms.json")
    assert len({t["id"] for t in terms}) == len(terms)
    for term in terms:
        assert term["topic_id"] in topics, term["id"]
        assert term["ja"] and term["ru"], term["id"]
