"""Проверка «тип ↔ цитата»: LLM предлагает тип, правила проверяют, что цитата его поддерживает.

Валидатор цитат ловит выдуманный текст, но не выдуманный тип: цитата «пояснения к ним» настоящая,
а тип «источник происхождения средств» к ней не относится. Здесь для каждого типа документа и
сценария задан минимальный словарь основ; если в цитатах нет ни одной — тип не подтверждён:
документ получает тип other, сценарий — unknown (дальше его даёт слой правил).
"""
from __future__ import annotations

import re

from .negation import NEG

REQUEST_CTX = re.compile(
    r"предостав|представ|пришлите|прислать|направьте|направить|отправьте|просим|прошу|запрашива|запрос|"
    r"необходимо|нужн[оы]|подайте|оформите|загрузите|приложите|ответьте|документ\w*\s+(?:и|или)\s+пояснени",
    re.IGNORECASE,
)

DOC_STEMS: dict[str, tuple[str, ...]] = {
    "explanation_operations": ("пояснен", "разъяснен", "экономическ", "смысл", "цел"),
    "explanation_business": ("деятельност", "бизнес", "схем", "вид "),
    "source_of_funds": ("источник", "происхожден", "легальн"),
    "income_certificate": ("ндфл", "доход"),
    "tax_return": ("декларац", "ндфл"),
    "tax_payment_proof": ("налог",),
    "accounting_statements": ("бухгалтер", "отчетност", "отчётност", "баланс"),
    "bank_statements_other_banks": ("выписк",),
    "bank_statements_own": ("выписк",),
    "operation_supporting_docs": ("документ", "обоснов", "подтвержд"),
    "contracts": ("договор", "контракт", "расписк", "соглашен"),
    "primary_docs": ("акт", "упд", "счет", "счёт", "фактур", "накладн", "ттн"),
    "payment_orders": ("платежн", "платёжн", "поручен", "платёжк", "платежк"),
    "cash_usage_proof": ("наличн",),
    "staff_docs": ("штат", "численност", "работник", "сотрудник", "трудов"),
    "premises_docs": ("аренд", "помещен", "собственност"),
    "photos_premises": ("фото",),
    "marketplace_docs": ("маркетплейс", "озон", "ozon", "wildberries", "вайлдберриз", "кабинет", "fbo", "fbs"),
    "procurement_logistics": ("закуп", "доставк", "транспорт", "поставк", "сертификат", "логист"),
    "questionnaire": ("анкет", "опросн", "форм"),
    "beneficiary_info": ("бенефициар", "выгодоприобретател"),
    "property_sale_proof": ("продаж", "имуществ"),
    "receipts": ("чек",),
    "kudir": ("кудир", "книг"),
    "advertising_docs": ("реклам",),
    "identity_document": ("удостоверя", "паспорт", "личност"),
}

SCENARIO_STEMS: dict[str, tuple[str, ...]] = {
    "doc_request": ("запрос", "предостав", "представ", "пришлите", "ответьте", "направьте", "отправьте", "документ", "пояснен", "уточн", "сведен"),
    "operation_refusal": ("отказ", "отклон"),
    "remote_access_restriction": ("огранич", "заблокир", "блокир", "приостанов", "не сможете", "канал", "доступ", "дбо", "онлайн", "прекрат"),
    "contract_termination": ("расторг", "расторж", "прекращ", "сотруднич", "закры"),
    "contract_refusal": ("отказ", "открыт", "заключ"),
    "zsk_high_cbr_only": ("риск", "зск", "знай своего"),
    "zsk_measures_7_7": ("7.7", "7⁷", "риск"),
    "zsk_medium": ("риск", "зск"),
    "suspension_rfm_court": ("суд", "росфинмониторинг", "приостанов"),
    "fz161_transfer_suspension": ("приостанов", "подтверд", "перевод"),
    "fz161_restriction": ("баз", "161", "согласия", "огранич", "блок", "карт"),
    "not_aml": ("налог", "пристав", "фнс", "таможн"),
}


# Угроза «если не…, то…» должна называть последствие. Существительное «отказ» сюда не входит:
# «если не согласны с отказом» говорит об уже принятом решении, а не об угрозе.
CONSEQ_STEMS = ("огранич", "заблокир", "блокир", "расторг", "расторж", "прекрат", "прекращ", "откаж",
                "сотрудничеств", "приостанов", "закро", "закрыт")


def _quotes(obj: dict) -> str:
    return " ".join(e.get("quote", "") for e in obj.get("evidence") or []).lower().replace("ё", "е")


def _supported(stems: tuple[str, ...], text: str) -> bool:
    return any(s.replace("ё", "е") in text for s in stems)


def _sentence_at(text: str, start: int, end: int) -> str:
    a = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start)) + 1
    b_candidates = [i for i in (text.find(".", end), text.find("!", end), text.find("?", end)) if i != -1]
    b = min(b_candidates) if b_candidates else len(text)
    return text[a:b]


def _retype(quote: str, current: str) -> str:
    """Тип, который подтверждает цитата: текущий, если подтверждён; иначе единственный подходящий; иначе other."""
    q = quote.lower().replace("ё", "е")
    fits = [t for t, st in DOC_STEMS.items() if _supported(st, q)]
    if current in fits:
        return current
    specific = [t for t in fits if t not in ("operation_supporting_docs", "other")]
    return specific[0] if len(specific) == 1 else ("operation_supporting_docs" if fits == ["operation_supporting_docs"] else "other")


# ---------- «цитата подтверждает поле»: маршруты обжалования, сроки, нормы ----------
# Принцип «нет цитаты — нет поля» не ловит чужую настоящую цитату: маршрут mvk с цитатой «Банк отказал
# в проведении операции» проходит заземление. Здесь цитата должна сама называть то, что утверждает поле.
ROUTE_SUPPORT: dict[str, re.Pattern] = {
    "mvk": re.compile(r"межведомственн|\bмвк\b|комисси", re.IGNORECASE),
    "cbr_complaint": re.compile(r"банк\w*\s+росси|\bцб\b|центральн\w+\s+банк|интернет-при[её]мн", re.IGNORECASE),
    "cbr_161_exclusion": re.compile(r"банк\w*\s+росси|\bцб\b|центральн\w+\s+банк|интернет-при[её]мн", re.IGNORECASE),
    "court": re.compile(r"\bсуд|судебн", re.IGNORECASE),
}
MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
NUM_WORDS: dict[int, str] = {
    1: r"один|одного|одн(?:ого|ий|ие)|следующ\w+|сут(?:ки|ок)", 2: r"два|две|двух", 3: r"три|тр[её]х", 4: r"четыре|четыр[её]х",
    5: r"пять|пяти", 6: r"шесть|шести", 7: r"семь|семи", 8: r"восемь|восьми", 9: r"девять|девяти", 10: r"десять|десяти",
    14: r"четырнадцат\w*", 15: r"пятнадцат\w*", 20: r"двадцат\w*", 30: r"тридцат\w*",
}


def _has_number(q: str, n: str) -> bool:
    """Число n стоит в цитате отдельным токеном: «ст.7» да, «ст. 7.7» для 7 нет."""
    return re.search(r"(?<!\d)(?<!\d\.)" + re.escape(n) + r"(?!\.?\d)", q) is not None


def route_supported(route: dict) -> bool:
    rx = ROUTE_SUPPORT.get(route.get("type"))
    if rx is None:
        return True
    q = _quotes(route)
    # цитата «обжалование в МВК не предусмотрено» называет МВК, но маршрут отрицает
    return bool(rx.search(q)) and NEG.search(q) is None


def deadline_supported(d: dict) -> bool:
    q = _quotes(d)
    if d.get("date"):
        y, m, day = (int(x) for x in str(d["date"]).split("-"))
        numeric = any(int(a) == day and int(b) == m for a, b in re.findall(r"(?<!\d)(\d{1,2})\.(\d{1,2})(?!\d)", q))
        worded = re.search(rf"(?<!\d)0?{day}\s+{MONTHS_GEN[m - 1]}\w*", q) is not None
        if not (numeric or worded):
            return False
    amount = d.get("amount")
    if amount is not None:
        if not _has_number(q, str(amount)) and not (amount in NUM_WORDS and re.search(rf"\b(?:{NUM_WORDS[amount]})\b", q)):
            return False
    return True


def legal_ref_supported(it: dict) -> bool:
    q = _quotes(it)
    if it.get("kind") == "contract":
        cl = re.sub(r"^(?:п\.|пункт)\s*", "", (it.get("contract_clause") or "").strip())
        return not cl or _has_number(q, cl)
    for k in ("article", "point", "part", "subpoint"):
        v = it.get(k)
        if v and not _has_number(q, str(v).rstrip(".")):
            return False
    law = it.get("law")
    if law == "115-ФЗ":
        return bool(re.search(r"115|07\.08\.2001|легализаци", q))
    if law == "161-ФЗ":
        return bool(re.search(r"161|национальн\w+\s+платежн", q))
    return True


def check_support(ext: dict, notes: list[str]) -> dict:
    """Отбросить маршруты, сроки и нормы, чья цитата не называет МВК/ЦБ/суд, число дней или дату, номер статьи."""
    ap = ext.get("appeal") or {}
    if ap.get("routes"):
        kept = []
        for i, r in enumerate(ap["routes"]):
            if r.get("evidence") and not route_supported(r):
                notes.append(f"appeal.routes[{i}]={r.get('type')}: цитата не подтверждает маршрут, убран")
                continue
            kept.append(r)
        ap["routes"] = kept
    if ext.get("deadlines"):
        kept = []
        for i, d in enumerate(ext["deadlines"]):
            if d.get("evidence") and not deadline_supported(d):
                notes.append(f"deadlines[{i}]: в цитате нет этого числа дней или даты, убран")
                continue
            kept.append(d)
        ext["deadlines"] = kept
    lb = ext.get("legal_basis") or {}
    if lb.get("items"):
        kept = []
        for i, it in enumerate(lb["items"]):
            if it.get("evidence") and not legal_ref_supported(it):
                notes.append(f"legal_basis.items[{i}]={it.get('canonical')}: цитата не называет эту норму, убрано")
                continue
            kept.append(it)
        lb["items"] = kept
    return ext


def check_types(ext: dict, notes: list[str], text: str | None = None) -> dict:
    """Проверить типы и контекст. Меняет ext на месте и возвращает его.

    - пункт перечня должен стоять в предложении с просьбой (если передан text);
    - «документ, удостоверяющий личность» как инструкция для визита в отделение — не пункт пакета;
    - неподтверждённый цитатой тип переопределяется по цитате (или other);
    - угроза (consequences) без глагола последствия в цитате убирается.
    """
    kept = []
    for i, it in enumerate(ext.get("requested_items") or []):
        evs = it.get("evidence") or []
        q = _quotes(it)
        if it.get("type") == "identity_document" and not any(w in q for w in ("копи", "паспорт")):
            notes.append(f"requested_items[{i}]: инструкция для визита, не пункт пакета — убран")
            continue
        if text is not None and evs and all("start" in e for e in evs):
            ctx = " ".join(_sentence_at(text, e["start"], e["end"]) for e in evs)
            if not REQUEST_CTX.search(ctx):
                notes.append(f"requested_items[{i}]: нет просьбы в предложении — убран")
                continue
        t = it.get("type")
        if t in DOC_STEMS and not _supported(DOC_STEMS[t], q):
            nt = _retype(q, t)
            notes.append(f"requested_items[{i}].type: {t} -> {nt} (по цитате)")
            it["type"] = nt
        kept.append(it)
    if "requested_items" in ext:
        ext["requested_items"] = kept
    conseq = []
    for i, c in enumerate(ext.get("consequences") or []):
        if c.get("evidence") and not _supported(CONSEQ_STEMS, _quotes(c)):
            notes.append(f"consequences[{i}]: цитата не называет последствие — убрано")
            continue
        conseq.append(c)
    if "consequences" in ext:
        ext["consequences"] = conseq
    sc = ext.get("scenario") or {}
    v = sc.get("value")
    if v in SCENARIO_STEMS and sc.get("evidence") and not _supported(SCENARIO_STEMS[v], _quotes(sc)):
        notes.append(f"scenario: {v} -> unknown (цитата не подтверждает сценарий)")
        ext["scenario"] = {"value": "unknown", "confidence": 0.0, "evidence": []}
    check_support(ext, notes)
    return ext
