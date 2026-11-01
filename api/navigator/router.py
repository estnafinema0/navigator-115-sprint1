"""Маршрутизатор M5: какие пути обжалования и действий допустимы для сценария.

Детерминированно, по таблице kb/norms/routes.yaml. LLM здесь не участвует.
Главный инвариант: маршрут, не разрешённый для сценария, не возвращается никогда; МВК —
только для 4 видов решений и, где требуется, только после первого уровня.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

ROUTES_PATH = Path(__file__).resolve().parents[2] / "kb" / "norms" / "routes.yaml"


@lru_cache(maxsize=1)
def load_routes(path: Path = ROUTES_PATH) -> dict:
    d = yaml.safe_load(path.read_text(encoding="utf-8"))
    catalog = set(d["routes"])
    for sc, spec in d["scenarios"].items():
        unknown = set(spec["allowed"]) - catalog
        if unknown:
            raise ValueError(f"routes.yaml: сценарий {sc} ссылается на неизвестные маршруты {unknown}")
        if "mvk" in spec["allowed"] and sc not in d["mvk_admissible_scenarios"]:
            raise ValueError(f"routes.yaml: МВК разрешена для {sc}, но его нет в mvk_admissible_scenarios")
    return d


@dataclass
class RouteOption:
    id: str
    title: str
    available: bool
    blocked_reason: str | None = None
    norm: str | None = None
    template: int | None = None
    timer: str | None = None
    deadline_months: int | None = None
    source: dict = field(default_factory=dict)


@dataclass
class RouterResult:
    scenario: str
    options: list[RouteOption]
    mvk_note: str | None  # объяснение, почему МВК недопустима (если недопустима)


def _template_for(route: dict, scenario: str) -> int | None:
    t = route.get("template")
    if not isinstance(t, dict):
        return None
    if scenario in t:
        return t[scenario]
    if scenario == "operation_refusal":
        return t.get("after_operation_refusal")
    if scenario == "contract_refusal":
        return t.get("after_contract_refusal")
    if scenario == "zsk_high_cbr_only":
        return t.get("cbr_zsk_decision", t.get("zsk_high_cbr_only"))
    return None


def routes_for(scenario: str, first_level_done: bool = False) -> RouterResult:
    """first_level_done — клиент прошёл первый уровень (банк или ЦБ не устранили основания)."""
    d = load_routes()
    spec = d["scenarios"].get(scenario) or d["scenarios"]["unknown"]
    conds = spec.get("conditions", {})
    options = []
    for rid in spec["allowed"]:
        r = d["routes"][rid]
        c = conds.get(rid, {})
        available, reason = True, None
        if c.get("requires_first_level") and not first_level_done:
            available = False
            reason = ("Сначала первый уровень: банк должен рассмотреть ваши документы (п. 13.4 ст. 7 115-ФЗ)"
                      if scenario in ("operation_refusal", "contract_refusal")
                      else "Сначала заявление в Банк России о пересмотре уровня риска")
        options.append(RouteOption(
            id=rid, title=r["title"], available=available, blocked_reason=reason, norm=r.get("norm"),
            template=_template_for(r, scenario), timer=r.get("timer"), deadline_months=c.get("deadline_months"),
            source=r.get("source") or {},
        ))
    mvk_note = None if scenario in d["mvk_admissible_scenarios"] else d["inadmissible_explanations"].get(scenario)
    return RouterResult(scenario=scenario, options=options, mvk_note=mvk_note)
