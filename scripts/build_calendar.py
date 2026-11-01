"""Собирает kb/calendar/ru-<год>.yaml из данных xmlcalendar (kb/sources/calendar/).

Формат xmlcalendar: t=1 — нерабочий (праздник или перенос), t=2 — сокращённый (если это суббота
или воскресенье — значит, рабочий выходной по переносу), t=3 — рабочий выходной. Первоисточник — постановления Правительства РФ о переносе выходных и ст. 112 ТК РФ;
сверка xmlcalendar с ними сделана при сборе (kb/sources/MANIFEST.yaml, поле reconciliation)
и закреплена тестом tests/test_calendar_data.py.

Запуск: python scripts/build_calendar.py
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "kb" / "sources" / "calendar"
OUT = ROOT / "kb" / "calendar"

DECREES = {
    2026: {"decree": "Постановление Правительства РФ от 24.09.2025 № 1466", "file": "kb/sources/calendar/gov-decree-1466_2025-09-24.pdf"},
    2027: {"decree": "Постановление Правительства РФ от 17.09.2026 № 1187", "file": "kb/sources/calendar/gov-decree-1187_2026-09-17.pdf"},
}


def build(year: int) -> dict:
    root = ET.parse(SRC / f"xmlcalendar-ru-{year}.xml").getroot()
    nonworking, working_weekends, shortened, holidays = [], [], [], []
    for d in root.iter("day"):
        mm, dd = (int(x) for x in d.get("d").split("."))
        dt = date(year, mm, dd)
        t = d.get("t")
        if t == "1":
            if d.get("h"):
                holidays.append(dt.isoformat())
            if dt.weekday() < 5:
                nonworking.append(dt.isoformat())
        elif t == "2":
            shortened.append(dt.isoformat())
            if dt.weekday() >= 5:  # сокращённый день на выходном = рабочий выходной (перенос)
                working_weekends.append(dt.isoformat())
        elif t == "3":
            if dt.weekday() >= 5:
                working_weekends.append(dt.isoformat())
    return {
        "year": year,
        "source": {
            "primary": DECREES[year]["decree"] + "; ст. 112 ТК РФ (автоматический перенос)",
            "primary_file": DECREES[year]["file"],
            "data": f"xmlcalendar (kb/sources/calendar/xmlcalendar-ru-{year}.xml), атрибут date={root.get('date')}",
            "reconciled": "2026-10-21: нерабочие будни и переносы совпадают с постановлением и ст. 112 ТК (MANIFEST.yaml → reconciliation)",
        },
        "holidays": sorted(holidays),
        "nonworking_weekdays": sorted(nonworking),
        "working_weekends": sorted(working_weekends),
        "shortened": sorted(shortened),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for year in sorted(DECREES):
        data = build(year)
        path = OUT / f"ru-{year}.yaml"
        header = f"# Производственный календарь РФ на {year} год. Сгенерировано scripts/build_calendar.py — не править вручную.\n"
        path.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"{year}: нерабочих будней {len(data['nonworking_weekdays'])}, рабочих выходных {len(data['working_weekends'])} → {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
