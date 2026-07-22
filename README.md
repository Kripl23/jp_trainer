# jp_trainer — тренажёр японской лексики

Веб-приложение для практики перевода слов (RU → JP и JP → RU) с вводом ответа
с клавиатуры, интервальными повторениями (упрощённый SM-2) и статистикой.

## Возможности

- **Два направления**: показывается русское слово — вспоминаете японское, и наоборот.
- **Ввод ромадзи**: в направлении RU → JP печатаете латиницей (`neko`), поле само
  превращает её в кану (`ねこ`) — библиотека WanaKana, лежит локально в `app/static/`.
  Ответ засчитывается по кане; написание кандзи тоже принимается.
- **SRS**: верный ответ отодвигает слово (1д → 3д → интервал × ease), неверный —
  возвращает через 10 минут и снижает ease. Прогресс по направлениям независимый.
- **Колоды**: JLPT N5 (стартовый набор ~240 слов), Minna no Nihongo уроки 1–5,
  свои слова (ручное добавление и импорт CSV).
- **Лимит новых слов** в день — `NEW_WORDS_PER_DAY` в `.env` (по умолчанию 10).
- Оценка ответа японскими школьными знаками: ◯ — верно, ✕ — неверно.

## Установка

```bash
cd jp_trainer
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp example.env .env
.venv/bin/python scripts/seed_data.py   # заливка словарей (идемпотентно)
```

## Запуск

Dev:

```bash
./run.sh          # uvicorn --reload на порту из .env (по умолчанию 8040)
```

Prod (supervisord внутри .venv, без рута):

```bash
.venv/bin/supervisord -c supervisord.conf
.venv/bin/supervisorctl -c supervisord.conf status
```

Логи — в `logs/` (приложение, uvicorn, supervisord).

## Тесты

```bash
.venv/bin/python -m pytest test/
```

## Пополнение словарей

Формат CSV (заголовок обязателен, разделитель — запятая, варианты перевода через `;`):

```csv
kanji,kana,ru,pos,level
猫,ねこ,кошка; кот,сущ,N5
```

- Файлы `data/jlpt_n4.csv` … `jlpt_n1.csv` и новые уроки в `data/minna_lessons.csv`
  подхватываются `scripts/seed_data.py` автоматически.
- Свои слова — через страницу «Слова» (форма или кнопка «Импорт CSV»,
  колонки `kana,ru` обязательны, `kanji,pos,level` опциональны).

## Структура

```
app/
  main.py            FastAPI, статика, роутеры
  db.py              SQLite (aiosqlite), схема: words / srs_progress / review_log
  services/srs.py    алгоритм SM-2
  services/checker.py нормализация и проверка ответов (кана/кандзи/катакана, ё→е)
  routers/           training (сессии), words (CRUD+CSV), stats, pages
  templates/, static/  Jinja2 + vanilla JS, WanaKana
scripts/seed_data.py заливка data/*.csv в БД
```
