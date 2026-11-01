"""Собирает docs/sprint1/05-finmodel.xlsx — финмодель v2 эффекта для ВТБ (с формулами).

Спецификация — PROMPT.md, разд. 10: B = 1,3 млн; s = 0,3 / 1,7 / 3,6 %; остальные параметры —
из context/docs/concept.md, разд. 6.3; лист чувствительности по s и a; затраты — грубая оценка
(1 GPU on-prem, 3 FTE × 6 месяцев) с пометкой «уточняется в спринте 2».
Все результаты — формулы Excel; входы — синие, ключевые допущения — с жёлтой заливкой.

Запуск: python scripts/build_finmodel.py
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parents[1] / "docs" / "sprint1" / "05-finmodel.xlsx"

FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT, color="000000")
GREEN = Font(name=FONT, color="008000")
BOLD = Font(name=FONT, bold=True)
TITLE = Font(name=FONT, bold=True, size=13)
NOTE = Font(name=FONT, italic=True, color="555555", size=9)
YELLOW = PatternFill("solid", fgColor="FFFF00")
HEAD = PatternFill("solid", fgColor="CFE9FE")
THIN = Border(bottom=Side(style="thin", color="BBBBBB"))

RUB = '#,##0 "₽";(#,##0 "₽");-'
NUM = "#,##0;(#,##0);-"
NUM2 = "#,##0.00;(#,##0.00);-"
PCT = "0.0%;(0.0%);-"
YRS = '0.0 "лет";;-'

SCEN = ["Консерв.", "Базовый", "Оптим."]
COLS = ["C", "D", "E"]


def style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = BOLD
        cell.fill = HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="center")


def widths(ws, ws_widths: dict[str, int]) -> None:
    for col, w in ws_widths.items():
        ws.column_dimensions[col].width = w


def build() -> Workbook:
    wb = Workbook()

    # ---------------- Допущения ----------------
    a = wb.active
    a.title = "Допущения"
    a["A1"] = "Навигатор-115 · финмодель v2 эффекта для ВТБ · допущения"
    a["A1"].font = TITLE
    a["A2"] = ("Синий — вход (менять здесь), чёрный — формула, жёлтая заливка — ключевые допущения. "
               "«оценка» — допущение команды, а не факт источника. Версия 21.10.2026, черновик агента.")
    a["A2"].font = NOTE
    hdr = ["Параметр", "Обозн.", *SCEN, "Ед.", "Источник / основание"]
    for i, h in enumerate(hdr, 1):
        a.cell(row=4, column=i, value=h)
    style_header(a, 4, len(hdr))
    rows = [
        # (label, sym, values, fmt, unit, source, key)
        ("Клиенты МСБ ВТБ", "B", [1_300_000] * 3, NUM, "клиентов",
         "Д. Бортников, 28.02.2024: ~1,3 млн, «каждый третий реально действующий бизнес» (expertnw.com); свежей цифры за 2026 нет", False),
        ("Доля клиентов с запросом или ограничением за год", "s", [0.003, 0.017, 0.036], PCT, "доля",
         "0,3 % — Сбер: запросы получают <0,3 % клиентов (sberbusiness.live, 25.12.2025); 1,7 % и 3,6 % — Опора России × ПСБ, 2024: по 115-ФЗ 1,7 %, +1,9 % без объяснения (The Moscow Times, 02.08.2024)", True),
        ("Доля воспользовавшихся сервисом", "a", [0.10, 0.25, 0.40], PCT, "доля",
         "оценка: сервис встроен в Бизнес Платформу, клиенту присылают ссылку (concept.md, разд. 6.3)", True),
        ("Доля пакетов с повторным запросом без сервиса", "r", [0.30, 0.40, 0.50], PCT, "доля",
         "оценка, проверяем анкетой (Q12) и интервью", False),
        ("Снижение повторных запросов с сервисом", "d", [0.15, 0.25, 0.35], PCT, "доля",
         "ориентир Klarna −25 % повторных обращений (другой контекст: чат поддержки, самоотчёт); оценка", False),
        ("Часы комплаенса на один повторный цикл", "h_c", [0.75, 1.0, 1.5], NUM2, "ч",
         "оценка", False),
        ("Экономия на структурированном пакете (опись «пункт → документ»)", "h_s", [0.10, 0.25, 0.40], NUM2, "ч на пакет",
         "оценка; паттерн ING (GenAI-извлечение для CDD)", False),
        ("Средняя зарплата в банках", "w", [180_000] * 3, RUB, "₽/мес до НДФЛ",
         "Коммерсантъ, 27.04.2026 (concept.md, разд. 6.2); согласуется со срезом hh.ru по ПОД/ФТ (медиана 165 тыс., bank-request.md, 1.3)", False),
        ("Страховые взносы", "ins", [0.302] * 3, PCT, "доля", "упрощение (concept.md, разд. 6.2)", False),
        ("Рабочих часов в месяц", "hrs", [165] * 3, NUM, "ч", "оценка", False),
        ("Стоимость часа сотрудника банка", "c_h", None, RUB, "₽/ч", "формула: w × (1 + ins) / hrs; без накладных расходов", False),
        ("Обращения в КЦ по теме на клиента", "k", [1, 2, 3], NUM, "обращ.", "оценка", False),
        ("Снижение обращений в КЦ", "q", [0.15, 0.25, 0.35], PCT, "доля", "ориентир Klarna; антиметрика CommBank — рост обращений останавливает пилот", False),
        ("Стоимость обращения в КЦ", "p", [100, 150, 190], RUB, "₽", "оценка: 190 ₽ ≈ 8 мин × стоимость часа (верхняя граница)", False),
        ("Часы клиента, сэкономленные на сборе пакета", "t", [2, 3, 4], NUM2, "ч", "оценка, проверяем анкетой (Q15) и интервью", False),
        ("Срок рассмотрения документов банком", "rev", [7] * 3, NUM, "р. д.", "п. 13.4 ст. 7 115-ФЗ", False),
    ]
    sym_row: dict[str, int] = {}
    r = 5
    for label, sym, vals, fmt, unit, src, key in rows:
        a.cell(row=r, column=1, value=label).font = BLACK
        a.cell(row=r, column=2, value=sym).font = BLACK
        for j, col in enumerate(COLS):
            cell = a[f"{col}{r}"]
            if vals is None:  # c_h — формула
                cell.value = f"={col}{sym_row['w']}*(1+{col}{sym_row['ins']})/{col}{sym_row['hrs']}"
                cell.font = BLACK
            else:
                cell.value = vals[j]
                cell.font = BLUE
                if key:
                    cell.fill = YELLOW
            cell.number_format = fmt
        a.cell(row=r, column=6, value=unit).font = BLACK
        sc = a.cell(row=r, column=7, value=src)
        sc.font = Font(name=FONT, size=9)
        sc.alignment = Alignment(wrap_text=True, vertical="top")
        for c in range(1, 8):
            a.cell(row=r, column=c).border = THIN
        sym_row[sym] = r
        r += 1
    widths(a, {"A": 46, "B": 8, "C": 14, "D": 14, "E": 14, "F": 14, "G": 90})
    a.freeze_panes = "C5"

    def A(sym: str, col: str, absolute: bool = False) -> str:
        rr = sym_row[sym]
        return f"Допущения!${col}${rr}" if absolute else f"Допущения!{col}{rr}"

    # ---------------- Эффект ----------------
    e = wb.create_sheet("Эффект")
    e["A1"] = "Эффект для банка и клиентов в год (оценка, 3 сценария)"
    e["A1"].font = TITLE
    e["A2"] = ("Главная ценность для банка — исполнение писем ЦБ ИН-01-59/98 и ИН-03-59/11 (страж уведомлений), меньше жалоб и "
               "повторных циклов. Экономия ФОТ и КЦ — вторична. Удержание клиентов МСБ не монетизируем до данных пилота.")
    e["A2"].font = NOTE
    e["A2"].alignment = Alignment(wrap_text=True)
    e.row_dimensions[2].height = 30
    for i, h in enumerate(["Показатель", "Формула", *SCEN, "Ед."], 1):
        e.cell(row=4, column=i, value=h)
    style_header(e, 4, 6)
    eff = [
        ("N — клиенты ВТБ с запросом или ограничением", "B × s", lambda c: f"={A('B', c)}*{A('s', c)}", NUM, "клиентов"),
        ("U — пользователи сервиса", "N × a", lambda c: f"={c}5*{A('a', c)}", NUM, "пользователей"),
        ("C — избежанные повторные циклы запроса", "U × r × d", lambda c: f"={c}6*{A('r', c)}*{A('d', c)}", NUM, "циклов"),
        ("Часы комплаенса", "C × h_c + U × h_s", lambda c: f"={c}7*{A('h_c', c)}+{c}6*{A('h_s', c)}", NUM, "ч/год"),
        ("Экономия комплаенса", "часы × c_h", lambda c: f"={c}8*{A('c_h', c)}", RUB, "₽/год"),
        ("Избежанные обращения в КЦ", "U × k × q", lambda c: f"={c}6*{A('k', c)}*{A('q', c)}", NUM, "обращений"),
        ("Экономия КЦ", "обращения × p", lambda c: f"={c}10*{A('p', c)}", RUB, "₽/год"),
        ("Итого экономия банка", "комплаенс + КЦ", lambda c: f"={c}9+{c}11", RUB, "₽/год"),
        ("Часы клиентов", "U × t", lambda c: f"={c}6*{A('t', c)}", NUM, "ч/год"),
        ("Клиенто-дни ожидания, верхняя граница", "C × 7 р. д.", lambda c: f"={c}7*{A('rev', c)}", NUM, "дней"),
    ]
    for i, (label, formula, fn, fmt, unit) in enumerate(eff, start=5):
        e.cell(row=i, column=1, value=label).font = BOLD if label.startswith("Итого") else BLACK
        e.cell(row=i, column=2, value=formula).font = Font(name=FONT, size=9)
        for col in COLS:
            cell = e[f"{col}{i}"]
            cell.value = fn(col)
            cell.font = GREEN if "Допущения!" in cell.value else BLACK
            cell.number_format = fmt
            if label.startswith("Итого"):
                cell.font = Font(name=FONT, bold=True)
        e.cell(row=i, column=6, value=unit).font = BLACK
        for c in range(1, 7):
            e.cell(row=i, column=c).border = THIN
    widths(e, {"A": 44, "B": 22, "C": 16, "D": 16, "E": 16, "F": 14})

    # ---------------- Затраты ----------------
    z = wb.create_sheet("Затраты")
    z["A1"] = "Затраты: грубая оценка — уточняется в спринте 2"
    z["A1"].font = TITLE
    z["A2"] = "1 GPU on-prem в контуре банка и команда 3 FTE × 6 месяцев (PROMPT.md, разд. 10). Окупаемость — только на ФОТ и КЦ, без регуляторной ценности."
    z["A2"].font = NOTE
    for i, h in enumerate(["Статья", "Значение", "Ед.", "Источник / основание"], 1):
        z.cell(row=4, column=i, value=h)
    style_header(z, 4, 4)
    zrows = [
        ("Ускоритель NVIDIA L40S 48 ГБ", 1_083_000, RUB, "₽", "ServerFlow, карточка товара (с расширенной гарантией и НДС), срез 21.10.2026: serverflow.ru/catalog/komplektuyushchie/videokarty/nvidia-l40s/", True),
        ("Платформа сервера (CPU, RAM, SSD, корпус)", 1_500_000, RUB, "₽", "оценка команды без источника — запросить у поставщика в спринте 2", True),
        ("Срок амортизации оборудования", 3, NUM, "лет", "оценка", True),
        ("Команда на разработку и пилот, FTE", 3, NUM, "FTE", "PROMPT.md, разд. 10", True),
        ("Длительность разработки и пилота", 6, NUM, "мес", "PROMPT.md, разд. 10", True),
        ("Стоимость FTE в месяц", f"={A('w', 'D')}*(1+{A('ins', 'D')})", RUB, "₽/мес", "прокси: средняя зарплата в банках × (1 + взносы); оценка", False),
        ("Поддержка после пилота, FTE", 1, NUM, "FTE", "оценка", True),
    ]
    zr: dict[int, int] = {}
    for i, (label, val, fmt, unit, src, is_input) in enumerate(zrows, start=5):
        z.cell(row=i, column=1, value=label).font = BLACK
        c = z.cell(row=i, column=2, value=val)
        c.font = BLUE if is_input else GREEN
        c.number_format = fmt
        if "без источника" in src:
            c.fill = YELLOW
            c.comment = Comment("Оценка команды без источника. Уточнить у поставщика (спринт 2).", "Pulsar")
        z.cell(row=i, column=3, value=unit).font = BLACK
        s = z.cell(row=i, column=4, value=src)
        s.font = Font(name=FONT, size=9)
        s.alignment = Alignment(wrap_text=True)
        zr[i] = i
    # B5 GPU, B6 platform, B7 years, B8 FTE, B9 months, B10 FTE cost, B11 support FTE
    calc = [
        ("Оборудование, единовременно", "=B5+B6", RUB, "₽"),
        ("Разработка и пилот, единовременно", "=B8*B9*B10", RUB, "₽"),
        ("Итого единовременно", "=B13+B14", RUB, "₽"),
        ("Амортизация оборудования в год", "=IF(B7>0,B13/B7,0)", RUB, "₽/год"),
        ("Поддержка в год", "=B11*12*B10", RUB, "₽/год"),
        ("Итого текущие затраты в год", "=B16+B17", RUB, "₽/год"),
    ]
    for i, (label, f, fmt, unit) in enumerate(calc, start=13):
        z.cell(row=i, column=1, value=label).font = BOLD if label.startswith("Итого") else BLACK
        c = z.cell(row=i, column=2, value=f)
        c.font = BLACK
        c.number_format = fmt
        z.cell(row=i, column=3, value=unit).font = BLACK
    z["A21"] = "Окупаемость на экономии ФОТ и КЦ"
    z["A21"].font = BOLD
    for i, h in enumerate(["Показатель", *SCEN], 1):
        z.cell(row=22, column=i, value=h)
    style_header(z, 22, 4)
    z["A23"] = "Экономия банка в год"
    z["A24"] = "Чистая экономия в год (минус текущие затраты)"
    z["A25"] = "Срок окупаемости единовременных затрат"
    for j, col in enumerate(["B", "C", "D"]):
        ecol = COLS[j]
        z[f"{col}23"] = f"=Эффект!{ecol}12"
        z[f"{col}23"].font = GREEN
        z[f"{col}23"].number_format = RUB
        z[f"{col}24"] = f"={col}23-$B$18"
        z[f"{col}24"].number_format = RUB
        z[f"{col}24"].font = BLACK
        z[f"{col}25"] = f'=IF({col}24>0,$B$15/{col}24,"не окупается на ФОТ")'
        z[f"{col}25"].number_format = YRS
        z[f"{col}25"].font = BLACK
    z["A27"] = ("Вывод (оценка): в консервативном и базовом сценариях экономия ФОТ и КЦ не покрывает текущие затраты — "
                "окупаемость на ФОТ есть только в оптимистичном. Ценность для банка — исполнение писем ЦБ, меньше жалоб и "
                "повторных циклов, удержание МСБ (не монетизировано). Электроэнергия, лицензии и накладные не учтены (спринт 2).")
    z["A27"].font = NOTE
    z["A27"].alignment = Alignment(wrap_text=True)
    z.row_dimensions[27].height = 30
    widths(z, {"A": 46, "B": 18, "C": 18, "D": 60})

    # ---------------- Чувствительность ----------------
    s = wb.create_sheet("Чувствительность")
    s["A1"] = "Чувствительность итоговой экономии банка (₽/год) к s и a; остальные параметры — базовый сценарий"
    s["A1"].font = TITLE
    s["A2"] = "Строки — s (доля клиентов с запросом или ограничением), столбцы — a (доля воспользовавшихся). Значения s и a — входы, их можно менять."
    s["A2"].font = NOTE
    s_vals = [0.003, 0.010, 0.017, 0.027, 0.036]
    a_vals = [0.10, 0.25, 0.40]
    s["A4"] = "s \\ a"
    s["A4"].font = BOLD
    for j, av in enumerate(a_vals):
        c = s.cell(row=4, column=2 + j, value=av)
        c.font = BLUE
        c.number_format = PCT
        c.fill = HEAD
    per_user = (f"(({A('r', 'D', True)}*{A('d', 'D', True)}*{A('h_c', 'D', True)}+{A('h_s', 'D', True)})*{A('c_h', 'D', True)}"
                f"+{A('k', 'D', True)}*{A('q', 'D', True)}*{A('p', 'D', True)})")
    for i, sv in enumerate(s_vals):
        rr = 5 + i
        c = s.cell(row=rr, column=1, value=sv)
        c.font = BLUE
        c.number_format = PCT
        c.fill = HEAD
        for j in range(len(a_vals)):
            col = get_column_letter(2 + j)
            cell = s[f"{col}{rr}"]
            cell.value = f"={A('B', 'D', True)}*$A{rr}*{col}$4*{per_user}"
            cell.number_format = RUB
            cell.font = BLACK
    s["A11"] = "Пользователи сервиса U = B × s × a"
    s["A11"].font = BOLD
    s["A12"] = "s \\ a"
    s["A12"].font = BOLD
    for j in range(len(a_vals)):
        col = get_column_letter(2 + j)
        s[f"{col}12"] = f"={col}4"
        s[f"{col}12"].number_format = PCT
        s[f"{col}12"].fill = HEAD
    for i in range(len(s_vals)):
        rr = 13 + i
        s[f"A{rr}"] = f"=A{5 + i}"
        s[f"A{rr}"].number_format = PCT
        s[f"A{rr}"].fill = HEAD
        for j in range(len(a_vals)):
            col = get_column_letter(2 + j)
            s[f"{col}{rr}"] = f"={A('B', 'D', True)}*$A{rr}*{col}$12"
            s[f"{col}{rr}"].number_format = NUM
    widths(s, {"A": 18, "B": 18, "C": 18, "D": 18})

    # ---------------- Источники ----------------
    src = wb.create_sheet("Источники")
    src["A1"] = "Источники"
    src["A1"].font = TITLE
    items = [
        ("Клиенты МСБ ВТБ ~1,3 млн; цель ×1,5 к концу 2026", "https://expertnw.com/news/klientskaya-baza-srednego-i-malogo-biznesa-vtb-budet-rasshirena-v-1-5-raza/"),
        ("ИП — 53 % клиентов СМБ ВТБ (2023)", "https://www.dp.ru/a/2023/01/23/Klientami_VTB_stali_svishe"),
        ("Сбер: запросы по 115-ФЗ получают <0,3 % клиентов", "https://sberbusiness.live/publications/115fz-kak-sohranit-biznes-i-otnosheniya-s-bankom"),
        ("Опора России × ПСБ, 2024: блокировки МСП 11 %, по 115-ФЗ 1,7 %, без объяснения 1,9 %", "https://ru.themoscowtimes.com/2024/08/02/rossiiskim-kompaniyam-stali-vtroe-chasche-blokirovat-scheta-a138515"),
        ("Средняя зарплата в банках 180 тыс. ₽ (Коммерсантъ, 27.04.2026)", "https://www.kommersant.ru/doc/8623368"),
        ("Klarna: −25 % повторных обращений (самоотчёт, другой контекст)", "https://siliconcanals.com/klarna-unveils-ai-assistant/"),
        ("CommBank: откат голосового бота — антиметрика", "https://fstech.co.uk/fst/CommBank_Backtracks_On_Plans_To_Replace_Customer_Service_Roles_With_AI.php"),
        ("NVIDIA L40S 48 ГБ — 1 083 000 ₽ (ServerFlow, срез 21.10.2026)", "https://serverflow.ru/catalog/komplektuyushchie/videokarty/nvidia-l40s/"),
        ("Срок рассмотрения документов 7 р. д. — п. 13.4 ст. 7 115-ФЗ", "kb/sources (первоисточник, см. MANIFEST.yaml)"),
        ("Методика и параметры — concept.md, разд. 6", "context/docs/concept.md"),
    ]
    for i, (t, u) in enumerate(items, start=3):
        src.cell(row=i, column=1, value=t).font = BLACK
        src.cell(row=i, column=2, value=u).font = Font(name=FONT, size=9, color="0A86E0")
    widths(src, {"A": 80, "B": 100})

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.font and cell.font.name != FONT:
                    cell.font = Font(name=FONT, bold=cell.font.bold, italic=cell.font.italic, color=cell.font.color, size=cell.font.size)
    wb.calculation.fullCalcOnLoad = True
    return wb


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    build().save(OUT)
    print(f"→ {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
