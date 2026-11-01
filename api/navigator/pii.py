"""Маскирование ПДн на входе /api/v1/parse и /api/v1/guard (152-ФЗ, docs/sprint1/03-market.md).

Регулярки, без LLM. Маскируются: ИНН (10 и 12 цифр), номер счёта (20 цифр), номер карты (16–19 цифр,
проверка Луна), паспорт РФ рядом со словом «паспорт», дата рождения рядом с «рожд», телефон, СНИЛС, e-mail.
Не маскируются: суммы, даты, номера статей и пунктов, номера писем Банка России («ИН-01-59/98»),
номера телефонов 8-800 (линия банка, не ПДн клиента; нужны элементу E6 «канал»).

Маска сохраняет длину: каждая цифра или буква заменяется на «*». Поэтому смещения цитат (start/end),
которые валидатор считает по маскированному тексту, совпадают и с исходным текстом пользователя.
Разбор, LLM и страж получают уже маскированный текст; исходный текст дальше эндпоинта не идёт.
ФИО и адрес не маскируются: регулярками это ненадёжно (ограничение, README).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MASK = "*"

# Порядок важен: длинные шаблоны раньше коротких (счёт 20 цифр раньше ИНН 10/12).
_L = r"(?<!\d)(?<!\d[.,/-])"  # слева не цифра и не «3.», «3,» (дробь, дата, номер письма)
_R = r"(?!\d|[.,/-]\d)"  # справа то же; точка или запятая в конце предложения допустимы
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", re.UNICODE)),
    ("passport", re.compile(r"(?<=паспорт)(?:\w*[\s:,№]*(?:серия\s*)?)\d{2}[ \u00a0]?\d{2}[ \u00a0№]*(?:номер\s*)?\d{6}(?!\d)", re.IGNORECASE)),
    ("birth_date", re.compile(r"(?<=рожд)\w*[\s:,]*\d{1,2}[./]\d{1,2}[./]\d{2,4}(?!\d)", re.IGNORECASE)),
    ("account", re.compile(_L + r"\d{5}[ \u00a0]?\d{3}[ \u00a0]?\d[ \u00a0]?\d{4}[ \u00a0]?\d{7}" + _R)),
    ("snils", re.compile(_L + r"\d{3}-\d{3}-\d{3}[ \u00a0-]\d{2}" + _R)),
    ("phone", re.compile(
        r"(?:" + _L + r"(?<!\+)8|\+7)[ \u00a0-]?\(?(?!800)\d{3}\)?[ \u00a0-]?\d{3}[ \u00a0-]?\d{2}[ \u00a0-]?\d{2}" + _R)),
    ("card", re.compile(_L + r"\d{4}(?:[ \u00a0-]?\d{4}){3}(?:\d{1,3})?" + _R)),
    ("inn", re.compile(_L + r"(?:\d{12}|\d{10})" + _R + r"(?!\s*(?:руб|₽|р\.|рублей|тыс|млн))")),
    ("snils", re.compile(r"(?<=СНИЛС)[\s:№]*\d{11}(?!\d)")),
]


@dataclass
class MaskResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def masked(self) -> bool:
        return bool(self.counts)

    def meta(self) -> dict:
        return {"pii_masked": self.masked, "pii_counts": self.counts}


def _luhn(s: str) -> bool:
    """Контрольная сумма номера карты: отсекает случайные 16-значные числа."""
    digits = [int(c) for c in s if c.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            d -= 9 if d > 9 else 0
        total += d
    return total % 10 == 0


def _blank(s: str) -> str:
    return "".join(MASK if ch.isalnum() else ch for ch in s)


def mask(text: str) -> MaskResult:
    """Заменить ПДн на «*» той же длины. Возвращает маскированный текст и число замен по видам."""
    counts: dict[str, int] = {}
    out = text
    for kind, rx in _PATTERNS:
        def repl(m: re.Match, kind: str = kind) -> str:
            if kind == "card" and not _luhn(m.group(0)):
                return m.group(0)
            counts[kind] = counts.get(kind, 0) + 1
            if kind in ("passport", "birth_date"):  # слова «серия», «рождения» остаются, маскируются цифры
                return "".join(MASK if ch.isdigit() else ch for ch in m.group(0))
            return _blank(m.group(0))
        out = rx.sub(repl, out)
    assert len(out) == len(text)
    return MaskResult(out, counts)
