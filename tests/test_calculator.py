import json
import socket
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from pydantic import ValidationError as InputValidationError

from licensing_calc import Inventory, calculate, compare_editions
from licensing_calc.engine import LOGIC
from licensing_calc.models import LicenseEstimate, Product
from licensing_calc.rules import RuleFamily, load_rules
from licensing_calc.schema import inventory_schema

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = sorted((ROOT / "evals/scenarios/calc").glob("*.yaml"))


def inventory_data(
    product: Product = "Windows Server",
    edition: str = "Standard",
    licensing_model: str = "physical_core",
    vm_count: int = 2,
    processors: int = 2,
    cores: int = 8,
) -> dict[str, Any]:
    return {
        "context": {
            "agreement_type": "EA",
            "software_assurance": {product: "yes"},
            "subscription": {product: "no"},
        },
        "hosts": [
            {
                "id": "h1",
                "processors": processors,
                "cores_per_processor": cores,
                "hypervisor": "Hyper-V",
                "cluster_id": None,
            }
        ],
        "os_environments": [
            {
                "id": f"v{i}",
                "host_id": "h1",
                "cluster_id": None,
                "kind": "virtual",
                "virtual_cores": 4,
                "hardware_threads": 4,
                "workloads": [product],
                "sql_role": "active",
                "server_os": True,
            }
            for i in range(vm_count)
        ],
        "products": [
            {
                "product": product,
                "edition": edition,
                "version": "SE" if product in ("SharePoint Server", "Exchange Server") else "2025",
                "where_deployed": [f"v{i}" for i in range(vm_count)],
                "licensing_model": licensing_model,
                "cal_entitlement_active": "yes",
                "enterprise_features": False,
                "public_content_only": False,
                "instances_per_ose": {f"v{i}": 1 for i in range(vm_count)},
            }
        ],
        "users_devices": {
            "internal_users": 25,
            "devices": 12,
            "external_users": 0,
            "cal_preference": "user",
            "complete_population": True,
        },
    }


def run(data: dict[str, Any]) -> LicenseEstimate:
    return calculate(Inventory.model_validate(data))


def quantity(estimate: LicenseEstimate, license_type: str = "2-core pack") -> int:
    return sum(i.quantity for i in estimate.line_items if i.license_type == license_type)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda p: p.stem)
def test_golden_scenario(scenario: Path) -> None:
    document = yaml.safe_load(scenario.read_text(encoding="utf-8"))
    assert document["expert_reviewed"] is False
    result = run(document["inventory"])
    expected = document["expected"]
    assert [
        {
            "product": i.product,
            "edition": i.edition,
            "license_type": i.license_type,
            "quantity": i.quantity,
        }
        for i in result.line_items
    ] == expected["line_items"]
    assert result.missing_inputs == expected["missing_inputs"]
    assert sorted(result.unverified_rules_used) == sorted(expected["unverified_rules_used"])
    assert all(i.rationale and i.citations and i.rule_ids for i in result.line_items)
    assert all(i.unverified for i in result.line_items)
    assert any("UNVERIFIED" in warning for warning in result.warnings)
    assert LicenseEstimate.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("scenario_name", ["01-windows-standard-rds.yaml", "08-sql-failover.yaml"])
@pytest.mark.parametrize("verification", ["none", "some", "all"])
def test_line_item_verification_tracks_only_its_applied_rules(
    monkeypatch: pytest.MonkeyPatch, scenario_name: str, verification: str
) -> None:
    rules = {key: rule.model_copy(deep=True) for key, rule in load_rules().items()}
    for rule_id, rule in rules.items():
        if verification == "all" or (
            verification == "some" and rule_id in {"windows_physical", "sql_vm"}
        ):
            rules[rule_id] = rule.model_validate(
                {
                    **rule.model_dump(),
                    "verified": True,
                    "verified_by": "test-reviewer",
                    "verified_on": "2026-11-20",
                }
            )
    monkeypatch.setattr("licensing_calc.engine.load_rules", lambda: rules)
    scenario = yaml.safe_load((ROOT / "evals/scenarios/calc" / scenario_name).read_text())
    result = run(scenario["inventory"])
    assert result.line_items and not result.missing_inputs
    assert any(item.unverified for item in result.line_items) is (verification != "all")
    assert any(not item.unverified for item in result.line_items) is (verification != "none")
    for item in result.line_items:
        assert item.unverified is any(not rules[rule_id].verified for rule_id in item.rule_ids)
    assert set(result.unverified_rules_used) == {
        rule_id
        for item in result.line_items
        for rule_id in item.rule_ids
        if not rules[rule_id].verified
    }
    assert LicenseEstimate.model_validate_json(result.model_dump_json()) == result


def test_ten_golden_scenarios_cover_every_rule() -> None:
    assert len(SCENARIOS) == 10
    exercised = {
        rule_id
        for path in SCENARIOS
        for rule_id in yaml.safe_load(path.read_text())["expected"]["unverified_rules_used"]
    }
    assert exercised == set(LOGIC) == set(load_rules())


@pytest.mark.parametrize("rule_id", sorted(LOGIC))
def test_each_rule_has_a_cited_executable_unit_case(rule_id: str) -> None:
    for path in SCENARIOS:
        scenario = yaml.safe_load(path.read_text())
        if rule_id in scenario["expected"]["unverified_rules_used"]:
            result = run(scenario["inventory"])
            items = [i for i in result.line_items if rule_id in i.rule_ids]
            assert items
            assert all(load_rules()[rule_id].source in i.citations for i in items)
            assert not result.missing_inputs
            return
    pytest.fail(f"No executable case for {rule_id}")


def test_generated_agent_schema_is_current() -> None:
    assert (ROOT / "agent/tools/calculate_licenses.schema.json").read_text(
        encoding="utf-8"
    ) == inventory_schema()
    schema = json.loads(inventory_schema())
    Draft202012Validator(schema).validate(inventory_data())
    assert set(schema["required"]) == {
        "context",
        "hosts",
        "os_environments",
        "products",
        "users_devices",
    }


def test_all_seed_rules_are_unverified_with_complete_provenance() -> None:
    rules = load_rules()
    assert rules
    for rule in rules.values():
        assert not rule.verified
        assert rule.verified_by is None and rule.verified_on is None
        assert rule.effective_date.isoformat() == "2026-11-01"
        assert rule.source.url.startswith("https://www.microsoft.com/")
        assert rule.source.document and rule.source.section and rule.notes


def test_schema_rejects_bad_rule_provenance_and_verification() -> None:
    schema = json.loads((ROOT / "src/licensing_calc/rules.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    family = yaml.safe_load((ROOT / "src/licensing_calc/rules/windows_server.yaml").read_text())
    validator.validate(family)
    bad = deepcopy(family)
    bad["rules"][0]["verified"] = True
    with pytest.raises(ValidationError):
        validator.validate(bad)
    bad = deepcopy(family)
    bad["rules"][0]["source"]["url"] = "https://example.org/invented"
    with pytest.raises(ValidationError):
        validator.validate(bad)
    bad = deepcopy(family)
    bad["rules"][0]["effective_date"] = "not-a-date"
    with pytest.raises(ValidationError):
        validator.validate(bad)


def test_omitted_verification_defaults_to_false_never_approved() -> None:
    schema = json.loads((ROOT / "src/licensing_calc/rules.schema.json").read_text())
    family = yaml.safe_load((ROOT / "src/licensing_calc/rules/windows_server.yaml").read_text())
    del family["rules"][0]["verified"]
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(family)
    assert RuleFamily.model_validate(family).rules[0].verified is False


@pytest.mark.parametrize("field", ["processors", "cores_per_processor"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "8"])
def test_invalid_core_counts_are_not_coerced(field: str, value: object) -> None:
    data = inventory_data()
    data["hosts"][0][field] = value
    with pytest.raises(InputValidationError):
        Inventory.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_host",
        "duplicate_ose",
        "duplicate_product",
        "unknown_host",
        "unknown_ose",
        "ambiguous_placement",
        "duplicate_target",
        "bad_instances",
    ],
)
def test_invalid_topology_is_rejected(mutation: str) -> None:
    data = inventory_data()
    if mutation == "duplicate_host":
        data["hosts"].append(deepcopy(data["hosts"][0]))
    elif mutation == "duplicate_ose":
        data["os_environments"].append(deepcopy(data["os_environments"][0]))
    elif mutation == "duplicate_product":
        data["products"].append(deepcopy(data["products"][0]))
    elif mutation == "unknown_host":
        data["os_environments"][0]["host_id"] = "unknown"
    elif mutation == "unknown_ose":
        data["products"][0]["where_deployed"] = ["unknown"]
    elif mutation == "ambiguous_placement":
        data["os_environments"][0]["cluster_id"] = "cluster"
    elif mutation == "duplicate_target":
        data["products"][0]["where_deployed"] = ["v0", "v0"]
    else:
        data["products"][0]["instances_per_ose"] = {"unknown": 1}
    with pytest.raises(InputValidationError):
        Inventory.model_validate(data)


@pytest.mark.parametrize("field", ["processors", "cores_per_processor", "hypervisor"])
def test_unknown_host_fact_blocks_core_quantity(field: str) -> None:
    data = inventory_data()
    data["hosts"][0][field] = None
    result = run(data)
    assert any(field in missing for missing in result.missing_inputs)
    assert not any(i.license_type == "2-core pack" for i in result.line_items)
    assert "windows_physical" not in result.unverified_rules_used


@pytest.mark.parametrize("agreement", [None, "unknown", "CSP", "MPSA", "Select Plus", "OEM"])
def test_unsourced_agreements_are_not_assumed_to_be_ea(agreement: str | None) -> None:
    data = inventory_data()
    data["context"]["agreement_type"] = agreement
    result = run(data)
    assert result.missing_inputs
    assert not result.line_items


def test_unknown_inventory_and_absence_are_distinct() -> None:
    unknown = Inventory(
        context=None, hosts=None, os_environments=None, products=None, users_devices=None
    )
    assert calculate(unknown).missing_inputs == ["context", "products"]
    data = inventory_data(vm_count=0)
    result = run(data)
    assert not result.line_items and not result.missing_inputs
    assert not result.unverified_rules_used


def test_missing_vm_list_is_not_zero_vms() -> None:
    data = inventory_data()
    data["products"][0]["where_deployed"] = None
    data["products"][0]["instances_per_ose"] = None
    result = run(data)
    assert result.missing_inputs and not result.line_items


def test_cluster_placement_requires_a_plan() -> None:
    data = inventory_data()
    data["hosts"][0]["cluster_id"] = "c1"
    for ose in data["os_environments"]:
        ose["host_id"] = None
        ose["cluster_id"] = "c1"
    result = run(data)
    assert not result.line_items
    assert any("fixed placement" in m for m in result.missing_inputs)


def test_standard_counts_productive_physical_ose_but_excludes_management_only() -> None:
    data = inventory_data()
    physical = {
        "id": "physical",
        "host_id": "h1",
        "cluster_id": None,
        "kind": "physical",
        "virtual_cores": None,
        "workloads": ["Windows Server"],
        "management_only": False,
    }
    data["os_environments"].append(physical)
    data["products"][0]["where_deployed"].append("physical")
    data["products"][0]["instances_per_ose"] = None
    assert quantity(run(data)) == 16
    physical["management_only"] = True
    assert quantity(run(data)) == 8
    physical["management_only"] = None
    assert quantity(run(data)) == 0
    assert any("management_only" in m for m in run(data).missing_inputs)
    data["products"][0]["edition"] = "Datacenter"
    assert quantity(run(data)) == 8
    assert not run(data).missing_inputs


def test_rounding_is_per_host_and_per_vm_not_global() -> None:
    data = inventory_data("SQL Server", licensing_model="per_vm")
    for ose in data["os_environments"]:
        ose["virtual_cores"] = 5
        ose["hardware_threads"] = 5
    assert quantity(run(data)) == 6
    data = inventory_data("Windows Server", processors=1, cores=17)
    data["hosts"].append({**data["hosts"][0], "id": "h2"})
    data["os_environments"][1]["host_id"] = "h2"
    assert quantity(run(data)) == 18


@pytest.mark.parametrize(
    "sa,subscription",
    [
        ("unknown", "no"),
        (None, "no"),
        ("no", "unknown"),
        ("no", "no"),
    ],
)
def test_sql_vm_entitlement_must_be_confirmed(sa: str | None, subscription: str) -> None:
    data = inventory_data("SQL Server", licensing_model="per_vm")
    data["context"]["software_assurance"]["SQL Server"] = sa
    data["context"]["subscription"]["SQL Server"] = subscription
    result = run(data)
    assert result.missing_inputs and not result.line_items


def test_subscription_can_supply_sql_vm_rights() -> None:
    data = inventory_data("SQL Server", licensing_model="per_vm")
    data["context"]["software_assurance"]["SQL Server"] = "no"
    data["context"]["subscription"]["SQL Server"] = "yes"
    assert not run(data).missing_inputs
    assert quantity(run(data)) == 4


def test_sql_standard_physical_does_not_license_vms() -> None:
    result = run(inventory_data("SQL Server"))
    assert not result.line_items
    assert any("do not cover virtual" in m for m in result.missing_inputs)


def test_sql_enterprise_without_sa_has_finite_ose_allowance() -> None:
    data = inventory_data("SQL Server", edition="Enterprise", processors=1, cores=4, vm_count=5)
    data["context"]["software_assurance"]["SQL Server"] = "no"
    assert quantity(run(data)) == 3


@pytest.mark.parametrize("field", ["virtual_cores", "hardware_threads", "sql_role"])
def test_sql_vm_missing_inputs_do_not_produce_quantities(field: str) -> None:
    data = inventory_data("SQL Server", licensing_model="per_vm")
    data["os_environments"][0][field] = None
    result = run(data)
    assert not result.line_items and result.missing_inputs


@pytest.mark.parametrize(
    "field,value",
    [
        ("serves_data", True),
        ("serves_data", None),
        ("asynchronous_manual", False),
        ("asynchronous_manual", None),
        ("virtual_cores", 8),
        ("primary_ose_id", None),
        ("failover_purpose", None),
    ],
)
def test_failover_conditions_are_not_assumed(field: str, value: object) -> None:
    data = yaml.safe_load((ROOT / "evals/scenarios/calc/08-sql-failover.yaml").read_text())[
        "inventory"
    ]
    data["os_environments"][2][field] = value
    result = run(data)
    assert result.missing_inputs and not result.line_items


def test_duplicate_ha_replicas_exceed_allowance() -> None:
    data = yaml.safe_load((ROOT / "evals/scenarios/calc/08-sql-failover.yaml").read_text())[
        "inventory"
    ]
    data["os_environments"][2]["failover_purpose"] = "HA"
    result = run(data)
    assert not result.line_items
    assert any("exceeds on-prem allowance" in m for m in result.missing_inputs)


def test_failover_can_use_the_full_primary_pack_allocation() -> None:
    data = yaml.safe_load((ROOT / "evals/scenarios/calc/08-sql-failover.yaml").read_text())[
        "inventory"
    ]
    data["os_environments"][0]["virtual_cores"] = 5
    data["os_environments"][2]["virtual_cores"] = 6
    result = run(data)
    assert not result.missing_inputs
    assert quantity(result) == 3
    assert quantity(result, "Additional failover core licenses") == 0


@pytest.mark.parametrize("mobility", [None, True])
def test_failover_cannot_assume_license_mobility_eligibility(mobility: bool | None) -> None:
    data = yaml.safe_load((ROOT / "evals/scenarios/calc/08-sql-failover.yaml").read_text())[
        "inventory"
    ]
    data["products"][0]["license_mobility_through_sa"] = mobility
    result = run(data)
    assert not result.line_items
    assert any("license_mobility_through_sa" in m for m in result.missing_inputs)


def test_rule_schema_rejects_missing_or_zero_denominators() -> None:
    schema = json.loads((ROOT / "src/licensing_calc/rules.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    family = yaml.safe_load((ROOT / "src/licensing_calc/rules/windows_server.yaml").read_text())
    family["rules"][0]["parameters"]["pack_size"] = 0
    with pytest.raises(ValidationError):
        validator.validate(family)
    del family["rules"][0]["parameters"]["pack_size"]
    with pytest.raises(ValidationError):
        validator.validate(family)


def test_runtime_uses_yaml_parameters_not_hidden_minimums(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = {key: rule.model_copy(deep=True) for key, rule in load_rules().items()}
    rules["windows_physical"].parameters["min_per_server"] = 32
    monkeypatch.setattr("licensing_calc.engine.load_rules", lambda: rules)
    assert quantity(run(inventory_data())) == 16


@pytest.mark.parametrize(
    "field,value",
    [
        ("complete_population", None),
        ("cal_preference", "unknown"),
        ("internal_users", None),
        ("external_users", 1),
    ],
)
def test_cal_unknowns_are_not_guessed(field: str, value: object) -> None:
    data = inventory_data()
    data["users_devices"][field] = value
    result = run(data)
    assert result.missing_inputs
    assert not any(i.license_type.endswith("CAL") for i in result.line_items)
    assert quantity(result) == 8


def test_cal_population_is_not_multiplied_by_server_count() -> None:
    data = inventory_data("SQL Server", licensing_model="server_cal", vm_count=8)
    result = run(data)
    assert quantity(result, "Server") == 8
    assert quantity(result, "User CAL") == 25


@pytest.mark.parametrize("product", ["SharePoint Server", "Exchange Server"])
def test_se_requires_server_and_cal_entitlement(product: Product) -> None:
    data = inventory_data(product, licensing_model="server_cal")
    data["products"][0]["cal_entitlement_active"] = "unknown"
    result = run(data)
    assert result.missing_inputs and not result.line_items


def test_enterprise_exchange_server_does_not_imply_enterprise_cals() -> None:
    data = inventory_data("Exchange Server", edition="Enterprise", licensing_model="server_cal")
    result = run(data)
    assert quantity(result, "Server") == 2
    assert quantity(result, "User CAL") == 25
    assert not any(i.license_type.startswith("Enterprise") for i in result.line_items)


def test_exchange_subscription_equivalency_is_not_a_server_license_assumption() -> None:
    data = inventory_data("Exchange Server", licensing_model="server_cal")
    data["context"]["software_assurance"]["Exchange Server"] = "no"
    data["context"]["subscription"]["Exchange Server"] = "yes"
    result = run(data)
    assert not result.line_items
    assert any("Extended Use Rights" in m for m in result.missing_inputs)


@pytest.mark.parametrize("server_os", [None, False])
def test_system_center_needs_server_os_classification(server_os: bool | None) -> None:
    data = inventory_data("System Center")
    data["os_environments"][0]["server_os"] = server_os
    result = run(data)
    assert not result.line_items
    assert any("server_os" in m for m in result.missing_inputs)


def test_declared_workload_cannot_be_omitted_from_deployment_targets() -> None:
    data = inventory_data()
    data["products"][0]["where_deployed"] = ["v0"]
    data["products"][0]["instances_per_ose"] = {"v0": 1}
    with pytest.raises(InputValidationError, match="omit an OSE"):
        Inventory.model_validate(data)


def test_sharepoint_public_and_external_access_waivers() -> None:
    data = inventory_data("SharePoint Server", licensing_model="server_cal")
    data["users_devices"]["external_users"] = 200
    assert quantity(run(data), "User CAL") == 25
    data["products"][0]["public_content_only"] = True
    result = run(data)
    assert not result.missing_inputs
    assert quantity(result, "User CAL") == 0
    assert quantity(result, "Server") == 2


def test_exchange_external_enterprise_access_requires_review() -> None:
    data = inventory_data("Exchange Server", licensing_model="server_cal")
    data["products"][0]["enterprise_features"] = True
    data["products"][0]["enterprise_population"] = {
        **data["users_devices"],
        "internal_users": 5,
        "external_users": 2,
    }
    result = run(data)
    assert any("external additive CAL" in m for m in result.missing_inputs)
    assert not any(i.license_type.endswith("CAL") for i in result.line_items)


def test_compare_editions_preserves_inventory_and_disclosures() -> None:
    inventory = Inventory.model_validate(inventory_data(vm_count=5))
    before = inventory.model_dump()
    result = compare_editions(inventory, "Windows Server")
    assert inventory.model_dump() == before
    assert [a.edition for a in result.alternatives] == ["Standard", "Datacenter"]
    assert [
        sum(i.quantity for i in a.line_items if i.license_type == "2-core pack")
        for a in result.alternatives
    ] == [24, 8]
    assert all(a.unverified_rules_used and a.warnings for a in result.alternatives)
    assert all(item.unverified for a in result.alternatives for item in a.line_items)


def test_unknown_comparison_target_returns_missing_inputs() -> None:
    result = compare_editions(Inventory.model_validate(inventory_data()), "System Center")
    assert result.missing_inputs and not result.alternatives


def test_no_network_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Calculator attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    load_rules.cache_clear()
    assert quantity(run(inventory_data())) == 8


@given(
    product=st.sampled_from(["Windows Server", "System Center"]),
    initial=st.integers(1, 128),
    increment=st.integers(0, 128),
    processors=st.integers(1, 8),
    vms=st.integers(1, 30),
)
@settings(max_examples=80)
def test_more_physical_cores_never_reduces_licenses(
    product: Product, initial: int, increment: int, processors: int, vms: int
) -> None:
    data = inventory_data(product, cores=initial, processors=processors, vm_count=vms)
    before = run(data)
    data["hosts"][0]["cores_per_processor"] += increment
    after = run(data)
    assert not before.missing_inputs and not after.missing_inputs
    assert quantity(after) >= quantity(before)


@given(initial=st.integers(1, 128), increment=st.integers(0, 128))
def test_more_virtual_cores_never_reduces_sql_licenses(initial: int, increment: int) -> None:
    data = inventory_data("SQL Server", licensing_model="per_vm", vm_count=1)
    data["os_environments"][0]["virtual_cores"] = initial
    before = run(data)
    data["os_environments"][0]["virtual_cores"] += increment
    after = run(data)
    assert not before.missing_inputs and not after.missing_inputs
    assert quantity(after) >= quantity(before)


@given(
    initial=st.integers(1, 128),
    increment=st.integers(0, 128),
    model=st.sampled_from(["physical_core", "unlimited_virtualization"]),
)
def test_more_sql_physical_cores_never_reduces_licenses(
    initial: int, increment: int, model: str
) -> None:
    data = inventory_data("SQL Server", edition="Enterprise", cores=initial, licensing_model=model)
    before = run(data)
    data["hosts"][0]["cores_per_processor"] += increment
    after = run(data)
    assert not before.missing_inputs and not after.missing_inputs
    assert quantity(after) >= quantity(before)


@given(initial=st.integers(0, 100000), increment=st.integers(0, 100000))
def test_more_users_never_reduces_cals(initial: int, increment: int) -> None:
    data = inventory_data()
    data["users_devices"]["internal_users"] = initial
    before = run(data)
    data["users_devices"]["internal_users"] += increment
    after = run(data)
    assert not before.missing_inputs and not after.missing_inputs
    assert quantity(after, "User CAL") >= quantity(before, "User CAL")


@given(vms=st.integers(1, 100), cores=st.integers(1, 128))
def test_datacenter_core_count_does_not_depend_on_vm_count(vms: int, cores: int) -> None:
    for product in ("Windows Server", "System Center"):
        before = run(inventory_data(product, edition="Datacenter", cores=cores, vm_count=1))
        after = run(inventory_data(product, edition="Datacenter", cores=cores, vm_count=vms))
        assert not before.missing_inputs and not after.missing_inputs
        assert quantity(before) == quantity(after)
