"""M1, слой 1: детерминированное извлечение по правилам (без LLM).

Выход — объект по схеме bank_request с дословными цитатами. Правила намеренно общие
(формы записи норм, дат, сроков, каналов), а не подогнаны под конкретные тексты корпуса:
корпус — eval-набор. Что правила не умеют уверенно (тонкая классификация перечня,
причина), дополняет LLM-слой; всё проходит через валидатор.
"""
from __future__ import annotations

import re
from datetime import date

from .negation import negated

F = re.IGNORECASE | re.UNICODE

SCENARIO_PRIORITY = [
    "zsk_measures_7_7", "suspension_rfm_court", "contract_termination", "operation_refusal",
    "contract_refusal", "fz161_transfer_suspension", "fz161_restriction", "zsk_high_cbr_only",
    "zsk_medium", "not_aml", "remote_access_restriction", "doc_request",
]


def empty() -> dict:
    return {
        "schema_version": "0.1.0", "scenario": {"value": "unknown", "confidence": 0.0, "evidence": []},
        "measures": [], "legal_basis": {"level": "none", "items": []}, "reason": {"level": "none", "text": None, "evidence": []},
        "requested_items": [], "period": None, "deadlines": [], "response_channels": [],
        "next_steps": {"stated": False, "text": None, "evidence": []}, "consequences": [],
        "appeal": {"level": "none", "routes": [], "explicit_denial": None}, "operations": [],
        "request_meta": {"bank_name": None, "date": None, "number": None}, "questions_to_user": [],
    }


def ev(m: re.Match | str) -> list[dict]:
    q = m.group(0) if isinstance(m, re.Match) else m
    return [{"quote": q.strip(" ,.;:«»\"")}]


def _ru_date(s: str) -> str | None:
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", s)
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


# ---------- основание ----------
LAW_NUM = r"(?:№\s*)?(115|161)\s?-?\s?ФЗ"
NORM_FWD = re.compile(
    r"(?:(?P<sub>подп\.|пп\.)\s*(?P<subn>\d+(?:\.\d+)?)\s+)?(?P<pt>п\.|пункт\w*|ч\.|част\w*)\s*(?P<ptn>\d+(?:\.\d+)*)\s*"
    r"(?:ст\.|стать\w*)\s*(?P<art>\d+(?:\.\d+)?)\s*(?:Федерального\s+закона\s+)?(?:от\s+[\d.]+\s*(?:г\.\s*)?)?" + LAW_NUM,
    F,
)
NORM_ART = re.compile(
    r"(?:ст\.|стать\w*)\s*(?P<art>\d+(?:\.\d+)?)\s+(?:Федерального\s+закона\s+)?(?:от\s+[\d.]+\s*(?:г\.\s*)?)?" + LAW_NUM, F
)
LAW_ONLY = re.compile(r"(?:Федеральн\w+\s+закон\w*\s+(?:от\s+07\.08\.2001\s*(?:г\.\s*)?)?)?" + LAW_NUM + r"|Федеральн\w+\s+закон\w*\s+от\s+07\.08\.2001", F)
CONTRACT = re.compile(
    r"(?:на\s+основании\s+|согласно\s+|в\s+соответствии\s+с\s+)?(?:пункт\w*|пп?\.)\s*(?P<cl>\d+(?:\.\d+){1,3})\.?"
    r"(?P<doc>\s+(?:Условий|Правил|УКБО|ДКБО|договор\w*|правил\w*|УБО|приложени\w*)[^.,;]{0,40})?",
    F,
)
CONTRACT_DOC = re.compile(r"\b(УКБО|ДКБО|УБО)\b", F)


def legal_basis(text: str) -> dict:
    items, spans = [], []
    for m in NORM_FWD.finditer(text):
        pt = m.group("pt").lower()
        is_part = pt.startswith("ч")
        law = f"{m.group(m.lastindex)}-ФЗ" if m.lastindex else None
        law = f"{re.search(r'(115|161)', m.group(0)).group(1)}-ФЗ"
        art, ptn = m.group("art"), m.group("ptn").rstrip(".")
        canon = f"{law} ст. {art}" + (f" ч. {ptn}" if is_part else f" п. {ptn}")
        if m.group("subn"):
            canon += f" пп. {m.group('subn')}"
        items.append({"kind": "law", "law": law, "article": art, "part": ptn if is_part else None,
                      "point": None if is_part else ptn, "subpoint": m.group("subn"), "contract_clause": None,
                      "canonical": canon, "evidence": ev(m)})
        spans.append((m.start(), m.end()))
    for m in NORM_ART.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        law = f"{re.search(r'(115|161)', m.group(0)).group(1)}-ФЗ"
        items.append({"kind": "law", "law": law, "article": m.group("art"), "part": None, "point": None, "subpoint": None,
                      "contract_clause": None, "canonical": f"{law} ст. {m.group('art')}", "evidence": ev(m)})
        spans.append((m.start(), m.end()))
    if not items:
        seen = set()
        for m in LAW_ONLY.finditer(text):
            if any(s <= m.start() < e for s, e in spans):
                continue
            num = re.search(r"(115|161)", m.group(0))
            law = f"{num.group(1)}-ФЗ" if num else "115-ФЗ"
            if law in seen:
                continue
            seen.add(law)
            items.append({"kind": "law", "law": law, "article": None, "part": None, "point": None, "subpoint": None,
                          "contract_clause": None, "canonical": law, "evidence": ev(m)})
    for m in CONTRACT.finditer(text):
        tail = text[m.end(): m.end() + 25]
        if re.match(r"\s*(?:ст\.|стать)", tail, F):  # это пункт статьи закона, а не договора
            continue
        if any(s <= m.start() < e for s, e in spans):
            continue
        cl = m.group("cl")
        doc_m = CONTRACT_DOC.search(m.group(0))
        clause = f"{doc_m.group(1).upper()} п. {cl}" if doc_m else f"п. {cl}"
        items.append({"kind": "contract", "law": None, "article": None, "part": None, "point": None, "subpoint": None,
                      "contract_clause": f"п. {cl}", "canonical": f"договор: {clause}", "evidence": ev(m)})
    return {"level": "none", "items": items}  # уровень пересчитает валидатор


# ---------- сроки ----------
DATE_DEADLINE = re.compile(r"до\s+(\d{1,2}\.\d{1,2}\.\d{2,4})(\s+включительно)?", F)
REL_DEADLINE = re.compile(
    r"(?:в\s+течение|не\s+позднее|в\s+срок\s+(?:не\s+более|до)?|до)\s+(\d+)\s+(рабоч\w+|календарн\w+)?\s*(дн\w+|час\w*)"
    r"(?P<anchor>\s+(?:с\s+(?:даты|момента)\s+(?:получения|направления)[^.,;]{0,40}))?",
    F,
)
REVIEW_CTX = re.compile(r"рассм[ао]тр|обрабатыва|проверк|ответ\w*\s+банка|срок\s+ответа", F)
CLIENT_CTX = re.compile(r"ответьте|предостав|представ|пришлите|направьте|отправьте|обратиться|получения\s+настоящего", F)


def deadlines(text: str) -> list[dict]:
    out = []
    for m in DATE_DEADLINE.finditer(text):
        ctx = text[max(0, m.start() - 120): m.start()]
        # «Платёж от 12.10.2026» не срок; срок — «до DD.MM.YYYY»
        applies = "client_response"
        if REVIEW_CTX.search(ctx[-40:]) and not CLIENT_CTX.search(ctx[-60:]):
            applies = "bank_review"
        out.append({"applies_to": applies, "kind": "date", "date": _ru_date(m.group(1)),
                    "inclusive": True if m.group(2) else None, "amount": None, "unit": None, "anchor": None,
                    "raw": m.group(0).strip(), "evidence": ev(m)})
    for m in REL_DEADLINE.finditer(text):
        n = int(m.group(1))
        kind_word = (m.group(2) or "").lower()
        unit_word = m.group(3).lower()
        unit = "hours" if unit_word.startswith("час") else (
            "working_days" if kind_word.startswith("рабоч") else "calendar_days" if kind_word.startswith("календар") else "days_unspecified")
        ctx = text[max(0, m.start() - 80): m.end()]
        applies = "bank_review" if REVIEW_CTX.search(ctx) and not re.search(r"ответьте|предоставьте|пришлите|направить", ctx, F) else "client_response"
        anchor = None
        if m.group("anchor"):
            anchor = "receipt_of_notice" if "получени" in m.group("anchor").lower() else "notice_date"
        elif applies == "bank_review":
            anchor = None
        out.append({"applies_to": applies, "kind": "relative", "date": None, "inclusive": None, "amount": n, "unit": unit,
                    "anchor": anchor, "raw": m.group(0).strip(), "evidence": ev(m)})
    return out


# ---------- каналы ----------
CHANNELS = [
    ("chat", re.compile(r"(?:в\s+(?:этот\s+)?|прямо\s+сюда,\s+в\s+|через\s+)чат\w*|в\s+чате", F)),
    ("online_banking_upload", re.compile(r"(?:в|через)\s+(?:интернет-банк\w*|мобильн\w+\s+приложени\w+|личн\w+\s+кабинет\w*)"
                                          r"|в\s+разделе\s+«[^»]{2,40}»", F)),
    ("email", re.compile(r"(?:на\s+)?(?:электронн\w+\s+почт\w+|e-?mail|почт\w+\s+[\w.-]+@)", F)),
    ("branch_office", re.compile(r"(?:в|любом)\s+(?:офис\w*|отделени\w+)(?:\s+банка)?|в\s+офис\w*", F)),
    ("phone", re.compile(r"по\s+телефону|по\s+номеру|позвони\w+|8-800[\d-]*", F)),
]


def channels(text: str) -> list[dict]:
    out = []
    for typ, rx in CHANNELS:
        hits = list(rx.finditer(text))
        if hits:
            out.append({"type": typ, "raw": hits[0].group(0).strip(), "evidence": [ev(h)[0] for h in hits[:3]]})
    return out


# ---------- обжалование ----------
APPEALS = [
    ("mvk", re.compile(r"межведомственн\w+\s+комисси\w+(?:\s+при\s+Банке\s+России)?|\bМВК\b", F)),
    ("cbr_161_exclusion", re.compile(r"исключени\w+\s+(?:сведений\s+)?из\s+баз\w+\s+данн\w+[^.]{0,40}Банк\w*\s+России", F)),
    ("cbr_complaint", re.compile(r"(?:обра\w+|напиши\w*|жалоб\w+)\s+(?:в\s+)?(?:интернет-при[её]мн\w+\s+)?(?:ЦБ(?:\s+РФ)?|Банк\w*\s+России)|интернет-при[её]мн\w+\s+(?:ЦБ|Банк)", F)),
    ("court", re.compile(r"в\s+суд\b|в\s+судебном\s+порядке", F)),
    ("bank_rehabilitation", re.compile(r"(?:заявлени\w+\s+на\s+)?реабилитаци\w+", F)),
    ("bank_review", re.compile(r"документы\s+об\s+отсутствии\s+оснований|(?:повторно\s+)?(?:подать|направить)[^.]{0,30}на\s+пересмотр", F)),
]
DENIAL = re.compile(r"(?:решение\s+)?(?:пересмотру\s+не\s+подлежит|нет\s+возможности\s+пересмотреть\s+это\s+решение|"
                    r"процедуры,\s+предусмотренные\s+п\.\s*13\.4[^.]{0,60}не\s+применим\w*)", F)


def appeal(text: str) -> dict:
    routes = []
    for typ, rx in APPEALS:
        # первое упоминание маршрута, которое не стоит в отрицании («МВК не предусмотрена»)
        m = next((x for x in rx.finditer(text) if typ in ("bank_rehabilitation", "bank_review") or not negated(text, x.start(), x.end())), None)
        if m:
            if typ == "cbr_complaint" and any(r["type"] == "cbr_161_exclusion" for r in routes):
                continue
            routes.append({"type": typ, "evidence": ev(m)})
    d = DENIAL.search(text)
    return {"level": "none", "routes": routes, "explicit_denial": {"value": d.group(0).strip(), "evidence": ev(d)} if d else None}


# ---------- меры и сценарий ----------
MEASURES = [
    ("funds_freeze", "zsk_measures_7_7", re.compile(r"мер\w*,?\s+предусмотренн\w+\s+п\.\s*5\s+ст\.\s*7\.7|п\.\s*5\s+ст\.\s*7\.7", F)),
    ("risk_level", "zsk_high_cbr_only", re.compile(r"(?:групп\w+\s+)?высок\w+\s+(?:степен\w+\s+\(уровня\)\s+)?риск\w*", F)),
    ("risk_level", "zsk_medium", re.compile(r"средн\w+\s+(?:уров\w+\s+)?риск\w*", F)),
    ("operation_suspension", "not_aml", re.compile(r"(?:по\s+)?решени\w+\s+налогов\w+\s+орган\w*|судебн\w+\s+пристав\w*|\bФНС\b", F)),
    ("operation_suspension", "suspension_rfm_court", re.compile(r"по\s+решени\w+\s+(?:суда|Росфинмониторинга)|приостановлен\w*\s+на\s+(?:пять|5)\s+рабоч", F)),
    ("contract_termination", "contract_termination", re.compile(
        r"расторж\w+\s+договор\w*|расторга\w+\s+договор\w*|больше\s+не\s+может\s+сотрудничать|не\s+можем\s+сотрудничать|"
        r"прекрати\w*\s+(?:с\s+\w+\s+)?отношени\w+|отношения\s+со\s+мной\s+прекраща\w+", F)),
    ("operation_refusal", "operation_refusal", re.compile(
        r"отказа\w*\s+в\s+(?:совершении|проведении|выполнении|исполнении|зачислении)\s+операци\w*|"
        r"отказа\w*\s+в\s+(?:совершении|проведении)|операци\w+\s+(?:была\s+)?отклонен\w*|"
        # формулировка закона (п. 11 ст. 7 115-ФЗ): «отказ от выполнения (в выполнении) распоряжения клиента о совершении операции»
        r"отказ\w*\s+(?:от|в)\s+(?:выполнени|исполнени)\w*\s+распоряжени\w*(?:\s+клиента)?(?:\s+о\s+совершении\s+операци\w*)?", F)),
    ("contract_refusal", "contract_refusal", re.compile(r"отказа\w*\s+в\s+(?:заключении\s+договор\w*|открытии\s+сч[её]т\w*)|в\s+открытии\s+сч[её]т\w+\s+отказ\w*", F)),
    ("operation_suspension", "fz161_transfer_suspension", re.compile(r"(?:перевод|платёж|платеж|операция)\s+приостановлен\w*|приостановили\s+перевод", F)),
    ("card_block", "fz161_restriction", re.compile(r"баз\w+\s+данных\s+(?:Банка\s+России|МВД|ЦБ)|без\s+согласия\s+клиента|161-ФЗ", F)),
    ("card_block", "remote_access_restriction", re.compile(r"карт\w*\s+(?:заблокирован\w*|приостановлен\w*)|заблокирова\w+\s+карт\w*|блокировк\w+\s+карт\w*", F)),
    ("remote_access_restriction", "remote_access_restriction", re.compile(
        r"(?:ограничи\w+|заблокирова\w+|прекрати\w+|приостанов\w+)\s+(?:\w+\s+){0,3}(?:доступ\w*|дистанционн\w+|ДБО|интернет-банк\w*|онлайн|канал\w*)|"
        r"(?:доступ\w*|дистанционн\w+\s+(?:банковское\s+)?обслуживани\w*|канал\s+обслуживания|СберБанк\s+Онлайн|"
        r"интернет-банк\w*)[^.]{0,40}(?:ограничен\w*|заблокирован\w*|прекращ\w+)|ограничен\w*\s+(?:доступ|дистанционн)", F)),
    ("operations_limit", "remote_access_restriction", re.compile(
        r"не\s+сможете\s+совершать\s+\w+|ограничи\w*\s+(?:отдельные\s+виды\s+)?операци\w*|операции\s+(?:по\s+сч[её]ту\s+)?(?:ограничен\w*|приостановлен\w*)|"
        r"сч[её]т\w*\s+заблокирован\w*|(?:приостановлен\w*|ограничен\w*)\s+(?:и\s+ограничен\w*\s+)?(?:расходн\w+\s+)?(?:операци\w*|движени\w*)|"
        r"ограничили\s+расходные", F)),
    ("document_request", "doc_request", re.compile(
        r"(?:просим|прошу|просит)\s+(?:вас\s+)?(?:[^.]{0,40}?\s)?(?:предостав|представ|направ|прислать)\w*|пришлите\b[^.]{0,80}|предоставьте\b[^.]{0,80}|"
        # формулировки п. 14 ст. 7 115-ФЗ и типовых запросов: «банк запрашивает у вас документы», «необходимо представить»
        r"запрашива\w*\s+(?:у\s+(?:вас|клиента)\s+)?(?:\w+\s+){0,2}(?:документ|сведени|пояснени|информаци)\w*|"
        r"необходимо\s+(?:[^.]{0,40}?\s)?(?:предостав|представ)\w*|"
        r"представьте\b[^.]{0,80}|запрос\w*\s+(?:документ\w*|сведени\w*|пояснени\w*)|ответьте\s+на\s+запрос|нужн\w+\s+уточнени\w+|"
        r"(?:отправьте|направьте)\s+в\s+банк", F)),
]
# мера-угроза («если не ответите — ограничим») не считается применённой мерой
THREAT_CTX = re.compile(r"(?:если|в\s+случае)\s+[^.]{0,80}$", F)


def measures_and_scenario(text: str) -> tuple[list[dict], dict]:
    found: list[tuple[str, str, re.Match]] = []
    for mtype, scen, rx in MEASURES:
        for m in rx.finditer(text):
            if THREAT_CTX.search(text[max(0, m.start() - 100): m.start()]) and mtype != "document_request":
                continue
            found.append((mtype, scen, m))
            break
    measures, seen = [], set()
    for mtype, _scen, m in found:
        if mtype in seen:
            continue
        seen.add(mtype)
        measures.append({"type": mtype, "evidence": ev(m), "confidence": 0.7})
    scen_hits = {scen: m for _t, scen, m in found}
    is_161 = bool(re.search(r"161-?\s?ФЗ|без\s+согласия\s+клиента|баз\w+\s+данных", text, F))
    for scen in SCENARIO_PRIORITY:
        if scen in scen_hits:
            if scen == "remote_access_restriction" and is_161 and "fz161_restriction" in scen_hits:
                scen = "fz161_restriction"
            m = scen_hits[scen]
            return measures, {"value": scen, "confidence": 0.6, "evidence": ev(m)}
    return measures, {"value": "unknown", "confidence": 0.0, "evidence": []}


# ---------- перечень ----------
DOCS = [
    ("income_certificate", r"2-?НДФЛ|справк\w+\s+о\s+доход\w*"),
    ("tax_return", r"3-?НДФЛ|налогов\w+\s+декларац\w+|декларац\w+(?:\s+по)?\s+УСН\w*|декларац\w+"),
    ("tax_payment_proof", r"(?:документ\w*|платёжк\w+|платежк\w+|платежн\w+\s+поручени\w+)\s+(?:об\s+уплате|по)\s+налог\w*|уплат\w+\s+налог\w*|справк\w+\s+об\s+уплате"),
    ("property_sale_proof", r"(?:подтверждени\w+|договор\w*)\s+(?:продажи|купли-продажи)[^.;,)]{0,50}имуществ\w*"),
    ("source_of_funds", r"(?:источник\w*|происхождени\w+)\s+(?:происхождения\s+)?(?:денежных\s+)?средств\w*|легальност\w+\s+происхождени\w+"),
    ("bank_statements_other_banks", r"выписк\w+[^.;]{0,40}(?:других|иных|сторонних)\s+банк\w*|выписк\w+\s+из\s+других\s+банк\w*"),
    ("bank_statements_own", r"выписк\w+\s+(?:по|с)\s+(?:расч[её]тн\w+|валютн\w+|карточн\w+)?\s*сч[её]т\w*"),
    ("contracts", r"договор\w*\s+с\s+контрагент\w+|договор\w*(?:\s+(?:поставки|аренды|оказания))?(?=[,;.)\s])|расписк\w+"),
    ("primary_docs", r"акт\w*\s+(?:выполненных|оказанных|сверки)[^.;,]{0,20}|сч[её]т\w*-фактур\w*|\bУПД\b|\bТТН\b|товарн\w+\s+накладн\w+|накладн\w+"),
    ("explanation_operations", r"пояснени\w*\s+(?:по|о)\s+(?:кажд\w+\s+)?(?:проведённ\w+\s+|проведенн\w+\s+)?операци\w*|"
                               r"(?:письменн\w+\s+)?пояснени\w*\s+(?:о\s+целях\s+и\s+)?экономическ\w+\s+смысл\w*|разъяснени\w+\s+по\s+\w+\s+операци\w*"),
    ("explanation_business", r"пояснени\w*\s+о\s+(?:характере\s+)?(?:вашей\s+)?деятельност\w*|схем\w+\s+(?:работы|бизнеса)|вид\w*\s+деятельност\w*"),
    ("staff_docs", r"штатн\w+\s+расписани\w+|численност\w+\s+(?:работник|сотрудник)\w*"),
    ("premises_docs", r"договор\w*\s+аренды|аренд\w+\s+помещени\w+"),
    ("photos_premises", r"фото\w*\s+(?:рабочего\s+места|офиса|склада|торгового\s+зала|помещени\w+)"),
    ("marketplace_docs", r"маркетплейс\w*|личн\w+\s+кабинет\w*\s+продавц\w+"),
    ("procurement_logistics", r"закуп\w*[^.;]{0,30}(?:доставк|транспортировк)\w*|закупк\w+"),
    ("questionnaire", r"анкет\w+|опросн\w+\s+лист\w*"),
    ("beneficiary_info", r"бенефициар\w*|выгодоприобретател\w*"),
    ("kudir", r"книг\w+\s+уч[её]та\s+доходов|\bКУДиР\b"),
    ("cash_usage_proof", r"расходовани\w+\s+(?:снят\w+\s+)?наличн\w+|куда\s+ушли\s+наличные|целев\w+\s+расходовани\w+"),
    ("accounting_statements", r"бухгалтерск\w+\s+отч[её]тност\w*|баланс\w*"),
    ("receipts", r"чек\w*\s+по\s+перевод\w*"),
    ("operation_supporting_docs", r"документ\w*,?\s+(?:подтверждающ|обосновывающ)\w+\s+(?:ваши\s+)?операци\w*|обосновывающ\w+\s+операци\w+\s+документ\w*|подтверждени\w+\s+операци\w*"),
]
DOC_RX = [(t, re.compile(p, F)) for t, p in DOCS]


def requested_items(text: str) -> list[dict]:
    out, seen = [], set()
    for t, rx in DOC_RX:
        m = rx.search(text)
        if m and t not in seen:
            seen.add(t)
            out.append({"type": t, "raw": m.group(0).strip(), "period": None, "format": None, "evidence": ev(m), "confidence": 0.6})
    return out


PERIOD_RX = re.compile(r"(?:за\s+период\s+)?с\s+(\d{1,2}\.\d{1,2}\.\d{4})\s+по\s+(\d{1,2}\.\d{1,2}\.\d{4})", F)
PERIOD_REL = re.compile(r"за\s+(?:последние\s+)?(\d+)\s+(месяц\w*|мес\.|дн\w+|год\w*)|с\s+момента\s+открытия\s+сч[её]та", F)


def period(text: str) -> dict | None:
    m = PERIOD_RX.search(text)
    if m:
        return {"from": _ru_date(m.group(1)), "to": _ru_date(m.group(2)), "relative": None, "raw": m.group(0).strip(), "evidence": ev(m)}
    m = PERIOD_REL.search(text)
    if m:
        if m.group(0).lower().startswith("с момента"):
            rel = {"amount": None, "unit": "since_account_opening"}
        else:
            u = m.group(2).lower()
            rel = {"amount": int(m.group(1)), "unit": "months" if u.startswith("мес") else "days" if u.startswith("дн") else "years"}
        return {"from": None, "to": None, "relative": rel, "raw": m.group(0).strip(), "evidence": ev(m)}
    return None


# ---------- операции ----------
OP_RX = re.compile(r"операци\w+\s+(?:на\s+(?P<amt1>[\d\s ]+(?:,\d{2})?|…)\s*(?:RUB|руб\w*|₽)\s+)?от\s+(?P<d>\d{1,2}\.\d{1,2}\.\d{4})", F)
AMT_RX = re.compile(r"(?:внесли|поступил\w*|перевели|сняли)[^.]{0,40}?(?P<amt>\d[\d\s ]*(?:,\d{2})?)\s*(?:₽|руб\w*|RUB)", F)


def _amount(s: str | None) -> str | None:
    if not s or "…" in s:
        return None
    s = re.sub(r"[\s ]", "", s).replace(",", ".")
    try:
        return f"{float(s):.2f}"
    except ValueError:
        return None


def operations(text: str) -> list[dict]:
    out = []
    for m in OP_RX.finditer(text):
        out.append({"date": _ru_date(m.group("d")), "amount": _amount(m.group("amt1")), "currency": "RUB" if m.group("amt1") else None,
                    "direction": None, "payment_order_number": None, "raw": m.group(0).strip(), "evidence": ev(m)})
    for m in AMT_RX.finditer(text):
        out.append({"date": None, "amount": _amount(m.group("amt")), "currency": "RUB", "direction": None,
                    "payment_order_number": None, "raw": m.group(0).strip(), "evidence": ev(m)})
    return out


# ---------- последствия, причина, следующий шаг ----------
CONSEQ_RX = re.compile(
    r"(?:если|в\s+случае)\s+[^.]{0,80}?(?:не\s+(?:предостав|представ|получим|отправ|поступ)\w*)[^.]{0,30}?,?\s*"
    r"(?P<what>(?:мы\s+|банк\s+)?(?:можем\s+|может\s+|будем\s+вынуждены\s+|вынужден\w*\s+)?"
    r"(?:ограничи\w+|заблокир\w+|расторг\w+|прекрати\w+|принять\s+решение\s+о\s+расторжении|откаж\w+)[^.]{0,80}\w*"
    r"|о\s+возможности\s+дальнейшего\s+сотрудничества[^.]{0,60}\w*)",
    F,
)


def consequences(text: str) -> list[dict]:
    out = []
    for m in CONSEQ_RX.finditer(text):
        w = m.group("what").lower()
        t = ("card_block" if "карт" in w else "contract_termination" if ("расторг" in w or "сотрудничеств" in w)
             else "remote_access_restriction" if ("доступ" in w or "онлайн" in w or "интернет" in w)
             else "operations_limit" if ("ограни" in w or "операци" in w) else "other")
        out.append({"type": t, "raw": m.group("what").strip(), "evidence": ev(m.group("what"))})
    return out


REASON_GENERAL = re.compile(
    r"по\s+причине\s+(?:[^\s.,;]+\s+){0,7}[^\s.,;]+|в\s+связи\s+с\s+(?:наличием\s+)?(?:признак\w+|сомнительн\w+|подозрени\w+)(?:\s+[^\s.,;]+){0,6}|"
    r"признак\w*\s+необычн\w+\s+операци\w*|подозрительн\w+\s+операци\w*|сомнительн\w+\s+характер\w*\s+операци\w*|"
    r"появились\s+вопросы(?:\s+[^\s.;]+){0,10}|обнаружили\s+операци\w*,?\s+которые\s+вызывают\s+вопросы", F)
REASON_SPECIFIC = re.compile(r"(?:Вы\s+внесли|на\s+ваш\s+сч[её]т\s+поступил\w*)[^.]{0,80}?\d[\d\s ]*(?:,\d{2})?\s*(?:₽|руб\w*)[^.…]{0,30}", F)
# Точка внутри даты («до 25.02.2026») не конец предложения; закрывающая кавычка конец.
_SENT = r"(?:[^.»]|\.(?=\d))"


def _whole_words(text: str, m: re.Match) -> str:
    """Цитата не обрывается посреди слова: если совпадение кончилось внутри слова, отступаем
    до предыдущего пробела. Иначе карточка показывает «Предоставьте информацию об»."""
    q, end = m.group(0), m.end()
    if end < len(text) and text[end].isalnum() and q[-1:].isalnum():
        cut = q.rstrip().rfind(" ")
        if cut > 0:
            q = q[:cut]
    return q.rstrip(" ,;:…").strip()


def reason(text: str) -> dict:
    m = REASON_SPECIFIC.search(text)
    if m:
        q = _whole_words(text, m)
        return {"level": "specific", "text": q, "evidence": ev(q)}
    hits = list(REASON_GENERAL.finditer(text))
    if hits:
        return {"level": "general", "text": "; ".join(h.group(0).strip() for h in hits[:2]), "evidence": [ev(h)[0] for h in hits[:2]]}
    return {"level": "none", "text": None, "evidence": []}


NEXT_RX = re.compile(
    r"(?:Если\s+(?:Вы\s+|вы\s+)?не\s+согласны[^.]{0,20},\s*)?(?:оформите|подайте|пришлите|предоставьте|представьте|направьте|отправьте|"
    r"ответьте|загрузите|подтвердите|обратитесь|заполните)" + _SENT + r"{3,140}|(?:просим|прошу)\s+(?:вас\s+)?(?:предостав|представ|направ)\w*" + _SENT + r"{3,140}",
    F,
)


def next_steps(text: str) -> dict:
    m = NEXT_RX.search(text)
    if not m:
        return {"stated": False, "text": None, "evidence": []}
    q = _whole_words(text, m)
    return {"stated": True, "text": q, "evidence": ev(q)}


def extract(text: str) -> dict:
    """Извлечение правилами. Уверенности низкие намеренно: правила — первый проход."""
    out = empty()
    out["measures"], out["scenario"] = measures_and_scenario(text)
    out["legal_basis"] = legal_basis(text)
    out["reason"] = reason(text)
    out["requested_items"] = requested_items(text)
    out["period"] = period(text)
    out["deadlines"] = deadlines(text)
    out["response_channels"] = channels(text)
    out["next_steps"] = next_steps(text)
    out["consequences"] = consequences(text)
    out["appeal"] = appeal(text)
    out["operations"] = operations(text)
    # мера-угроза не должна запускать сценарий запроса: если единственная «мера» — угроза, это запрос
    return out
