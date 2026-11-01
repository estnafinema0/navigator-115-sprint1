"""Шаблоны команды (M5, P1): напоминание банку о сроке п. 13.4 и обращение в Банк России.

Каждый документ помечен «Шаблон Навигатора-115, не шаблон Банка России». В документе — только
факты дела (даты, номера, реквизиты) и дословные нормы из kb/norms/timers.yaml. Доводы и оценки
действий банка не пишутся. Пустые поля остаются «____», заявитель заполняет их сам.

Проверки до сборки (протокол красной команды 27.10, атака 7): документ не утверждает того, чего нет в
фактах дела. Напоминание «срок истёк» собирается, только если по дате представления документов
и производственному календарю срок банка (7 р. д., п. 13.4 ст. 7 115-ФЗ) уже истёк; дату истечения
считает код, а не пользователь. Коды предупреждений и отказов — DOC_CODES (их показывает веб).
"""
from __future__ import annotations

import io
from datetime import date

from docx import Document
from docx.shared import Pt

from .deadlines import compute, load_timers
from .workcalendar import CalendarGap

MARK = "Шаблон Навигатора-115, не шаблон Банка России. Проверьте данные перед отправкой; это не юридическая консультация."
BLANK = "________"


# Коды для веба: X-Navigator-Warnings (через запятую) при 200 и detail.code при 409/422.
DOC_CODES: dict[str, str] = {
    "docs_submitted_date_missing": "Укажите дату, когда вы представили документы в банк: без неё срок банка не посчитать.",
    "bank_deadline_not_expired": "Срок банка по п. 13.4 ст. 7 115-ФЗ ещё не истёк: напоминание можно будет собрать после этой даты.",
    "calendar_gap": "Для этого года нет проверенного производственного календаря: срок не посчитан.",
    "review_due_date_recomputed": "Дата истечения срока банка посчитана по календарю и заменила введённую вручную.",
    "first_level_required": "Заявление в МВК подаётся после первого уровня: сначала документы в банк по п. 13.4 и ответ банка.",
    "first_level_pending": "Банк ещё рассматривает документы (срок 7 рабочих дней не истёк): заявление в МВК пока рано.",
    "first_level_unverified": "Не удалось проверить, пройден ли первый уровень: укажите дату представления документов в банк и дату ответа банка.",
    "bank_answer_missing": "Срок банка истёк, а дата ответа банка не указана: проверьте, что у вас есть решение банка по п. 13.4.",
    "template_not_for_scenario": "Этот шаблон не подходит к мере из письма банка.",
    "refusal_date_missing": "Дата отказа не указана: возьмите её из уведомления банка, а не из даты платёжки.",
    "refusal_date_equals_po_date": "Дата отказа совпадает с датой платёжки: проверьте по уведомлению банка, это могут быть разные дни.",
    "refusal_date_before_po_date": "Дата отказа раньше даты платёжки: проверьте даты.",
    "bank_reasons_inserted": "В заявление вставлены причины, которые сообщил банк, дословно: проверьте их по письму банка.",
}


class DocBlocked(Exception):
    """Документ не собирается: факты дела противоречат его утверждениям или не позволяют их проверить."""

    def __init__(self, code: str, status: int = 409, **extra):
        super().__init__(code)
        self.code, self.status, self.extra = code, status, extra

    def detail(self) -> dict:
        return {"code": self.code, "message": DOC_CODES[self.code], **self.extra}


def _today() -> date:
    return date.today()


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v:
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def bank_review_due(values: dict) -> date | None:
    """Последний день срока банка (7 р. д. со дня представления документов) или None, если даты нет."""
    submitted = _as_date(values.get("docs_submitted_date"))
    if submitted is None:
        return None
    try:
        return compute("bank_review_7wd", submitted).due
    except CalendarGap as e:
        raise DocBlocked("calendar_gap", status=422) from e


def refusal_date_warnings(values: dict) -> list[str]:
    ref, po = _as_date(values.get("refusal_date")), _as_date(values.get("po_date"))
    if ref is None:
        return ["refusal_date_missing"]
    if po and ref == po:
        return ["refusal_date_equals_po_date"]
    if po and ref < po:
        return ["refusal_date_before_po_date"]
    return []


def check_reminder(values: dict, today: date | None = None) -> tuple[dict, list[str]]:
    """Проверка перед напоминанием п. 13.4: срок банка по календарю истёк к сегодняшнему дню и к дате письма."""
    today = today or _today()
    due = bank_review_due(values)
    if due is None:
        raise DocBlocked("docs_submitted_date_missing", status=422)
    letter = _as_date(values.get("letter_date"))
    if today <= due or (letter is not None and letter <= due):
        raise DocBlocked("bank_deadline_not_expired", review_due_date=due.isoformat())
    warnings = []
    manual = _as_date(values.get("review_due_date"))
    if manual is not None and manual != due:
        warnings.append("review_due_date_recomputed")
    if values.get("scenario") != "contract_refusal":
        warnings += refusal_date_warnings(values)
    return {**values, "review_due_date": due.isoformat()}, warnings


def _v(values: dict, key: str) -> str:
    v = values.get(key)
    if v is None or v == "":
        return BLANK
    if isinstance(v, date):
        return v.strftime("%d.%m.%Y")
    if isinstance(v, str):
        try:
            return date.fromisoformat(v).strftime("%d.%m.%Y")
        except ValueError:
            return v
    return str(v)


def _doc() -> Document:
    d = Document()
    st = d.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(12)
    p = d.add_paragraph(MARK)
    p.runs[0].italic = True
    p.runs[0].font.size = Pt(9)
    return d


def reminder_13_4(values: dict) -> bytes:
    """Напоминание банку: срок рассмотрения документов по п. 13.4 ст. 7 115-ФЗ истёк."""
    t = load_timers()["timers"]["bank_review_7wd"]
    d = _doc()
    d.add_paragraph(f"В {_v(values, 'bank_full_name')}\nот {_v(values, 'company_name')}, ИНН {_v(values, 'company_inn')}\n"
                    f"адрес: {_v(values, 'company_address')}, телефон: {_v(values, 'company_phone')}")
    d.add_paragraph("О сроке рассмотрения представленных документов").runs[0].bold = True
    if values.get("scenario") == "contract_refusal":
        d.add_paragraph(f"{_v(values, 'refusal_date')} Банк отказал в заключении договора банковского счёта (вклада) "
                        "(пункт 5.2 статьи 7 Федерального закона № 115-ФЗ).")
    else:
        d.add_paragraph(
            f"{_v(values, 'refusal_date')} Банк отказал в совершении операции по платёжному поручению от {_v(values, 'po_date')} "
            f"№ {_v(values, 'po_number')} на сумму {_v(values, 'po_amount')} (пункт 11 статьи 7 Федерального закона № 115-ФЗ)."
        )
    d.add_paragraph(
        f"{_v(values, 'docs_submitted_date')} мы представили в Банк документы и сведения в целях устранения оснований "
        f"для принятия решения об отказе (канал: {_v(values, 'docs_channel')}, номер обращения: {_v(values, 'docs_request_number')})."
    )
    d.add_paragraph(
        f"Согласно пункту 13.4 статьи 7 Федерального закона № 115-ФЗ организация «{t['quote']}» об устранении оснований "
        f"либо о невозможности их устранения. По нашему расчёту по производственному календарю срок истёк {_v(values, 'review_due_date')}."
    )
    d.add_paragraph("Просим сообщить о принятом решении.")
    d.add_paragraph(f"Дата: {_v(values, 'letter_date')}\n\nПодпись: {BLANK}")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def cbr_complaint(values: dict) -> bytes:
    """Обращение в Банк России (интернет-приёмная): только хронология фактов."""
    d = _doc()
    d.add_paragraph("В Банк России (интернет-приёмная: https://www.cbr.ru/Reception/)\n"
                    f"от {_v(values, 'company_name')}, ИНН {_v(values, 'company_inn')}, телефон: {_v(values, 'company_phone')}, "
                    f"e-mail: {_v(values, 'company_email')}")
    d.add_paragraph("Обращение о действиях кредитной организации").runs[0].bold = True
    d.add_paragraph(f"Кредитная организация: {_v(values, 'bank_full_name')}.")
    d.add_paragraph("Хронология:")
    for line in values.get("timeline") or [f"{BLANK}: {BLANK}"]:
        d.add_paragraph(str(line), style="List Bullet")
    d.add_paragraph(
        "Что сообщил банк (дословно): «" + _v(values, "bank_message_quote") + "»."
    )
    d.add_paragraph("Суть обращения (заполняет заявитель): " + BLANK)
    d.add_paragraph("Приложения: копии сообщений банка, переписки и представленных документов.")
    d.add_paragraph(f"Дата: {_v(values, 'letter_date')}\n\nПодпись: {BLANK}")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


TEAM_TEMPLATES = {"reminder_13_4": reminder_13_4, "cbr_complaint": cbr_complaint}
