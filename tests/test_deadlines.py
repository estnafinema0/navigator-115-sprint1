"""M4: календарь и таймеры. Даты — детерминированно, по производственному календарю."""
from datetime import date

import pytest
from navigator import deadlines as dl
from navigator import workcalendar as wc


def test_known_holidays_2026():
    # 01–11.01.2026 — нерабочие (новогодние каникулы с переносом), 12.01 — понедельник, рабочий
    assert not wc.is_workday(date(2026, 1, 5))
    assert not wc.is_workday(date(2026, 1, 9))
    assert wc.is_workday(date(2026, 1, 12))
    assert not wc.is_workday(date(2026, 11, 4))  # День народного единства (ср)
    assert not wc.is_workday(date(2026, 10, 24))  # суббота


def test_add_workdays_skips_weekend_and_holiday():
    # отказ 30.10.2026 (пт) → 5 р.д.: 2.11 (пн), 3.11 (вт), [4.11 праздник], 5.11, 6.11, 9.11
    assert wc.add_workdays(date(2026, 10, 30), 5) == date(2026, 11, 9)


def test_bank_review_7wd_over_new_year():
    # документы 29.12.2026 (вт): 30.12 — 1-й р.д.; 31.12 и январские праздники 2027 — по календарю
    d = dl.compute("bank_review_7wd", date(2026, 12, 29))
    assert wc.workdays_between(date(2026, 12, 29), d.due) == 7
    assert wc.is_workday(d.due)


def test_2027_spring_holidays_from_data():
    # из ресерча (tech-architecture.md): 22.02, 03.05, 10.05.2027 — нерабочие; проверено по постановлению
    for d in (date(2027, 2, 22), date(2027, 5, 3), date(2027, 5, 10)):
        assert not wc.is_workday(d), d


def test_months_end_of_month_and_shift():
    # ст. 192 ГК: 31.08 + 6 мес. = 28.02 (нет 31-го), ст. 193: перенос на рабочий день, если выходной
    due = wc.add_months(date(2026, 8, 31), 6)
    assert due >= date(2027, 2, 28) and wc.is_workday(due)


def test_missing_year_is_honest_gap():
    with pytest.raises(wc.CalendarGap):
        wc.is_workday(date(2031, 1, 1))


def test_doc_request_has_no_statutory_deadline():
    assert not dl.has_statutory_client_deadline("doc_request")
    assert dl.timers_for("doc_request") == []


def test_operation_refusal_timers():
    assert {"refusal_notice_5wd", "bank_review_7wd", "mvk_review_20wd"} <= set(dl.timers_for("operation_refusal"))
