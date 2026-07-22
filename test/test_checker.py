from app.services.checker import (
    check_jp_to_ru,
    check_ru_to_jp,
    kata_to_hira,
    normalize_ru,
)


def test_kata_to_hira():
    assert kata_to_hira("ネコ") == "ねこ"
    assert kata_to_hira("テレビ") == "てれび"
    assert kata_to_hira("ねこ") == "ねこ"
    #長音 и кандзи не трогаем
    assert kata_to_hira("コーヒー") == "こーひー"
    assert kata_to_hira("猫") == "猫"


def test_normalize_ru():
    assert normalize_ru("  Ёлка  ") == "елка"
    assert normalize_ru("кошка, домашняя") == "кошка домашняя"
    assert normalize_ru("По-японски") == "по-японски"


def test_jp_to_ru_accepts_any_variant():
    assert check_jp_to_ru("кошка", "кошка; кот")
    assert check_jp_to_ru("КОТ", "кошка; кот")
    assert not check_jp_to_ru("собака", "кошка; кот")
    assert not check_jp_to_ru("", "кошка")


def test_ru_to_jp_accepts_kana_and_kanji():
    assert check_ru_to_jp("ねこ", kana="ねこ", kanji="猫")
    assert check_ru_to_jp("猫", kana="ねこ", kanji="猫")
    assert check_ru_to_jp("ネコ", kana="ねこ", kanji="猫")  # катакана
    assert not check_ru_to_jp("いぬ", kana="ねこ", kanji="猫")
    assert not check_ru_to_jp("", kana="ねこ", kanji="猫")


def test_ru_to_jp_without_kanji():
    assert check_ru_to_jp("これ", kana="これ", kanji="")
    assert not check_ru_to_jp("それ", kana="これ", kanji="")
