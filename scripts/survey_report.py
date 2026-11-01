"""Отчёт по опросам спринта 1 (docs/ops/opros-prompt.md) из CSV-выгрузок.

Ожидает в папке файлы, имя которых начинается с О1…О5 (основная, эксперты, после демо,
через 14 дней, сотрудники банков); колонки называются кодами вопросов (Q1, BH1, T1, D5, F3, S1…).
Множественный выбор разделён «; ». Колонки «метка» и «разметка_персонаж» необязательны:
если хотя бы одна строка помечена «СИНТЕТИКА», отчёт получает плашку «не доказательство».

Правила показа (разд. 2 и 4 опросника): доли с 95 % интервалом Уилсона; проценты по всей
выборке при n ≥ 30, в подгруппах при n ≥ 10, иначе «k из n»; при n < 5 «не измерено».

Пример: python scripts/survey_report.py --dir data/synthetic/survey --out reports/survey-synthetic-2026-10-26.md
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path

ORD = {
    "Q11": ["в течение часа", "в тот же день", "2–3 дня", "около недели", "больше недели", "так и не понял(а)"],
    "Q13": ["до 1 дня", "2–5 дней", "6–14 дней", "15–30 дней", "1–3 месяца", "больше 3 месяцев"],
    "Q14": ["до 10 дней", "11–20 дней", "21–45 дней", "больше 45 дней"],
    "Q15": ["до 2 часов", "2–5", "6–10", "11–20", "больше 20"],
    "Q16a": ["до 5 тыс. ₽", "5–15 тыс.", "15–30 тыс.", "30–50 тыс.", "50–100 тыс.", "больше 100 тыс."],
    "BH1": ["до 5", "6–10", "11–20", "21–50", "больше 50"],
    "BH4": ["до 1 часа", "1–3", "3–5", "5–10", "больше 10"],
    "BH6": ["до 2 тыс. ₽", "2–5 тыс.", "5–10 тыс.", "10–20 тыс.", "больше 20 тыс."],
    "D5": ["меньше минуты", "1–3 минуты", "3–10 минут", "больше 10 минут", "так и не понял(а)"],
    "F4": ["до 3", "4–7", "8–14", "больше 14"],
}
MULTI = {"Q8", "Q11a", "Q16", "Q19", "D6a", "F6", "S4"}


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def find(d: Path, prefix: str) -> list[dict]:
    files = sorted(d.glob(f"{prefix}*.csv"))
    return load(files[0]) if files else []


def vals(r: dict, k: str) -> list[str]:
    v = r.get(k, "")
    if not v:
        return []
    return [x.strip() for x in v.split(";") if x.strip()] if k in MULTI else [v]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def share(k: int, n: int, min_pct: int = 30) -> str:
    if n < 5:
        return f"{k} из {n} (не измерено, n < 5)"
    if n < min_pct:
        return f"{k} из {n}"
    lo, hi = wilson(k, n)
    return f"{k} из {n} = {k / n:.0%} (95 % ДИ {lo:.0%}–{hi:.0%})"


def median_bin(rows: list[dict], k: str) -> str:
    order = ORD[k]
    xs = sorted(order.index(r[k]) for r in rows if r.get(k) in order)
    if len(xs) < 5:
        return f"не измерено (n = {len(xs)})"
    return f"медиана: {order[xs[(len(xs) - 1) // 2]]} (n = {len(xs)})"


def dist(rows: list[dict], k: str) -> tuple[Counter, int]:
    c: Counter = Counter()
    n = 0
    for r in rows:
        v = vals(r, k)
        if v:
            n += 1
            c.update(v)
    return c, n


def table(rows: list[dict], k: str, title: str, min_pct: int = 30) -> list[str]:
    c, n = dist(rows, k)
    out = [f"**{k}. {title}** (ответили {n})", "", "| Вариант | Доля |", "|---|---|"]
    out += [f"| {v} | {share(m, n, min_pct)} |" for v, m in c.most_common()]
    return out + [""]


def section_main(rows: list[dict]) -> list[str]:
    total = len(rows)
    rows = [r for r in rows if r.get("Q3") and not r["Q3"].startswith("Нет")]
    out = ["## Опрос 1. Основная анкета", "", f"Всего анкет: {total}; прошли скрининг (Q3 не «Нет»): {len(rows)}.", ""]
    if len(rows) < 30:
        out += ["**Меньше 30 ответов после скрининга: проценты по всей выборке не показываем.**", ""]
    case = [r for r in rows if "налоговая" not in r.get("Q5", "")]
    out += ["### Главные цифры для Discovery", "", "| Показатель | Значение |", "|---|---|"]
    q11 = [r for r in case if r.get("Q11")]
    out.append(f"| Так и не понял(а) или дольше недели до понимания «что делать» (Q11) | "
               f"{share(sum(r['Q11'] in ('больше недели', 'так и не понял(а)') for r in q11), len(q11))} |")
    q12 = [r for r in case if r.get("Q12") in ("ни разу", "1 раз", "2 раза", "3 раза и больше")]
    out.append(f"| Был хотя бы один дозапрос, среди ответивших банку (Q12) | {share(sum(r['Q12'] != 'ни разу' for r in q12), len(q12))} |")
    out.append(f"| Пакет принят без дозапроса: базовая линия North Star (Q12 = «ни разу») | {share(sum(r['Q12'] == 'ни разу' for r in q12), len(q12))} |")
    q14 = [r for r in case if r.get("Q14") in ORD["Q14"]]
    out.append(f"| Банк рассматривал документы дольше 10 дней (Q14) | {share(sum(r['Q14'] != 'до 10 дней' for r in q14), len(q14))} |")
    q16 = [r for r in case if r.get("Q16")]
    paid = [r for r in q16 if any(v.startswith("Да") for v in vals(r, "Q16"))]
    out.append(f"| Платили за помощь (Q16) | {share(len(paid), len(q16))} |")
    out.append(f"| Сколько заплатили (Q16a) | {median_bin(paid, 'Q16a')} |")
    q18 = [r for r in case if r.get("Q18")]
    out.append(f"| Сменили банк хотя бы частично (Q18) | {share(sum(r['Q18'].startswith(('Открыл', 'Полностью')) for r in q18), len(q18))} |")
    out.append(f"| Полностью ушли в другой банк (Q18) | {share(sum(r['Q18'].startswith('Полностью') for r in q18), len(q18))} |")
    q10 = [r for r in case if r.get("Q10д") in ("было", "не было")]
    out.append(f"| МВК была в тексте банка, по памяти (Q10д) | {share(sum(r['Q10д'] == 'было' for r in q10), len(q10))} |")
    q19 = [r for r in case if r.get("Q19")]
    out.append(f"| Обращались в МВК (Q19) | {share(sum('МВК' in r['Q19'] for r in q19), len(q19))} |")
    q11a = [r for r in case if r.get("Q11a")]
    out.append(f"| Пробовали нейросети, чтобы разобраться (Q11a) | {share(sum('Нейросеть' in r['Q11a'] for r in q11a), len(q11a))} |")
    for k in ("Q11", "Q13", "Q14", "Q15"):
        out.append(f"| {k}: срединный интервал | {median_bin(case, k)} |")
    out += ["", "### Что банк написал, по памяти респондентов (Q10)", "", "| Элемент | Было |", "|---|---|"]
    for k, lab in [("Q10а", "закон или статья"), ("Q10б", "срок"), ("Q10в", "список документов"),
                   ("Q10г", "что сделать"), ("Q10д", "МВК"), ("Q10е", "как обжаловать")]:
        rr = [r for r in case if r.get(k) in ("было", "не было", "не помню")]
        out.append(f"| {lab} | {share(sum(r[k] == 'было' for r in rr), len(rr))} |")
    out += ["", "Сравнение с корпусом (норма 16 %, срок 22 %, МВК 0 из 45) только с оговоркой: анкета это память, корпус это тексты.", ""]
    out += ["### Распределения", ""]
    for k, t in [("Q1", "Кто вы"), ("Q5", "Что произошло"), ("Q6", "Банк"), ("Q8", "Как узнали"),
                 ("Q11a", "Чем пользовались, чтобы разобраться"), ("Q17", "Чем закончилось"),
                 ("Q19", "Куда обращались"), ("Q20", "Удар по работе, 1–5"), ("Q22", "Канал прихода")]:
        out += table(rows, k, t)
    out += ["### Срезы (проценты только при n ≥ 10)", "", "| Срез | n | Дозапрос ≥ 1 | Платили | Сменили банк |", "|---|---|---|---|---|"]
    groups = {"ВТБ": [r for r in case if r.get("Q6") == "ВТБ"], "другие банки": [r for r in case if r.get("Q6") and r["Q6"] != "ВТБ"]}
    for seg in sorted({r["Q1"] for r in case if r.get("Q1")}):
        groups[seg] = [r for r in case if r.get("Q1") == seg]
    for g, rr in groups.items():
        a = [r for r in rr if r.get("Q12") in ("ни разу", "1 раз", "2 раза", "3 раза и больше")]
        b = [r for r in rr if r.get("Q16")]
        c = [r for r in rr if r.get("Q18")]
        out.append(f"| {g} | {len(rr)} | {share(sum(r['Q12'] != 'ни разу' for r in a), len(a), 10)} | "
                   f"{share(sum(any(v.startswith('Да') for v in vals(r, 'Q16')) for r in b), len(b), 10)} | "
                   f"{share(sum(r['Q18'].startswith(('Открыл', 'Полностью')) for r in c), len(c), 10)} |")
    bh = [r for r in rows if r.get("BH1")]
    out += ["", f"### Бухгалтеры на аутсорсе (n = {len(bh)})", ""]
    for k in ("BH1", "BH4", "BH6"):
        out.append(f"- {k}: {median_bin(bh, k)}")
    out += [""] + table(bh, "BH5", "Отдельная плата за ответ", 10)
    out += ["### Открытые ответы (Q21, YU3)", "", "Раскладывают по болям двое из команды независимо; здесь только количество.", "",
            f"- Q21: {sum(bool(r.get('Q21')) for r in rows)} ответов; YU3: {sum(bool(r.get('YU3')) for r in rows)} ответов.", ""]
    return out


def section_experts(rows: list[dict]) -> list[str]:
    out = ["## Опрос 2. Экспертная проверка сроков и маршрутов", "", f"Экспертов: {len(rows)}.", "",
           "| Утверждение | верно | с оговоркой | неверно | не знаю |", "|---|---|---|---|---|"]
    keys = [k for k in (rows[0].keys() if rows else []) if k[:1] in "TR" and k[1:].isdigit()]
    flagged = []
    for k in keys:
        c = Counter(r.get(k, "") for r in rows)
        out.append(f"| {k} | {c['верно']} | {c['верно с оговоркой']} | {c['неверно']} | {c['не знаю']} |")
        for r in rows:
            if r.get(k) in ("верно с оговоркой", "неверно") and r.get(f"{k}_комм"):
                flagged.append(f"- **{k}** ({r[k]}, {r.get('resp_id', '?')}): {r[f'{k}_комм']}")
    out += ["", "### Оговорки и возражения: что править в kb/norms", ""] + (flagged or ["- нет"]) + [""]
    for k, t in [("G2", "Где сервис может навредить"), ("G3", "Чего не делать"), ("G4", "Что упущено")]:
        ans = [f"- {r[k]}" for r in rows if r.get(k)]
        if ans:
            out += [f"### {t} ({k})", ""] + ans + [""]
    return out


def section_demo(rows: list[dict], main: list[dict]) -> list[str]:
    out = ["## Опрос 3. После пробы демо", "", f"Ответов: {len(rows)}.", ""]
    out += table(rows, "D2", "На каком тексте", 30) + table(rows, "D6", "Совпали ли цитаты", 30) + table(rows, "D6a", "Где ошибки", 30)
    out.append(f"- Время до понимания с продуктом (D5): {median_bin(rows, 'D5')}; без продукта (Q11 основной анкеты): {median_bin(main, 'Q11')}. Шкалы разные (минуты против дней), сравнение только качественное.")
    um = [((int(r["D9"]) - 1) + (int(r["D10"]) - 1)) / 12 * 100 for r in rows if r.get("D9", "").isdigit() and r.get("D10", "").isdigit()]
    if len(um) >= 5:
        out.append(f"- UMUX-Lite (D9, D10): среднее {sum(um) / len(um):.0f} из 100 (n = {len(um)}).")
    else:
        out.append(f"- UMUX-Lite: не измерено (n = {len(um)}).")
    cs = [r for r in rows if r.get("D11", "").isdigit()]
    out.append(f"- CSAT, доля 4–5 (D11): {share(sum(int(r['D11']) >= 4 for r in cs), len(cs))}.")
    tr = [r for r in rows if r.get("D7", "").isdigit()]
    out.append(f"- Доверие к сроку 4–5 (D7): {share(sum(int(r['D7']) >= 4 for r in tr), len(tr))}.")
    out += [""] + table(rows, "D8", "Заявление", 30)
    return out


def section_followup(rows: list[dict]) -> list[str]:
    den = [r for r in rows if r.get("F2", "").startswith("да")]
    num = [r for r in den if r.get("F3") == "да, без дозапроса"]
    return ["## Опрос 4. Через 14 дней", "", f"Ответов: {len(rows)}.", "",
            f"- North Star (пакет принят без дозапроса, среди ответивших банку): {share(len(num), len(den))}.", ""] + table(rows, "F5", "Исход", 30)


def section_bank(rows: list[dict]) -> list[str]:
    out = ["## Опрос 5. Сотрудники банков", "", f"Ответов: {len(rows)}. Мнение отдельных сотрудников, не позиция банка.", ""]
    for k, t in [("S1", "Роль"), ("S4", "Что непонятно клиентам"), ("S6", "Как часто повторный запрос"), ("S8", "Полезность проверки уведомлений, 1–5"), ("S9", "Полезность пакета по пунктам, 1–5")]:
        out += table(rows, k, t, 30)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.dir)
    data = {p: find(d, p) for p in ("О1", "О2", "О3", "О4", "О5")}
    labels = Counter(r.get("метка", "") for rows in data.values() for r in rows)
    synth = any("СИНТЕТИКА" in k.upper() for k in labels)
    out = ["# Отчёт по опросам спринта 1", ""]
    if synth:
        out += ["> **СИНТЕТИКА. Не доказательство.** Ответы сгенерированы для проверки анализа, это не реальные респонденты.",
                "> В дек, Discovery и материалы для жюри эти цифры не берём.", ""]
    out += [f"Источник: `{d}`. Метки строк: " + ", ".join(f"{k or 'без метки'} — {v}" for k, v in labels.items()) + ".",
            "Ограничения выборки: самоотбор, перекос по каналу (Q22), память за 2 года, нет закрывшихся бизнесов, возможны дубли.", ""]
    if data["О1"]:
        out += section_main(data["О1"])
    if data["О2"]:
        out += section_experts(data["О2"])
    if data["О3"]:
        out += section_demo(data["О3"], data["О1"])
    if data["О4"]:
        out += section_followup(data["О4"])
    if data["О5"]:
        out += section_bank(data["О5"])
    Path(a.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{a.out}: {sum(len(v) for v in data.values())} строк, синтетика: {synth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
