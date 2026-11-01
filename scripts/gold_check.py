"""Проверка и нормализация gold-разметки eval/gold/*.json.

Для каждого файла:
- текст берётся из data/real/corpus.jsonl по doc_id, хеш текста должен совпасть;
- extraction проверяется по JSON Schema;
- всем цитатам проставляются start/end (если их нет) и проверяется text[start:end] == quote;
- валидатор не должен ничего отбросить: gold обязан быть полностью подтверждён цитатами.

Флаг --write перезаписывает файлы с проставленными смещениями.
Код возврата 1, если есть ошибки.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from navigator.evidence import check_span, iter_evidence, locate  # noqa: E402
from navigator.validator import ValidationReport, enforce_support, schema_errors  # noqa: E402

CORPUS = ROOT / "data" / "real" / "corpus.jsonl"
GOLD = ROOT / "eval" / "gold"


def load_corpus() -> dict[str, dict]:
    return {r["id"]: r for r in (json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x)}


def check_file(path: Path, corpus: dict[str, dict], write: bool) -> list[str]:
    g = json.loads(path.read_text(encoding="utf-8"))
    errs: list[str] = []
    rec = corpus.get(g["doc_id"])
    if rec is None:
        return [f"{path.name}: doc_id {g['doc_id']} нет в корпусе"]
    if rec["text_sha256"] != g.get("text_sha256"):
        errs.append(f"{path.name}: хеш текста не совпадает с корпусом (текст менялся — перепроверить разметку)")
    text = rec["text"]
    ex = g["extraction"]
    errs += [f"{path.name}: schema: {e}" for e in schema_errors(ex)]
    for p, evs in iter_evidence(ex):
        for ev in evs:
            if "start" not in ev or "end" not in ev:
                span = locate(text, ev["quote"])
                if span is None:
                    errs.append(f"{path.name}: {p}: цитаты нет в тексте: {ev['quote'][:60]!r}")
                    continue
                ev["start"], ev["end"], ev["quote"] = span.start, span.end, span.quote
            elif not check_span(text, ev):
                errs.append(f"{path.name}: {p}: span {ev['start']}:{ev['end']} не совпадает с цитатой")
    probe = json.loads(json.dumps(ex))
    rep = ValidationReport()
    enforce_support(probe, rep)
    if rep.dropped_fields:
        errs.append(f"{path.name}: поля без опоры: {rep.dropped_fields}")
    if rep.recomputed:
        errs.append(f"{path.name}: уровни не согласованы с фактами: {rep.recomputed}")
    if write and not errs:
        path.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dir", default=str(GOLD), help="папка с gold-файлами, например eval/gold/work/c1")
    args = ap.parse_args()
    corpus = load_corpus()
    files = sorted(Path(args.dir).glob("*.json"))
    all_errs: list[str] = []
    for f in files:
        all_errs += check_file(f, corpus, args.write)
    for e in all_errs:
        print("ОШИБКА", e)
    print(f"gold: {len(files)} файлов, ошибок: {len(all_errs)}")
    return 1 if all_errs else 0


if __name__ == "__main__":
    raise SystemExit(main())
