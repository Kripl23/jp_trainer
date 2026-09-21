"""Рендер игровой разметки Wagotabi в HTML.

В текстах игры встречаются:
    <style=Title1>Заголовок</style>   заголовок раздела
    <word=K00462>                     подстановка слова из словаря
    <sentence=279>                    подстановка примера-предложения
    <tooltip key=Tooltip/Uchi>…</tooltip>  всплывающая подсказка
    <sprite name=warning>             иконка-предупреждение
    <b> <i> <u> <br>                  обычное оформление
    [note]…[/note]                    блок-примечание

Всё неизвестное вырезается. Текст сначала экранируется целиком, и только затем
из экранированных последовательностей собирается разрешённый HTML — так
произвольная разметка из данных не может протечь на страницу.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

FURIGANA_RE = re.compile(r"([^\[\]]+)\[([^\]]+)\]")


def furigana_html(furigana: str, fallback: str = "") -> str:
    """`分[わ]かる` -> `<ruby>分<rt>わ</rt></ruby>かる`."""
    if not furigana:
        return html.escape(fallback)
    out, i = [], 0
    for m in FURIGANA_RE.finditer(furigana):
        out.append(html.escape(furigana[i:m.start()]))
        out.append(f"<ruby>{html.escape(m.group(1))}"
                   f"<rt>{html.escape(m.group(2))}</rt></ruby>")
        i = m.end()
    out.append(html.escape(furigana[i:]))
    return "".join(out)


def reading_of(furigana: str, word: str = "") -> str:
    """`分[わ]かる` -> `わかる`."""
    if not furigana:
        return ""
    out, i = [], 0
    for m in FURIGANA_RE.finditer(furigana):
        out.append(furigana[i:m.start()])
        out.append(m.group(2))
        i = m.end()
    out.append(furigana[i:])
    reading = "".join(out)
    return "" if reading == word else reading


@dataclass
class Context:
    """Справочники для подстановок `<word=…>` и `<sentence=…>`."""

    words: dict[str, dict] = field(default_factory=dict)
    sentences: dict[str, dict] = field(default_factory=dict)
    texts: dict[str, dict] = field(default_factory=dict)  # ключ -> {ru, en}

    def word_chip(self, word_id: str) -> str:
        word = self.words.get(word_id)
        if not word:
            return ""
        body = furigana_html(word.get("furigana", ""), word.get("word", word_id))
        title = word.get("meaning_ru") or word.get("meaning_en") or ""
        return (f'<a class="wchip" href="/dictionary?word={html.escape(word_id)}"'
                f' title="{html.escape(title)}">{body}</a>')

    def sentence_block(self, sentence_id: str) -> str:
        sentence = self.sentences.get(sentence_id)
        if not sentence:
            return ""
        return (f'<div class="ex"><div class="ex-jp">'
                f'{html.escape(sentence.get("japanese", ""))}</div>'
                f'<div class="ex-ru">{html.escape(sentence.get("ru", ""))}</div></div>')

    def tooltip(self, key: str) -> str:
        entry = self.texts.get(key) or {}
        return entry.get("ru") or entry.get("en") or ""


# Экранированные варианты тегов: html.escape превращает '<' в '&lt;'.
E = re.escape
_TITLE = re.compile(r"&lt;style=Title(\d)&gt;(.*?)&lt;/style&gt;", re.S)
_STYLE_ANY = re.compile(r"&lt;/?style[^&]*&gt;")
_WORD = re.compile(r"&lt;word=([A-Za-z0-9]+)&gt;")
_SENTENCE = re.compile(r"&lt;sentence=([0-9]+)&gt;")
_TOOLTIP = re.compile(r"&lt;tooltip key=([^&]+?)&gt;(.*?)&lt;/tooltip&gt;", re.S)
_SPRITE = re.compile(r"&lt;sprite name=([a-zA-Z]+)&gt;")
_SPRITE_ANY = re.compile(r"&lt;sprite[^&]*&gt;")
_SIMPLE = re.compile(r"&lt;(/?)(b|i|u)&gt;")
_BR = re.compile(r"&lt;br\s*/?&gt;")
_NOTE = re.compile(r"\[note\](.*?)\[/note\]", re.S)
_LEFTOVER = re.compile(r"&lt;/?[a-zA-Z][^&]*&gt;")
_LINK_MARK = re.compile(r"\[#[^\]]*\]")
_MANY_BR = re.compile(r"(<br>\s*){3,}")
# служебные пометки переводчиков в данных игры: «(#IMPLIES_FAVOR)»
_ANNOTATION = re.compile(r"\s*\(#[A-Z0-9_]+\)")

SPRITES = {"warning": "⚠", "info": "ℹ", "check": "✓", "cross": "✕"}


def render(text: str, ctx: Context | None = None) -> str:
    """Игровая разметка -> HTML, пригодный для вставки на страницу."""
    if not text:
        return ""
    ctx = ctx or Context()
    out = html.escape(text)
    out = _LINK_MARK.sub("", out)
    out = _NOTE.sub(lambda m: f'<div class="note">{m.group(1).strip()}</div>', out)
    out = _TITLE.sub(lambda m: f"<h{min(int(m.group(1)) + 2, 6)}>{m.group(2).strip()}"
                               f"</h{min(int(m.group(1)) + 2, 6)}>", out)
    out = _STYLE_ANY.sub("", out)
    out = _TOOLTIP.sub(
        lambda m: f'<abbr title="{html.escape(ctx.tooltip(html.unescape(m.group(1))))}">'
                  f'{m.group(2)}</abbr>', out)
    out = _WORD.sub(lambda m: ctx.word_chip(m.group(1)), out)
    out = _SENTENCE.sub(lambda m: ctx.sentence_block(m.group(1)), out)
    out = _SPRITE.sub(lambda m: f'<span class="ic">{SPRITES.get(m.group(1), "•")}</span> ', out)
    out = _SPRITE_ANY.sub("", out)
    out = _SIMPLE.sub(lambda m: f"<{m.group(1)}{m.group(2)}>", out)
    out = _BR.sub("<br>", out)
    out = _LEFTOVER.sub("", out)
    out = out.replace("##VALUE", "")
    out = _ANNOTATION.sub("", out)
    out = _MANY_BR.sub("<br><br>", out)
    return out.strip()


def plain(text: str) -> str:
    """Текст без разметки — для подсказок и сравнения ответов."""
    if not text:
        return ""
    out = re.sub(r"<[^>]*>", " ", text)
    out = _LINK_MARK.sub("", out)
    out = re.sub(r"\[/?note\]", " ", out)
    out = _ANNOTATION.sub("", out)
    return re.sub(r"\s+", " ", out).replace("##VALUE", "").strip(" ;")
