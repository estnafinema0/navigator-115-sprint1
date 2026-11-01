"""Инварианты валидатора M1: «нет цитаты — нет поля»."""
import copy
import json
from pathlib import Path

import pytest
from navigator.evidence import check_span, locate
from navigator.validator import schema_errors, validate

ROOT = Path(__file__).resolve().parents[1]
CORPUS = {r["id"]: r for r in (json.loads(x) for x in (ROOT / "data/real/corpus.jsonl").read_text().splitlines() if x)}


def gold(doc_id: str) -> tuple[dict, str]:
    g = json.loads((ROOT / f"eval/gold/{doc_id}.json").read_text())
    return g["extraction"], CORPUS[doc_id]["text"]


@pytest.mark.parametrize("doc_id", ["A1", "B1", "B3"])
def test_gold_passes_unchanged(doc_id):
    ex, text = gold(doc_id)
    out, rep = validate(ex, text)
    assert rep.ok, rep.schema_errors
    assert rep.dropped_quotes == [] and rep.dropped_fields == [] and rep.recomputed == []
    assert out == ex


def test_hallucinated_quote_drops_field():
    ex, text = gold("B1")
    ex = copy.deepcopy(ex)
    # модель «додумала» норму закона, которой в тексте нет
    ex["legal_basis"] = {"level": "norm", "items": [{
        "kind": "law", "law": "115-ФЗ", "article": "7", "point": "14", "canonical": "115-ФЗ ст. 7 п. 14",
        "evidence": [{"quote": "на основании п. 14 ст. 7 115-ФЗ"}]}]}
    out, rep = validate(ex, text)
    assert out["legal_basis"] == {"level": "none", "items": []}
    assert rep.dropped_quotes and any("legal_basis" in f for f in rep.dropped_fields)


def test_field_without_evidence_is_nulled():
    ex, text = gold("A1")
    ex = copy.deepcopy(ex)
    ex["deadlines"] = [{"applies_to": "bank_review", "kind": "relative", "amount": 7, "unit": "working_days",
                        "raw": "7 рабочих дней", "evidence": []}]
    ex["appeal"]["routes"].append({"type": "mvk", "evidence": []})
    out, rep = validate(ex, text)
    assert out["deadlines"] == []
    assert out["appeal"]["level"] == "internal_only"  # МВК без цитаты не считается
    assert len(rep.dropped_fields) == 2


def test_scenario_without_evidence_becomes_unknown():
    ex, text = gold("B3")
    ex = copy.deepcopy(ex)
    ex["scenario"] = {"value": "operation_refusal", "confidence": 0.9, "evidence": [{"quote": "отказано в операции"}]}
    out, _ = validate(ex, text)
    assert out["scenario"]["value"] == "unknown"


def test_levels_recomputed_from_facts():
    ex, text = gold("B3")
    ex = copy.deepcopy(ex)
    ex["legal_basis"]["level"] = "norm"  # модель завысила уровень
    out, rep = validate(ex, text)
    assert out["legal_basis"]["level"] == "contract_only"
    assert rep.recomputed


def test_offsets_filled_and_tolerant_to_typography():
    text = "Счёт заблокирован. Основание: «Федеральный закон № 115-ФЗ» — срок ответа до 3 рабочих дней."
    span = locate(text, 'Счет заблокирован. Основание: "Федеральный закон № 115-ФЗ" - срок')
    assert span is not None and span.start == 0
    assert text[span.start:span.end].startswith("Счёт")
    assert check_span(text, {"quote": span.quote, "start": span.start, "end": span.end})
    assert locate(text, "срок ответа до 5 рабочих дней") is None


def test_schema_rejects_unknown_scenario():
    ex, _ = gold("A1")
    bad = copy.deepcopy(ex)
    bad["scenario"]["value"] = "unblock_guaranteed"
    assert schema_errors(bad)


def test_confidence_percent_normalized_not_fatal():
    ex, text = gold("B1")
    ex = copy.deepcopy(ex)
    ex["scenario"]["confidence"] = 100
    out, rep = validate(ex, text)
    assert rep.ok and out["scenario"]["confidence"] == 1.0
    assert any("confidence" in r for r in rep.recomputed)


def test_near_verbatim_quote_snaps_to_source_text():
    ex, text = gold("B1")
    ex = copy.deepcopy(ex)
    # модель исказила падеж и опечаталась: «справка о доходах», «прислите»
    ex["requested_items"][3]["evidence"] = [{"quote": "справка о доходах"}]
    ex["next_steps"]["evidence"] = [{"quote": "прислите подтверждающие документы"}]
    out, rep = validate(ex, text)
    assert out["requested_items"][3]["evidence"][0]["quote"] in text
    assert out["next_steps"]["evidence"][-1]["quote"].startswith("пришлите")
    assert len(rep.snapped_quotes) == 2 and not rep.dropped_quotes


def test_fuzzy_does_not_rescue_invented_quote():
    ex, text = gold("B1")
    ex = copy.deepcopy(ex)
    ex["appeal"]["routes"] = [{"type": "mvk", "evidence": [{"quote": "вы вправе обратиться в межведомственную комиссию"}]}]
    out, rep = validate(ex, text)
    assert out["appeal"]["routes"] == [] and rep.dropped_quotes


# ---- «цитата подтверждает поле» (протокол жюри score-risk-compliance.md, K5): настоящая, но чужая цитата ----
SWAP_TEXT = ("Банк отказал в проведении операции на основании п. 11 ст. 7 Федерального закона № 115-ФЗ. "
             "Документы рассматриваем до 7 рабочих дней. Ответьте до 25.02.2026. Вопросы можно задать в чате.")


def _swap_base() -> dict:
    from navigator.rules import extract
    return extract(SWAP_TEXT)


def test_swapped_quote_drops_external_route():
    ex = _swap_base()
    for typ in ("mvk", "cbr_complaint", "court"):
        e = copy.deepcopy(ex)
        e["appeal"]["routes"] = [{"type": typ, "evidence": [{"quote": "Банк отказал в проведении операции"}]}]
        out, rep = validate(e, SWAP_TEXT)
        assert out["appeal"]["routes"] == [] and out["appeal"]["level"] == "none", typ
        assert any("не подтверждает маршрут" in f for f in rep.dropped_fields)


def test_route_with_own_quote_kept():
    text = SWAP_TEXT + " Вы вправе обратиться в межведомственную комиссию при Банке России."
    e = _swap_base()
    e["appeal"]["routes"] = [{"type": "mvk", "evidence": [{"quote": "обратиться в межведомственную комиссию"}]}]
    out, _ = validate(e, text)
    assert out["appeal"]["level"] == "external"


def test_swapped_quote_drops_deadline_amount_and_date():
    e = _swap_base()
    e["deadlines"] = [
        {"applies_to": "bank_review", "kind": "relative", "amount": 5, "unit": "working_days", "raw": "5 р.д.",
         "evidence": [{"quote": "Документы рассматриваем до 7 рабочих дней"}]},
        {"applies_to": "client_response", "kind": "date", "date": "2026-03-01", "raw": "до 01.03",
         "evidence": [{"quote": "Ответьте до 25.02.2026"}]},
        {"applies_to": "client_response", "kind": "date", "date": "2026-02-25", "raw": "до 25.02",
         "evidence": [{"quote": "Ответьте до 25.02.2026"}]},
    ]
    out, rep = validate(e, SWAP_TEXT)
    assert [d.get("date") for d in out["deadlines"]] == ["2026-02-25"]
    assert sum("нет этого числа" in f for f in rep.dropped_fields) == 2


def test_word_number_deadline_supported():
    from navigator.typecheck import check_support
    e = {"deadlines": [{"applies_to": "client_response", "kind": "relative", "amount": 1, "unit": "days_unspecified",
                        "raw": "x", "evidence": [{"quote": "не позднее следующего дня"}]}]}
    notes: list[str] = []
    check_support(e, notes)
    assert len(e["deadlines"]) == 1 and not notes


def test_swapped_quote_drops_legal_basis():
    e = _swap_base()
    e["legal_basis"]["items"] = [{"kind": "law", "law": "115-ФЗ", "article": "7", "point": "5.2", "canonical": "115-ФЗ ст. 7 п. 5.2",
                                  "evidence": [{"quote": "на основании п. 11 ст. 7 Федерального закона № 115-ФЗ"}]}]
    out, rep = validate(e, SWAP_TEXT)
    assert out["legal_basis"] == {"level": "none", "items": []}
    assert any("не называет эту норму" in f for f in rep.dropped_fields)


def test_article_7_7_not_confused_with_7():
    from navigator.typecheck import legal_ref_supported
    q = [{"quote": "п. 5 ст. 7.7 Федерального закона № 115-ФЗ"}]
    assert legal_ref_supported({"kind": "law", "law": "115-ФЗ", "article": "7.7", "point": "5", "evidence": q})
    assert not legal_ref_supported({"kind": "law", "law": "115-ФЗ", "article": "7", "point": "5", "evidence": q})
