"""Рабочий пакет для голден-разметки: заготовки файлов и тексты без чужой разметки.

Создаёт папку eval/gold/work/<кодировщик>/:
- <id>.json — заготовка gold-файла (метаданные из корпуса и пустое extraction);
- texts.md — только тексты и метаданные источника, без разметки кодировщика 1 и подсказок агента;
- elements.csv — пустая таблица элементов уведомления (блок В).

Пример: python scripts/gold_pack.py --coder c2 --set double
Наборы описаны в docs/ops/gold-tz.md, разд. 2. Существующие файлы не перезаписываются.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from navigator.rules import empty  # noqa: E402

CORPUS = ROOT / "data" / "real" / "corpus.jsonl"
WORK = ROOT / "eval" / "gold" / "work"

SETS = {
    "calib": ["A14", "A15", "C3"],
    "double": ["A1", "A2", "A6", "A7", "A10", "B1", "B2", "B3", "B4", "B6",
               "B7", "B9", "B12", "B13", "C1", "C4", "C6", "C7", "C11", "C12"],
    "single": ["B10", "C13", "C14"],
    "retell": ["A3", "A4", "A5", "A8", "A9", "A11", "A12", "A13", "A16", "A17",
               "B5", "B8", "B11", "B14", "C2", "C5", "C8", "C9", "C10"],
}
ELEMENT_COLS = ["id", "E2", "E3", "E4", "E5", "E6", "deadline", "mvk", "forbidden", "comment"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coder", required=True, help="код кодировщика без имени, например c1 или c2")
    ap.add_argument("--set", choices=[*SETS, "all"], default=None)
    ap.add_argument("--ids", default="", help="список id через запятую, вместо --set")
    args = ap.parse_args()

    corpus = {r["id"]: r for r in (json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x)}
    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    elif args.set == "all":
        ids = list(corpus)
    elif args.set:
        ids = SETS[args.set]
    else:
        ap.error("нужен --set или --ids")
    missing = [i for i in ids if i not in corpus]
    if missing:
        print("Нет в корпусе:", ", ".join(missing))
        return 1

    out = WORK / args.coder
    out.mkdir(parents=True, exist_ok=True)
    made = 0
    for i in ids:
        r = corpus[i]
        f = out / f"{i}.json"
        if f.exists():
            continue
        g = {
            "doc_id": i,
            "corpus_ref": f"data/real/corpus.jsonl#{i}",
            "text_sha256": r["text_sha256"],
            "text_type": r["text_type"],
            "annotator": args.coder,
            "status": "in_progress",
            "notes": [],
            "extraction": empty(),
        }
        f.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        made += 1

    lines = [f"# Тексты для разметки ({args.coder})", ""]
    for i in ids:
        r = corpus[i]
        lines += [f"## {i}", "", f"Банк: {r['bank']} · год: {r['year']} · клиент: {r['client_type']} · "
                  f"закон по источнику: {r['law']} · текст: {r['text_type']}", "", "```text", r["text"], "```", ""]
    (out / "texts.md").write_text("\n".join(lines), encoding="utf-8")

    el = out / "elements.csv"
    if not el.exists():
        with el.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(ELEMENT_COLS)
            for i in ids:
                w.writerow([i] + [""] * (len(ELEMENT_COLS) - 1))
    print(f"{out}: заготовок создано {made}, текстов в texts.md {len(ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
