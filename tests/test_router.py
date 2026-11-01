"""M5: 0 недопустимых маршрутов на всех сценариях."""
import json
from pathlib import Path

import pytest
from navigator.router import load_routes, routes_for

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = json.loads((ROOT / "api/schema/bank_request.schema.json").read_text())["$defs"]["Scenario"]["enum"]
MVK_ONLY = {"operation_refusal", "contract_refusal", "zsk_measures_7_7", "zsk_high_cbr_only"}


def test_every_schema_scenario_has_routes():
    d = load_routes()
    assert set(SCENARIOS) == set(d["scenarios"])


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("first_level", [False, True])
def test_no_inadmissible_routes(scenario, first_level):
    res = routes_for(scenario, first_level)
    ids = [o.id for o in res.options]
    allowed = set(load_routes()["scenarios"][scenario]["allowed"])
    assert set(ids) <= allowed
    if scenario not in MVK_ONLY:
        assert "mvk" not in ids
        assert res.mvk_note or scenario in ("other", "unknown")


@pytest.mark.parametrize("scenario", ["operation_refusal", "contract_refusal", "zsk_high_cbr_only"])
def test_mvk_requires_first_level(scenario):
    mvk = next(o for o in routes_for(scenario, False).options if o.id == "mvk")
    assert not mvk.available and mvk.blocked_reason
    assert next(o for o in routes_for(scenario, True).options if o.id == "mvk").available


def test_measures_7_7_mvk_direct_with_6_months():
    mvk = next(o for o in routes_for("zsk_measures_7_7").options if o.id == "mvk")
    assert mvk.available and mvk.deadline_months == 6 and mvk.template == 7


def test_templates_for_hero_scenario():
    opts = {o.id: o for o in routes_for("operation_refusal", True).options}
    assert opts["bank_docs_after_refusal"].template == 4
    assert opts["mvk"].template == 5


def test_remote_access_restriction_explains_no_mvk():
    res = routes_for("remote_access_restriction")
    assert "4 вида решений" in res.mvk_note
    assert {"request_reasons", "paper_payments"} <= {o.id for o in res.options}
