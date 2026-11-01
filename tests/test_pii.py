"""Маскирование ПДн на входе (152-ФЗ): ИНН, счёт, телефон, СНИЛС, e-mail. Примеры — синтетика."""
from fastapi.testclient import TestClient
from navigator.app import app
from navigator.pii import mask

client = TestClient(app)


def test_masks_personal_data_and_keeps_length():
    cases = {
        "ИНН 7701234567": "inn", "ИНН ИП 770123456789": "inn",
        "счёт 40802810900001234567": "account", "счёт 40802 810 9 0000 1234567": "account",
        "тел. +7 (916) 123-45-67": "phone", "тел. 8 916 123 45 67": "phone", "тел. 89161234567": "phone",
        "СНИЛС 123-456-789 01": "snils", "СНИЛС 12345678901": "snils", "почта ip.ivanov@mail.ru": "email",
    }
    for src, kind in cases.items():
        r = mask(src)
        assert len(r.text) == len(src) and r.counts.get(kind) == 1, (src, r.text, r.counts)
        assert not any(ch.isdigit() for ch in r.text.split(" ", 1)[1]) or kind == "account", (src, r.text)
        assert "@" not in r.text or kind == "email"


def test_does_not_mask_amounts_dates_norms_letters():
    keep = ("Операция от 12.10.2026 на сумму 1 000 000 руб. отклонена на основании п. 11 ст. 7 Федерального закона № 115-ФЗ "
            "от 07.08.2001. Письма Банка России ИН-01-59/98 и ИН-03-59/11. Платёжное поручение № 123. Сумма 5000000 рублей, "
            "1500000000 рублей. БИК 044525225. Звоните 8-800-100-24-24 или 8 (800) 555-35-35.")
    r = mask(keep)
    assert r.text == keep and not r.masked, r.counts


def test_parse_masks_before_analysis_and_offsets_match_original():
    text = ("Банк отказал в проведении операции на основании п. 11 ст. 7 Федерального закона № 115-ФЗ. "
            "Клиент ИП Иванов, ИНН 770123456789, счёт 40802810900001234567, тел. +7 (916) 123-45-67. "
            "Пришлите пояснения в чат до 25.02.2026.")
    r = client.post("/api/v1/parse", json={"text": text, "mode": "rules"}).json()
    assert r["meta"]["pii_masked"] is True and r["meta"]["pii_counts"] == {"account": 1, "phone": 1, "inn": 1}
    assert "770123456789" not in str(r) and "40802810900001234567" not in str(r)
    for it in r["extraction"]["legal_basis"]["items"] + r["extraction"]["deadlines"]:
        for e in it["evidence"]:
            assert text[e["start"]:e["end"]] == e["quote"]  # ПДн в этих цитатах нет: смещения верны и для исходника
    assert r["extraction"]["scenario"]["value"] == "operation_refusal"


def test_guard_masks_and_keeps_bank_hotline():
    text = "Счёт заблокирован. Ваш ИНН 7701234567. Вопросы по телефону 8-800-100-24-24."
    r = client.post("/api/v1/guard", json={"text": text}).json()
    assert r["pii_masked"] is True and r["pii_counts"] == {"inn": 1}
    assert r["elements"]["E6"] == "yes"
    assert "7701234567" not in str(r)


def test_no_pii_flag_false():
    r = client.post("/api/v1/guard", json={"text": "Сведения направлены в Росфинмониторинг."}).json()
    assert r["pii_masked"] is False and r["light"] == "red"
