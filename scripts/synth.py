"""Генератор синтетических уведомлений и запросов банков с эталоном (make synth).

Каждый объект — СИНТЕТИКА: текст собран из шаблонных фраз по мотивам публичного корпуса
(стили: чат, официальное письмо, SMS, push), эталонный JSON по схеме bank_request ставится
программно, цитаты — точные подстроки сгенерированного текста.

Комбинаторика: стиль банка × сценарий × основание × срок × канал × причина × перечень ×
последствия × обжалование. Банки обезличены («Банк А»…): стиль играет роль банка-источника
для сплита (синтетика не попадает в test, если её «родитель» в train — сплит по style).

Нормы в шаблонах — только те, что сверены по первоисточникам в kb/ (см. NORM_BY_SCENARIO;
непроверенные варианты помечены и не используются).

Запуск: python scripts/synth.py --n 150 --seed 20261021
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from navigator.evidence import iter_evidence, locate  # noqa: E402
from navigator.validator import ValidationReport, enforce_support, schema_errors  # noqa: E402

OUT = ROOT / "data" / "synthetic" / "synth-v1.jsonl"
GENERATOR_VERSION = "synth-v1.0"

STYLES = {
    "chat": "Банк А (чат в приложении)",
    "letter": "Банк Б (письмо на e-mail / в ДБО)",
    "sms": "Банк В (SMS / push)",
    "formal": "Банк Г (официальное уведомление)",
}

# Сценарий → правовое основание, которое банк МОЖЕТ указать (сверено по тексту 115-ФЗ/161-ФЗ в kb/).
# law_text — как это обычно пишут в уведомлении.
NORM_BY_SCENARIO = {
    "doc_request": [("115-ФЗ", "7", None, "14", None, "на основании п. 14 ст. 7 Федерального закона от 07.08.2001 № 115-ФЗ")],
    "operation_refusal": [("115-ФЗ", "7", None, "11", None, "на основании п. 11 ст. 7 Федерального закона № 115-ФЗ")],
    "contract_refusal": [("115-ФЗ", "7", None, "5.2", None, "в соответствии с п. 5.2 ст. 7 Федерального закона № 115-ФЗ")],
    "contract_termination": [("115-ФЗ", "7", None, "5.2", None, "на основании п. 5.2 ст. 7 Федерального закона № 115-ФЗ")],
    "zsk_measures_7_7": [("115-ФЗ", "7.7", None, "5", None, "в соответствии с п. 5 ст. 7.7 Федерального закона № 115-ФЗ")],
}

DOC_PHRASES = {
    "explanation_operations": ["пояснения по операциям за указанный период", "письменные пояснения о целях и экономическом смысле операций"],
    "explanation_business": ["пояснения о характере вашей деятельности", "описание схемы работы бизнеса"],
    "source_of_funds": ["документы, подтверждающие источник происхождения денежных средств"],
    "income_certificate": ["справку о доходах", "справку 2-НДФЛ"],
    "tax_return": ["налоговую декларацию за последний отчётный период", "декларацию по УСН с отметкой налогового органа"],
    "tax_payment_proof": ["документы об уплате налогов"],
    "accounting_statements": ["бухгалтерскую отчётность за последний год"],
    "bank_statements_other_banks": ["выписки по счетам в других банках за 3 месяца", "выписки из других банков в формате xlsx"],
    "contracts": ["договоры с контрагентами по операциям", "договоры с основными покупателями и поставщиками"],
    "primary_docs": ["акты выполненных работ и счета-фактуры", "товарные накладные и УПД"],
    "staff_docs": ["штатное расписание", "сведения о численности работников"],
    "premises_docs": ["договор аренды помещения"],
    "photos_premises": ["фото рабочего места или склада"],
    "marketplace_docs": ["отчёт о реализации товаров на маркетплейсе", "скриншоты личного кабинета продавца на маркетплейсе"],
    "procurement_logistics": ["документы о закупке и доставке товара"],
    "questionnaire": ["заполненную анкету о виде деятельности", "опросный лист клиента"],
    "beneficiary_info": ["сведения о бенефициарных владельцах"],
    "kudir": ["книгу учёта доходов и расходов"],
    "cash_usage_proof": ["документы, подтверждающие расходование снятых наличных"],
}

CHANNELS = {  # назначение: docs — куда отправить документы; contact — как связаться с банком
    "docs": {
        "chat": ["Ответ и документы пришлите в этот чат.", "Документы можно отправить прямо сюда, в чат."],
        "online_banking_upload": ["Загрузите документы в разделе «Запросы банка» интернет-банка."],
        "email": ["Документы направьте на электронную почту, указанную в письме."],
        "branch_office": ["Документы можно предоставить в любом отделении банка."],
    },
    "contact": {
        "chat": ["Задать вопрос можно в чате поддержки.", "Мы на связи в этом чате."],
        "email": ["Вопросы можно направить на электронную почту, указанную в письме."],
        "branch_office": ["Обратитесь в отделение банка с документом, удостоверяющим личность."],
        "phone": ["По вопросам звоните по номеру на обороте карты."],
    },
}

STYLE_WRAP = {  # обёртки не размечаются
    "chat": ("Здравствуйте!", "Спасибо!"),
    "letter": ("Уважаемый клиент!", "С уважением, Банк Б."),
    "sms": ("", ""),
    "formal": ("Уважаемый клиент! Настоящим уведомляем Вас о следующем.", "Банк Г."),
}


def iso(d: date) -> str:
    return d.isoformat()


def ru(d: date) -> str:
    return d.strftime("%d.%m.%Y")


class Doc:
    """Сборка текста и эталона: каждая фраза добавляется в текст, цитаты — подстроки фраз."""

    def __init__(self, scenario: str):
        self.parts: list[str] = []
        self.g = {
            "schema_version": "0.1.0",
            "scenario": {"value": scenario, "confidence": 1.0, "evidence": []},
            "measures": [], "legal_basis": {"level": "none", "items": []},
            "reason": {"level": "none", "text": None, "evidence": []},
            "requested_items": [], "period": None, "deadlines": [], "response_channels": [],
            "next_steps": {"stated": False, "text": None, "evidence": []}, "consequences": [],
            "appeal": {"level": "none", "routes": [], "explicit_denial": None}, "operations": [],
            "request_meta": {"bank_name": None, "date": None, "number": None}, "questions_to_user": [],
        }

    def say(self, s: str) -> str:
        self.parts.append(s)
        return s

    @property
    def text(self) -> str:
        return " ".join(self.parts)


def ev(*quotes: str) -> list[dict]:
    return [{"quote": q} for q in quotes]


def add_norm(doc: Doc, rnd: random.Random, scenario: str, mode: str) -> str:
    """mode: norm | law_only | contract_only | none. Возвращает фразу-основание (может быть пустой)."""
    if mode == "norm" and scenario in NORM_BY_SCENARIO:
        law, art, part, point, sub, phrase = rnd.choice(NORM_BY_SCENARIO[scenario])
        canon = f"{law} ст. {art}" + (f" ч. {part}" if part else "") + (f" п. {point}" if point else "")
        doc.g["legal_basis"]["items"].append({
            "kind": "law", "law": law, "article": art, "part": part, "point": point, "subpoint": sub,
            "contract_clause": None, "canonical": canon, "evidence": ev(phrase)})
        doc.g["legal_basis"]["level"] = "norm"
        return phrase
    if mode == "law_only":
        if scenario.startswith("fz161"):
            phrase = rnd.choice(["в соответствии с Федеральным законом № 161-ФЗ «О национальной платёжной системе»", "на основании 161-ФЗ"])
            law = "161-ФЗ"
        else:
            phrase = rnd.choice(["в рамках Федерального закона № 115-ФЗ", "в соответствии с требованиями 115-ФЗ", "на основании Федерального закона от 07.08.2001 № 115-ФЗ"])
            law = "115-ФЗ"
        doc.g["legal_basis"]["items"].append({
            "kind": "law", "law": law, "article": None, "part": None, "point": None, "subpoint": None,
            "contract_clause": None, "canonical": law, "evidence": ev(phrase)})
        doc.g["legal_basis"]["level"] = "law_only"
        return phrase
    if mode == "contract_only":
        clause = rnd.choice(["п. 4.5", "п. 9.2.24", "п. 7.3.9", "п. 4.12"])
        phrase = rnd.choice([f"на основании {clause} Условий обслуживания", f"согласно {clause} Правил банковского обслуживания"])
        doc.g["legal_basis"]["items"].append({
            "kind": "contract", "law": None, "article": None, "part": None, "point": None, "subpoint": None,
            "contract_clause": clause, "canonical": f"договор: {clause}", "evidence": ev(phrase)})
        doc.g["legal_basis"]["level"] = "contract_only"
        return phrase
    return ""


def add_docs(doc: Doc, rnd: random.Random, k: int, period: tuple[date, date] | None) -> str:
    types = rnd.sample(sorted(DOC_PHRASES), k)
    lead = rnd.choice(["Пожалуйста, предоставьте:", "Просим предоставить следующие документы:", "Пришлите, пожалуйста:"])
    items = []
    for i, t in enumerate(types, 1):
        phrase = rnd.choice(DOC_PHRASES[t])
        items.append((t, phrase, f"{i}) {phrase}"))
    body = lead + " " + "; ".join(x[2] for x in items) + "."
    doc.say(body)
    for t, phrase, _ in items:
        doc.g["requested_items"].append({"type": t, "raw": phrase, "period": None, "format": None, "evidence": ev(phrase)})
    if period:
        p = f"за период с {ru(period[0])} по {ru(period[1])}"
        doc.say(f"Документы нужны {p}.")
        doc.g["period"] = {"from": iso(period[0]), "to": iso(period[1]), "relative": None, "raw": p, "evidence": ev(p)}
    doc.g["next_steps"] = {"stated": True, "text": "предоставить запрошенные документы", "evidence": ev(lead)}
    return lead


def add_deadline(doc: Doc, rnd: random.Random, base: date, mode: str) -> None:
    if mode == "date":
        d = base + timedelta(days=rnd.choice([5, 7, 10, 14]))
        incl = rnd.random() < 0.5
        raw = f"до {ru(d)}" + (" включительно" if incl else "")
        doc.say(f"Срок ответа — {raw}.")
        doc.g["deadlines"].append({"applies_to": "client_response", "kind": "date", "date": iso(d), "inclusive": True if incl else None,
                                   "amount": None, "unit": None, "anchor": None, "raw": raw, "evidence": ev(raw)})
    elif mode == "relative":
        n = rnd.choice([3, 5, 7, 10])
        raw = f"в течение {n} рабочих дней с даты получения настоящего запроса"
        doc.say(f"Ответ необходимо направить {raw}.")
        doc.g["deadlines"].append({"applies_to": "client_response", "kind": "relative", "date": None, "inclusive": None,
                                   "amount": n, "unit": "working_days", "anchor": "receipt_of_notice", "raw": raw, "evidence": ev(raw)})
    elif mode == "review":
        n = rnd.choice([3, 5, 7])
        raw = f"рассматриваем документы до {n} рабочих дней"
        doc.say(f"Обычно {raw}.")
        doc.g["deadlines"].append({"applies_to": "bank_review", "kind": "relative", "date": None, "inclusive": None,
                                   "amount": n, "unit": "working_days", "anchor": "submission", "raw": raw, "evidence": ev(raw)})


def add_channel(doc: Doc, rnd: random.Random, ch: str | None, purpose: str = "docs") -> None:
    if not ch:
        return
    phrase = rnd.choice(CHANNELS[purpose][ch])
    doc.say(phrase)
    doc.g["response_channels"].append({"type": ch, "raw": phrase.rstrip("."), "evidence": ev(phrase.rstrip("."))})


def add_reason(doc: Doc, rnd: random.Random, mode: str, op_date: date) -> None:
    if mode == "general":
        phrase = rnd.choice([
            "Мы обнаружили операции, которые вызывают вопросы",
            "Запрос связан с сомнительным характером операций",
            "Операции по счёту имеют признаки необычных операций",
        ])
        doc.say(phrase + ".")
        doc.g["reason"] = {"level": "general", "text": phrase, "evidence": ev(phrase)}
    elif mode == "specific":
        amt = rnd.choice([150_000, 480_000, 1_200_000, 3_000_000])
        amt_s = f"{amt:,}".replace(",", " ") + ",00 ₽"
        phrase = f"{ru(op_date)} на ваш счёт поступило {amt_s} от физических лиц"
        doc.say(f"У нас появились вопросы: {phrase}.")
        doc.g["reason"] = {"level": "specific", "text": phrase, "evidence": ev(phrase)}
        doc.g["operations"].append({"date": iso(op_date), "amount": f"{amt}.00", "currency": "RUB", "direction": "incoming",
                                    "payment_order_number": None, "raw": phrase, "evidence": ev(phrase)})


def add_consequence(doc: Doc, rnd: random.Random) -> None:
    t, phrase = rnd.choice([
        ("operations_limit", "мы ограничим отдельные виды операций по счёту"),
        ("remote_access_restriction", "мы будем вынуждены ограничить доступ к интернет-банку"),
        ("contract_termination", "банк может принять решение о расторжении договора банковского счёта"),
        ("card_block", "мы заблокируем карты"),
    ])
    doc.say(f"Если документы не поступят, {phrase}.")
    doc.g["consequences"].append({"type": t, "raw": phrase, "evidence": ev(phrase)})


def add_appeal(doc: Doc, rnd: random.Random, mode: str) -> None:
    if mode == "internal":
        phrase = "Если вы не согласны с решением, подайте в банк документы об отсутствии оснований для его принятия"
        doc.say(phrase + ".")
        doc.g["appeal"]["routes"].append({"type": "bank_review", "evidence": ev(phrase)})
        doc.g["appeal"]["level"] = "internal_only"
    elif mode == "mvk":
        phrase = "Если банк не изменит решение, вы вправе обратиться в межведомственную комиссию при Банке России"
        doc.say(phrase + ".")
        doc.g["appeal"]["routes"].append({"type": "mvk", "evidence": ev(phrase)})
        doc.g["appeal"]["level"] = "external"
    elif mode == "cbr161":
        phrase = "Вы можете подать заявление об исключении сведений из базы данных Банка России через банк или интернет-приёмную Банка России"
        doc.say(phrase + ".")
        doc.g["appeal"]["routes"].append({"type": "cbr_161_exclusion", "evidence": ev(phrase)})
        doc.g["appeal"]["level"] = "external"
    elif mode == "denial":
        phrase = "Решение пересмотру не подлежит"
        doc.say(phrase + ".")
        doc.g["appeal"]["explicit_denial"] = {"value": phrase, "evidence": ev(phrase)}


def measure(doc: Doc, mtype: str, quote: str) -> None:
    doc.g["measures"].append({"type": mtype, "evidence": ev(quote)})


def scene(doc: Doc, quote: str) -> None:
    doc.g["scenario"]["evidence"] = ev(quote)


def gen_one(rnd: random.Random, i: int) -> dict:
    style = rnd.choice(sorted(STYLES))
    scenario = rnd.choice([
        "doc_request", "doc_request", "doc_request", "remote_access_restriction", "remote_access_restriction",
        "operation_refusal", "operation_refusal", "contract_termination", "contract_refusal",
        "fz161_restriction", "fz161_transfer_suspension", "zsk_measures_7_7", "zsk_high_cbr_only",
        "zsk_medium", "suspension_rfm_court", "not_aml",
    ])
    base = date(2026, 1, 12) + timedelta(days=rnd.randrange(0, 280))
    op_date = base - timedelta(days=rnd.randrange(3, 40))
    doc = Doc(scenario)
    norm_mode = rnd.choice(["norm", "law_only", "contract_only", "none"])

    if scenario == "doc_request":
        opener = rnd.choice(["Нам нужно уточнить информацию по операциям по вашему счёту.", "Банк проводит проверку операций по счёту."])
        doc.say(opener)
        nphrase = add_norm(doc, rnd, scenario, norm_mode if norm_mode != "contract_only" else "law_only")
        if nphrase:
            doc.say(f"Запрос направлен {nphrase}.")
        add_reason(doc, rnd, rnd.choice(["none", "general", "specific"]), op_date)
        k = rnd.randint(1, 5)
        lead = add_docs(doc, rnd, k, (op_date - timedelta(days=60), op_date) if rnd.random() < 0.4 else None)
        measure(doc, "document_request", lead)
        scene(doc, lead)
        add_deadline(doc, rnd, base, rnd.choice(["date", "relative", "none", "review"]))
        add_channel(doc, rnd, rnd.choice([None, "chat", "online_banking_upload", "email", "branch_office"]))
        if rnd.random() < 0.5:
            add_consequence(doc, rnd)
    elif scenario == "remote_access_restriction":
        q = rnd.choice(["мы ограничили доступ к интернет-банку", "дистанционное банковское обслуживание ограничено", "вы не сможете совершать платежи через мобильное приложение"])
        doc.say(f"Сообщаем, что {q}.")
        measure(doc, "remote_access_restriction", q)
        scene(doc, q)
        nphrase = add_norm(doc, rnd, scenario, rnd.choice(["law_only", "contract_only", "none"]))
        if nphrase:
            doc.say(f"Ограничение введено {nphrase}.")
        add_reason(doc, rnd, rnd.choice(["none", "general"]), op_date)
        if rnd.random() < 0.6:
            measure(doc, "document_request", add_docs(doc, rnd, rnd.randint(1, 4), None))
        if rnd.random() < 0.5:
            paper = "Платёжные поручения на бумажном носителе можно передать в отделении банка"
            doc.say(paper + ".")
            doc.g["response_channels"].append({"type": "branch_office", "raw": paper, "evidence": ev(paper)})
        add_channel(doc, rnd, rnd.choice([None, "chat", "email"]), "docs" if doc.g["requested_items"] else "contact")
        add_appeal(doc, rnd, rnd.choice(["none", "none", "denial"]))
    elif scenario == "operation_refusal":
        q = f"банк отказал в проведении операции от {ru(op_date)}"
        doc.say(f"Уведомляем: {q}.")
        measure(doc, "operation_refusal", q)
        scene(doc, q)
        nphrase = add_norm(doc, rnd, scenario, rnd.choice(["norm", "norm", "law_only", "none"]))
        if nphrase:
            doc.say(f"Решение принято {nphrase}.")
        add_reason(doc, rnd, rnd.choice(["general", "none"]), op_date)
        doc.g["operations"].append({"date": iso(op_date), "amount": None, "currency": None, "direction": None,
                                    "payment_order_number": None, "raw": f"операция от {ru(op_date)}", "evidence": ev(f"операции от {ru(op_date)}")})
        add_appeal(doc, rnd, rnd.choice(["internal", "internal", "mvk", "none"]))
        if doc.g["appeal"]["routes"]:
            doc.g["next_steps"] = {"stated": True, "text": "подать в банк документы об отсутствии оснований",
                                   "evidence": ev(doc.g["appeal"]["routes"][0]["evidence"][0]["quote"])}
        add_deadline(doc, rnd, base, rnd.choice(["review", "none"]))
        add_channel(doc, rnd, rnd.choice([None, "branch_office", "online_banking_upload"]))
    elif scenario in ("contract_termination", "contract_refusal"):
        if scenario == "contract_termination":
            q = rnd.choice(["банк принял решение о расторжении договора банковского счёта", "банк расторгает договор банковского счёта"])
            measure(doc, "contract_termination", q)
        else:
            q = rnd.choice(["банк отказал в заключении договора банковского счёта", "в открытии счёта отказано"])
            measure(doc, "contract_refusal", q)
        doc.say(f"Сообщаем, что {q}.")
        scene(doc, q)
        nphrase = add_norm(doc, rnd, scenario, rnd.choice(["norm", "law_only", "none"]))
        if nphrase:
            doc.say(f"Решение принято {nphrase}.")
        if rnd.random() < 0.5:
            r = "Причины расторжения не раскрываются" if scenario == "contract_termination" else "Причины отказа не раскрываются"
            doc.say(r + ".")
        if scenario == "contract_termination" and rnd.random() < 0.6:
            rq = "Сообщите реквизиты счёта в другом банке для перевода остатка"
            doc.say(rq + ".")
            doc.g["next_steps"] = {"stated": True, "text": "сообщить реквизиты для перевода остатка", "evidence": ev(rq)}
        add_appeal(doc, rnd, rnd.choice(["none", "internal", "mvk"] if scenario == "contract_refusal" else ["none", "none", "denial"]))
        add_channel(doc, rnd, rnd.choice([None, "chat", "branch_office"]), "contact")
    elif scenario == "fz161_restriction":
        q = rnd.choice(["использование ваших карт приостановлено", "мы ограничили переводы с использованием электронных средств платежа"])
        doc.say(f"Сообщаем, что {q}.")
        measure(doc, "card_block" if "карт" in q else "remote_access_restriction", q)
        scene(doc, q)
        r = "Сведения о вас содержатся в базе данных Банка России о случаях и попытках осуществления переводов без согласия клиента"
        if rnd.random() < 0.7:
            doc.say(r + ".")
            doc.g["reason"] = {"level": "specific", "text": "сведения в базе данных Банка России", "evidence": ev(r)}
        nphrase = add_norm(doc, rnd, scenario, rnd.choice(["law_only", "none"]))
        if nphrase:
            doc.say(f"Меры приняты {nphrase}.")
        add_appeal(doc, rnd, rnd.choice(["cbr161", "cbr161", "none"]))
        add_channel(doc, rnd, rnd.choice([None, "phone", "branch_office"]), "contact")
    elif scenario == "fz161_transfer_suspension":
        q = rnd.choice(["перевод приостановлен", "операция приостановлена до подтверждения"])
        doc.say(f"Ваш {q.replace('операция приостановлена', 'платёж приостановлен')}." if style == "sms" else f"Внимание: {q}.")
        sq = q if style != "sms" else q.replace("операция приостановлена", "платёж приостановлен")
        measure(doc, "operation_suspension", sq)
        scene(doc, sq)
        conf = "Подтвердите перевод в приложении или по телефону не позднее следующего дня"
        doc.say(conf + ".")
        doc.g["next_steps"] = {"stated": True, "text": "подтвердить перевод", "evidence": ev(conf)}
        doc.g["deadlines"].append({"applies_to": "client_response", "kind": "relative", "date": None, "inclusive": None, "amount": 1,
                                   "unit": "calendar_days", "anchor": "notice_date", "raw": "не позднее следующего дня", "evidence": ev("не позднее следующего дня")})
        doc.g["response_channels"].append({"type": "phone", "raw": "по телефону", "evidence": ev("по телефону")})
        doc.g["response_channels"].append({"type": "other", "raw": "в приложении", "evidence": ev("в приложении")})
    elif scenario == "zsk_measures_7_7":
        q = "к вам применены меры, предусмотренные п. 5 ст. 7.7 Федерального закона № 115-ФЗ"
        doc.say(f"Уведомляем, что {q}.")
        measure(doc, "funds_freeze", q)
        scene(doc, q)
        doc.g["legal_basis"] = {"level": "norm", "items": [{
            "kind": "law", "law": "115-ФЗ", "article": "7.7", "part": None, "point": "5", "subpoint": None, "contract_clause": None,
            "canonical": "115-ФЗ ст. 7.7 п. 5", "evidence": ev("п. 5 ст. 7.7 Федерального закона № 115-ФЗ")}]}
        r = "Банк России и банк отнесли вас к группе высокой степени (уровня) риска"
        doc.say(r + ".")
        doc.g["reason"] = {"level": "specific", "text": "высокий уровень риска (ЗСК)", "evidence": ev(r)}
        add_appeal(doc, rnd, rnd.choice(["mvk", "none"]))
    elif scenario == "zsk_high_cbr_only":
        q = "по данным платформы «Знай своего клиента» Банк России отнёс вашу компанию к группе высокой степени (уровня) риска"
        doc.say(f"Сообщаем, что {q}.")
        measure(doc, "risk_level", q)
        scene(doc, q)
        if rnd.random() < 0.5:
            a = "Вы можете подать в Банк России заявление о пересмотре уровня риска"
            doc.say(a + ".")
            doc.g["appeal"]["routes"].append({"type": "other", "evidence": ev(a)})
            doc.g["appeal"]["level"] = "internal_only"
    elif scenario == "zsk_medium":
        q = "вашей компании присвоен средний уровень риска по данным платформы ЗСК"
        doc.say(f"Информируем: {q}.")
        measure(doc, "risk_level", q)
        scene(doc, q)
        if rnd.random() < 0.6:
            measure(doc, "document_request", add_docs(doc, rnd, rnd.randint(1, 3), None))
    elif scenario == "suspension_rfm_court":
        q = rnd.choice(["операция приостановлена на пять рабочих дней", "операции по счёту приостановлены по решению суда"])
        doc.say(f"Сообщаем: {q}.")
        measure(doc, "operation_suspension", q)
        scene(doc, q)
    elif scenario == "not_aml":
        q = "операции по счёту приостановлены по решению налогового органа"
        doc.say(f"Уведомляем: {q}.")
        measure(doc, "operation_suspension", q)
        scene(doc, q)
        nphrase = "решение налогового органа о приостановлении операций (ст. 76 НК РФ)"
        doc.say(f"Основание — {nphrase}.")
        doc.g["legal_basis"] = {"level": "norm", "items": [{
            "kind": "law", "law": "НК РФ", "article": "76", "part": None, "point": None, "subpoint": None,
            "contract_clause": None, "canonical": "НК РФ ст. 76", "evidence": ev(nphrase)}]}
        nx = "Для снятия ограничения обратитесь в вашу налоговую инспекцию"
        doc.say(nx + ".")
        doc.g["next_steps"] = {"stated": True, "text": "обратиться в налоговую инспекцию", "evidence": ev(nx)}

    pre, post = STYLE_WRAP[style]
    if pre:
        doc.parts.insert(0, pre)
    if post:
        doc.parts.append(post)
    text = doc.text
    gold = doc.g
    # проставить смещения
    for _p, evs in iter_evidence(gold):
        for e in evs:
            sp = locate(text, e["quote"])
            if sp is None:
                raise AssertionError(f"цитаты нет в синтетическом тексте: {e['quote']!r}\n{text}")
            e["start"], e["end"], e["quote"] = sp.start, sp.end, sp.quote
    errs = schema_errors(gold)
    rep = ValidationReport()
    probe = json.loads(json.dumps(gold))
    enforce_support(probe, rep)
    if errs or rep.dropped_fields or rep.recomputed:
        raise AssertionError(f"S{i:04d}: {errs} {rep.dropped_fields} {rep.recomputed}\n{text}")
    return {
        "id": f"S{i:04d}",
        "synthetic": True,
        "label": "синтетика",
        "generator": GENERATOR_VERSION,
        "style": style,
        "style_desc": STYLES[style],
        "split_group": f"synth_{style}",
        "scenario": scenario,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "gold": gold,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261021)
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    recs = [gen_one(rnd, i + 1) for i in range(args.n)]
    with OUT.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter(r["scenario"] for r in recs)
    print(f"синтетика: {len(recs)} → {OUT.relative_to(ROOT)}")
    print(", ".join(f"{k}: {v}" for k, v in sorted(c.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
