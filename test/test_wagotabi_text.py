from app.services.wagotabi_text import Context, furigana_html, plain, reading_of, render


def test_furigana_to_ruby():
    assert furigana_html("分[わ]かる") == "<ruby>分<rt>わ</rt></ruby>かる"
    assert furigana_html("天[てん]気[き]") == (
        "<ruby>天<rt>てん</rt></ruby><ruby>気<rt>き</rt></ruby>"
    )
    assert furigana_html("", "ねこ") == "ねこ"


def test_reading_of():
    assert reading_of("分[わ]かる", "分かる") == "わかる"
    assert reading_of("天[てん]気[き]", "天気") == "てんき"
    # если чтение совпадает с написанием, показывать его незачем
    assert reading_of("ねこ", "ねこ") == ""
    assert reading_of("", "ねこ") == ""


def test_render_headings_and_formatting():
    html = render("<style=Title1>Заголовок</style>Текст<br><b>жирный</b>")
    assert "<h3>Заголовок</h3>" in html
    assert "<b>жирный</b>" in html
    assert "<br>" in html


def test_render_substitutes_word_and_sentence():
    ctx = Context(
        words={"K00001": {"word": "です", "furigana": "", "meaning_ru": "быть"}},
        sentences={"12": {"japanese": "たなかです。", "ru": "Я Танака."}},
    )
    html = render("Смотрите: <word=K00001> и <sentence=12>", ctx)
    assert "です" in html
    assert "たなかです。" in html
    assert "Я Танака." in html


def test_render_resolves_tooltip():
    ctx = Context(texts={"Tooltip/Uchi": {"ru": "свой круг", "en": "inner circle"}})
    html = render("<tooltip key=Tooltip/Uchi>Uchi</tooltip>", ctx)
    assert 'title="свой круг"' in html
    assert ">Uchi</abbr>" in html


def test_render_escapes_unknown_markup():
    html = render("<script>alert(1)</script><img src=x onerror=boom>")
    assert "<script>" not in html
    assert "<img" not in html
    assert "onerror" not in html


def test_render_strips_translator_annotations():
    assert "(#IMPLIES_FAVOR)" not in render("даёт (#IMPLIES_FAVOR) мне")
    assert plain("вода (#PROVIDE_CONTEXT), пить?") == "вода, пить?"


def test_render_wraps_note_block():
    html = render("значение[note]пояснение[/note]")
    assert '<div class="note">пояснение</div>' in html
    assert "[note]" not in html


def test_plain_removes_everything():
    assert plain("<b>です</b> ##VALUE") == "です"
    assert plain("") == ""
