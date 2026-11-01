"""M5: генераторы по шаблонам ЦБ — только поля кейса, структура шаблона не меняется. Данные — синтетика."""
import io
from datetime import date

import pytest
from docx import Document
from navigator.docgen import TEMPLATES_DIR, generate, iter_paragraphs, load_spec, template_text

CASE = {  # синтетика
    "bank_full_name": "АО «Банк А»", "bank_short": "АО «Банк А»", "bank_address": "г. Москва, ул. Примерная, д. 1",
    "company_name": "ИП Тестов Тест Тестович", "company_short": "ИП Тестов Т. Т.", "company_inn": "500100732259",
    "company_kpp": "—", "company_address": "г. Москва", "company_phone": "+7 000 000-00-00",
    "contract_date": date(2024, 3, 1), "contract_number": "40802-01", "account_first": "40802810000000000001",
    "refusal_date": date(2026, 10, 12), "po_date": date(2026, 10, 12), "po_number": "41", "po_amount": "150 000,00 руб.",
    "po_purpose": "Оплата по договору поставки № 7", "reasons_letter_date": date(2026, 10, 15), "reasons_letter_number": "115/77",
    "attachments": "договор поставки № 7; товарная накладная № 12; УПД № 12",
}


def structure(content: bytes) -> tuple[int, int]:
    d = Document(io.BytesIO(content))
    return len(iter_paragraphs(d)), len(d.tables)


@pytest.mark.parametrize("no", [1, 4, 5])
def test_structure_preserved_and_empty_case_changes_nothing(no):
    spec = load_spec()["templates"][no]
    original = (TEMPLATES_DIR / spec["file"]).read_bytes()
    res = generate(no, {})
    assert structure(res.content) == structure(original)
    assert template_text(res.content) == template_text(original)
    assert res.filled == []


def test_template_4_filled_from_case():
    res = generate(4, CASE)
    text = template_text(res.content)
    for v in ("АО «Банк А»", "500100732259", "12.10.2026", "№ 41 на сумму 150 000,00 руб.", "«Оплата по договору поставки № 7»",
              "от 15.10.2026г. №115/77", "товарная накладная № 12"):
        assert v in text, v
    assert "(укажите наименование компании)" not in text
    assert "account_last" in res.left_blank  # второго счёта нет — поле осталось пустым
    spec_struct = structure((TEMPLATES_DIR / "cbr-template-04.docx").read_bytes())
    assert structure(res.content) == spec_struct


def test_template_5_never_fills_arguments():
    case = dict(CASE, applicant_name="ИП Тестов Тест Тестович", applicant_short="ИП Тестов Т. Т.",
                bank_reasons="операция имеет запутанный или необычный характер", first_appeal_date=date(2026, 10, 12))
    res = generate(5, case)
    text = template_text(res.content)
    assert "в связи с тем, что _" in text  # доводы — только сам заявитель
    assert "«12» октября 2026" in text
    assert text.count("150 000,00 руб.") == 5  # реквизиты платёжки — во всех 5 местах шаблона
    assert "операция имеет запутанный или необычный характер" in text


def test_team_templates_marked_and_factual():
    from navigator.docgen_team import MARK, cbr_complaint, reminder_13_4

    for fn, vals in ((reminder_13_4, {"bank_full_name": "АО «Банк А»", "review_due_date": "2026-11-11"}), (cbr_complaint, {})):
        d = Document(io.BytesIO(fn(vals)))
        text = "\n".join(p.text for p in d.paragraphs)
        assert text.startswith(MARK)
        assert "________" in text  # незаполненные поля остаются пустыми
        assert "в связи с тем, что" not in text  # доводы не пишем
    d = Document(io.BytesIO(reminder_13_4({"review_due_date": "2026-11-11"})))
    t = "\n".join(p.text for p in d.paragraphs)
    assert "11.11.2026" in t and "не позднее семи рабочих дней" in t


# ---- проверки до сборки (протокол красной команды 27.10, атака 7); даты — синтетика ----
def test_reminder_blocked_until_bank_deadline_expires():
    from navigator.docgen_team import DocBlocked, check_reminder

    v = {"docs_submitted_date": "2026-10-26", "review_due_date": "2026-10-27"}  # «истёк 27.10» при подаче 26.10
    with pytest.raises(DocBlocked) as e:
        check_reminder(v, today=date(2026, 10, 27))
    assert e.value.code == "bank_deadline_not_expired" and e.value.extra["review_due_date"] == "2026-11-05"
    with pytest.raises(DocBlocked):  # день истечения сам по себе ещё срок банка
        check_reminder(v, today=date(2026, 11, 5))
    out, warns = check_reminder(dict(v, refusal_date="2026-10-20", po_date="2026-10-19"), today=date(2026, 11, 6))
    assert out["review_due_date"] == "2026-11-05" and warns == ["review_due_date_recomputed"]


def test_reminder_needs_submission_date_and_letter_after_deadline():
    from navigator.docgen_team import DocBlocked, check_reminder

    with pytest.raises(DocBlocked) as e:
        check_reminder({"review_due_date": "2026-10-01"}, today=date(2026, 11, 6))
    assert e.value.code == "docs_submitted_date_missing" and e.value.status == 422
    with pytest.raises(DocBlocked):
        check_reminder({"docs_submitted_date": "2026-10-26", "letter_date": "2026-11-03"}, today=date(2026, 11, 20))


def test_reminder_contract_refusal_wording():
    from navigator.docgen_team import reminder_13_4

    d = Document(io.BytesIO(reminder_13_4({"scenario": "contract_refusal", "review_due_date": "2026-11-05"})))
    t = "\n".join(p.text for p in d.paragraphs)
    assert "в заключении договора" in t and "платёжному поручению" not in t


def test_template_5_requires_first_level():
    from navigator.docgen import check_template
    from navigator.docgen_team import DocBlocked

    with pytest.raises(DocBlocked) as e:
        check_template(5, {"docs_submitted_date": "2026-10-26"}, "operation_refusal", today=date(2026, 10, 27))
    assert e.value.code == "first_level_pending"
    with pytest.raises(DocBlocked) as e:
        check_template(5, {}, "operation_refusal", first_level_done=False, today=date(2026, 10, 27))
    assert e.value.code == "first_level_required"
    with pytest.raises(DocBlocked) as e:
        check_template(5, {}, "remote_access_restriction", today=date(2026, 10, 27))
    assert e.value.code == "template_not_for_scenario"
    assert "first_level_unverified" in check_template(5, {}, "operation_refusal", today=date(2026, 10, 27))
    ok = check_template(5, {"docs_submitted_date": "2026-10-01", "bank_answer_date": "2026-10-09", "refusal_date": "2026-09-30",
                            "po_date": "2026-09-29"}, "operation_refusal", today=date(2026, 10, 27))
    assert ok == []


def test_refusal_date_not_silently_equal_to_po_date():
    from navigator.docgen import check_template

    assert check_template(4, {"po_date": "2026-10-12"}) == ["refusal_date_missing"]
    assert check_template(4, {"po_date": "2026-10-12", "refusal_date": "2026-10-12"}) == ["refusal_date_equals_po_date"]


def test_api_contract_for_document_checks(monkeypatch):
    from fastapi.testclient import TestClient
    from navigator import docgen_team
    from navigator.app import app

    monkeypatch.setattr(docgen_team, "_today", lambda: date(2026, 10, 27))
    c = TestClient(app)
    r = c.post("/api/v1/documents/team/reminder_13_4", json={"values": {"docs_submitted_date": "2026-10-26"}})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "bank_deadline_not_expired"
    assert r.json()["detail"]["review_due_date"] == "2026-11-05" and r.json()["detail"]["message"]
    r = c.post("/api/v1/documents/team/reminder_13_4", json={"values": {"docs_submitted_date": "2026-10-01"}})
    assert r.status_code == 200 and r.headers["X-Review-Due-Date"] == "2026-10-12"
    assert "refusal_date_missing" in r.headers["X-Navigator-Warnings"]
    r = c.post("/api/v1/documents/5", json={"values": {"docs_submitted_date": "2026-10-26"}, "scenario": "operation_refusal"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "first_level_pending"
    r = c.post("/api/v1/documents/5", json={"values": {}})
    assert r.status_code == 200 and "first_level_unverified" in r.headers["X-Navigator-Warnings"].split(",")
    codes = c.get("/api/v1/documents/codes").json()
    assert {"bank_deadline_not_expired", "first_level_pending", "refusal_date_equals_po_date"} <= set(codes)
