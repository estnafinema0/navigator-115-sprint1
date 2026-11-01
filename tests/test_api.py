import json
from pathlib import Path

from fastapi.testclient import TestClient
from navigator.app import app

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_validate_endpoint_drops_unsupported():
    g = json.loads((ROOT / "eval/gold/B1.json").read_text())["extraction"]
    text = next(json.loads(x)["text"] for x in (ROOT / "data/real/corpus.jsonl").read_text().splitlines() if '"id": "B1"' in x)
    g["appeal"]["routes"] = [{"type": "mvk", "evidence": [{"quote": "вы вправе обратиться в МВК"}]}]
    r = client.post("/api/v1/validate", json={"text": text, "extraction": g}).json()
    assert r["extraction"]["appeal"]["routes"] == []
    assert r["report"]["dropped_quotes"]


def test_parse_rules_mode_returns_grounded_fields():
    text = next(json.loads(x)["text"] for x in (ROOT / "data/real/corpus.jsonl").read_text().splitlines() if '"id": "A1"' in x)
    r = client.post("/api/v1/parse", json={"text": text, "mode": "rules"}).json()
    assert r["extraction"]["scenario"]["value"] == "operation_refusal"
    assert any(i["canonical"] == "115-ФЗ ст. 7 п. 11" for i in r["extraction"]["legal_basis"]["items"])
    assert "не гарантия" in r["disclaimer"]


def test_deadlines_endpoint():
    r = client.post("/api/v1/deadlines", json={"scenario": "operation_refusal", "events": {"bank_review_7wd": "2026-10-30"}}).json()
    t = {x["timer_id"]: x for x in r["timers"]}
    assert t["bank_review_7wd"]["due"] == "2026-11-11"  # 7 р.д. с учётом 04.11
    assert t["refusal_notice_5wd"]["status"] == "ждёт даты события"


def test_routes_and_document_endpoints():
    r = client.get("/api/v1/routes/remote_access_restriction").json()
    assert "mvk" not in {o["id"] for o in r["options"]} and r["mvk_note"]
    d = client.post("/api/v1/documents/4", json={"values": {"bank_short": "АО «Банк А»"}})
    assert d.status_code == 200 and d.content[:2] == b"PK"
    assert "refusal_date" in d.headers["X-Fields-Left-Blank"]


def test_guard_endpoint():
    r = client.post("/api/v1/guard", json={"text": "Сведения направлены в Росфинмониторинг."}).json()
    assert r["light"] == "red"
