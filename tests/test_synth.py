"""Синтетика: каждый эталон проходит валидатор без потерь и помечен как синтетика."""
import json
from collections import Counter
from pathlib import Path

from navigator.validator import validate

ROOT = Path(__file__).resolve().parents[1]
RECS = [json.loads(x) for x in (ROOT / "data/synthetic/synth-v1.jsonl").read_text().splitlines() if x]


def test_synthetic_labeled_and_sized():
    assert len(RECS) >= 100
    assert all(r["synthetic"] is True and r["label"] == "синтетика" for r in RECS)
    assert len({r["id"] for r in RECS}) == len(RECS)


def test_every_scenario_has_at_least_5():
    c = Counter(r["scenario"] for r in RECS)
    assert len(c) == 12 and min(c.values()) >= 5, c


def test_gold_fully_grounded():
    for r in RECS:
        out, rep = validate(r["gold"], r["text"])
        assert rep.ok and not rep.dropped_quotes and not rep.dropped_fields and not rep.recomputed, (r["id"], rep.to_dict())
        assert out == r["gold"], r["id"]
