"""Отрицание и новые виды ПДн (протокол жюри «риск и комплаенс», раунд 2, 27.10). Тексты: синтетика."""
from navigator.guard import check
from navigator.pii import _luhn, mask
from navigator.rules import extract
from navigator.typecheck import route_supported
from navigator.validator import validate

NEG_TEXT = ("Банк отказал в проведении операции. Обжалование в межведомственной комиссии при Банке России "
            "в данном случае не предусмотрено.")
POS_TEXT = "Если не согласны с решением, вы вправе обратиться в межведомственную комиссию при Банке России."


def test_negated_mvk_is_not_a_route():
    ex = extract(NEG_TEXT)
    assert not any(r["type"] == "mvk" for r in ex["appeal"]["routes"])
    out, _ = validate(ex, NEG_TEXT)
    assert out["appeal"]["level"] != "external"


def test_conditional_mvk_is_still_a_route():
    assert any(r["type"] == "mvk" for r in extract(POS_TEXT)["appeal"]["routes"])


def test_guard_does_not_count_negated_appeal_as_e5():
    g = check(NEG_TEXT)
    assert g.elements["E5"] != "external"


def test_llm_route_with_negated_quote_is_dropped():
    route = {"type": "mvk", "evidence": [{"quote": "Обжалование в межведомственной комиссии при Банке России в данном случае не предусмотрено"}]}
    assert not route_supported(route)


def _card() -> str:
    base = "427638001234567"
    return next(base + str(d) for d in range(10) if _luhn(base + str(d)))


def test_card_passport_birthdate_masked_amounts_kept():
    n = _card()
    text = f"Карта {n[:4]} {n[4:8]} {n[8:12]} {n[12:]}, паспорт серия 4512 номер 345678, дата рождения 01.02.1990. Сумма 5 000 000,00 ₽ до 25.02.2026, ст. 7 п. 11."
    r = mask(text)
    assert len(r.text) == len(text)
    assert {"card", "passport", "birth_date"} <= set(r.counts)
    assert n[:4] not in r.text and "345678" not in r.text and "1990" not in r.text
    assert "5 000 000,00 ₽" in r.text and "25.02.2026" in r.text and "ст. 7 п. 11" in r.text


def test_random_16_digits_not_luhn_kept():
    assert mask("номер заявки 1234 5678 9012 3456").counts == {}
