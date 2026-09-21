import aiosqlite
import pytest
import pytest_asyncio

from app.db import SCHEMA
from app.services import marks, progress


@pytest_asyncio.fixture
async def conn():
    connection = await aiosqlite.connect(":memory:")
    connection.row_factory = aiosqlite.Row
    await connection.executescript(SCHEMA)
    yield connection
    await connection.close()


LESSONS = [
    {"id": "P0_1", "ord": 1, "chapter": "Кагава", "chapter_index": 0,
     "word_ids": ["K001", "K002"], "word_count": 2},
    {"id": "P0_2", "ord": 2, "chapter": "Кагава", "chapter_index": 0,
     "word_ids": ["K003"], "word_count": 1},
    {"id": "P1_1", "ord": 3, "chapter": "Окаяма", "chapter_index": 1,
     "word_ids": ["K004"], "word_count": 1},
]


@pytest.mark.asyncio
async def test_record_lesson_marks_completed_above_threshold(conn):
    result = await progress.record_lesson(conn, "P0_1", 90)
    assert result["completed"] is True
    assert result["best_percent"] == 90
    assert result["attempts"] == 1


@pytest.mark.asyncio
async def test_record_lesson_below_threshold_is_not_completed(conn):
    result = await progress.record_lesson(conn, "P0_1", 50)
    assert result["completed"] is False
    assert result["best_percent"] == 50


@pytest.mark.asyncio
async def test_best_percent_keeps_maximum(conn):
    await progress.record_lesson(conn, "P0_1", 90)
    result = await progress.record_lesson(conn, "P0_1", 40)
    assert result["best_percent"] == 90
    assert result["last_percent"] == 40
    assert result["attempts"] == 2
    # однажды пройденный урок не «разпроходится» из-за плохой попытки
    assert result["completed"] is True


@pytest.mark.asyncio
async def test_chapters_group_and_count(conn):
    await progress.record_lesson(conn, "P0_1", 100)
    state = await progress.lesson_map(conn)
    chapters = progress.chapters(LESSONS, state)
    assert [c["title"] for c in chapters] == ["Кагава", "Окаяма"]
    assert chapters[0]["done"] == 1
    assert chapters[0]["total"] == 2
    assert chapters[0]["percent"] == 50
    assert chapters[0]["words"] == 3


@pytest.mark.asyncio
async def test_current_lesson_is_first_unfinished(conn):
    assert progress.current_lesson(LESSONS, {})["id"] == "P0_1"
    await progress.record_lesson(conn, "P0_1", 100)
    state = await progress.lesson_map(conn)
    assert progress.current_lesson(LESSONS, state)["id"] == "P0_2"


@pytest.mark.asyncio
async def test_unlocked_words_cover_finished_plus_current(conn):
    await progress.record_lesson(conn, "P0_1", 100)
    state = await progress.lesson_map(conn)
    ids = progress.unlocked_word_ids(LESSONS, state)
    assert ids == ["K001", "K002", "K003"]


@pytest.mark.asyncio
async def test_marks_are_set_and_cleared(conn):
    await marks.set_mark(conn, "word", "K001", "hard")
    assert (await marks.get_map(conn, "word"))["K001"]["status"] == "hard"

    await marks.set_mark(conn, "word", "K001", "known")
    assert (await marks.get_map(conn, "word"))["K001"]["status"] == "known"

    await marks.set_mark(conn, "word", "K001", "new")
    assert "K001" not in await marks.get_map(conn, "word")


@pytest.mark.asyncio
async def test_marks_reject_unknown_values(conn):
    with pytest.raises(ValueError):
        await marks.set_mark(conn, "word", "K001", "выучено")
    with pytest.raises(ValueError):
        await marks.set_mark(conn, "мысли", "K001", "known")


@pytest.mark.asyncio
async def test_mark_counts_fill_new_bucket(conn):
    await marks.set_mark(conn, "word", "K001", "known")
    await marks.set_mark(conn, "word", "K002", "hard")
    counts = await marks.counts(conn, "word", total=10)
    assert counts["known"] == 1
    assert counts["hard"] == 1
    assert counts["new"] == 8


@pytest.mark.asyncio
async def test_ids_with_status_filters(conn):
    await marks.set_mark(conn, "word", "K001", "known")
    await marks.set_mark(conn, "word", "K002", "hard")
    await marks.set_mark(conn, "word", "K003", "learning")
    assert sorted(await marks.ids_with_status(conn, "word", ["hard", "learning"])) == \
        ["K002", "K003"]
    # «new» не хранится в таблице, поэтому и не выбирается
    assert await marks.ids_with_status(conn, "word", ["new"]) == []


@pytest.mark.asyncio
async def test_topic_progress_is_independent(conn):
    await progress.record_topic(conn, "cryptography", 100)
    await progress.mark_topic_read(conn, "logic")
    state = await progress.topic_map(conn)
    assert state["cryptography"]["completed_at"]
    assert state["logic"]["read_at"]
    assert not state["logic"]["completed_at"]
