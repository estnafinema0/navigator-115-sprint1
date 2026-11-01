"""Производственный календарь РФ и счёт сроков (M4).

Данные — kb/calendar/ru-<год>.yaml: перечень нерабочих будних дней и рабочих выходных по
постановлению Правительства РФ о переносе выходных (первоисточник в kb/sources/), сверено
с данными xmlcalendar. Онлайн-API в рантайме не используется.

Правила счёта (ГК РФ):
- ст. 191: течение срока, определённого периодом, начинается на следующий день после
  календарной даты или события, которым определено его начало;
- ст. 192: срок в месяцах истекает в соответствующее число последнего месяца; если такого
  числа нет — в последний день месяца;
- ст. 193: если последний день срока приходится на нерабочий день, днём окончания срока
  считается ближайший следующий рабочий день.
Срок в рабочих днях: «не позднее N рабочих дней со дня X» = N-й рабочий день после X.
"""
from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass
from datetime import date, timedelta
from functools import cache
from pathlib import Path

import yaml

KB_CALENDAR = Path(__file__).resolve().parents[2] / "kb" / "calendar"


class CalendarGap(LookupError):
    """Для года нет проверенных данных календаря — считать нельзя, честно сообщаем."""


@dataclass(frozen=True)
class YearCalendar:
    year: int
    nonworking_weekdays: frozenset[date]  # будни, объявленные нерабочими (праздники и переносы)
    working_weekends: frozenset[date]  # выходные, объявленные рабочими
    shortened: frozenset[date]
    source: dict


@cache
def load_year(year: int, base: Path = KB_CALENDAR) -> YearCalendar:
    path = base / f"ru-{year}.yaml"
    if not path.exists():
        raise CalendarGap(f"нет данных производственного календаря на {year} год ({path.name})")
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    as_dates = lambda xs: frozenset(date.fromisoformat(str(x)) for x in (xs or []))  # noqa: E731
    yc = YearCalendar(
        year=int(d["year"]),
        nonworking_weekdays=as_dates(d.get("nonworking_weekdays")),
        working_weekends=as_dates(d.get("working_weekends")),
        shortened=as_dates(d.get("shortened")),
        source=d.get("source", {}),
    )
    for x in yc.nonworking_weekdays:
        if x.weekday() >= 5 or x.year != year:
            raise ValueError(f"{path.name}: {x} не будний день {year} года")
    for x in yc.working_weekends:
        if x.weekday() < 5 or x.year != year:
            raise ValueError(f"{path.name}: {x} не выходной день {year} года")
    return yc


def is_workday(d: date) -> bool:
    yc = load_year(d.year)
    if d in yc.working_weekends:
        return True
    if d in yc.nonworking_weekdays:
        return False
    return d.weekday() < 5


def add_workdays(start: date, n: int) -> date:
    """N-й рабочий день после start (start не считается). n ≥ 1."""
    if n < 1:
        raise ValueError("n должно быть ≥ 1")
    d = start
    left = n
    while left:
        d += timedelta(days=1)
        if is_workday(d):
            left -= 1
    return d


def next_workday_on_or_after(d: date) -> date:
    """Ст. 193 ГК: перенос окончания срока с нерабочего дня."""
    while not is_workday(d):
        d += timedelta(days=1)
    return d


def add_calendar_days(start: date, n: int, shift_to_workday: bool = True) -> date:
    end = start + timedelta(days=n)
    return next_workday_on_or_after(end) if shift_to_workday else end


def add_months(start: date, months: int, shift_to_workday: bool = True) -> date:
    """Ст. 192 ГК + ст. 193 ГК."""
    y, m = divmod(start.month - 1 + months, 12)
    y += start.year
    m += 1
    last = _cal.monthrange(y, m)[1]
    end = date(y, m, min(start.day, last))
    return next_workday_on_or_after(end) if shift_to_workday else end


def workdays_between(a: date, b: date) -> int:
    """Число рабочих дней в (a, b] — сколько рабочих дней прошло после a к концу дня b."""
    if b <= a:
        return 0
    n = 0
    d = a
    while d < b:
        d += timedelta(days=1)
        if is_workday(d):
            n += 1
    return n
