"""M3 (P1): чек-лист пакета — «пункт запроса → файлы» и полнота по пунктам запроса.

Полнота считается только относительно пунктов самого запроса банка, а не «эталона банка».
Сопоставление файла с пунктом — по названию файла и словарю типа документа (детерминированно);
пользователь всегда может привязать файл вручную. Подсказки типовых дозапросов — из открытых
источников, с пометкой «не требование вашего банка».
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .typecheck import DOC_STEMS

PDN_NOTE = ("Прикладывайте то, что запрошено. Документы с персональными данными третьих лиц сверх запроса "
            "создают риск по 152-ФЗ: их лучше не отправлять без необходимости.")

# Типовые дозапросы из открытых источников. Ссылки на конкретные отзывы: context/research/v2/client-journey.md,
# разд. 2, шаг 4 и «10 требований», п. 4; запросы ВТБ и Точки: bank-request.md, разд. 1.2; corpus-requests.md, B3.
TYPICAL_FOLLOWUPS = [
    {"text": "Документы за весь запрошенный период, а не за его часть", "source": "публичные отзывы клиентов Т-Банка (banki.ru)"},
    {"text": "Выписки по счетам в других банках", "source": "публичные тексты запросов ВТБ и Точки из корпуса Навигатора"},
    {"text": "КУДиР или налоговая декларация", "source": "публичные отзывы клиентов банков (banki.ru, vc.ru, pikabu)"},
    {"text": "Подтверждение места деятельности (аренда, фото рабочего места)", "source": "публичный отзыв клиента Точки"},
]
FOLLOWUP_LABEL = "может понадобиться: из открытых памяток и отзывов, не требование вашего банка"


@dataclass
class ItemStatus:
    index: int
    type: str
    raw: str
    files: list[str] = field(default_factory=list)
    status: str = "нет файла"  # «есть файл» / «нет файла»


# Для имён файлов «ндфл» неоднозначен: 2-НДФЛ — справка о доходах, 3-НДФЛ — декларация.
FILE_STEMS = {**DOC_STEMS, "income_certificate": ("2 ндфл", "справк", "доход"), "tax_return": ("декларац", "3 ндфл", "усн")}


def _matches(doc_type: str, filename: str) -> bool:
    name = filename.lower().replace("ё", "е").replace("_", " ").replace("-", " ")
    stems = FILE_STEMS.get(doc_type, ())
    return any(s.replace("ё", "е") in name for s in stems)


def checklist(extraction: dict, files: list[str], manual: dict[int, list[str]] | None = None) -> dict:
    """files — имена загруженных файлов; manual — ручные привязки {номер пункта: [файлы]}."""
    manual = manual or {}
    items = []
    used: set[str] = set()
    for i, it in enumerate(extraction.get("requested_items") or []):
        st = ItemStatus(i, it["type"], it["raw"])
        st.files = list(manual.get(i, []))
        if not st.files and it["type"] != "other":
            st.files = [f for f in files if _matches(it["type"], f)]
        st.status = "есть файл" if st.files else "нет файла"
        used.update(st.files)
        items.append(st)
    n = len(items)
    done = sum(1 for s in items if s.files)
    return {
        "items": [asdict(s) for s in items],
        "completeness": {"done": done, "total": n, "pct": round(100 * done / n) if n else None},
        "unmatched_files": [f for f in files if f not in used],
        "followups": [{**f, "label": FOLLOWUP_LABEL} for f in TYPICAL_FOLLOWUPS],
        "pdn_note": PDN_NOTE,
        "disclaimer": "Полнота проверена по пунктам текста запроса; это не гарантия, что банк не запросит ещё.",
    }
