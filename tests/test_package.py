"""M3: полнота пакета считается по пунктам запроса банка."""
import json
from pathlib import Path

from navigator.package import checklist

ROOT = Path(__file__).resolve().parents[1]


def test_checklist_by_request_items():
    g = json.loads((ROOT / "eval/gold/B1.json").read_text())["extraction"]
    files = ["2-НДФЛ_2025.pdf", "договор_купли-продажи_авто.pdf", "фото_кота.jpg"]
    r = checklist(g, files)
    st = {i["type"]: i["status"] for i in r["items"]}
    assert st["income_certificate"] == "есть файл"
    assert st["property_sale_proof"] == "есть файл"
    assert st["tax_return"] == "нет файла"
    assert "фото_кота.jpg" in r["unmatched_files"]
    assert r["completeness"]["total"] == 5 and 0 < r["completeness"]["pct"] < 100
    assert "152-ФЗ" in r["pdn_note"] and all("не требование вашего банка" in f["label"] for f in r["followups"])


def test_manual_binding_and_other_type():
    g = json.loads((ROOT / "eval/gold/B3.json").read_text())["extraction"]
    r = checklist(g, ["скан.pdf"], manual={0: ["скан.pdf"]})
    assert r["items"][0]["status"] == "есть файл" and r["completeness"]["pct"] == 100
