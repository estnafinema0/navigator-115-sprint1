"""Генераторы документов M5 по шаблонам Банка России (docx).

Принципы (PROMPT.md, разд. 6.2, M5):
- в документ попадают только поля кейса (реквизиты, даты, номера) — факты от пользователя
  или из текста банка;
- доводы, пояснения и экономический смысл операций пишет сам заявитель — для них правил нет;
- структура DOCX совпадает с шаблоном ЦБ: заменяются только пустые поля внутри runs,
  абзацы и таблицы не добавляются и не удаляются;
- незаполненные поля остаются пустыми, и генератор возвращает их список;
- check_template: до сборки проверяет, что документ уместен по фактам дела (шаблон № 5, МВК, только
  после первого уровня п. 13.4; даты отказа и платёжки не путаются). Коды — docgen_team.DOC_CODES.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "kb" / "templates" / "cbr-templates.yaml"
TEMPLATES_DIR = ROOT / "kb" / "sources" / "cbr" / "templates"

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]


@lru_cache(maxsize=1)
def load_spec() -> dict:
    return yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))


def fmt_value(v, fmt: str | None) -> str:
    if v is None:
        return ""
    if isinstance(v, str) and fmt in ("date", "date_quoted"):
        try:
            v = date.fromisoformat(v)
        except ValueError:
            return v
    if isinstance(v, date):
        if fmt == "date_quoted":
            return f"«{v.day:02d}» {MONTHS[v.month - 1]} {v.year}"
        return v.strftime("%d.%m.%Y")
    return str(v)


def iter_paragraphs(doc) -> list[Paragraph]:
    """Абзацы в порядке чтения: тело и таблицы (включая вложенные)."""
    out: list[Paragraph] = []

    def walk(parent_el, parent):
        for el in parent_el.iterchildren():
            tag = el.tag.rsplit("}", 1)[-1]
            if tag == "p":
                out.append(Paragraph(el, parent))
            elif tag == "tbl":
                t = Table(el, parent)
                for row in t.rows:
                    seen = set()
                    for cell in row.cells:
                        if id(cell._tc) in seen:  # объединённые ячейки
                            continue
                        seen.add(id(cell._tc))
                        walk(cell._tc, cell)
            elif tag == "sdt":
                content = el.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sdtContent")
                if content is not None:
                    walk(content, parent)

    walk(doc.element.body, doc)
    return out


def replace_span(p: Paragraph, start: int, end: int, new: str) -> None:
    """Заменить символы [start, end) текста абзаца, сохранив форматирование остальных runs."""
    pos = 0
    first = True
    for run in p.runs:
        t = run.text
        r0, r1 = pos, pos + len(t)
        pos = r1
        if r1 <= start or r0 >= end:
            continue
        a, b = max(start, r0) - r0, min(end, r1) - r0
        if first:
            run.text = t[:a] + new + t[b:]
            first = False
        else:
            run.text = t[:a] + t[b:]


@dataclass
class DocResult:
    template_no: int
    content: bytes
    filled: list[str] = field(default_factory=list)
    left_blank: list[str] = field(default_factory=list)


def generate(template_no: int, values: dict) -> DocResult:
    spec = load_spec()["templates"][template_no]
    doc = Document(str(TEMPLATES_DIR / spec["file"]))
    paragraphs = iter_paragraphs(doc)
    held: dict[str, str] = {}  # маркер → исходное пустое поле (временно, чтобы правила не путались)
    filled, blank = [], []
    for rule in spec["fields"]:
        rx = re.compile(rule["pattern"])
        key = rule["key"]
        value = fmt_value(values.get(key), rule.get("fmt"))
        done = False
        for p in paragraphs:
            while True:
                m = rx.search(p.text)
                if m is None:
                    break
                if value:
                    replace_span(p, m.start("blank"), m.end("blank"), value)
                else:
                    token = f"\u27e6{len(held)}\u27e7"
                    held[token] = m.group("blank")
                    replace_span(p, m.start("blank"), m.end("blank"), token)
                done = True
                if not rule.get("all"):
                    break
            if done and not rule.get("all"):
                break
        if done:
            (filled if value else blank).append(key)
    for p in paragraphs:  # вернуть незаполненные поля
        while "\u27e6" in p.text:
            m = re.search("\u27e6\\d+\u27e7", p.text)
            if m is None:
                break
            replace_span(p, m.start(), m.end(), held[m.group(0)])
    doc.core_properties.comments = (
        f"{spec['source']}. Поля заполнены Навигатором-115 из данных пользователя; "
        "доводы и пояснения заявитель пишет сам. Проверьте документ перед отправкой. Это не юридическая консультация."
    )
    buf = io.BytesIO()
    doc.save(buf)
    return DocResult(template_no, buf.getvalue(), sorted(set(filled)), sorted(set(blank) - set(filled)))


def check_template(template_no: int, values: dict, scenario: str | None = None,
                   first_level_done: bool | None = None, today: date | None = None) -> list[str]:
    """Проверка до сборки. Возвращает коды предупреждений или бросает DocBlocked (docgen_team).

    Шаблон № 5 (МВК по отказу в операции) — только после первого уровня (п. 13.4 ст. 7 115-ФЗ, kb/norms/routes.yaml):
    - есть дата ответа банка (bank_answer_date) — первый уровень пройден;
    - есть дата представления документов, срок банка не истёк и ответа нет — отказ first_level_pending;
    - срок истёк, ответа нет — предупреждение bank_answer_missing;
    - клиент явно указал first_level_done=false — отказ first_level_required;
    - данных нет — документ собирается с предупреждением first_level_unverified.
    """
    from .docgen_team import DocBlocked, _as_date, _today, bank_review_due, refusal_date_warnings
    from .router import routes_for

    warnings: list[str] = []
    if template_no == 5:
        if scenario:
            opts = [o for o in routes_for(scenario, first_level_done=True).options if o.template == 5]
            if not opts:
                raise DocBlocked("template_not_for_scenario", scenario=scenario)
        today = today or _today()
        answered = _as_date(values.get("bank_answer_date")) or _as_date(values.get("bank_answer_letter_date"))
        due = bank_review_due(values)
        if answered is None:
            if due is not None and today <= due:
                raise DocBlocked("first_level_pending", review_due_date=due.isoformat())
            if due is not None:
                warnings.append("bank_answer_missing")
            elif first_level_done is False:
                raise DocBlocked("first_level_required")
            else:
                warnings.append("first_level_unverified")
        if values.get("bank_reasons"):
            warnings.append("bank_reasons_inserted")
    if template_no in (4, 5):
        warnings += refusal_date_warnings(values)
    return warnings


def template_text(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in iter_paragraphs(doc))
