"""M1, слой 2: извлечение локальной LLM со строгой схемой (Ollama, on-prem).

- Модель по умолчанию — T-lite-it-2.1 Q4_K_M (Apache-2.0), запасная — GigaChat 3.1 Lightning (MIT).
- JSON Schema передаётся в `format`: валидность JSON гарантирует декодер, а не промпт.
- Цитаты модель даёт без смещений; смещения ставит валидатор, цитаты не из текста отбрасываются.
- temperature 0: извлечение, а не чат.
- Реальные тексты пользователей уходят только в локальную модель (PROMPT.md, разд. 1, п. 6).

Гибрид (combine) — явная политика по полям: где регулярные выражения точнее (нормы, даты,
сроки, операции), берём правила; где нужна классификация (сценарий, перечень, причина),
берём LLM; каналы и маршруты обжалования объединяем.
"""
from __future__ import annotations

import copy
import json
import os
import time
from functools import lru_cache

import httpx

from .validator import load_schema

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("NAVIGATOR_LLM", "hf.co/t-tech/T-lite-it-2.1-GGUF:Q4_K_M")

SYSTEM_PROMPT = """Ты — модуль разбора текста запроса или уведомления банка по 115-ФЗ и 161-ФЗ. Ты только извлекаешь факты из текста и заполняешь JSON по схеме. Ты не юрист и ничего не советуешь.

Правила:
1. Заполняй поле, только если это прямо написано в тексте. Не додумывай и не дополняй из своих знаний о законах.
2. У каждого заполненного поля в evidence — дословная цитата из текста (quote): скопируй фрагмент символ в символ, 2–25 слов. Не пересказывай.
3. Если чего-то в тексте нет — пустой список [], null или level "none". «Не указано банком» — нормальный ответ.
4. Норму закона (legal_basis) указывай только так, как она написана в тексте. Если назван только закон без статьи — article = null. Пункт договора или правил банка — kind "contract".
5. Сроки (deadlines) — только названные в тексте. client_response — срок для ответа клиента; bank_review — срок рассмотрения банком. Дату пиши в формате ГГГГ-ММ-ДД.
6. Угроза («если не ответите — ограничим») — это consequences, а не measures.
7. scenario — главный сценарий. Если мер несколько, выбери самую тяжёлую: zsk_measures_7_7 > suspension_rfm_court > contract_termination > operation_refusal > contract_refusal > remote_access_restriction > doc_request.

Сценарии (scenario.value):
- doc_request — запрос документов или пояснений, ограничения ещё нет
- operation_refusal — отказ в проведении операции (п. 11 ст. 7 115-ФЗ)
- remote_access_restriction — ограничение ДБО, интернет-банка, карт или отдельных операций по договору или в ходе проверки
- contract_termination — расторжение договора, отказ от обслуживания
- contract_refusal — отказ в открытии счёта / заключении договора
- zsk_high_cbr_only — высокий уровень риска по платформе ЗСК Банка России
- zsk_measures_7_7 — меры по п. 5 ст. 7.7 115-ФЗ (почти все операции заморожены)
- zsk_medium — средний уровень риска ЗСК
- suspension_rfm_court — приостановление по решению Росфинмониторинга или суда
- fz161_transfer_suspension — 161-ФЗ: перевод приостановлен до подтверждения
- fz161_restriction — 161-ФЗ: карты или переводы ограничены, база данных Банка России о переводах без согласия
- not_aml — блокировка не по 115-ФЗ: налоговая, приставы, таможня
- other — другое уведомление без меры
- unknown — не удаётся определить

Типы запрошенного (requested_items.type): explanation_operations — пояснения по операциям, экономический смысл; explanation_business — о деятельности, схеме бизнеса; source_of_funds — происхождение средств; income_certificate — 2-НДФЛ, справка о доходах; tax_return — декларации, 3-НДФЛ; tax_payment_proof — уплата налогов; accounting_statements — бухотчётность; bank_statements_other_banks — выписки других банков; bank_statements_own — выписки по счетам в этом банке; operation_supporting_docs — «документы, обосновывающие операцию» без уточнения; contracts — договоры, расписки; primary_docs — акты, УПД, счета-фактуры, накладные; payment_orders — платёжки; cash_usage_proof — расходование наличных; staff_docs — штатное, численность; premises_docs — аренда помещения; photos_premises — фото офиса или склада; marketplace_docs — отчёты и кабинет маркетплейса; procurement_logistics — закупка, доставка; questionnaire — анкета, опросный лист; beneficiary_info — бенефициары, выгодоприобретатели; property_sale_proof — продажа имущества; receipts — чеки; kudir — КУДиР; advertising_docs — реклама; identity_document — документ, удостоверяющий личность; other — иное."""


# Поля, которые в гибриде даёт LLM (классификация и смысл); остальное точнее берут правила.
LIST_CAPS = {"measures": 4, "requested_items": 10, "deadlines": 4, "response_channels": 4, "consequences": 3, "operations": 10}

SLIM_FIELDS = ["schema_version", "scenario", "measures", "reason", "requested_items", "next_steps", "consequences", "appeal"]


@lru_cache(maxsize=2)
def llm_schema(slim: bool = False) -> dict:
    """Схема для декодера: без start/end у цитат (их ставит валидатор) и без вопросов пользователю.
    slim=True — только поля классификации (меньше токенов, быстрее на ноутбуке)."""
    s = copy.deepcopy(load_schema())
    s["$defs"]["Evidence"]["properties"].pop("start", None)
    s["$defs"]["Evidence"]["properties"].pop("end", None)
    s["properties"].pop("questions_to_user", None)
    for k in ("$schema", "$id", "description"):
        s.pop(k, None)
    # Верхний предел длины списков в грамматике декодера. Без него модель на коротких текстах
    # (B12, B13, C12) бесконечно повторяла один элемент measures с той же цитатой, пока не упиралась
    # в MAX_TOKENS. Пределы не ниже максимума правил и gold на корпусе (меры 3, документы 5, цитаты 2, маршруты 1).
    s["$defs"]["EvidenceList"]["maxItems"] = 2
    props = s["properties"]
    for key, cap in LIST_CAPS.items():
        props[key]["maxItems"] = cap
    props["legal_basis"]["properties"]["items"]["maxItems"] = 6
    props["appeal"]["properties"]["routes"]["maxItems"] = 3
    if slim:
        s["properties"] = {k: v for k, v in s["properties"].items() if k in SLIM_FIELDS}
        s["required"] = [k for k in s["required"] if k in SLIM_FIELDS]
        s["properties"]["appeal"] = copy.deepcopy(s["properties"]["appeal"])
        s["properties"]["appeal"]["properties"].pop("explicit_denial", None)
        s["properties"]["appeal"]["required"] = ["level", "routes"]
    return s


# Нормальный ответ на корпусе занимает 114–1097 токенов (медиана 206, 34 вызова, eval/cache);
# без предела декодирование по схеме на B12, B13, C12 не завершалось за 1200 с (reports/diy-2026-10-27.md).
MAX_TOKENS = int(os.environ.get("NAVIGATOR_LLM_MAX_TOKENS", "1536"))


def extract(text: str, model: str = DEFAULT_MODEL, timeout: float = 300.0, slim: bool = False) -> tuple[dict, dict]:
    """Возвращает (raw_extraction, meta). raw — как выдала модель, до валидатора.
    В режиме slim недостающие поля дополняются пустыми значениями (их заполнят правила в combine)."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Текст банка:\n<<<\n{text}\n>>>\nЗаполни JSON по схеме."},
        ],
        "format": llm_schema(slim),
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": MAX_TOKENS},
    }
    t0 = time.time()
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("done_reason") == "length":  # упёрлись в предел: JSON оборван, честно уходим на правила
        raise RuntimeError(f"LLM output truncated at {MAX_TOKENS} tokens")
    content = data["message"]["content"]
    out = json.loads(content)
    from .rules import empty
    base = empty()
    for k, v in base.items():
        out.setdefault(k, v)
    out["appeal"].setdefault("explicit_denial", None)
    meta = {"model": model, "slim": slim, "seconds": round(time.time() - t0, 2), "eval_count": data.get("eval_count"),
            "prompt_eval_count": data.get("prompt_eval_count")}
    return out, meta


def _union_by_type(a: list[dict], b: list[dict]) -> list[dict]:
    seen = {x.get("type") for x in a}
    return a + [x for x in b if x.get("type") not in seen]


def combine(rules: dict, llm: dict, text: str | None = None) -> dict:
    """Гибрид правил и LLM. Если передан text, ответ LLM сначала проверяется валидатором:
    неподтверждённые поля LLM отбрасываются и уступают место правилам."""
    from .rules import SCENARIO_PRIORITY
    from .typecheck import check_types

    if text is not None:  # обе стороны проходят одинаковую проверку до слияния
        from .validator import validate
        llm, _ = validate(llm, text)
        check_types(llm, [], text)
        rules, _ = validate(rules, text)
        check_types(rules, [], text)
    out = copy.deepcopy(llm)
    # сценарий: из подтверждённых кандидатов (LLM и правила) берём более тяжёлую меру
    cands = [s for s in (out["scenario"], rules["scenario"]) if s.get("value") in SCENARIO_PRIORITY and s.get("evidence")]
    if cands:
        out["scenario"] = min(cands, key=lambda s: SCENARIO_PRIORITY.index(s["value"]))
    elif out["scenario"]["value"] == "unknown" and rules["scenario"]["value"] != "unknown":
        out["scenario"] = rules["scenario"]
    out["measures"] = _union_by_type(out.get("measures", []), rules["measures"])
    if rules["legal_basis"]["items"]:
        out["legal_basis"] = rules["legal_basis"]
    if out["reason"]["level"] == "none":
        out["reason"] = rules["reason"]
    if not out.get("requested_items"):
        out["requested_items"] = rules["requested_items"]
    if rules.get("period"):
        out["period"] = rules["period"]
    if rules["deadlines"]:
        out["deadlines"] = rules["deadlines"]
    out["response_channels"] = _union_by_type(out.get("response_channels", []), rules["response_channels"])
    if not out["next_steps"].get("stated"):
        out["next_steps"] = rules["next_steps"]
    if not out.get("consequences"):
        out["consequences"] = rules["consequences"]
    ap = out["appeal"]
    ap["routes"] = _union_by_type(ap.get("routes", []), rules["appeal"]["routes"])
    if not ap.get("explicit_denial"):
        ap["explicit_denial"] = rules["appeal"]["explicit_denial"]
    if rules["operations"]:
        out["operations"] = rules["operations"]
    return out
