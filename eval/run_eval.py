"""Прогон eval M1 (make eval): предиктор → валидатор → метрики → reports/eval-YYYY-MM-DD.md.

Предикторы:
- gold   — подаёт эталон как предсказание (санити-проверка каркаса: все метрики = 1.00);
- empty  — ничего не извлекает (нижняя граница: показывает, сколько даёт «угадывание пустоты»);
- rules  — детерминированные правила (M1, слой 1);
- llm    — локальная LLM со схемой (M1, слой 2).

Наборы считаются раздельно: real (data/real + eval/gold, только дословные и частично
дословные тексты) и synth (data/synthetic). Метрики с n < 5 — «не измерено».
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from navigator.metrics import MIN_N, evaluate  # noqa: E402
from navigator.validator import validate  # noqa: E402

THRESHOLDS = {  # PROMPT.md, разд. 9
    "scenario": ("Вид меры / сценарий — accuracy", 0.90),
    "norm_exact": ("Норма — exact match", 0.85),
    "client_deadline_exact": ("Срок клиента — exact match", 0.90),
    "docs_f1": ("Перечень документов — micro-F1", 0.80),
    "channel_exact": ("Канал — exact match по набору", 0.85),
    "appeal_level": ("Обжалование — accuracy уровня", 0.85),
    "span_valid_raw": ("Цитаты модели найдены в тексте (до валидатора)", 1.00),
    "halluc_raw": ("«Галлюцинации» до валидатора (меньше — лучше)", 0.02),
    "halluc_validated": ("«Галлюцинации» после валидатора (меньше — лучше)", 0.02),
}
LOWER_IS_BETTER = {"halluc_raw", "halluc_validated"}


def empty_prediction() -> dict:
    return {
        "schema_version": "0.1.0", "scenario": {"value": "unknown", "confidence": 0.0, "evidence": []},
        "measures": [], "legal_basis": {"level": "none", "items": []}, "reason": {"level": "none", "text": None, "evidence": []},
        "requested_items": [], "period": None, "deadlines": [], "response_channels": [],
        "next_steps": {"stated": False, "text": None, "evidence": []}, "consequences": [],
        "appeal": {"level": "none", "routes": [], "explicit_denial": None}, "operations": [],
        "request_meta": {"bank_name": None, "date": None, "number": None}, "questions_to_user": [],
    }


def predict(name: str, text: str, gold: dict) -> dict:
    if name == "gold":
        return copy.deepcopy(gold)
    if name == "empty":
        return empty_prediction()
    if name == "rules":
        from navigator.rules import extract
        return extract(text)
    if name in ("llm", "hybrid"):
        raw = llm_cached(text, slim=(name == "hybrid"))
        if name == "llm":
            return raw
        from navigator.llm import combine
        from navigator.rules import extract
        return combine(extract(text), raw, text)
    raise SystemExit(f"предиктор '{name}' ещё не реализован (M1, 23–24.10)")


CACHE = ROOT / "eval" / "cache"
LATENCY: list[float] = []
QUOTES = {"exact": 0, "snapped": 0, "dropped": 0, "fields_dropped": 0}  # точность цитат самой модели (до гибрида)


def llm_cached(text: str, slim: bool = False) -> dict:
    """Ответы модели кэшируются по (модель, промпт, схема декодера, текст): правка промпта или схемы
    даёт новый ключ, старые ответы не подмешиваются в замер."""
    import hashlib

    from navigator.llm import DEFAULT_MODEL, SYSTEM_PROMPT, extract, llm_schema
    setup = hashlib.sha256((SYSTEM_PROMPT + json.dumps(llm_schema(slim), sort_keys=True)).encode()).hexdigest()[:12]
    key = hashlib.sha256((DEFAULT_MODEL + ("|slim" if slim else "") + "|" + setup + "\n" + text).encode()).hexdigest()[:24]
    path = CACHE / f"{key}.json"
    if path.exists():
        rec = json.loads(path.read_text())
    else:
        try:
            raw, meta = extract(text, slim=slim)
        except Exception as e:  # модель вернула невалидный JSON или упала — честно считаем пустым ответом
            raw, meta = empty_prediction(), {"error": repr(e)[:300]}
        rec = {"raw": raw, "meta": meta}
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rec, ensure_ascii=False))
    if "seconds" in rec["meta"]:
        LATENCY.append(rec["meta"]["seconds"])
    from navigator.validator import validate as _v
    _, rep = _v(rec["raw"], text)
    n_ev = sum(len(e) for _, e in __import__("navigator.evidence", fromlist=["iter_evidence"]).iter_evidence(rec["raw"]))
    QUOTES["snapped"] += len(rep.snapped_quotes)
    QUOTES["dropped"] += len(rep.dropped_quotes)
    QUOTES["exact"] += max(0, n_ev - len(rep.snapped_quotes) - len(rep.dropped_quotes))
    QUOTES["fields_dropped"] += len(rep.dropped_fields)
    return rec["raw"]


def load_real() -> list[dict]:
    corpus = {r["id"]: r for r in (json.loads(x) for x in (ROOT / "data/real/corpus.jsonl").read_text().splitlines() if x)}
    out = []
    for f in sorted((ROOT / "eval/gold").glob("*.json")):
        g = json.loads(f.read_text())
        rec = corpus[g["doc_id"]]
        if rec["text_type"] == "retelling":
            continue
        out.append({"id": g["doc_id"], "text": rec["text"], "gold": g["extraction"], "status": g.get("status")})
    return out


SYNTH_PER_CLASS: int | None = None


def load_synth() -> list[dict]:
    """Синтетика; при --per-class N — детерминированная стратифицированная выборка по N на сценарий."""
    p = ROOT / "data/synthetic/synth-v1.jsonl"
    recs = [json.loads(x) for x in p.read_text().splitlines() if x]
    if SYNTH_PER_CLASS:
        seen: dict[str, int] = {}
        picked = []
        for r in recs:
            if seen.get(r["scenario"], 0) < SYNTH_PER_CLASS:
                seen[r["scenario"]] = seen.get(r["scenario"], 0) + 1
                picked.append(r)
        recs = picked
    return [{"id": r["id"], "text": r["text"], "gold": r["gold"]} for r in recs]


def run(name: str, items: list[dict]) -> dict:
    rows = []
    for it in items:
        raw = predict(name, it["text"], it["gold"])
        pred, _ = validate(raw, it["text"])
        rows.append({**it, "raw_pred": raw, "pred": pred})
    return evaluate(rows)


def verdict(key: str, rate) -> str:
    v = rate.value
    n = getattr(rate, "n", None) if hasattr(rate, "n") else rate.docs
    if v is None or (n is not None and n < MIN_N):
        return "—"
    thr = THRESHOLDS[key][1]
    ok = v <= thr if key in LOWER_IS_BETTER else v >= thr
    return "да" if ok else "нет"


def render(predictor: str, results: dict[str, dict]) -> str:
    lines = [
        f"# Eval M1 — предиктор `{predictor}` — {date.today():%d.%m.%Y}",
        "",
        "Сформирован `make eval`. Реальные тексты и синтетика считаются отдельно; на реальных — только дословные и "
        "частично дословные тексты с проверенной gold-разметкой. Метрики с n < 5 — «не измерено». LLM-as-judge не используется.",
        "",
    ]
    if predictor == "gold":
        lines += ["> Санити-проверка каркаса: эталон подаётся как предсказание, все метрики должны быть 1.00 (галлюцинации — 0.00). "
                  "Это не качество модели.", ""]
    if predictor == "empty":
        lines += ["> Нижняя граница: предиктор ничего не извлекает. Показывает, сколько метрик набирается «угадыванием пустоты».", ""]
    if predictor == "hybrid":
        lines += ["> Гибрид: правила + T-lite-it-2.1 (облегчённая схема) → валидатор цитат → проверка «тип ↔ цитата» → более тяжёлый "
                  "из подтверждённых сценариев. Строка «цитаты найдены» для гибрида относится к уже проверенному выходу; точность "
                  "цитат самой модели — строкой выше.", ""]
    if LATENCY:
        xs = sorted(LATENCY)
        p95 = xs[min(len(xs) - 1, int(0.95 * len(xs)))]
        lines += [f"Латентность LLM (новые вызовы и кэш): медиана {xs[len(xs) // 2]:.1f} с, p95 {p95:.1f} с, n={len(xs)}; "
                  "MacBook M1 16 ГБ, Ollama, T-lite-it-2.1 Q4_K_M.", ""]
    tq = sum(QUOTES[k] for k in ("exact", "snapped", "dropped"))
    if tq:
        lines += [f"Цитаты модели (до проверки): дословно {QUOTES['exact']}/{tq} = {QUOTES['exact'] / tq:.2f}; привязаны к тексту "
                  f"(опечатка, падеж) {QUOTES['snapped']}/{tq}; отброшены как отсутствующие в тексте {QUOTES['dropped']}/{tq}; "
                  f"полей обнулено из-за отсутствия опоры: {QUOTES['fields_dropped']}.", ""]
    for set_name, res in results.items():
        lines += [f"## Набор: {set_name} (n={res['n']})", "", "| Метрика | Значение | Порог | Достигнут |", "|---|---|---|---|"]
        for key, (label, thr) in THRESHOLDS.items():
            r = res["metrics"][key]
            sign = "≤" if key in LOWER_IS_BETTER else "≥"
            lines.append(f"| {label} | {r.fmt()} | {sign}{thr:.2f} | {verdict(key, r)} |")
        lines += ["", "Сценарий по классам (recall):", "", "| Класс | Значение |", "|---|---|"]
        for cls, r in sorted(res["per_class"].items()):
            lines.append(f"| {cls} | {r.fmt()} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predictor", default="gold")
    ap.add_argument("--sets", default="real,synth")
    ap.add_argument("--out", default=None)
    ap.add_argument("--per-class", type=int, default=None, help="синтетика: N текстов на сценарий (для медленных LLM)")
    args = ap.parse_args()
    global SYNTH_PER_CLASS
    SYNTH_PER_CLASS = args.per_class
    loaders = {"real": load_real, "synth": load_synth}
    results = {s: run(args.predictor, loaders[s]()) for s in args.sets.split(",")}
    md = render(args.predictor, results)
    if args.per_class:
        md = md.replace("\n## Набор: synth", f"\n> Синтетика: стратифицированная выборка по {args.per_class} текста на сценарий.\n\n## Набор: synth", 1)
    out = Path(args.out) if args.out else ROOT / "reports" / f"eval-{date.today():%Y-%m-%d}-{args.predictor}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"→ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
