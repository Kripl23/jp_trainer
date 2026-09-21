"""Извлечение учебных данных из игры Wagotabi в data/wagotabi/.

Игра — Unity (Mono), данные лежат в ScriptableObject'ах класса DictionaryData
внутри Wagotabi_Data/data.unity3d. Typetree генерируется из игровых DLL.

Запуск (нужен доступ к установленной игре):
    .venv/bin/python scripts/extract_wagotabi.py --game "D:/Steam/steamapps/common/Wagotabi"

Результат — JSON-файлы в data/wagotabi/, они и заливаются в БД seed_wagotabi.py.
Скрипт нужен только для обновления данных под новую версию игры; для работы
приложения достаточно уже выгруженных JSON.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEFAULT_GAME = r"C:\Program Files (x86)\Steam\steamapps\common\Wagotabi"

# ---------------------------------------------------------------- чтение бандла


class Reader:
    """Последовательное чтение сериализованного MonoBehaviour."""

    def __init__(self, buf: bytes):
        self.b = buf
        self.i = 0

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.b, self.i)[0]
        self.i += 4
        return v

    def align(self) -> None:
        self.i = (self.i + 3) & ~3

    def string(self) -> str:
        n = self.i32()
        v = self.b[self.i:self.i + n].decode("utf-8", "replace")
        self.i += n
        self.align()
        return v

    def string_array(self) -> list[str]:
        return [self.string() for _ in range(self.i32())]

    def header(self) -> str:
        """m_GameObject(12) + m_Enabled(1, align) + m_Script(12) -> m_Name."""
        self.i = 13
        self.align()
        self.i += 12
        return self.string()


def load_tables(game_dir: Path) -> dict[str, dict]:
    """Все DictionaryData-таблицы: {имя ScriptableObject: {header, keys, rows}}."""
    import UnityPy

    env = UnityPy.load(str(game_dir / "Wagotabi_Data" / "data.unity3d"))
    script_cache: dict[tuple, str | None] = {}

    def class_of(obj) -> str | None:
        raw = obj.get_raw_data()
        if len(raw) < 24:
            return None
        fid, pid = struct.unpack_from("<iq", raw, 16)
        key = (id(obj.assets_file), fid, pid)
        if key not in script_cache:
            try:
                script_cache[key] = obj.read(check_read=False).m_Script.read().m_ClassName
            except Exception:
                script_cache[key] = None
        return script_cache[key]

    tables: dict[str, dict] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        raw = obj.get_raw_data()
        if len(raw) < 4000:  # все учебные таблицы крупные
            continue
        if class_of(obj) not in DICT_CLASSES:
            continue
        r = Reader(raw)
        try:
            name = r.header()
            header, keys, rows = r.string_array(), r.string_array(), r.string_array()
        except Exception:
            continue
        if len(keys) != len(rows):
            continue
        tables[name] = {
            "header": header,
            "rows": [dict(zip(["key"] + header, [k] + row.split("\t") +
                              [""] * (len(header) - len(row.split("\t")))))
                     for k, row in zip(keys, rows)],
        }
    return tables


DICT_CLASSES = {
    "DictionaryData", "JapaneseTextData", "ExempleSentencesData", "JapaneseVerbsData",
    "JapaneseAdjectivesData", "KanjidexData", "KanjiReadingData", "KanjiRadicalData",
    "GrammarFormationData", "NPCNameDictionaryData", "LocalizationData",
}

LESSON_CLASSES = {
    "WordLessonData", "PrefectureData", "LocationData",
    "SingleTopicLessonData", "ConjugationLessonData", "UnlockableConjugationForm",
}


def load_lessons(game_dir: Path) -> dict[str, list[dict]]:
    """Уроки, локации и префектуры с разобранным typetree."""
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

    env = UnityPy.load(str(game_dir / "Wagotabi_Data" / "data.unity3d"))
    version = env.assets[0].unity_version
    gen = TypeTreeGenerator(version)
    gen.load_local_dll_folder(str(game_dir / "Wagotabi_Data" / "Managed"))

    script_cache: dict[tuple, str | None] = {}

    def class_of(obj) -> str | None:
        raw = obj.get_raw_data()
        if len(raw) < 24:
            return None
        fid, pid = struct.unpack_from("<iq", raw, 16)
        key = (id(obj.assets_file), fid, pid)
        if key not in script_cache:
            try:
                script_cache[key] = obj.read(check_read=False).m_Script.read().m_ClassName
            except Exception:
                script_cache[key] = None
        return script_cache[key]

    def raw_name(obj) -> str:
        raw = obj.get_raw_data()
        i = 28
        n = struct.unpack_from("<i", raw, i)[0]
        return raw[i + 4:i + 4 + n].decode("utf-8", "replace")

    out: dict[str, list[dict]] = collections.defaultdict(list)
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        cls = class_of(obj)
        if cls not in LESSON_CLASSES:
            continue
        try:
            data = obj.read_typetree(gen.get_nodes_up("MJJ.Scripts.dll", cls))
        except Exception:
            # у части уроков сгенерированный typetree расходится с данными;
            # имя и ключи локализации всё равно достаём из сырых байтов
            data = {"m_Name": raw_name(obj), "_partial": True}
        data["__class"] = cls
        data["__pid"] = obj.path_id
        data["__strings"] = embedded_strings(obj.get_raw_data())
        out[cls].append(data)
    return dict(out)


KEY_RE = re.compile(rb"[A-Za-z][A-Za-z0-9_]*(?:/[A-Za-z0-9_]+)+")


def embedded_strings(raw: bytes) -> list[str]:
    """Ключи локализации вида `Lessons/Te/Content`, встречающиеся в объекте."""
    return list(dict.fromkeys(m.decode("ascii") for m in KEY_RE.findall(raw)))


# ---------------------------------------------------------------- очистка разметки

STYLE_TAG = re.compile(
    r"<sprite[^>]*>|</?b>|</?i>|</?u>|</?style[^>]*>|</?color[^>]*>|</?size[^>]*>"
    r"|</?tooltip[^>]*>|</?link[^>]*>|</?align[^>]*>|</?voffset[^>]*>|</?indent[^>]*>"
    r"|</?nobr>|</?cspace[^>]*>|</?mspace[^>]*>|</?font[^>]*>|</?pos[^>]*>|</?line-height[^>]*>")
LINK_TAG = re.compile(r"\[#[^\]]*\]")
NOTE_TAG = re.compile(r"\[note\](.*?)\[/note\]", re.S)
TOKEN_REF = re.compile(r"~[a-z]:[^~]*~|\*[A-Z]\d+\*")
WORD_REF = re.compile(r"~[a-z]:[^~]*~\*([A-Z]\d+)\*|~w:([A-Z]\d+)~")
FURIGANA = re.compile(r"([^\[\]]+)\[([^\]]+)\]")
# служебные пометки переводчиков: «(#IMPLIES_FAVOR)»
ANNOTATION = re.compile(r"\s*\(#[A-Z0-9_]+\)")


def to_html(text: str) -> str:
    """Игровая разметка -> безопасный HTML (<b>, <br>, подсказки-иконки убираем)."""
    if not text:
        return ""
    text = LINK_TAG.sub("", text)
    text = re.sub(r"<sprite name=warning>", "⚠ ", text)
    text = re.sub(r"<sprite[^>]*>", "• ", text)
    text = re.sub(r"</?(?!b>|/b>|br)[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"(<br\s*/?>\s*){3,}", "<br><br>", text)
    return text.strip()


def plain(text: str) -> str:
    if not text:
        return ""
    text = STYLE_TAG.sub(" ", text)
    text = LINK_TAG.sub("", text)
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"\[/?note\]", " ", text)
    text = ANNOTATION.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ;")


def split_note(text: str) -> tuple[str, str]:
    """Значение (очищенное) и примечание в сырой разметке игры."""
    if not text:
        return "", ""
    notes = NOTE_TAG.findall(text)
    return plain(NOTE_TAG.sub("", text)), " ".join(n.strip() for n in notes).strip()


def clean_japanese(text: str) -> str:
    text = TOKEN_REF.sub("", text or "").replace("|", "").replace("$", "")
    return STYLE_TAG.sub("", text).replace("##VALUE", "").strip()


def reading_of(furigana: str, word: str) -> str:
    """分[わ]かる -> わかる (пусто, если чтение совпадает с написанием)."""
    if not furigana:
        return ""
    out, i = [], 0
    for m in FURIGANA.finditer(furigana):
        out.append(furigana[i:m.start()])
        out.append(m.group(2))
        i = m.end()
    out.append(furigana[i:])
    reading = "".join(out)
    return reading if reading != word else ""


def sentence_blocks(raw: str) -> list[dict]:
    """Предложение игры -> блоки для упражнения «собери предложение».

    Формат: `きれい~a:2101za~*K00265*|な~w:K01037~|公園~w:K00096~|...`
    """
    blocks = []
    for chunk in (raw or "").replace("$", "").split("|"):
        if not chunk.strip():
            continue
        ids = [a or b for a, b in WORD_REF.findall(chunk)]
        surface = clean_japanese(chunk)
        if not surface:
            continue
        blocks.append({"text": surface, "word_id": ids[0] if ids else ""})
    return blocks


# ---------------------------------------------------------------- сборка

LANGS = {"ru": "meaning_ru", "en": "meaning_en"}
PREFECTURES = {
    -1: "Пролог",
    0: "Кагава: прибытие",
    1: "Кагава",
    2: "Окаяма",
    3: "Тоттори",
}
PREFIX_TO_INDEX = {"P-1": -1, "P0": 0, "P01": 1, "P02": 2, "P03": 3}
LESSON_KIND = {
    "WordLessonData": "words",
    "ConjugationLessonData": "conjugation",
    "SingleTopicLessonData": "topic",
}


def build(game_dir: Path, out_dir: Path) -> None:
    print("читаю таблицы...")
    tables = load_tables(game_dir)
    missing = {"JapaneseWordsData", "ExempleSentencesData", "LocalizationData"} - set(tables)
    if missing:
        sys.exit(f"не найдены таблицы: {missing}; проверьте путь к игре")
    print("  " + ", ".join(f"{k}={len(v['rows'])}" for k, v in sorted(tables.items())))

    print("читаю уроки...")
    objects = load_lessons(game_dir)
    print("  " + ", ".join(f"{k}={len(v)}" for k, v in sorted(objects.items())))

    loc = {r["key"]: r for r in tables["LocalizationData"]["rows"]}
    jp_texts = {r["key"]: r["Content"] for r in tables["JapaneseTextsData"]["rows"]}
    raw_words = {r["key"]: r for r in tables["JapaneseWordsData"]["rows"]}

    def localized(key: str, lang: str = "RU") -> str:
        """Ключ -> текст. Часть ключей ведёт в японские тексты, часть — в слова."""
        if not key:
            return ""
        if key in loc:
            row = loc[key]
            value = row.get(lang) or row.get("English") or ""
            return value.replace("##VALUE", "").strip()
        if key in jp_texts:
            return clean_japanese(jp_texts[key])
        if key in raw_words:
            return raw_words[key]["word"]
        # часть заголовков записана прямо японским текстом, а не ключом
        return "" if "/" in key else key

    def game_text(node: dict | None, lang: str = "RU") -> str:
        if not node:
            return ""
        return localized(node.get("_key", ""), lang)

    def optional(node: dict | None) -> dict | None:
        if node and node.get("_enabled"):
            return node.get("_value")
        return None

    # --- порядок: префектура -> локация -> список уроков локации
    by_pid = {o["__pid"]: o for cls in objects.values() for o in cls}
    prefectures = {o["__pid"]: o for o in objects.get("PrefectureData", [])}

    locations = []
    for loc_obj in objects.get("LocationData", []):
        pref = prefectures.get(loc_obj["_prefecture"]["m_PathID"])
        lessons = [by_pid.get(p["m_PathID"]) for p in loc_obj.get("_lessons", [])]
        lessons = [x for x in lessons if x]
        groups = [x.get("_group", 999) for x in lessons if x["__class"] == "WordLessonData"]
        locations.append({
            "prefecture": pref["_index"] if pref else 99,
            "index": loc_obj.get("_indexInPrefecture", 0),
            "tiebreak": min(groups) if groups else 999,
            "name": loc_obj["m_Name"],
            "key": loc_obj.get("_key", ""),
            "lessons": lessons,
        })
    locations.sort(key=lambda x: (x["prefecture"], x["index"], x["tiebreak"]))

    # --- слова по урокам: (префектура, группа) -> отсортированные слова
    buckets: dict[tuple, list[dict]] = collections.defaultdict(list)
    for row in tables["JapaneseWordsData"]["rows"]:
        index = PREFIX_TO_INDEX.get(row["prefecture"])
        if index is None or not row["group"] or row["group"] == "0":
            continue
        buckets[(index, int(row["group"]))].append(row)
    for rows in buckets.values():
        rows.sort(key=lambda r: (int(r["group_index"] or 0), r["key"]))

    # --- уроки
    lessons_out, word_order, lesson_of = [], {}, {}
    position = 0
    for location in locations:
        for obj in location["lessons"]:
            kind = LESSON_KIND.get(obj["__class"], "topic")
            lesson_id = obj["m_Name"]
            word_ids: list[str] = []
            if obj["__class"] == "WordLessonData":
                bucket = buckets.get((obj["_prefecture"], obj["_group"]), [])
                word_ids = [r["key"] for r in bucket]
                for wid in word_ids:
                    if wid not in word_order:
                        word_order[wid] = position
                        lesson_of[wid] = lesson_id
                        position += 1
            node = optional(obj.get("_lessonContent")) if not obj.get("_partial") else None
            content_key = node.get("_key", "") if node else ""
            if not content_key:
                content_key = next((s for s in obj["__strings"]
                                    if s.endswith("/Content") and s in loc), "")
            title_key = ""
            if not obj.get("_partial"):
                title_key = (obj.get("_title") or {}).get("_key", "")
            if not title_key:
                title_key = next((s for s in obj["__strings"]
                                  if (s.endswith("/Title") or s.startswith("Lessons/Title/"))
                                  and (s in loc or s in jp_texts)), "")
            lessons_out.append({
                "id": lesson_id,
                "kind": kind,
                "chapter": PREFECTURES.get(location["prefecture"], ""),
                "chapter_index": location["prefecture"],
                "location": location["name"],
                "location_key": location["key"],
                "title_ru": localized(title_key) or lesson_id,
                "title_en": localized(title_key, "English"),
                # сырая разметка игры, рендерится приложением (app/services/wagotabi_text.py)
                "explanation_ru": (loc.get(content_key, {}).get("RU") or "").strip(),
                "explanation_en": (loc.get(content_key, {}).get("English") or "").strip(),
                "content_key": content_key,
                "has_grammar": bool(obj.get("_hasGrammar")),
                "word_ids": word_ids,
                "example_sentence_keys": obj.get("_exempleSentenceKeys", []) or [],
            })
    for row in tables["JapaneseWordsData"]["rows"]:
        if row["key"] not in word_order:
            word_order[row["key"]] = position
            position += 1

    for n, lesson in enumerate(lessons_out, 1):
        lesson["order"] = n

    # --- слова
    words_out = []
    for row in sorted(tables["JapaneseWordsData"]["rows"], key=lambda r: word_order[r["key"]]):
        furigana = row["furigana"] or row["FullKanji"] or ""
        meanings = {}
        for code, column in LANGS.items():
            meaning, note = split_note(row[column])
            meanings[code] = {"meaning": meaning, "note": note}
        words_out.append({
            "id": row["key"],
            "order": word_order[row["key"]] + 1,
            "word": row["word"],
            "furigana": furigana,
            "reading": reading_of(furigana, row["word"]),
            "meaning_ru": meanings["ru"]["meaning"],
            "note_ru": meanings["ru"]["note"],
            "meaning_en": meanings["en"]["meaning"],
            "note_en": meanings["en"]["note"],
            "category": row["category"],
            "jlpt": row["jlpt"],
            "tags": [t.strip() for t in (row["tag"] or "").split(",") if t.strip()],
            "is_grammar": row["Grammar"] == "TRUE",
            "lesson_id": lesson_of.get(row["key"], ""),
            "synonym": row["synonym"],
        })

    # --- предложения
    sentences_out = []
    for row in tables["ExempleSentencesData"]["rows"]:
        blocks = sentence_blocks(row["sentence"])
        ids = [b["word_id"] for b in blocks if b["word_id"]]
        anchor = row["word"] if row["word"] in raw_words else (ids[0] if ids else "")
        sentences_out.append({
            "id": row["key"],
            # собираем из блоков, чтобы текст и упражнение «собери предложение»
            # всегда совпадали (в сыром виде рядом с разделителями бывают пробелы)
            "japanese": "".join(b["text"] for b in blocks),
            "blocks": blocks,
            "word_ids": list(dict.fromkeys(ids)),
            "anchor_word_id": anchor,
            "ru": ANNOTATION.sub("", row["RU"]).strip(),
            "en": ANNOTATION.sub("", row["EN"]).strip(),
            "politeness": row["PolitenessLevel"],
            "order": word_order.get(anchor, 10 ** 6),
        })
    sentences_out.sort(key=lambda s: (s["order"], s["id"]))

    # --- кандзи
    readings: dict[str, dict[str, list[str]]] = collections.defaultdict(
        lambda: {"on": [], "kun": []})
    for row in tables["KanjiReadingData"]["rows"]:
        readings[row["Kanji"]]["on" if row["On/Kun"] == "On" else "kun"].append(row["Reading"])

    first_seen: dict[str, int] = {}
    kanji_words: dict[str, list[str]] = collections.defaultdict(list)
    for word in words_out:
        for ch in dict.fromkeys(word["word"] + word["furigana"]):
            if "\u4e00" <= ch <= "\u9fff":
                first_seen.setdefault(ch, word["order"])
                if len(kanji_words[ch]) < 6:
                    kanji_words[ch].append(word["id"])

    kanji_out = []
    for row in sorted(tables["KanjidexData"]["rows"],
                      key=lambda r: (first_seen.get(r["key"], 10 ** 6), int(r["Index"] or 0))):
        ch = row["key"]
        kanji_out.append({
            "kanji": ch,
            "order": len(kanji_out) + 1,
            "meaning_ru": row["RU"] or row["EN"],
            "meaning_en": row["EN"],
            "on": readings[ch]["on"],
            "kun": readings[ch]["kun"],
            "strokes": row["Stroke count"],
            "grade": row["School grade"],
            "jlpt": row["JLPT"],
            "decomposition": row["Decomposition"],
            "resembling": row["Resembling"],
            "word_ids": kanji_words.get(ch, []),
        })

    radicals_out = [{
        "radical": r["key"], "reading": r["Japanese"],
        "meaning_ru": r["Russian"] or r["English"], "meaning_en": r["English"],
        "strokes": int(r["Stroke Count"] or 0),
    } for r in sorted(tables["KanjiRadicalData"]["rows"],
                      key=lambda r: (int(r["Stroke Count"] or 0), r["key"]))]

    # --- спряжения
    def conjugation(rows: list[dict], kind: str) -> list[dict]:
        skip = {"key", "word", "category", "furigana", "hasFuriganaException"}
        out = []
        for row in rows:
            word = next((w for w in words_out if w["word"] == row["word"]), None)
            out.append({
                "id": f"{kind}-{row['key']}",
                "kind": kind,
                "word": row["word"],
                "furigana": row["furigana"] or (word["furigana"] if word else ""),
                "reading": word["reading"] if word else "",
                "meaning_ru": word["meaning_ru"] if word else "",
                "word_id": word["id"] if word else "",
                "category": row["category"],
                "order": word["order"] if word else 10 ** 6,
                "forms": {k: v for k, v in row.items() if k not in skip and v and v != "N/A"},
            })
        out.sort(key=lambda x: (x["order"], x["word"]))
        return out

    conjugations_out = (conjugation(tables["VerbsData"]["rows"], "verb") +
                        conjugation(tables["AdjectivesData"]["rows"], "adjective"))

    grammar_out = []
    for row in sorted(tables["GrammarFormationsData"]["rows"],
                      key=lambda r: (word_order.get(r["Word"], 10 ** 6), r["key"])):
        word = raw_words.get(row["Word"])
        meaning, note = split_note(word["meaning_ru"]) if word else ("", "")
        meaning_en, _ = split_note(word["meaning_en"]) if word else ("", "")
        grammar_out.append({
            "id": row["key"],
            "formation": row["Formation"],
            "word_id": row["Word"],
            "word": word["word"] if word else "",
            "meaning_ru": meaning or meaning_en,
            "note_ru": note,
            "lesson_id": lesson_of.get(row["Word"], ""),
            "order": len(grammar_out) + 1,
        })

    # --- локализация: ключи, на которые ссылаются объяснения и интерфейс форм
    keep_prefixes = ("Tooltip/", "Conjugation/", "Lessons/", "Exercice/", "DictionaryTag/",
                     "Basic/", "Kanjidex/", "DictionaryEntry/", "ShortDef/", "Variable/")
    localization_out = {
        k: {"ru": (v.get("RU") or "").strip(), "en": (v.get("English") or "").strip()}
        for k, v in loc.items() if k.startswith(keep_prefixes)
    }

    forms_out = []
    for obj in objects.get("UnlockableConjugationForm", []):
        keys = [s_ for s_ in obj["__strings"] if s_.startswith("Conjugation/")]
        forms_out.append({
            "id": obj["m_Name"],
            "name_ru": next((localization_out[k]["ru"] for k in keys
                             if k in localization_out and not k.endswith("/Info")), ""),
            "info_ru": next((localization_out[k]["ru"] for k in keys
                             if k.endswith("/Info") and k in localization_out), ""),
            "keys": keys,
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "localization.json": localization_out,
        "conjugation_forms.json": forms_out,
        "lessons.json": lessons_out,
        "words.json": words_out,
        "sentences.json": sentences_out,
        "kanji.json": kanji_out,
        "radicals.json": radicals_out,
        "conjugations.json": conjugations_out,
        "grammar.json": grammar_out,
    }
    for name, data in payload.items():
        (out_dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {name}: {len(data)}")
    with_explanation = sum(1 for x in lessons_out if x["explanation_ru"])
    print(f"  уроков с объяснением: {with_explanation}/{len(lessons_out)}")
    print(f"готово -> {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default=DEFAULT_GAME, help="папка установленной игры")
    parser.add_argument("--out", default=str(BASE / "data" / "wagotabi"))
    args = parser.parse_args()

    game_dir = Path(args.game)
    if not (game_dir / "Wagotabi_Data" / "data.unity3d").exists():
        sys.exit(f"не вижу Wagotabi_Data/data.unity3d в {game_dir}")
    build(game_dir, Path(args.out))


if __name__ == "__main__":
    main()
