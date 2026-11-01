"""Таймеры M4: законные сроки по сценарию и дате события.

Даты считает workcalendar по производственному календарю; нормы и точки отсчёта — из
kb/norms/timers.yaml. Если для года нет данных календаря — честный отказ (CalendarGap),
а не «примерная» дата.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from . import workcalendar as wc

TIMERS_PATH = Path(__file__).resolve().parents[2] / "kb" / "norms" / "timers.yaml"


@lru_cache(maxsize=1)
def load_timers(path: Path = TIMERS_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class Deadline:
    timer_id: str
    title: str
    start: date
    due: date
    unit: str
    amount: int
    norm: str
    who: str
    verified: bool


def compute(timer_id: str, start: date) -> Deadline:
    t = load_timers()["timers"][timer_id]
    unit, n = t["unit"], int(t["amount"])
    if unit == "working_days":
        due = wc.add_workdays(start, n)
    elif unit == "calendar_days":
        due = wc.add_calendar_days(start, n)
    elif unit == "months":
        due = wc.add_months(start, n)
    else:
        raise ValueError(f"неизвестная единица срока: {unit}")
    return Deadline(timer_id, t["title"], start, due, unit, n, t["norm"], t["who"], bool(t.get("verified")))


def timers_for(scenario: str) -> list[str]:
    return [tid for tid, t in load_timers()["timers"].items() if scenario in t["applies_to"]]


def has_statutory_client_deadline(scenario: str) -> bool:
    return scenario not in load_timers()["no_statutory_client_deadline"]
