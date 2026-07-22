"""Проверка ответов.

JP -> RU: ответ верен, если после нормализации совпадает с любым из
переводов в поле ru (варианты разделены ';').
RU -> JP: ответ (кана после WanaKana либо кандзи) верен, если после
нормализации катаканы в хирагану совпадает с kana или с kanji.
"""
import re

_KATAKANA_START = 0x30A1
_KATAKANA_END = 0x30F6
_KANA_SHIFT = 0x60  # катакана -> хирагана


def kata_to_hira(text: str) -> str:
    return "".join(
        chr(ord(ch) - _KANA_SHIFT)
        if _KATAKANA_START <= ord(ch) <= _KATAKANA_END
        else ch
        for ch in text
    )


def normalize_ru(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def normalize_jp(text: str) -> str:
    text = re.sub(r"[\s、。･・～〜!！?？]", "", text)
    return kata_to_hira(text)


def ru_variants(ru_field: str) -> list[str]:
    return [v.strip() for v in ru_field.split(";") if v.strip()]


def check_jp_to_ru(answer: str, ru_field: str) -> bool:
    ans = normalize_ru(answer)
    if not ans:
        return False
    return any(ans == normalize_ru(v) for v in ru_variants(ru_field))


def check_ru_to_jp(answer: str, kana: str, kanji: str) -> bool:
    ans = normalize_jp(answer)
    if not ans:
        return False
    if ans == normalize_jp(kana):
        return True
    return bool(kanji) and ans == normalize_jp(kanji)
