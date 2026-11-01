"""Собирает data/real/corpus.jsonl из таблицы корпуса context/research/corpus-requests.md.

Источник истины для разметки — таблица (кодировщик 1, 10.10.2026). Скрипт ничего не
придумывает: переносит ячейки как есть и переводит коды «да/нет/частично/н/п» в enum.
Единственное, что добавляет агент, — поле scenario_suggested (предложение триажа по
колонке «Мера»); оно помечено scenario_suggested_by и подлежит проверке кодировщиками.

Для пяти демо-примеров (разд. 5 того же файла) берётся более полный текст, источник
помечен в text_origin.

Запуск: python scripts/build_corpus.py  (или make corpus)
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "context" / "research" / "corpus-requests.md"
OUT = ROOT / "data" / "real" / "corpus.jsonl"

COLUMNS = [
    "id", "bank", "year", "client", "law", "measure", "text_type", "fragment",
    "requested", "deadline", "norm", "reason", "todo", "appeal", "channel", "source",
]

# Предложение триажа по колонке «Мера» (агент, 20.10.2026). Порядок тяжести — как в
# описании поля scenario в api/schema/bank_request.schema.json.
SCENARIO_SUGGESTED = {
    "A1": "operation_refusal", "A2": "remote_access_restriction", "A3": "remote_access_restriction",
    "A4": "remote_access_restriction", "A5": "remote_access_restriction", "A6": "fz161_restriction",
    "A7": "fz161_restriction", "A8": "fz161_restriction", "A9": "fz161_restriction",
    "A10": "remote_access_restriction", "A11": "remote_access_restriction", "A12": "fz161_restriction",
    "A13": "remote_access_restriction", "A14": "remote_access_restriction", "A15": "contract_termination",
    "A16": "remote_access_restriction", "A17": "contract_termination",
    "B1": "doc_request", "B2": "remote_access_restriction", "B3": "remote_access_restriction",
    "B4": "contract_termination", "B5": "contract_termination", "B6": "remote_access_restriction",
    "B7": "doc_request", "B8": "remote_access_restriction", "B9": "remote_access_restriction",
    "B10": "remote_access_restriction", "B11": "operation_refusal", "B12": "remote_access_restriction",
    "B13": "contract_termination", "B14": "fz161_restriction",
    "C1": "doc_request", "C2": "doc_request", "C3": "doc_request", "C4": "doc_request",
    "C5": "operation_refusal", "C6": "doc_request", "C7": "remote_access_restriction",
    "C8": "doc_request", "C9": "operation_refusal", "C10": "operation_refusal", "C11": "other",
    "C12": "fz161_restriction", "C13": "remote_access_restriction", "C14": "remote_access_restriction",
}

BANK_KEYS = {
    "Сбер": "sber", "Сбер («зелёный банк»)": "sber", "Т-Банк": "tbank", "Т-Банк и др. (база ЦБ)": "tbank",
    "Райффайзенбанк": "raiffeisen", "Газпромбанк": "gazprombank", "Газпромбанк (ответ ЦБ клиенту)": "gazprombank",
    "МКБ": "mkb", "Россельхозбанк": "rshb", "Альфа-Банк": "alfa", "Яндекс Банк": "yandex", "Точка": "tochka",
    "ВТБ": "vtb", "Озон Банк": "ozon", "Модульбанк": "modulbank", "Балтийский Банк": "baltiysky",
    "банк не назван": "unknown", "банк скрыт": "unknown",
}

TEXT_TYPE = {"дословно": "verbatim", "частично дословно": "partial_verbatim", "пересказ": "retelling"}

# Номер демо-примера разд. 5 → ID строки таблицы
DEMO_EXAMPLES = {1: "A1", 2: "B1", 3: "B3", 4: "C7", 5: "B13"}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def code_norm(cell: str) -> str:
    c = cell.strip().lower()
    if c.startswith("да"):
        return "norm"
    if c.startswith("закон без статьи"):
        return "law_only"
    if c.startswith("только договор"):
        return "contract_only"
    if c.startswith("нет"):
        return "no"
    raise ValueError(f"norm: {cell!r}")


def code_reason(cell: str) -> str:
    c = cell.strip().lower()
    return {"да": "specific", "общая": "general", "частично": "partial", "нет": "no"}[c]


def code_ynpn(cell: str) -> str:
    c = cell.strip().lower()
    if c in ("да",):
        return "yes"
    if c.startswith("частично"):
        return "partial"
    if c in ("нет",):
        return "no"
    if c in ("н/п",):
        return "na"
    raise ValueError(f"y/n/p/na: {cell!r}")


def code_appeal(cell: str) -> str:
    c = code_ynpn(cell)
    return {"yes": "external", "partial": "internal_only", "no": "no"}[c]


def code_deadline(cell: str) -> str:
    c = cell.strip().lower()
    if c.startswith("да"):
        return "yes"
    if c.startswith("нет"):
        return "no"
    raise ValueError(f"deadline: {cell!r}")


def parse_table(md: str) -> list[dict]:
    rows = []
    for line in md.splitlines():
        if not re.match(r"^\| [ABC]\d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) != len(COLUMNS):
            raise ValueError(f"{len(cells)} колонок в строке: {line[:60]}")
        rows.append(dict(zip(COLUMNS, cells, strict=True)))
    return rows


def parse_demo_examples(md: str) -> dict[str, str]:
    """Текст демо-примеров разд. 5: склеиваем строки цитаты (> …)."""
    out: dict[str, str] = {}
    section = md.split("## 5. Пять реалистичных примеров для демо", 1)[1]
    blocks = re.split(r"\*\*Пример (\d)\.", section)[1:]
    for num, body in zip(blocks[0::2], blocks[1::2], strict=True):
        quote_lines = [ln[1:].strip() for ln in body.splitlines() if ln.startswith(">")]
        out[DEMO_EXAMPLES[int(num)]] = " ".join(quote_lines)
    return out


def main() -> int:
    md = nfc(SRC.read_text(encoding="utf-8"))
    rows = parse_table(md)
    demo = parse_demo_examples(md)
    if len(rows) != 45:
        print(f"ожидалось 45 строк, найдено {len(rows)}", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            url_m = re.search(r"\((https?://[^)]+)\)", r["source"])
            law = r["law"]
            text = demo.get(r["id"], r["fragment"])
            rec = {
                "id": r["id"],
                "source_group": r["id"][0],
                "source_url": url_m.group(1) if url_m else None,
                "source_note": re.sub(r"\[ссылка\]\([^)]+\)", "", r["source"]).strip() or None,
                "bank": r["bank"],
                "bank_key": BANK_KEYS[r["bank"]],
                "year": r["year"],
                "client_type": r["client"],
                "law": "161-ФЗ" if law.startswith("161") else "115-ФЗ",
                "law_assumed": "предположительно" in law,
                "measure_raw": r["measure"],
                "text_type": TEXT_TYPE[r["text_type"]],
                "text": text,
                "text_origin": "demo_example_sec5" if r["id"] in demo else "table_fragment",
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "requested_raw": r["requested"],
                "coding_raw": {
                    "deadline": r["deadline"], "norm": r["norm"], "reason": r["reason"],
                    "todo": r["todo"], "appeal": r["appeal"], "channel": r["channel"],
                },
                "elements": {
                    "E1": "yes",
                    "E2": code_norm(r["norm"]),
                    "E3": code_reason(r["reason"]),
                    "E4": code_ynpn(r["todo"]),
                    "E5": code_appeal(r["appeal"]),
                    "E6": code_ynpn(r["channel"]),
                    "E8": "not_coded",
                    "E9": "not_coded",
                    "deadline": code_deadline(r["deadline"]),
                },
                "coder": "coder1_2026-10-10",
                "scenario_suggested": SCENARIO_SUGGESTED[r["id"]],
                "scenario_suggested_by": "agent_2026-10-20_needs_review",
                "pii_removed": True,
                "split_group": BANK_KEYS[r["bank"]],
                "license_note": "цитата из публичного отзыва/публикации в объёме, необходимом для исследования; ПДн удалены",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"записано {len(rows)} → {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
