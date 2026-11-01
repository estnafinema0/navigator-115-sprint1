"""HTTP API Навигатора-115 (FastAPI). P0-каркас: схема, валидация разбора.

Эндпоинты разбора (M1), сроков (M4), маршрутов (M5) и стража (M9) добавляются по плану
PROMPT.md, разд. 15.1. Веб-демо (context/mvp/prototype/) будет ходить сюда.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import __version__
from .validator import load_schema, validate

app = FastAPI(
    title="Навигатор-115 API",
    version=__version__,
    description="Разбор запросов и уведомлений банков по 115-ФЗ/161-ФЗ. Каждое поле с цитатой из текста банка. "
    "Проверка по тексту запроса, не гарантия и не юридическая консультация.",
)


class ValidateIn(BaseModel):
    text: str = Field(..., description="Исходный текст запроса или уведомления банка")
    extraction: dict = Field(..., description="Результат разбора по схеме bank_request")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/schema/bank-request")
def bank_request_schema() -> dict:
    return load_schema()


@app.post("/api/v1/validate")
def validate_extraction(body: ValidateIn) -> dict:
    """«Нет цитаты — нет поля»: заземляет цитаты, обнуляет неподтверждённое, пересчитывает уровни."""
    out, report = validate(body.extraction, body.text)
    return {"extraction": out, "report": report.to_dict()}


# ---------- M1: разбор ----------
class ParseIn(BaseModel):
    text: str = Field(..., max_length=20000, description="Текст запроса или уведомления банка (обезличенный)")
    mode: str = Field("hybrid", pattern="^(rules|hybrid|llm)$", description="rules: без LLM; hybrid: правила + локальная LLM")


# p95 времени ответа модели на корпусе 73 с (M1); дольше ждать в демо нельзя, уходим на правила.
LLM_TIMEOUT = float(os.environ.get("NAVIGATOR_LLM_TIMEOUT", "90"))


@app.post("/api/v1/parse")
def parse(body: ParseIn) -> dict:
    """Разбор текста: маскирование ПДн → правила → локальная LLM → валидатор. Каждое поле с цитатой из текста.

    ПДн (ИНН, счёт, телефон, СНИЛС, e-mail) маскируются до разбора; маска сохраняет длину, поэтому
    start/end цитат верны и для исходного текста. Цитаты в ответе содержат «*» на месте ПДн."""
    from . import llm, rules
    from .pii import mask

    pm = mask(body.text)
    text = pm.text
    r = rules.extract(text)
    meta: dict = {"mode": body.mode, **pm.meta()}
    if body.mode == "rules":
        raw = r
    else:
        try:
            out_llm, meta_llm = llm.extract(text, slim=(body.mode == "hybrid"), timeout=LLM_TIMEOUT)
            meta.update(meta_llm)
            raw = llm.combine(r, out_llm, text) if body.mode == "hybrid" else out_llm
        except Exception as e:  # LLM недоступна — честно работаем на правилах
            meta.update({"llm_error": repr(e)[:200], "fallback": "rules"})
            raw = r
    out, report = validate(raw, text)
    from .intent import check_request

    inj = check_request(text)
    meta["injection_detected"] = "injection" in inj.categories  # инструкции из текста не исполняются, только фиксируются
    return {"extraction": out, "report": report.to_dict(), "meta": meta,
            "disclaimer": "Проверка по тексту запроса, не гарантия и не юридическая консультация."}


# ---------- M4: сроки ----------
class DeadlinesIn(BaseModel):
    scenario: str
    events: dict[str, str] = Field(default_factory=dict, description="timer_id → дата события (ГГГГ-ММ-ДД)")


@app.post("/api/v1/deadlines")
def deadlines_for(body: DeadlinesIn) -> dict:
    from datetime import date as _date

    from . import deadlines as dl
    from .workcalendar import CalendarGap

    out = []
    spec = dl.load_timers()["timers"]
    for tid in dl.timers_for(body.scenario):
        start = body.events.get(tid)
        t = spec[tid]
        base = {"timer_id": tid, "title": t["title"], "norm": t["norm"], "who": t["who"], "verified": bool(t.get("verified")),
                "amount": t["amount"], "unit": t["unit"], "quote": t.get("quote"), "anchor": t.get("anchor")}
        if not start:
            out.append({**base, "status": "ждёт даты события"})
            continue
        try:
            d = dl.compute(tid, _date.fromisoformat(start))
            out.append({**base, "start": d.start.isoformat(), "due": d.due.isoformat()})
        except CalendarGap as e:
            out.append({**base, "status": f"не посчитано: {e}"})
    return {"scenario": body.scenario, "statutory_client_deadline": dl.has_statutory_client_deadline(body.scenario), "timers": out}


# ---------- M5: маршруты и документы ----------
@app.get("/api/v1/routes/{scenario}")
def routes(scenario: str, first_level_done: bool = False) -> dict:
    from dataclasses import asdict

    from .router import routes_for

    res = routes_for(scenario, first_level_done)
    return {"scenario": res.scenario, "mvk_note": res.mvk_note, "options": [asdict(o) for o in res.options]}


class DocIn(BaseModel):
    values: dict = Field(default_factory=dict, description="Поля кейса: реквизиты, даты, номера. Доводы не принимаются")
    scenario: str | None = Field(None, description="Сценарий из разбора: проверка, подходит ли шаблон к мере")
    first_level_done: bool | None = Field(None, description="Клиент прошёл первый уровень (п. 13.4); null: не указано")


def _doc_response(content: bytes, filename: str, left_blank: list[str], warnings: list[str], extra: dict | None = None):
    from fastapi.responses import Response

    headers = {"Content-Disposition": f'attachment; filename="{filename}"',
               "X-Fields-Left-Blank": ",".join(left_blank), "X-Navigator-Warnings": ",".join(dict.fromkeys(warnings))}
    headers.update(extra or {})
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers=headers)


def _blocked(e):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=e.status, content={"detail": e.detail()})


@app.get("/api/v1/documents/codes")
def document_codes() -> dict:
    """Коды предупреждений (заголовок X-Navigator-Warnings) и отказов (detail.code при 409/422) с текстом для пользователя."""
    from .docgen_team import DOC_CODES

    return DOC_CODES


@app.post("/api/v1/documents/{template_no}")
def document(template_no: int, body: DocIn):
    from fastapi import HTTPException

    from .docgen import check_template, generate, load_spec
    from .docgen_team import DocBlocked

    if template_no not in load_spec()["templates"]:
        raise HTTPException(404, "шаблон не поддерживается")
    try:
        warnings = check_template(template_no, body.values, body.scenario, body.first_level_done)
    except DocBlocked as e:
        return _blocked(e)
    res = generate(template_no, body.values)
    return _doc_response(res.content, f"cbr-template-{template_no:02d}.docx", res.left_blank, warnings)


@app.post("/api/v1/documents/team/{name}")
def team_document(name: str, body: DocIn):
    from fastapi import HTTPException

    from .docgen_team import TEAM_TEMPLATES, DocBlocked, check_reminder

    if name not in TEAM_TEMPLATES:
        raise HTTPException(404, "шаблон не найден")
    values, warnings, extra = dict(body.values), [], {}
    if body.scenario:
        values["scenario"] = body.scenario
    if name == "reminder_13_4":
        try:
            values, warnings = check_reminder(values)
        except DocBlocked as e:
            return _blocked(e)
        extra["X-Review-Due-Date"] = values["review_due_date"]
    return _doc_response(TEAM_TEMPLATES[name](values), f"navigator-{name}.docx", [], warnings, extra)


# ---------- M3: чек-лист пакета ----------
class PackageIn(BaseModel):
    extraction: dict
    files: list[str] = Field(default_factory=list, description="Имена загруженных файлов (содержимое не передаётся)")
    manual: dict[int, list[str]] = Field(default_factory=dict)


@app.post("/api/v1/package")
def package(body: PackageIn) -> dict:
    from .package import checklist

    return checklist(body.extraction, body.files, body.manual)


# ---------- граница 115-ФЗ на входе ----------
class AskIn(BaseModel):
    text: str = Field(..., max_length=4000, description="Вопрос или просьба пользователя")


@app.post("/api/v1/intent")
def intent(body: AskIn) -> dict:
    from dataclasses import asdict

    from .intent import check_request

    return asdict(check_request(body.text))


# ---------- M9: страж ----------
class GuardIn(BaseModel):
    text: str = Field(..., max_length=20000)


@app.post("/api/v1/guard")
def guard(body: GuardIn) -> dict:
    """Страж уведомлений. ПДн маскируются до проверки (длина сохраняется, смещения находок верны)."""
    from .guard import check
    from .pii import mask

    pm = mask(body.text)
    return {**check(pm.text).to_dict(), **pm.meta()}


# ---------- веб-интерфейс: статический экспорт Next.js (web/out), иначе старое демо (web-legacy) ----------
def _mount_web() -> None:
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    root = Path(__file__).resolve().parents[2]
    # Собранный Next.js (design/DESIGN.md) — web/out; без сборки — старое демо как функциональный фолбэк.
    for web in (root / "web" / "out", root / "web-legacy"):
        if web.is_dir():
            app.mount("/", StaticFiles(directory=str(web), html=True), name="web")
            break


_mount_web()
