"""Генератор заданий — те же типы упражнений, что в самой игре.

Сессия не хранится на сервере: клиент присылает вместе с ответом тип задания и
идентификатор элемента, правильный ответ сервер каждый раз выводит из БД заново.
"""
from __future__ import annotations

import html
import json
import random
from dataclasses import dataclass

from app.services import checker
from app.services.wagotabi_text import furigana_html, plain

# kind -> человекочитаемое название и подсказка к вводу
KINDS: dict[str, dict] = {
    "word_meaning":   {"title": "Значение слова", "input": None},
    "meaning_word":   {"title": "Слово по значению", "input": None},
    "reading_choice": {"title": "Чтение слова", "input": None},
    "reading_write":  {"title": "Напишите чтение", "input": "kana"},
    "word_write":     {"title": "Напишите слово", "input": "kana"},
    "particle":       {"title": "Частица в предложении", "input": None},
    "sentence_order": {"title": "Соберите предложение", "input": "blocks"},
    "conjugation":    {"title": "Форма слова", "input": "kana"},
    "kanji_meaning":  {"title": "Значение кандзи", "input": None},
    "kanji_reading":  {"title": "Чтение кандзи", "input": None},
}

WORD_KINDS = ("word_meaning", "meaning_word", "reading_choice", "reading_write", "word_write")
SENTENCE_KINDS = ("particle", "sentence_order")
EXTRA_KINDS = ("conjugation", "kanji_meaning", "kanji_reading")

# Названия форм спряжения на русском — в данных игры они хранятся ключами.
FORM_NAMES = {
    "Stem": "основа (ます-основа)",
    "Te": "て-форма",
    "NonpastPolitePositive": "наст./буд., вежливая, +",
    "NonpastPoliteNegative": "наст./буд., вежливая, −",
    "NonpastFormalNegativeColl": "наст./буд., вежливая, − (разговорная)",
    "NonpastPoliteNegativeCasual": "наст./буд., вежливая, − (мягкая)",
    "NonpastPoliteNegativeColl": "наст./буд., вежливая, − (сокращённая)",
    "NonpastPlainPositive": "словарная форма",
    "NonpastPlainNegative": "простая, −",
    "NonpastPlainNegativeColl": "простая, − (сокращённая)",
    "PastPolitePositive": "прошедшее, вежливая, +",
    "PastPlainPositive": "прошедшее, простая, +",
    "VolitionalPolitePositive": "пригласительная (〜ましょう)",
    "PresentPolitePositive": "настоящее, вежливая, +",
    "PresentPoliteNegative": "настоящее, вежливая, −",
    "PresentPoliteNegativeColl": "настоящее, вежливая, − (сокращённая)",
    "PresentPoliteNegativeCasual": "настоящее, вежливая, − (мягкая)",
    "PresentPoliteNegativeCasualColl": "настоящее, вежливая, − (мягкая, сокр.)",
    "PresentPlainPositive": "простая, +",
    "PresentPlainNegative": "простая, −",
    "PresentPlainNegativeColl": "простая, − (сокращённая)",
    "Na": "перед существительным (〜な)",
    "Noun": "как существительное",
}

CATEGORY_NAMES = {
    "godan": "годан (五段)", "ichidan": "итидан (一段)", "irregular": "неправильный",
    "i": "い-прилагательное", "na": "な-прилагательное",
}

PUNCTUATION = {"。", "、", "？", "！", "「", "」", "…"}


@dataclass
class Pool:
    """Материал, из которого собираются задания."""

    words: list[dict]
    sentences: list[dict]
    conjugations: list[dict]
    kanji: list[dict]
    all_words: list[dict]        # для правдоподобных неверных вариантов


def _word_body(word: dict, *, furigana: bool = True) -> str:
    if furigana and word.get("furigana"):
        return furigana_html(word["furigana"], word["word"])
    return html.escape(word["word"])


def _meaning(word: dict) -> str:
    return word.get("meaning_ru") or word.get("meaning_en") or ""


def _distractors(rng: random.Random, correct: str, candidates: list[str], n: int = 3) -> list[str]:
    pool = [c for c in dict.fromkeys(candidates) if c and c != correct]
    rng.shuffle(pool)
    return pool[:n]


def _options(rng: random.Random, correct: str, wrong: list[str]) -> list[str]:
    opts = [correct] + wrong
    rng.shuffle(opts)
    return opts


def _question(kind: str, item_type: str, item_id: str, **extra) -> dict:
    return {
        "kind": kind,
        "title": KINDS[kind]["title"],
        "input": KINDS[kind]["input"],
        "item_type": item_type,
        "item_id": item_id,
        **extra,
    }


# ---------------------------------------------------------------- типы заданий


def q_word_meaning(rng, word, pool):
    correct = _meaning(word)
    if not correct:
        return None
    wrong = _distractors(rng, correct, [_meaning(w) for w in pool.all_words])
    if len(wrong) < 2:
        return None
    return _question("word_meaning", "word", word["id"],
                     prompt_html=f'<div class="jp">{_word_body(word)}</div>',
                     options=_options(rng, correct, wrong))


def q_meaning_word(rng, word, pool):
    correct = word["word"]
    wrong = _distractors(rng, correct, [w["word"] for w in pool.all_words])
    if not _meaning(word) or len(wrong) < 2:
        return None
    return _question("meaning_word", "word", word["id"],
                     prompt_html=f'<div class="meaning">{html.escape(_meaning(word))}</div>',
                     options=_options(rng, correct, wrong))


def q_reading_choice(rng, word, pool):
    correct = word.get("reading")
    if not correct:
        return None
    wrong = _distractors(rng, correct, [w.get("reading", "") for w in pool.all_words])
    if len(wrong) < 2:
        return None
    return _question("reading_choice", "word", word["id"],
                     prompt_html=f'<div class="jp">{html.escape(word["word"])}</div>',
                     hint=_meaning(word), options=_options(rng, correct, wrong))


def q_reading_write(rng, word, pool):
    if not word.get("reading"):
        return None
    return _question("reading_write", "word", word["id"],
                     prompt_html=f'<div class="jp">{html.escape(word["word"])}</div>',
                     hint=_meaning(word))


def q_word_write(rng, word, pool):
    if not _meaning(word):
        return None
    return _question("word_write", "word", word["id"],
                     prompt_html=f'<div class="meaning">{html.escape(_meaning(word))}</div>',
                     hint=word.get("category", ""))


def q_particle(rng, sentence, pool, particles):
    blocks = sentence["blocks"]
    slots = [i for i, b in enumerate(blocks)
             if b.get("word_id") and b["word_id"] in particles
             and b["text"] == particles[b["word_id"]]["word"]]
    if not slots:
        return None
    slot = rng.choice(slots)
    correct = blocks[slot]["text"]
    wrong = _distractors(rng, correct, [p["word"] for p in particles.values()])
    if len(wrong) < 2:
        return None
    shown = "".join(b["text"] if i != slot else "＿＿" for i, b in enumerate(blocks))
    return _question("particle", "sentence", sentence["id"],
                     prompt_html=f'<div class="jp-mid">{html.escape(shown)}</div>',
                     hint=sentence.get("ru", ""), slot=slot,
                     options=_options(rng, correct, wrong))


def q_sentence_order(rng, sentence, pool):
    blocks = [b["text"] for b in sentence["blocks"] if b["text"] not in PUNCTUATION]
    if len(blocks) < 3 or len(blocks) > 9:
        return None
    shuffled = blocks[:]
    for _ in range(5):
        rng.shuffle(shuffled)
        if shuffled != blocks:
            break
    return _question("sentence_order", "sentence", sentence["id"],
                     prompt_html=f'<div class="meaning">{html.escape(sentence.get("ru", ""))}</div>',
                     blocks=shuffled)


def q_conjugation(rng, conj, pool):
    # «основа» и формы, совпадающие со словарной записью, спрашивать бессмысленно
    forms = {k: v for k, v in conj["forms"].items()
             if k in FORM_NAMES and k != "Stem" and v != conj["word"]}
    if not forms:
        return None
    form = rng.choice(sorted(forms))
    return _question("conjugation", "conjugation", conj["id"],
                     prompt_html=f'<div class="jp">'
                                 f'{furigana_html(conj.get("furigana", ""), conj["word"])}</div>',
                     hint=f'{CATEGORY_NAMES.get(conj["category"], conj["category"])} · '
                          f'{conj.get("meaning_ru", "")}',
                     ask=FORM_NAMES[form], form=form)


def q_kanji_meaning(rng, kanji, pool):
    correct = kanji.get("meaning_ru") or kanji.get("meaning_en")
    if not correct:
        return None
    wrong = _distractors(rng, correct,
                         [k.get("meaning_ru") or k.get("meaning_en") for k in pool.kanji])
    if len(wrong) < 2:
        return None
    return _question("kanji_meaning", "kanji", kanji["kanji"],
                     prompt_html=f'<div class="jp">{html.escape(kanji["kanji"])}</div>',
                     options=_options(rng, correct, wrong))


def q_kanji_reading(rng, kanji, pool):
    readings = list(kanji.get("on", [])) + list(kanji.get("kun", []))
    if not readings:
        return None
    correct = rng.choice(readings)
    others: list[str] = []
    for k in pool.kanji:
        if k["kanji"] != kanji["kanji"]:
            others += list(k.get("on", [])) + list(k.get("kun", []))
    wrong = _distractors(rng, correct, others)
    if len(wrong) < 2:
        return None
    return _question("kanji_reading", "kanji", kanji["kanji"],
                     prompt_html=f'<div class="jp">{html.escape(kanji["kanji"])}</div>',
                     hint=kanji.get("meaning_ru", ""),
                     options=_options(rng, correct, wrong))


WORD_BUILDERS = {
    "word_meaning": q_word_meaning,
    "meaning_word": q_meaning_word,
    "reading_choice": q_reading_choice,
    "reading_write": q_reading_write,
    "word_write": q_word_write,
}


def build(pool: Pool, kinds: list[str], count: int, seed: int | None = None) -> list[dict]:
    """Собрать набор заданий. Возвращает вопросы без правильных ответов."""
    rng = random.Random(seed)
    particles = {w["id"]: w for w in pool.all_words if w.get("category") == "particle"}
    kinds = [k for k in kinds if k in KINDS] or list(KINDS)

    candidates: list[tuple[str, callable]] = []
    for kind in kinds:
        if kind in WORD_BUILDERS:
            for word in pool.words:
                candidates.append((kind, lambda r, w=word, k=kind: WORD_BUILDERS[k](r, w, pool)))
        elif kind == "particle":
            for sentence in pool.sentences:
                candidates.append((kind, lambda r, s=sentence: q_particle(r, s, pool, particles)))
        elif kind == "sentence_order":
            for sentence in pool.sentences:
                candidates.append((kind, lambda r, s=sentence: q_sentence_order(r, s, pool)))
        elif kind == "conjugation":
            for conj in pool.conjugations:
                candidates.append((kind, lambda r, c=conj: q_conjugation(r, c, pool)))
        elif kind == "kanji_meaning":
            for k in pool.kanji:
                candidates.append((kind, lambda r, kk=k: q_kanji_meaning(r, kk, pool)))
        elif kind == "kanji_reading":
            for k in pool.kanji:
                candidates.append((kind, lambda r, kk=k: q_kanji_reading(r, kk, pool)))

    rng.shuffle(candidates)
    questions, seen = [], set()
    for kind, make in candidates:
        if len(questions) >= count:
            break
        q = make(rng)
        if not q:
            continue
        key = (q["kind"], q["item_id"], q.get("form", ""), q.get("slot", ""))
        if key in seen:
            continue
        seen.add(key)
        q["n"] = len(questions) + 1
        questions.append(q)
    return questions


# ---------------------------------------------------------------- проверка


def correct_answer(kind: str, item: dict, extra: dict) -> str:
    """Эталонный ответ по данным из БД."""
    if kind in ("word_meaning",):
        return item.get("meaning_ru") or item.get("meaning_en") or ""
    if kind == "meaning_word":
        return item["word"]
    if kind in ("reading_choice", "reading_write"):
        return item.get("reading") or item["word"]
    if kind == "word_write":
        return item.get("reading") or item["word"]
    if kind == "particle":
        blocks = item["blocks"]
        slot = int(extra.get("slot", -1))
        return blocks[slot]["text"] if 0 <= slot < len(blocks) else ""
    if kind == "sentence_order":
        return "".join(b["text"] for b in item["blocks"] if b["text"] not in PUNCTUATION)
    if kind == "conjugation":
        return item["forms"].get(extra.get("form", ""), "")
    if kind == "kanji_meaning":
        return item.get("meaning_ru") or item.get("meaning_en") or ""
    if kind == "kanji_reading":
        return ""  # проверяется по списку чтений
    return ""


def check(kind: str, item: dict, answer: str, extra: dict) -> tuple[bool, str]:
    """(верно, эталонный ответ)."""
    if kind == "kanji_reading":
        readings = list(item.get("on", [])) + list(item.get("kun", []))
        ok = any(checker.check_ru_to_jp(answer, r, "") for r in readings)
        return ok, "、".join(readings)

    expected = correct_answer(kind, item, extra)
    if not expected:
        return False, ""
    if kind in ("word_meaning", "kanji_meaning"):
        return checker.check_jp_to_ru(answer, expected), expected
    if kind == "sentence_order":
        return checker.normalize_jp(answer) == checker.normalize_jp(expected), expected
    return checker.check_ru_to_jp(answer, expected, ""), expected


def load_json(value) -> list | dict:
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value or "[]")
    except json.JSONDecodeError:
        return []


def explain(kind: str, item: dict) -> str:
    """Короткая справка, показываемая после ответа."""
    if kind.startswith("kanji"):
        return plain(item.get("meaning_ru", ""))
    if kind in ("particle", "sentence_order"):
        return f'{item.get("japanese", "")} — {item.get("ru", "")}'
    if kind == "conjugation":
        return f'{item.get("word", "")} — {item.get("meaning_ru", "")}'
    reading = item.get("reading")
    parts = [item.get("word", "")]
    if reading:
        parts.append(f"({reading})")
    parts.append("— " + (item.get("meaning_ru") or item.get("meaning_en") or ""))
    return " ".join(p for p in parts if p)
