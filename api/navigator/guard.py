"""Страж уведомлений M9 (правила, v0).

Проверяет текст уведомления или запроса банка:
- обязательные элементы по письмам ЦБ ИН-01-59/98 и ИН-03-59/11 (коды E1–E6 — как в
  context/research/corpus-requests.md, разд. 1) + наличие срока;
- запрещённое (стоп-лист): сообщение о передаче сведений в Росфинмониторинг или «компетентные
  органы» (п. 6 ст. 7 115-ФЗ), внутренние критерии, коды признаков и скоринг ПВК, подсказки обхода
  контроля, отказ сообщать причины (противоречит E3; при нём E3 = «нет»);
- законный порог обязательного контроля (ст. 6 115-ФЗ) не красный;
- упоминание РФМ или суда как основания приостановления (сценарий suspension_rfm_court) не
  красное, а жёлтое с пометкой «нужна позиция комплаенса» (поле review).

Только правила, без LLM: результат объясним и воспроизводим. Каждая находка — с позицией в
тексте. Порт и доработка правил прототипа context/mvp/prototype/app.js (код команды).
Пороги качества (PROMPT.md, разд. 9): recall запрещённого ≥0.95, precision ≥0.8 — на
red-team наборе (eval/attacks/, к 26.10).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .negation import negated

F = re.IGNORECASE | re.UNICODE

MEASURE_RE = re.compile(
    r"отказ\w*\s+в\s+(?:совершении|проведении|выполнении|исполнении|зачислении|заключении|открытии)"
    r"|отказал\w*|приостанов\w+|заблокирова\w+|блокировк\w+|огранич\w+|заморож\w+"
    r"|расторг\w+|расторжени\w+|прекрати\w+\s+(?:дистанционн|обслуживан)|не\s+сможете\s+совершать"
    r"|запрос\w*|(?:просим|прошу|просит)\s+(?:вас\s+)?(?:предостав|представ|направ|прислать)"
    r"|(?:пришлите|предоставьте|представьте)\b",
    F,
)
NORM_RE = re.compile(
    r"(?:(?:пп?\.|подп\.|пункт\w*|ч\.|част\w*)\s*\d[\d.]*(?:\s*(?:,|и|–|-)\s*\d[\d.]*)*\s+)?"
    r"(?:ст\.|стать\w*)\s*\d+(?:\.\d+)?\s+(?:Федерального\s+закона\s+)?(?:от\s+[\d.]+\s+(?:г\.\s*)?)?(?:№\s*)?(?:115|161)-?\s?ФЗ",
    F,
)
NORM_RE_REV = re.compile(  # «на основании п.11 ст.7 № 115-ФЗ», «п.9 ст.9 №161-ФЗ»
    r"(?:пп?\.|пункт\w*|ч\.)\s*\d[\d.]*\s+ст\.\s*\d+(?:\.\d+)?\s*(?:№\s*)?(?:115|161)-?\s?ФЗ", F
)
NORM_RE_ART_FIRST = re.compile(  # «ст. 7 п. 5.2 115-ФЗ»
    r"(?:ст\.|стать\w*)\s*\d+(?:\.\d+)?\s*,?\s*(?:п\.|пункт\w*|ч\.|част\w*)\s*\d[\d.]*\s+(?:Федерального\s+закона\s+)?(?:№\s*)?(?:115|161)-?\s?ФЗ", F
)
LAW_RE = re.compile(r"(?:№\s*)?(?:115|161)-?\s?ФЗ|Федеральн\w+\s+закон\w*\s+(?:от\s+07\.08\.2001|«О\s+противодействии|«О\s+национальной)", F)
CONTRACT_RE = re.compile(
    r"(?:пункт\w*|пп?\.)\s*\d+(?:\.\d+){1,3}\.?(?:\s+(?:Условий|Правил|УКБО|ДКБО|договор\w*|правил\w*|УБО|приложени\w*))?"
    r"|(?:УКБО|ДКБО)\b",
    F,
)
REASON_RE = re.compile(
    r"причин\w*\s*[:—–-]\s*\w|основанием\s+послужил\w*|запутанн\w+|необычн\w+\s+характер\w*|по\s+причине|в\s+связи\s+с|причин\w*\s+(?:отказа|блокировк|ограничени)|подозрени\w+|сомнительн\w+|"
    r"необычн\w+\s+операц|подозрительн\w+|без\s+согласия\s+клиента|вы\s+внесли|поступил\w*\s+[\d\s]+|"
    r"появились\s+вопросы|не\s+удалось\s+подтвердить|высок\w+\s+степен\w+|остатки\s+денег",
    F,
)
REASON_DENIAL_RE = re.compile(
    r"(?:причин|основани)\w*[^.]{0,50}?(?:коммерческ\w+\s+тайн\w*|банковск\w+\s+тайн\w*|не\s+раскрыва\w*|не\s+сообща\w*|не\s+объясня\w*|"
    r"не\s+поясня\w*|не\s+подлеж\w+\s+(?:раскрыти|разглашени|сообщени)\w*|не\s+можем\s+(?:указать|сообщить|раскрыть|назвать)|"
    r"(?:указать|сообщить|раскрыть|назвать)\s+не\s+можем|конфиденциальн\w*)"
    r"|не\s+обязан\w*\s+(?:\w+\s+){0,2}(?:сообщать|объяснять|раскрывать|указывать|пояснять|называть)\s+(?:\w+\s+){0,2}(?:причин|основани)\w*",
    F,
)
ACTION_RE = re.compile(
    r"(?:пришлите|предоставьте|представьте|направьте|ответьте|оформите|заполните|подтвердите|обратитесь|обращаться|загрузите)"
    r"|вправе\s+представить|(?:просим|прошу)\s+(?:вас\s+)?(?:предостав|представ|направ)"
    r"|для\s+(?:снятия|разблокировки|устранения|возобновления|получения)|чтобы\s+снять",
    F,
)
DEADLINE_RE = re.compile(
    r"до\s+\d{1,2}\.\d{1,2}(?:\.\d{2,4})?(?:\s+включительно)?"
    r"|(?:в\s+течение|не\s+позднее|в\s+срок\s+(?:не\s+более|до)?|до)\s+\d+\s+(?:рабоч\w+|календарн\w+)?\s*(?:дн\w+|час\w*)"
    r"|не\s+позднее\s+(?:следующего|\d+)\s+\w*\s*дн\w+|срок\w*\s+(?:ответа|рассмотрения)[^.]{0,30}\d+\s+\w+\s+дн\w+",
    F,
)
APPEAL_EXT_RE = re.compile(r"межведомственн\w+\s+комисси\w+|\bМВК\b|интернет-при[её]мн\w+|Банк\w*\s+России|\bЦБ\b|в\s+суд\b|судебн\w+\s+порядк", F)
APPEAL_INT_RE = re.compile(r"реабилитац\w+|пересмотр\w*|если\s+(?:вы\s+)?не\s+согласн\w+|повторно\s+подать", F)
CHANNEL_REMOTE_RE = re.compile(
    r"интернет-банк\w*|мобильн\w+\s+приложени\w+|в\s+приложении|(?:в|этот|сюда,?\s+в)\s+чат\w*|\bчат\w*|онлайн|"
    r"электронн\w+\s+почт\w+|e-?mail|по\s+телефону|8-800|личн\w+\s+кабинет\w*|раздел\w*\s+«",
    F,
)
CHANNEL_OFFICE_RE = re.compile(r"в\s+офис\w*|отделени\w+|на\s+бумажн\w+\s+носител\w+", F)

@dataclass
class Hit:
    start: int
    end: int
    quote: str


@dataclass
class GuardResult:
    elements: dict[str, str]  # код → статус
    evidence: dict[str, list[Hit]] = field(default_factory=dict)
    forbidden: list[dict] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)  # не красное, но нужна позиция комплаенса банка
    light: str = "yellow"

    def to_dict(self) -> dict:
        return {
            "elements": self.elements,
            "evidence": {k: [h.__dict__ for h in v] for k, v in self.evidence.items()},
            "forbidden": self.forbidden,
            "review": self.review,
            "light": self.light,
        }


# Органы, о передаче сведений в которые банк не вправе сообщать клиенту (п. 6 ст. 7 115-ФЗ). Налоговый орган
# сюда не входит: о нём банк сообщает по НК РФ.
_ORGAN = (r"(?:компетентн|соответствующ|уполномоченн|государственн|контролирующ|надзорн|правоохранительн)\w*\s+"
          r"(?:\w+\s+){0,2}(?:орган|ведомств|служб|инстанци|регулятор)\w*")
RFM_RE = re.compile(
    r"росфинмон\w*\.?|\bРосфин\w*|rosfinmonitoring|\bФСФМ\b|\bРФМ\b|федеральн\w+\s+служб\w+\s+по\s+финансов\w+\s+мониторинг\w*|"
    r"уполномоченн\w+\s+(?:\w+\s+){0,2}орган\w*|"
    r"(?:сведени|информаци|данн|сообщени)\w*[^.]{0,80}?(?:направлен|передан|переда|представлен|сообщ)\w*\s+(?:в\s+)?" + _ORGAN + "|"
    r"(?:переда|направ|сообщ)\w+\s+(?:сведени\w+|информаци\w+|сообщени\w+|данн\w+)[^.]{0,40}(?:орган|ведомств|службу)|"
    r"(?:проинформир|уведомил|уведомлен|поставлен\w*\s+в\s+известность)\w*\s+(?:\w+\s+){0,3}(?:регулятор|орган|ведомств|служб)\w*",
    F,
)
# Приостановление по решению Росфинмониторинга или суда (п. 3 ст. 8 115-ФЗ; сценарий suspension_rfm_court): упоминание
# РФМ здесь описывает основание меры, а не передачу сведений. Не красный, а «нужна позиция комплаенса».
RFM_DECISION_RE = re.compile(
    r"(?:по|на\s+основании|во\s+исполнение)\s+(?:\w+\s+){0,2}решени\w+\s+(?:\w+\s+){0,3}"
    r"(?:суда|росфинмониторинг\w*|\bРФМ\b|уполномоченн\w+\s+орган\w*|федеральн\w+\s+служб\w+\s+по\s+финансов\w+\s+мониторинг\w*)",
    F,
)
SUSPEND_RE = re.compile(r"приостанов\w+|заморож\w+|блокир\w+", F)
TRANSMIT_RE = re.compile(r"(?:направ|переда|представ|сообщ|проинформир|уведом)\w*\s+(?:\w+\s+){0,3}(?:сведени|информаци|данн|сообщени)\w*|"
                         r"(?:сведени|информаци|данн)\w*[^.]{0,60}(?:направлен|передан|представлен)\w*", F)
# Порог из ст. 6 115-ФЗ (обязательный контроль) публичен: это закон, а не внутренний критерий банка.
LEGAL_THRESHOLD_RE = re.compile(r"(?:ст\.|стать\w*)\s*6(?![.\d]\d)|обязательн\w+\s+контрол\w*", F)
INTERNAL_CTX_RE = re.compile(r"скоринг|внутренн|балл|антифрод|модел|\bПВК\b|риск-?скор", F)
SCORE_CTX_RE = re.compile(r"риск|скоринг|присво|набрал|начисл", F)


_SENT_END = re.compile(r"[.!?…]+\s+(?=[«\"(]?[А-ЯЁA-Z])|\n")  # «ст. 6», «п. 11» не конец предложения


def _sentence(text: str, start: int, end: int) -> str:
    a = 0
    for m in _SENT_END.finditer(text, 0, start):
        a = m.end()
    m = _SENT_END.search(text, end)
    return text[a:m.start() if m else len(text)]


def _skip_rfm(text: str, h: Hit) -> bool:
    return "налогов" in h.quote.lower()


def _review_rfm(text: str, h: Hit) -> bool:
    s = _sentence(text, h.start, h.end)
    return bool(RFM_DECISION_RE.search(s) and SUSPEND_RE.search(s) and not TRANSMIT_RE.search(s))


def _skip_criteria(text: str, h: Hit) -> bool:
    q = h.quote.lower()
    s = _sentence(text, h.start, h.end)
    if q.startswith("порог"):  # законный порог ст. 6, если рядом нет внутренних моделей и баллов
        return bool(LEGAL_THRESHOLD_RE.search(s)) and not INTERNAL_CTX_RE.search(s)
    if "балльн" in q:  # «оцените по 10-балльной шкале» — не скоринг клиента
        return not SCORE_CTX_RE.search(s)
    return False


# Не запрещено само по себе, но требует решения комплаенса банка (жёлтый, поле review).
REVIEW = [
    {
        "id": "regulation_375p",
        "label": "Ссылка на Положение Банка России 375-П: проверьте, что не раскрыты коды и признаки; нужна позиция комплаенса",
        "basis": "375-П публично, но коды признаков и критерии ПВК банк клиенту не раскрывает",
        "re": re.compile(r"\b375-?\s?П\b", F),
    },
]

FORBIDDEN = [
    {
        "id": "rfm",
        "label": "Сообщение о передаче сведений в Росфинмониторинг или иной орган",
        "basis": "п. 6 ст. 7 115-ФЗ: организации, представляющие информацию в уполномоченный орган, «не вправе информировать об этом клиентов этих организаций или иных лиц»",
        "re": RFM_RE,
        "skip": _skip_rfm,
        "review": _review_rfm,
    },
    {
        "id": "internal_criteria",
        "label": "Раскрытие внутренних критериев, признаков, порогов, скоринга",
        "basis": "Критерии, коды признаков и пороги правил внутреннего контроля банк не раскрывает",
        "re": re.compile(r"скоринг\w*|риск-?скор\w*|(?:^|[^а-яё])балл\w*|порог\w*|"
                         r"внутренн\w+\s+(?:критери|модел|алгоритм|оценк|рейтинг)\w*|антифрод\w*\s+модел\w*|"
                         r"признак\w*\s+(?:№\s*)?\d{4}\b|код\w*\s+(?:признак|вида\s+операци)\w*\s*(?:№\s*)?\d{4}\b|"
                         r"критери\w*\s+(?:\w+\s+)?подозрит\w*|"
                         r"\d+(?:[.,]\d+)?\s*%\s+(?:от\s+)?(?:\w+\s+)?(?:оборот|поступлени|зачислени|выручк)\w*", F),
        "skip": _skip_criteria,
    },
    {
        "id": "bypass_advice",
        "label": "Подсказка, как обойти контроль",
        "basis": "Недопустимо для банка и для сервиса (PROMPT.md, разд. 1.3)",
        "re": re.compile(r"разб(?:е|и)[йв]\w*\s+(?:\w+\s+)?(?:платеж|платёж|сумм|операци|перевод)\w*|"
                         r"дроб\w*\s+(?:\w+\s+)?(?:платеж|платёж|сумм|операци|перевод)\w*|"
                         r"раздел(?:и|я)\w*\s+(?:платеж|платёж|сумм)\w*|сумм\w*\s+до\s+\d+[^.\n]{0,12}тыс\w*\s+чтобы|"
                         r"(?:измени|переформулир|перепиши|поменя)\w*\s+назначени\w*|не\s+попада\w*\s+под\s+проверк\w*|"
                         r"чтобы\s+(?:не\s+)?(?:банк\s+не\s+)?(?:заблокировал|заметил|проверял)|"
                         r"(?:проводи|переводи|снимай|снимите|вноси|отправля|совершай|делай)\w*\s+(?:\w+\s+){0,5}?"
                         r"(?:поменьше|помельче|частями|небольшими\s+суммами|мелкими\s+суммами)|"
                         r"(?:рекоменду|совету|предлага)\w*\s+(?:вам\s+)?(?:проводить|переводить|снимать|вносить|совершать|делать)\s+"
                         r"(?:\w+\s+){0,2}сумм\w*\s+(?:до|не\s+более|не\s+выше|меньше|менее)\s+\d|"
                         r"(?:рекоменду|совету|предлага)\w*\s+(?:вам\s+)?(?:открыть|использовать|завести)\s+(?:\w+\s+){0,2}"
                         r"(?:сч[её]т|карт)\w*\s+в\s+(?:другом|ином|стороннем)\s+банке", F),
    },
    {
        "id": "reason_withheld",
        "label": "Отказ сообщить причины («коммерческая тайна», «не обязан сообщать»)",
        "basis": "ИН-01-59/98: сообщать о причинах решения и не вводить клиента в заблуждение",
        "re": REASON_DENIAL_RE,
    },
]


def _hits(rx: re.Pattern, text: str, limit: int = 5) -> list[Hit]:
    out = []
    for m in rx.finditer(text):
        if m.end() > m.start():
            out.append(Hit(m.start(), m.end(), m.group(0)))
        if len(out) >= limit:
            break
    return out


def check(text: str) -> GuardResult:
    ev: dict[str, list[Hit]] = {}
    el: dict[str, str] = {}

    ev["E1"] = _hits(MEASURE_RE, text)
    el["E1"] = "yes" if ev["E1"] else "no"

    norm = _hits(NORM_RE, text) + _hits(NORM_RE_REV, text) + _hits(NORM_RE_ART_FIRST, text)
    law = _hits(LAW_RE, text)
    contract = [h for h in _hits(CONTRACT_RE, text, 10) if not NORM_RE_REV.search(text[max(0, h.start - 5): h.end + 20])]
    if norm:
        el["E2"], ev["E2"] = "norm", norm
    elif law:
        el["E2"], ev["E2"] = "law_only", law
    elif contract:
        el["E2"], ev["E2"] = "contract_only", contract
    else:
        el["E2"], ev["E2"] = "no", []

    denial = _hits(REASON_DENIAL_RE, text)
    reason = [h for h in _hits(REASON_RE, text, 10) if not any(d.start <= h.start < d.end + 40 for d in denial)]
    # Отказ назвать причину перекрывает общие слова о причине: элемент E3 не выполнен (ИН-01-59/98).
    if denial:
        reason = []
    el["E3"] = "present" if reason else "no"
    ev["E3"] = reason

    ev["E4"] = _hits(ACTION_RE, text)
    el["E4"] = "yes" if ev["E4"] else "no"

    # «обжалование в МВК не предусмотрено» не выполняет E5 (протокол жюри, раунд 2)
    ext = [h for h in _hits(APPEAL_EXT_RE, text, 10) if not negated(text, h.start, h.end)][:5]
    internal = _hits(APPEAL_INT_RE, text)
    el["E5"] = "external" if ext else ("internal_only" if internal else "no")
    ev["E5"] = ext or internal

    remote, office = _hits(CHANNEL_REMOTE_RE, text), _hits(CHANNEL_OFFICE_RE, text)
    el["E6"] = "yes" if remote else ("partial" if office else "no")
    ev["E6"] = remote or office

    ev["deadline"] = _hits(DEADLINE_RE, text)
    el["deadline"] = "yes" if ev["deadline"] else "no"

    forbidden, review = [], []
    for f in FORBIDDEN:
        hs = [h for h in _hits(f["re"], text, 10) if not (f.get("skip") and f["skip"](text, h))]
        rv = [h for h in hs if f.get("review") and f["review"](text, h)]
        hs = [h for h in hs if h not in rv]
        if hs:
            forbidden.append({"id": f["id"], "label": f["label"], "basis": f["basis"], "hits": [h.__dict__ for h in hs[:5]]})
        if rv:
            review.append({"id": f"{f['id']}_decision", "label": "Упоминание Росфинмониторинга или суда как основания приостановления: "
                           "нужна позиция комплаенса банка", "basis": f["basis"], "hits": [h.__dict__ for h in rv[:5]]})

    complete = el["E1"] == "yes" and el["E2"] == "norm" and el["E3"] == "present" and el["E4"] == "yes" \
        and el["E5"] == "external" and el["deadline"] == "yes"
    for r in REVIEW:
        hs = _hits(r["re"], text)
        if hs:
            review.append({"id": r["id"], "label": r["label"], "basis": r["basis"], "hits": [h.__dict__ for h in hs]})

    light = "red" if forbidden else ("green" if complete and not review else "yellow")
    return GuardResult(elements=el, evidence=ev, forbidden=forbidden, review=review, light=light)
