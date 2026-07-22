"""Упрощённый SM-2 с бинарной оценкой (верно/неверно).

Верно:   repetitions++, интервал 1д -> 3д -> interval * ease_factor.
Неверно: repetitions=0, интервал 10 минут (карточка вернётся в текущей
         сессии), lapses++, ease_factor -0.2 (не ниже 1.3).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MIN_EASE = 1.3
EASE_PENALTY = 0.2
FIRST_INTERVAL_DAYS = 1.0
SECOND_INTERVAL_DAYS = 3.0
LAPSE_INTERVAL = timedelta(minutes=10)


@dataclass
class SrsState:
    repetitions: int = 0
    ease_factor: float = 2.5
    interval_days: float = 0.0
    lapses: int = 0
    due_date: str = ""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def review(state: SrsState, correct: bool, now: datetime | None = None) -> SrsState:
    now = now or now_utc()
    if correct:
        if state.repetitions == 0:
            interval = FIRST_INTERVAL_DAYS
        elif state.repetitions == 1:
            interval = SECOND_INTERVAL_DAYS
        else:
            interval = state.interval_days * state.ease_factor
        due = now + timedelta(days=interval)
        return SrsState(
            repetitions=state.repetitions + 1,
            ease_factor=state.ease_factor,
            interval_days=interval,
            lapses=state.lapses,
            due_date=iso(due),
        )
    return SrsState(
        repetitions=0,
        ease_factor=max(MIN_EASE, state.ease_factor - EASE_PENALTY),
        interval_days=0.0,
        lapses=state.lapses + 1,
        due_date=iso(now + LAPSE_INTERVAL),
    )
