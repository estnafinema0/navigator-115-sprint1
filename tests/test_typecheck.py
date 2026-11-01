"""Проверка «тип ↔ цитата»: эталоны проходят без изменений, выдуманный тип понижается."""
import copy
import json
from pathlib import Path

from navigator.typecheck import check_types

ROOT = Path(__file__).resolve().parents[1]


CORPUS = {json.loads(x)["id"]: json.loads(x)["text"] for x in (ROOT / "data/real/corpus.jsonl").read_text().splitlines() if x}


def golds():
    for f in sorted((ROOT / "eval/gold").glob("*.json")):
        yield f.stem, json.loads(f.read_text())["extraction"], CORPUS[f.stem]
    for x in (ROOT / "data/synthetic/synth-v1.jsonl").read_text().splitlines():
        if x:
            r = json.loads(x)
            yield r["id"], r["gold"], r["text"]


def test_gold_types_supported_by_quotes():
    for gid, g, text in golds():
        notes: list[str] = []
        before = copy.deepcopy(g)
        check_types(g, notes, text)
        assert not notes and g == before, (gid, notes)


def test_invented_type_downgraded():
    g = json.loads((ROOT / "eval/gold/B3.json").read_text())["extraction"]
    g["requested_items"][0]["type"] = "source_of_funds"  # цитата «фото или сканы… пояснения к ним» этого не подтверждает
    notes: list[str] = []
    check_types(g, notes)
    assert g["requested_items"][0]["type"] == "other" and notes


def test_contract_mention_is_not_requested_document():
    text = "Сообщаем, что банк расторгает договор банковского счёта."
    ext = {"requested_items": [{"type": "contracts", "raw": "договор", "evidence": [{"quote": "договор", "start": 30, "end": 37}]}],
           "scenario": {"value": "contract_termination", "evidence": [{"quote": "расторгает договор"}]}}
    notes: list[str] = []
    check_types(ext, notes, text)
    assert ext["requested_items"] == [] and notes


def test_unsupported_type_is_retyped_by_quote():
    ext = {"requested_items": [{"type": "explanation_operations", "raw": "x", "evidence": [{"quote": "описание схемы работы бизнеса"}]}]}
    check_types(ext, [])
    assert ext["requested_items"][0]["type"] == "explanation_business"


def test_consequence_without_threat_in_quote_dropped():
    # Случай из гибрида на A1: модель вписала пример из промпта, а цитата говорит об уже принятом отказе.
    text = "Если Вы не согласны с отказом, оформите в офисе заявление на реабилитацию."
    q = {"quote": text, "start": 0, "end": len(text)}
    ext = {"consequences": [{"type": "operation_refusal", "raw": "если не ответите, ограничим", "evidence": [q]}]}
    notes: list[str] = []
    check_types(ext, notes, text)
    assert ext["consequences"] == [] and notes


def test_real_threat_kept():
    text = "Если вы не представите документы, мы ограничим отдельные виды операций по счёту."
    i = text.index("мы ограничим")
    q = {"quote": text[i:-1], "start": i, "end": len(text) - 1}
    ext = {"consequences": [{"type": "operations_limit", "raw": text[i:-1], "evidence": [q]}]}
    check_types(ext, [], text)
    assert len(ext["consequences"]) == 1
