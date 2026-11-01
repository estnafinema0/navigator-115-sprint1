"""Валидатор результата разбора (M1): «нет цитаты — нет поля».

Шаги:
1. Проверка по JSON Schema (контракт api/schema/bank_request.schema.json).
2. Заземление: для каждой цитаты ищем её место в исходном тексте и проставляем
   start/end; цитаты, которых в тексте нет, отбрасываем.
3. Цитата должна подтверждать поле (typecheck.check_support): маршрут mvk/cbr_complaint/court
   называет МВК/ЦБ/суд, срок — своё число дней или дату, норма — номер статьи и пункта.
   Поля, у которых не осталось ни одной цитаты, обнуляются (элемент списка удаляется,
   скалярное поле становится «не указано банком»). Всё отброшенное попадает в отчёт —
   это и есть метрика «галлюцинаций».
4. Производные уровни (legal_basis.level, appeal.level) пересчитываются по фактам,
   а не берутся у модели.

Валидатор не меняет смысл полей и ничего не дописывает.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import jsonschema

from .evidence import iter_evidence, locate, locate_fuzzy, nfc
from .typecheck import check_support

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "bank_request.schema.json"

LIST_FIELDS = ("measures", "requested_items", "deadlines", "response_channels", "consequences", "operations")
EXTERNAL_ROUTES = {"mvk", "cbr_complaint", "cbr_161_exclusion", "court"}
INTERNAL_ROUTES = {"bank_rehabilitation", "bank_review"}


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_errors(obj: dict) -> list[str]:
    validator = jsonschema.Draft202012Validator(load_schema(), format_checker=jsonschema.FormatChecker())
    return [f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}" for e in validator.iter_errors(obj)]


@dataclass
class ValidationReport:
    schema_errors: list[str] = field(default_factory=list)
    dropped_quotes: list[str] = field(default_factory=list)  # цитаты, которых нет в тексте
    snapped_quotes: list[str] = field(default_factory=list)  # почти дословные цитаты, привязанные к тексту
    dropped_fields: list[str] = field(default_factory=list)  # поля, обнулённые из-за отсутствия опоры
    filled_fields: int = 0  # заполненные поля после валидации
    recomputed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.schema_errors

    def to_dict(self) -> dict:
        return {
            "schema_errors": self.schema_errors,
            "dropped_quotes": self.dropped_quotes,
            "snapped_quotes": self.snapped_quotes,
            "dropped_fields": self.dropped_fields,
            "filled_fields": self.filled_fields,
            "recomputed": self.recomputed,
        }


def ground_evidence(obj: dict, text: str, report: ValidationReport, fuzzy: bool = True) -> None:
    """Проставить start/end всем цитатам; удалить цитаты, которых нет в тексте."""
    text = nfc(text)
    for path, evs in list(iter_evidence(obj)):
        kept = []
        for ev in evs:
            span = locate(text, ev.get("quote", ""), ev.get("start"))
            if span is None and fuzzy:
                span = locate_fuzzy(text, ev.get("quote", ""))
                if span is not None:
                    report.snapped_quotes.append(f"{path}: {ev.get('quote', '')[:60]!r} -> {span.quote[:60]!r}")
            if span is None:
                report.dropped_quotes.append(f"{path}: {ev.get('quote', '')[:80]!r}")
                continue
            kept.append({"quote": span.quote, "start": span.start, "end": span.end})
        evs[:] = kept


def _has_ev(o: dict | None) -> bool:
    return bool(o) and bool(o.get("evidence"))


def enforce_support(obj: dict, report: ValidationReport) -> None:
    """Обнулить поля без цитат и поля, чью цитату тип не подтверждает; пересчитать производные уровни."""
    check_support(obj, report.dropped_fields)  # чужая настоящая цитата: маршрут без МВК/ЦБ/суда, срок без числа
    # scenario
    sc = obj.get("scenario") or {}
    if not _has_ev(sc) and sc.get("value") not in (None, "unknown"):
        report.dropped_fields.append(f"scenario={sc.get('value')}")
        obj["scenario"] = {"value": "unknown", "confidence": 0.0, "evidence": []}

    # списки
    for name in LIST_FIELDS:
        items = obj.get(name) or []
        kept = []
        for i, it in enumerate(items):
            if _has_ev(it):
                if isinstance(it.get("period"), dict) and not _has_ev(it["period"]):
                    report.dropped_fields.append(f"{name}[{i}].period")
                    it["period"] = None
                kept.append(it)
            else:
                report.dropped_fields.append(f"{name}[{i}]={it.get('type') or it.get('raw', '')[:40]}")
        obj[name] = kept

    # legal_basis
    lb = obj.setdefault("legal_basis", {"level": "none", "items": []})
    kept = []
    for i, it in enumerate(lb.get("items") or []):
        if _has_ev(it):
            kept.append(it)
        else:
            report.dropped_fields.append(f"legal_basis.items[{i}]={it.get('canonical')}")
    lb["items"] = kept
    level = _legal_level(kept)
    if lb.get("level") != level:
        report.recomputed.append(f"legal_basis.level: {lb.get('level')} -> {level}")
        lb["level"] = level

    # reason
    rs = obj.setdefault("reason", {"level": "none", "text": None, "evidence": []})
    if rs.get("level") != "none" and not _has_ev(rs):
        report.dropped_fields.append(f"reason.level={rs.get('level')}")
        obj["reason"] = {"level": "none", "text": None, "evidence": []}

    # next_steps
    ns = obj.setdefault("next_steps", {"stated": False, "text": None, "evidence": []})
    if ns.get("stated") and not _has_ev(ns):
        report.dropped_fields.append("next_steps.stated")
        obj["next_steps"] = {"stated": False, "text": None, "evidence": []}

    # period
    if isinstance(obj.get("period"), dict) and not _has_ev(obj["period"]):
        report.dropped_fields.append("period")
        obj["period"] = None

    # appeal
    ap = obj.setdefault("appeal", {"level": "none", "routes": [], "explicit_denial": None})
    routes = []
    for i, r in enumerate(ap.get("routes") or []):
        if _has_ev(r):
            routes.append(r)
        else:
            report.dropped_fields.append(f"appeal.routes[{i}]={r.get('type')}")
    ap["routes"] = routes
    if isinstance(ap.get("explicit_denial"), dict) and not _has_ev(ap["explicit_denial"]):
        report.dropped_fields.append("appeal.explicit_denial")
        ap["explicit_denial"] = None
    level = _appeal_level(routes)
    if ap.get("level") != level:
        report.recomputed.append(f"appeal.level: {ap.get('level')} -> {level}")
        ap["level"] = level

    # request_meta
    rm = obj.setdefault("request_meta", {"bank_name": None, "date": None, "number": None})
    for k in ("bank_name", "date", "number"):
        if isinstance(rm.get(k), dict) and not _has_ev(rm[k]):
            report.dropped_fields.append(f"request_meta.{k}")
            rm[k] = None

    report.filled_fields = count_filled(obj)


def _legal_level(items: list[dict]) -> str:
    if any(it.get("kind") == "law" and (it.get("article") or it.get("point") or it.get("part")) for it in items):
        return "norm"
    if any(it.get("kind") in ("law", "regulation") for it in items):
        return "law_only"
    if any(it.get("kind") == "contract" for it in items):
        return "contract_only"
    return "none"


def _appeal_level(routes: list[dict]) -> str:
    types = {r.get("type") for r in routes}
    if types & EXTERNAL_ROUTES:
        return "external"
    if types & INTERNAL_ROUTES or types:
        return "internal_only"
    return "none"


def count_filled(obj: dict) -> int:
    """Число заполненных полей с опорой (для метрики «доля полей с валидным span»)."""
    n = 0
    for _, evs in iter_evidence(obj):
        if evs:
            n += 1
    return n


def normalize(obj, report: ValidationReport, path: str = "$") -> None:
    """Технические поправки, не меняющие смысл: уверенность в [0, 1] (модель иногда пишет проценты)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if k == "confidence" and isinstance(v, (int, float)) and not 0 <= v <= 1:
                nv = v / 100 if 1 < v <= 100 else (1.0 if v > 1 else 0.0)
                obj[k] = round(nv, 3)
                report.recomputed.append(f"{p}: {v} -> {obj[k]}")
            else:
                normalize(v, report, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            normalize(v, report, f"{path}[{i}]")


def validate(extraction: dict, text: str, fuzzy: bool = True) -> tuple[dict, ValidationReport]:
    """Полный цикл: нормализация → схема → заземление → обнуление неподтверждённого → схема."""
    obj = copy.deepcopy(extraction)
    report = ValidationReport()
    normalize(obj, report)
    errs = schema_errors(obj)
    if errs:
        report.schema_errors = errs
        return obj, report
    ground_evidence(obj, text, report, fuzzy=fuzzy)
    enforce_support(obj, report)
    report.schema_errors = schema_errors(obj)
    return obj, report
