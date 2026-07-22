from datetime import datetime, timezone

from app.services.srs import SrsState, review

NOW = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)


def test_first_correct_gives_one_day():
    st = review(SrsState(), correct=True, now=NOW)
    assert st.repetitions == 1
    assert st.interval_days == 1.0
    assert st.due_date == "2026-07-11T12:00:00"


def test_second_correct_gives_three_days():
    st = review(SrsState(repetitions=1, interval_days=1.0), correct=True, now=NOW)
    assert st.repetitions == 2
    assert st.interval_days == 3.0


def test_third_correct_multiplies_by_ease():
    st = review(
        SrsState(repetitions=2, interval_days=3.0, ease_factor=2.5),
        correct=True,
        now=NOW,
    )
    assert st.interval_days == 7.5
    assert st.due_date == "2026-07-18T00:00:00"


def test_incorrect_resets_and_penalizes():
    st = review(
        SrsState(repetitions=5, interval_days=30.0, ease_factor=2.5, lapses=1),
        correct=False,
        now=NOW,
    )
    assert st.repetitions == 0
    assert st.interval_days == 0.0
    assert st.lapses == 2
    assert st.ease_factor == 2.3
    assert st.due_date == "2026-07-10T12:10:00"


def test_ease_never_below_minimum():
    st = SrsState(ease_factor=1.4)
    st = review(st, correct=False, now=NOW)
    assert st.ease_factor == 1.3
    st = review(st, correct=False, now=NOW)
    assert st.ease_factor == 1.3
