"""Правила M1: формулировки закона дают сценарий, а не unknown (протокол красной команды 27.10). Тексты — синтетика."""
import pytest
from navigator.rules import extract
from navigator.validator import validate

CASES = [
    ("Банк отказал в выполнении распоряжения клиента о совершении операции на основании п. 11 ст. 7 115-ФЗ.", "operation_refusal"),
    ("Сообщаем об отказе от выполнения распоряжения о совершении операции по платёжному поручению № 15.", "operation_refusal"),
    ("Банк запрашивает у вас документы по 115-ФЗ: договор и акты по операциям за сентябрь.", "doc_request"),
    ("В рамках 115-ФЗ просим в течение 5 рабочих дней предоставить договор с контрагентом.", "doc_request"),
    ("Для проверки операции необходимо в течение 3 рабочих дней представить пояснения.", "doc_request"),
]


@pytest.mark.parametrize("text,scenario", CASES)
def test_law_wording_scenario(text, scenario):
    out, rep = validate(extract(text), text)
    assert out["scenario"]["value"] == scenario, out["scenario"]
    assert rep.ok


def test_refusal_outranks_request():
    text = "Банк отказал в выполнении распоряжения клиента о совершении операции. Просим предоставить пояснения."
    assert extract(text)["scenario"]["value"] == "operation_refusal"


def test_threat_still_not_measure():
    text = "Просим предоставить документы. Если не предоставите, банк вправе отказать в выполнении распоряжения клиента."
    assert extract(text)["scenario"]["value"] == "doc_request"


def test_quotes_do_not_stop_inside_date_or_word():
    """Цитата «что сделать» не рвётся на точке в дате, причина не обрывается посреди слова."""
    from navigator.rules import extract

    text = ("«Пожалуйста, ответьте до 25.02.2026. Вы внесли на свой счет 5 000 000,00 ₽ … "
            "Предоставьте информацию об источнике происхождения денежных средств»")
    ex = extract(text)
    assert ex["next_steps"]["text"] == "ответьте до 25.02.2026"
    assert ex["reason"]["text"] == "Вы внесли на свой счет 5 000 000,00 ₽"
    for q in (ex["next_steps"]["evidence"][0]["quote"], ex["reason"]["evidence"][0]["quote"]):
        assert q in text
