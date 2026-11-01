"""Страж M9 v0: запрещённое ловится, полный текст получает «зелёный». Примеры — синтетика."""
from navigator.guard import check

FULL = ("Сообщаем, что банк отказал в совершении операции от 12.10.2026 на основании п. 11 ст. 7 Федерального закона № 115-ФЗ "
        "в связи с сомнительным характером операции. Вы вправе представить в банк документы об отсутствии оснований — "
        "банк рассмотрит их в течение 7 рабочих дней. Документы можно загрузить в интернет-банке. Если банк не изменит решение, "
        "вы вправе обратиться в межведомственную комиссию при Банке России.")


def test_complete_notice_is_green():
    r = check(FULL)
    assert r.light == "green", r.elements
    assert r.elements["E2"] == "norm" and r.elements["E5"] == "external"


def test_rfm_disclosure_is_red():
    r = check(FULL + " Сведения об операции направлены в Росфинмониторинг.")
    assert r.light == "red" and r.forbidden[0]["id"] == "rfm"


def test_internal_scoring_is_red():
    r = check("Ваш риск-скоринг превысил порог 0,7, поэтому операции ограничены.")
    assert {f["id"] for f in r.forbidden} == {"internal_criteria"}


def test_bypass_advice_is_red():
    for t in ("Рекомендуем разбить платежи на суммы до 100 тыс., чтобы не попадать под проверку.",
              "Измените назначение платежа, и банк пропустит операцию."):
        assert any(f["id"] == "bypass_advice" for f in check(t).forbidden), t


def test_reason_withheld_flagged():
    r = check("Банк принял решение о расторжении договора. Причины расторжения — коммерческая тайна.")
    assert any(f["id"] == "reason_withheld" for f in r.forbidden)


def test_bare_notice_is_yellow_with_gaps():
    r = check("Уважаемый клиент, выбранный Вами канал обслуживания заблокирован.")
    assert r.light == "yellow"
    assert r.elements["E2"] == "no" and r.elements["E5"] == "no" and r.elements["deadline"] == "no"


# ---- правки 27.10 по протоколу жюри (score-risk-compliance.md) и красной команды (redteam.md); фразы — синтетика ----
NO_REASON = FULL.replace(" в связи с сомнительным характером операции", "")


def _ids(t):
    return {f["id"] for f in check(t).forbidden}


def test_soft_tipping_off_is_red():
    for t in ("Сведения о ваших операциях направлены в компетентные органы.",
              "Информация об операции передана в Росфин.",
              "Сведения переданы в соответствующие органы.",
              "Сведения об операции направлены в уполномоченный государственный орган.",
              "Об операции проинформирован финансовый регулятор по линии ПОД/ФТ.",
              "Информация направлена в Rosfinmonitoring."):
        assert "rfm" in _ids(FULL + " " + t), t


def test_criteria_disclosure_is_red():
    for t in ("Операция отнесена к сомнительным: признак 1101.",
              "Основание: обналичивание более 30 % оборота.",
              "Доля налоговых отчислений ниже 0,9 % от оборота.",
              "Операция соответствует критериям подозрительности банка."):
        assert "internal_criteria" in _ids(FULL + " " + t), t


def test_regulation_375p_alone_is_review_not_red():
    r = check(FULL + " Решение принято с учётом Положения Банка России № 375-П.")
    assert not r.forbidden and r.light == "yellow" and r.review[0]["id"] == "regulation_375p"


def test_legal_threshold_art6_is_not_red():
    for t in ("Операции на сумму, равную или превышающую пороговое значение по ст. 6 115-ФЗ, подлежат обязательному контролю.",
              "Пороговое значение 1 000 000 рублей для операций, подлежащих обязательному контролю, установлено ст. 6 115-ФЗ."):
        r = check(FULL + " " + t)
        assert not r.forbidden and r.light == "green", t


def test_internal_threshold_still_red_even_near_art6():
    assert "internal_criteria" in _ids(FULL + " Ваш риск-скоринг превысил внутренний порог, ст. 6 115-ФЗ тут ни при чём.")


def test_rating_scale_is_not_scoring():
    assert not check(FULL + " Оцените качество обслуживания по 10-балльной шкале.").forbidden
    assert "internal_criteria" in _ids(FULL + " Уровень риска клиента 8 по 10-балльной шкале.")


def test_soft_bypass_advice_is_red():
    for t in ("В дальнейшем проводите суммы поменьше.",
              "Рекомендуем проводить переводы суммами до 100 тысяч рублей.",
              "В дальнейшем переводите деньги с карты на карту частями.",
              "Советуем открыть счёт в другом банке для таких операций."):
        assert "bypass_advice" in _ids(FULL + " " + t), t


def test_reason_withheld_sets_e3_no():
    for t in ("Банк не обязан сообщать причины принятого решения.", "Основания решения не подлежат разглашению.",
              "Причины указать не можем по внутренним правилам банка.", "Причины отказа банком не раскрываются."):
        r = check(FULL + " " + t)
        assert "reason_withheld" in {f["id"] for f in r.forbidden} and r.elements["E3"] == "no", t


def test_rfm_court_suspension_is_yellow_review():
    t = NO_REASON.replace("банк отказал в совершении операции от 12.10.2026",
                          "операции по счёту приостановлены по решению Росфинмониторинга")
    r = check(t)
    assert not r.forbidden and r.light == "yellow"
    assert r.review and r.review[0]["id"] == "rfm_decision" and "комплаенс" in r.review[0]["label"]


def test_rfm_transmission_in_suspension_text_still_red():
    t = "Операции приостановлены по решению Росфинмониторинга. Сведения о ваших операциях направлены в Росфинмониторинг."
    assert "rfm" in _ids(t)


def test_tax_authority_is_not_tipping_off():
    assert "rfm" not in _ids(FULL + " Сведения об открытии счёта направлены в налоговый орган.")
