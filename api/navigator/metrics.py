"""Метрики качества разбора M1 (PROMPT.md, разд. 9).

Честность отчёта:
- метрики по классам с n; класс с n < 5 — «не измерено»;
- span и exact match — только на дословных и частично дословных текстах (фильтр делает
  вызывающий код);
- реальные данные и синтетика считаются отдельно;
- LLM-as-judge не используется: только exact match и F1 по эталону.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from .evidence import iter_evidence, locate

MIN_N = 5


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("ё", "е")).strip().lower()


def norm_set(ex: dict) -> frozenset[str]:
    return frozenset(_norm(i["canonical"]) for i in ex["legal_basis"]["items"])


def client_deadline(ex: dict) -> tuple | None:
    for d in ex["deadlines"]:
        if d["applies_to"] == "client_response":
            return (d["kind"], d.get("date"), d.get("amount"), d.get("unit"))
    return None


def doc_types(ex: dict) -> frozenset[str]:
    return frozenset(i["type"] for i in ex["requested_items"])


def channel_set(ex: dict) -> frozenset[str]:
    return frozenset(c["type"] for c in ex["response_channels"])


# Поля, по которым считаем «заполнено / не заполнено» для метрики галлюцинаций.
def filled_slots(ex: dict) -> dict[str, bool]:
    return {
        "legal_basis": bool(ex["legal_basis"]["items"]),
        "reason": ex["reason"]["level"] != "none",
        "requested_items": bool(ex["requested_items"]),
        "period": ex.get("period") is not None,
        "deadline_client": client_deadline(ex) is not None,
        "deadline_bank": any(d["applies_to"] == "bank_review" for d in ex["deadlines"]),
        "channels": bool(ex["response_channels"]),
        "next_steps": bool(ex["next_steps"]["stated"]),
        "consequences": bool(ex["consequences"]),
        "appeal": bool(ex["appeal"]["routes"]),
        "appeal_denial": ex["appeal"].get("explicit_denial") is not None,
        "operations": bool(ex["operations"]),
    }


@dataclass
class Rate:
    k: int = 0
    n: int = 0

    def add(self, ok: bool) -> None:
        self.n += 1
        self.k += int(ok)

    @property
    def value(self) -> float | None:
        return self.k / self.n if self.n else None

    def fmt(self) -> str:
        if self.n < MIN_N:
            return f"не измерено (n={self.n})"
        return f"{self.value:.2f} (n={self.n})"


@dataclass
class F1:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    docs: int = 0

    def add(self, gold: frozenset, pred: frozenset) -> None:
        self.docs += 1
        self.tp += len(gold & pred)
        self.fp += len(pred - gold)
        self.fn += len(gold - pred)

    @property
    def value(self) -> float | None:
        p = self.tp / (self.tp + self.fp) if self.tp + self.fp else None
        r = self.tp / (self.tp + self.fn) if self.tp + self.fn else None
        if p is None or r is None or p + r == 0:
            return None if p is None and r is None else 0.0
        return 2 * p * r / (p + r)

    def fmt(self) -> str:
        if self.docs < MIN_N:
            return f"не измерено (n={self.docs})"
        v = self.value
        return f"{v:.2f} (n={self.docs}, tp={self.tp}, fp={self.fp}, fn={self.fn})" if v is not None else f"н/д (n={self.docs})"


def evaluate(items: list[dict]) -> dict:
    """items: [{id, text, gold, raw_pred, pred}] — raw_pred до валидатора, pred после."""
    m = {
        "scenario": Rate(), "norm_exact": Rate(), "client_deadline_exact": Rate(), "channel_exact": Rate(),
        "appeal_level": Rate(), "docs_f1": F1(), "span_valid_raw": Rate(),
        "halluc_raw": Rate(), "halluc_validated": Rate(),
    }
    per_class: dict[str, Rate] = defaultdict(Rate)
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    for it in items:
        g, p, raw = it["gold"], it["pred"], it.get("raw_pred") or it["pred"]
        gs, ps = g["scenario"]["value"], p["scenario"]["value"]
        m["scenario"].add(gs == ps)
        per_class[gs].add(gs == ps)
        confusion[(gs, ps)] += 1
        m["norm_exact"].add(norm_set(g) == norm_set(p))
        m["client_deadline_exact"].add(client_deadline(g) == client_deadline(p))
        m["channel_exact"].add(channel_set(g) == channel_set(p))
        m["appeal_level"].add(g["appeal"]["level"] == p["appeal"]["level"])
        m["docs_f1"].add(doc_types(g), doc_types(p))
        for _, evs in iter_evidence(raw):
            for ev in evs:  # доля цитат модели, которые реально есть в тексте (до валидатора)
                m["span_valid_raw"].add(locate(it["text"], ev.get("quote", "")) is not None)
        gf = filled_slots(g)
        for which, pred in (("halluc_raw", raw), ("halluc_validated", p)):
            pf = filled_slots(pred)
            for slot, gold_filled in gf.items():
                if not gold_filled:
                    m[which].add(pf[slot])  # доля пустых в эталоне слотов, которые модель заполнила
    return {"metrics": m, "per_class": dict(per_class), "confusion": dict(confusion), "n": len(items)}
