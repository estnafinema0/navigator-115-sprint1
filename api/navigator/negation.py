"""Отрицание в пределах предложения: «обжалование в МВК не предусмотрено» не маршрут в МВК.

Список узкий намеренно: «если не согласны, обратитесь в МВК» отрицанием маршрута не считается.
Протокол жюри (риск и комплаенс), раунд 2, 27.10.2026.
"""
from __future__ import annotations

import re

NEG = re.compile(
    r"не\s+предусм\w*|не\s+является|не\s+являются|не\s+рассматрива\w*|не\s+рассмотр\w*|не\s+может\s+быть\s+обжалова\w*|"
    r"не\s+подлеж\w*|недопустим\w*|нельзя|не\s+вправе\s+обращ\w*|не\s+применя\w*|не\s+применим\w*|не\s+обжалу\w*",
    re.IGNORECASE,
)


def sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Границы предложения вокруг [start, end): точка, «!», «?», перевод строки; точка в дате не граница."""
    left = start
    while left > 0 and not (text[left - 1] in "!?\n" or (text[left - 1] == "." and not text[left:left + 1].isdigit())):
        left -= 1
    right = end
    while right < len(text) and not (text[right] in "!?\n" or (text[right] == "." and not text[right + 1:right + 2].isdigit())):
        right += 1
    return left, right


def negated(text: str, start: int, end: int) -> bool:
    a, b = sentence_span(text, start, end)
    return NEG.search(text[a:b]) is not None
