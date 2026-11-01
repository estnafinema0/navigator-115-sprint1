"""Календарь в kb/calendar совпадает с постановлениями Правительства РФ и ст. 112 ТК РФ.

Ожидаемые списки выписаны из первоисточников при сборе 21.10.2026:
2026 — ПП РФ от 24.09.2025 № 1466; 2027 — ПП РФ от 17.09.2026 № 1187
(kb/sources/calendar/gov-decree-*.txt) + автоматический перенос по ч. 2 ст. 112 ТК РФ.
"""
from datetime import date

import pytest
from navigator import workcalendar as wc

EXPECTED_NONWORKING_WEEKDAYS = {
    2026: ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09",
           "2026-02-23", "2026-03-09", "2026-05-01", "2026-05-11", "2026-06-12", "2026-11-04", "2026-12-31"],
    2027: ["2027-01-01", "2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08", "2027-02-22",
           "2027-02-23", "2027-03-08", "2027-05-03", "2027-05-10", "2027-06-14", "2027-11-04", "2027-11-05", "2027-12-31"],
}
EXPECTED_WORKING_WEEKENDS = {2026: [], 2027: ["2027-02-20"]}


@pytest.mark.parametrize("year", [2026, 2027])
def test_calendar_matches_decree(year):
    yc = wc.load_year(year)
    assert sorted(d.isoformat() for d in yc.nonworking_weekdays) == EXPECTED_NONWORKING_WEEKDAYS[year]
    assert sorted(d.isoformat() for d in yc.working_weekends) == EXPECTED_WORKING_WEEKENDS[year]
    assert "Постановление Правительства" in yc.source["primary"]


def test_working_saturday_2027():
    assert wc.is_workday(date(2027, 2, 20))
