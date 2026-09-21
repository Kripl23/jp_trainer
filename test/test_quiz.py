import pytest

from app.services import quiz


def word(wid, jp, furigana="", reading="", meaning="", category="noun"):
    return {"id": wid, "word": jp, "furigana": furigana, "reading": reading,
            "meaning_ru": meaning, "meaning_en": "", "category": category,
            "note_ru": "", "ord": int(wid[1:])}


WORDS = [
    word("K001", "です", meaning="быть", category="verb"),
    word("K002", "わかる", "分[わ]かる", "わかる", "понимать", "verb"),
    word("K003", "公園", "公[こう]園[えん]", "こうえん", "парк"),
    word("K004", "は", meaning="частица темы", category="particle"),
    word("K005", "を", meaning="частица дополнения", category="particle"),
    word("K006", "に", meaning="частица направления", category="particle"),
    word("K007", "天気", "天[てん]気[き]", "てんき", "погода"),
]

SENTENCE = {
    "id": "1",
    "japanese": "公園はきれいです。",
    "blocks": [{"text": "公園", "word_id": "K003"}, {"text": "は", "word_id": "K004"},
               {"text": "きれい", "word_id": ""}, {"text": "です", "word_id": "K001"},
               {"text": "。", "word_id": ""}],
    "word_ids": ["K003", "K004", "K001"],
    "ru": "Парк красивый.",
    "en": "The park is beautiful.",
}

CONJUGATION = {
    "id": "verb-1", "word": "わかる", "furigana": "分[わ]かる", "category": "godan",
    "meaning_ru": "понимать", "word_id": "K002",
    "forms": {"Stem": "わかり", "NonpastPolitePositive": "わかります",
              "NonpastPlainPositive": "わかる", "PastPlainPositive": "わかった"},
}

KANJI = [
    {"kanji": "公", "meaning_ru": "общественный", "meaning_en": "public",
     "on": ["こう"], "kun": [], "word_ids": ["K003"]},
    {"kanji": "園", "meaning_ru": "сад", "meaning_en": "garden",
     "on": ["えん"], "kun": ["その"], "word_ids": ["K003"]},
    {"kanji": "天", "meaning_ru": "небо", "meaning_en": "heaven",
     "on": ["てん"], "kun": [], "word_ids": ["K007"]},
    {"kanji": "気", "meaning_ru": "дух", "meaning_en": "spirit",
     "on": ["き"], "kun": [], "word_ids": ["K007"]},
]


@pytest.fixture
def pool():
    return quiz.Pool(words=WORDS, sentences=[SENTENCE], conjugations=[CONJUGATION],
                     kanji=KANJI, all_words=WORDS)


def test_build_returns_requested_number(pool):
    questions = quiz.build(pool, [], count=6, seed=1)
    assert len(questions) == 6
    assert all(q["kind"] in quiz.KINDS for q in questions)
    assert [q["n"] for q in questions] == [1, 2, 3, 4, 5, 6]


def test_build_respects_kind_filter(pool):
    questions = quiz.build(pool, ["word_meaning"], count=5, seed=2)
    assert questions
    assert {q["kind"] for q in questions} == {"word_meaning"}


def test_build_never_leaks_the_answer(pool):
    for question in quiz.build(pool, [], count=20, seed=3):
        assert "answer" not in question
        assert "expected" not in question


def test_multiple_choice_has_four_unique_options(pool):
    for question in quiz.build(pool, ["word_meaning", "meaning_word"], count=10, seed=4):
        assert len(question["options"]) == 4
        assert len(set(question["options"])) == 4


def test_check_word_meaning():
    item = WORDS[1]
    assert quiz.check("word_meaning", item, "понимать", {})[0]
    assert not quiz.check("word_meaning", item, "парк", {})[0]


def test_check_reading_accepts_katakana():
    item = WORDS[2]
    ok, expected = quiz.check("reading_write", item, "コウエン", {})
    assert ok and expected == "こうえん"


def test_check_sentence_order_ignores_punctuation():
    ok, expected = quiz.check("sentence_order", SENTENCE, "公園はきれいです", {})
    assert ok
    assert expected == "公園はきれいです"
    assert not quiz.check("sentence_order", SENTENCE, "きれい公園はです", {})[0]


def test_check_particle_uses_slot():
    ok, expected = quiz.check("particle", SENTENCE, "は", {"slot": 1})
    assert ok and expected == "は"
    assert not quiz.check("particle", SENTENCE, "を", {"slot": 1})[0]


def test_check_conjugation_uses_requested_form():
    ok, expected = quiz.check("conjugation", CONJUGATION, "わかります",
                              {"form": "NonpastPolitePositive"})
    assert ok and expected == "わかります"
    assert not quiz.check("conjugation", CONJUGATION, "わかった",
                          {"form": "NonpastPolitePositive"})[0]


def test_conjugation_question_skips_trivial_forms():
    import random
    for seed in range(20):
        question = quiz.q_conjugation(random.Random(seed), CONJUGATION, None)
        assert question is not None
        # словарная форма совпадает со словом — спрашивать её бессмысленно
        assert CONJUGATION["forms"][question["form"]] != CONJUGATION["word"]
        assert question["form"] != "Stem"


def test_check_kanji_reading_accepts_any_reading():
    assert quiz.check("kanji_reading", KANJI[1], "えん", {})[0]
    assert quiz.check("kanji_reading", KANJI[1], "その", {})[0]
    assert not quiz.check("kanji_reading", KANJI[1], "こう", {})[0]


def test_particle_question_blanks_a_particle(pool):
    import random
    particles = {w["id"]: w for w in WORDS if w["category"] == "particle"}
    question = quiz.q_particle(random.Random(0), SENTENCE, pool, particles)
    assert "＿＿" in question["prompt_html"]
    assert question["slot"] == 1
    assert "は" in question["options"]


def test_sentence_order_shuffles_blocks(pool):
    import random
    question = quiz.q_sentence_order(random.Random(7), SENTENCE, pool)
    assert "。" not in question["blocks"]
    assert sorted(question["blocks"]) == sorted(["公園", "は", "きれい", "です"])
