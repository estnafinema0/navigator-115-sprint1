"""Отчёт по корпусу: доли элементов уведомления E1–E9 (make corpus-stats).

Сейчас — по ручной разметке кодировщика 1 (data/real/corpus.jsonl, поле elements).
После M9 сюда добавится колонка автоматической проверки стражем и согласие страж ↔ человек.
Знаменатели честные: «н/п» исключается, n указывается всегда.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))
from navigator.guard import check  # noqa: E402

CORPUS = ROOT / "data" / "real" / "corpus.jsonl"
OUT = ROOT / "reports" / "corpus-compliance.md"


def pct(k: int, n: int) -> str:
    return f"{k}/{n} = {round(100 * k / n)} %" if n else "н/д"


def block(rows: list[dict]) -> dict[str, str]:
    n = len(rows)
    el = [r["elements"] for r in rows]
    todo = [e for e in el if e["E4"] != "na"]
    chan = [e for e in el if e["E6"] != "na"]
    all4 = sum(1 for e in el if e["E2"] == "norm" and e["deadline"] == "yes" and e["E4"] == "yes" and e["E5"] == "external")
    mvk = sum(1 for r in rows if "МВК" in r["text"] or "межведомствен" in r["text"].lower())
    return {
        "N": str(n),
        "E2 норма (статья/пункт закона)": pct(sum(e["E2"] == "norm" for e in el), n),
        "E2 закон назван хотя бы без статьи": pct(sum(e["E2"] in ("norm", "law_only") for e in el), n),
        "E2 только пункт договора": pct(sum(e["E2"] == "contract_only" for e in el), n),
        "Срок (ответа или рассмотрения)": pct(sum(e["deadline"] == "yes" for e in el), n),
        "E3 причина конкретная": pct(sum(e["E3"] == "specific" for e in el), n),
        "E3 причина хотя бы общая": pct(sum(e["E3"] in ("specific", "general") for e in el), n),
        "E4 что делать (да), без «н/п»": pct(sum(e["E4"] == "yes" for e in todo), len(todo)),
        "E5 обжалование вне банка (МВК/ЦБ/суд)": pct(sum(e["E5"] == "external" for e in el), n),
        "E5 хоть какое-то, вкл. реабилитацию в банке": pct(sum(e["E5"] in ("external", "internal_only") for e in el), n),
        "МВК упомянута в тексте (поиск по тексту)": pct(mvk, n),
        "E6 канал при ограничении ДБО, без «н/п»": pct(sum(e["E6"] == "yes" for e in chan), len(chan)),
        "Все четыре: норма + срок + что делать + обжалование": pct(all4, n),
    }


def human_for_guard(r: dict, k: str) -> str:
    e = r["elements"]
    return {
        "E2": e["E2"],
        "E3": "present" if e["E3"] in ("specific", "general", "partial") else "no",
        "E4": {"yes": "yes", "partial": "yes", "no": "no", "na": "na"}[e["E4"]],
        "E5": e["E5"],
        "E6": e["E6"],
        "deadline": e["deadline"],
    }[k]


GUARD_LABELS = {
    "E2": "E2 основание (норма / закон / договор / нет)",
    "E3": "E3 причина названа",
    "E4": "E4 что делать",
    "E5": "E5 обжалование (вне банка / в банке / нет)",
    "E6": "E6 канал (дистанционный / только офис / нет)",
    "deadline": "Срок",
}


def guard_agreement(rows: list[dict]) -> list[str]:
    """Согласие стража v0 (правила) с кодировщиком 1 — только дословные и частично дословные тексты."""
    rows = [r for r in rows if r["text_type"] != "retelling"]
    out = ["| Элемент | Совпадение с кодировщиком 1 | Расхождения (ID) |", "|---|---|---|"]
    forb = []
    for k, label in GUARD_LABELS.items():
        ok = n = 0
        bad = []
        for r in rows:
            h = human_for_guard(r, k)
            if h == "na":
                continue
            a = check(r["text"]).elements[k]
            n += 1
            ok += a == h
            if a != h:
                bad.append(f"{r['id']} ({h}→{a})")
        out.append(f"| {label} | {pct(ok, n)} | {', '.join(bad) or '—'} |")
    for r in rows:
        g = check(r["text"])
        for f in g.forbidden:
            forb.append(f"{r['id']}: {f['label']} — «{f['hits'][0]['quote']}»")
    out += ["", "Стоп-лист стража сработал: " + ("; ".join(forb) if forb else "ни разу") + "."]
    return out


def main() -> int:
    rows = [json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x]
    biz = [r for r in rows if "ИП" in r["client_type"]]
    verb = [r for r in rows if r["text_type"] != "retelling"]
    cols = {"Все": block(rows), "ИП и бизнес": block(biz), "Дословные и частично": block(verb)}
    keys = list(cols["Все"].keys())
    banks = Counter(r["bank_key"] for r in rows)
    lines = [
        "# Отчёт по корпусу уведомлений банков: элементы E1–E9",
        "",
        f"Сформирован `make corpus-stats` {date.today():%d.%m.%Y}. Источник — `data/real/corpus.jsonl` "
        "(45 публичных текстов 2007–2026, разметка кодировщика 1 от 10.10.2026, второго кодировщика пока нет).",
        "",
        "**Статус: предварительно.** Выборка из публичных отзывов и публикаций, смещена к конфликтным случаям; "
        "19 из 45 текстов — пересказы клиентов; «нет» означает «нет в опубликованном фрагменте». Это не аудит банков.",
        "",
        "| Показатель | " + " | ".join(cols) + " |",
        "|---|" + "---|" * len(cols),
    ]
    for k in keys:
        lines.append(f"| {k} | " + " | ".join(cols[c][k] for c in cols) + " |")
    lines += [
        "",
        "## Страж v0 (правила) против ручной разметки",
        "",
        "Базовая линия до настройки: правила портированы из прототипа и **не подгонялись под этот корпус** "
        "(он — eval-набор). Сравнение только на дословных и частично дословных текстах. Часть расхождений "
        "объясняется тем, что кодировщик видел полный источник, а в корпусе — фрагмент ≤300 знаков.",
        "",
        *guard_agreement(rows),
        "",
        "Элементы — по письмам ЦБ ИН-01-59/98 и ИН-03-59/11 (коды E1–E9 — `context/research/corpus-requests.md`, разд. 1). "
        "E1 (факт и вид меры) есть во всех текстах; E8 (проактивность) и E9 (не вводить в заблуждение) по отзывам не кодируются.",
        "",
        "Банки в корпусе: " + ", ".join(f"{b} — {n}" for b, n in banks.most_common()) + ".",
        "",
        "Следующие шаги: (1) второй кодировщик на 20 текстах и κ; (2) настройка стража на dev-части (сплит по банку) "
        "и red-team наборе ≥60 уведомлений, отчёт — на отложенной части (M9, до 26.10); (3) корпус ≥60 текстов к 01.11 "
        "(≥5 по ВТБ — только с согласия респондентов и обезличенно).",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[8 : 8 + len(keys)]))
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
