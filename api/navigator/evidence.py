"""Цитаты-источники (evidence spans): поиск в исходном тексте и проверка.

Правило продукта: заполненное поле обязано опираться на дословную цитату из текста
банка. Модель (или разметчик) даёт цитату; здесь мы находим её точное место в тексте.
Смещения — индексы Python str после NFC-нормализации, end не включается.

Сравнение терпимо только к различиям, которые не меняют смысл и типичны для копирования
из PDF/мессенджеров: пробельные символы, «ё/е», виды кавычек, тире и многоточий, мягкий
перенос. Регистр и слова — строго.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TRANSLATE = str.maketrans({
    "ё": "е", "Ё": "Е",
    "«": '"', "»": '"', "„": '"', "“": '"', "”": '"',
    "‘": "'", "’": "'",
    "–": "-", "—": "-", "‑": "-", "−": "-",
    " ": " ", " ": " ", " ": " ",
})


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _canon_with_map(text: str) -> tuple[str, list[int]]:
    """Каноническая форма для поиска + карта «индекс в канонической → индекс в исходной»."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "­":  # мягкий перенос
            i += 1
            continue
        if ch == "…":
            for _ in range(3):
                out.append(".")
                idx.append(i)
            prev_space = False
            i += 1
            continue
        ch = ch.translate(_TRANSLATE)
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
            prev_space = True
            i += 1
            continue
        prev_space = False
        out.append(ch)
        idx.append(i)
        i += 1
    return "".join(out), idx


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    quote: str  # точный фрагмент исходного текста text[start:end]


def locate(text: str, quote: str, hint_start: int | None = None) -> Span | None:
    """Найти цитату в тексте. Если вхождений несколько, берётся ближайшее к hint_start
    (или первое). Возвращает None, если цитаты в тексте нет."""
    text = nfc(text)
    quote = nfc(quote).strip()
    if not quote:
        return None
    # 1) точное совпадение
    hits = [m.start() for m in re.finditer(re.escape(quote), text)]
    if hits:
        s = _closest(hits, hint_start)
        return Span(s, s + len(quote), text[s : s + len(quote)])
    # 2) совпадение в канонической форме
    ct, cmap = _canon_with_map(text)
    cq, _ = _canon_with_map(quote)
    cq = cq.strip()
    if not cq:
        return None
    chits = [m.start() for m in re.finditer(re.escape(cq), ct)]
    if not chits:
        return None
    cs = _closest(chits, None if hint_start is None else _to_canon(cmap, hint_start))
    ce = cs + len(cq)
    start = cmap[cs]
    end = cmap[ce - 1] + 1
    return Span(start, end, text[start:end])


FUZZY_MIN_SCORE = 90.0
FUZZY_MIN_LEN = 12


def locate_fuzzy(text: str, quote: str, min_score: float = FUZZY_MIN_SCORE) -> Span | None:
    """Привязать почти дословную цитату (опечатка, другой падеж) к ближайшему фрагменту текста.

    Доказательством становится только реальный фрагмент текста банка, а не слова модели.
    Порог высокий (≥90 по rapidfuzz partial_ratio), короткие цитаты не привязываются.
    """
    from rapidfuzz import fuzz

    text = nfc(text)
    ct, cmap = _canon_with_map(text)
    cq, _ = _canon_with_map(nfc(quote).strip())
    cq = cq.strip()
    if len(cq) < FUZZY_MIN_LEN or not ct:
        return None
    al = fuzz.partial_ratio_alignment(cq.lower(), ct.lower())
    if al is None or al.score < min_score:
        return None
    cs, ce = al.dest_start, al.dest_end
    if ce <= cs:
        return None
    # не обрезать слово посередине: расширяем до границ слов
    while cs > 0 and ct[cs - 1].isalnum():
        cs -= 1
    while ce < len(ct) and ct[ce].isalnum():
        ce += 1
    start, end = cmap[cs], cmap[ce - 1] + 1
    return Span(start, end, text[start:end])


def _to_canon(cmap: list[int], orig_index: int) -> int:
    for ci, oi in enumerate(cmap):
        if oi >= orig_index:
            return ci
    return len(cmap)


def _closest(hits: list[int], hint: int | None) -> int:
    if hint is None:
        return hits[0]
    return min(hits, key=lambda h: abs(h - hint))


def check_span(text: str, ev: dict) -> bool:
    """Проверка размеченной цитаты: start/end есть и text[start:end] совпадает с quote
    (в канонической форме)."""
    s, e = ev.get("start"), ev.get("end")
    if s is None or e is None or not (0 <= s < e <= len(text)):
        return False
    a, _ = _canon_with_map(nfc(text)[s:e])
    b, _ = _canon_with_map(nfc(ev["quote"]))
    return a.strip() == b.strip()


def iter_evidence(obj, path: str = "$"):
    """Обход всех массивов evidence в объекте BankRequest: yield (path, evidence_list)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            if k == "evidence" and isinstance(v, list):
                yield p, v
            else:
                yield from iter_evidence(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_evidence(v, f"{path}[{i}]")
