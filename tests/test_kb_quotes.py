"""Каждая норма с verified: true подтверждена дословной цитатой из файла первоисточника в kb/sources/.

Сравнение терпимо только к переносам строк и пробелам (тексты извлечены из PDF).
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "kb" / "sources"


def flat(s: str) -> str:
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    s = s.replace("‑", "-").replace("ё", "е")
    return re.sub(r"\s+", " ", s)


def verified_items():
    timers = yaml.safe_load((ROOT / "kb/norms/timers.yaml").read_text())["timers"]
    for tid, t in timers.items():
        if t.get("verified"):
            yield f"timer:{tid}", t["source"]["file"], t["quote"]
    routes = yaml.safe_load((ROOT / "kb/norms/routes.yaml").read_text())["routes"]
    for rid, r in routes.items():
        src = r.get("source") or {}
        if src.get("verified"):
            yield f"route:{rid}", src["file"], src["quote"]


@pytest.mark.parametrize("item_id,file,quote", list(verified_items()))
def test_quote_present_in_source(item_id, file, quote):
    assert quote, f"{item_id}: verified без цитаты"
    text = flat((SOURCES / file).read_text(encoding="utf-8"))
    assert flat(quote) in text, f"{item_id}: цитата не найдена в {file}"
