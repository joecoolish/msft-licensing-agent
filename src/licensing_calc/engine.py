"""Deterministic rule dispatch with explicit eligibility and missing-input checks."""

from collections.abc import Callable
from dataclasses import dataclass, field

from licensing_calc.models import (
    Alternative,
    Edition,
    Host,
    Inventory,
    LicenseEstimate,
    LineItem,
    OperatingEnvironment,
    Population,
    Product,
    ProductDeployment,
)
from licensing_calc.rules import Rule, load_rules


class MissingInput(Exception):
    """A calculation cannot be completed without this fact or expert decision."""


def require(condition: bool, path: str) -> None:
    if not condition:
        raise MissingInput(path)


def packs(cores: int, pack_size: int) -> int:
    return (cores + pack_size - 1) // pack_size


@dataclass
class Calculation:
    inventory: Inventory
    deployment: ProductDeployment
    estimate: LicenseEstimate
    rules: dict[str, Rule]
    excluded: set[str] = field(default_factory=set)

    @property
    def prefix(self) -> str:
        return f"products.{self.deployment.product}"

    def rule(self, rule_id: str) -> Rule:
        rule = self.rules[rule_id]
        d = self.deployment
        require(
            d.version in rule.applies_to.versions, f"{self.prefix}.version (supported rule needed)"
        )
        require(
            d.edition in rule.applies_to.editions, f"{self.prefix}.edition (supported rule needed)"
        )
        context = self.inventory.context
        require(
            context is not None and context.agreement_type in rule.applies_to.agreements,
            "context.agreement_type (expert-reviewed rules for this agreement required)",
        )
        return rule

    def entitlement(self) -> bool:
        context = self.inventory.context
        assert context is not None
        sa = (context.software_assurance or {}).get(self.deployment.product)
        subscription = (context.subscription or {}).get(self.deployment.product)
        if sa == "yes" or subscription == "yes":
            return True
        require(
            sa == "no" and subscription == "no",
            f"context.entitlement.{self.deployment.product} (SA or subscription yes/no)",
        )
        return False

    def oses(self) -> list[OperatingEnvironment]:
        targets = self.deployment.where_deployed
        require(targets is not None, f"{self.prefix}.where_deployed")
        require(self.inventory.os_environments is not None, "os_environments")
        assert targets is not None
        lookup = {o.id: o for o in self.inventory.os_environments or []}
        result = []
        for target in targets:
            ose = lookup[target]
            require(ose.kind is not None, f"os_environments.{target}.kind")
            require(ose.workloads is not None, f"os_environments.{target}.workloads")
            require(
                self.deployment.product in (ose.workloads or []),
                f"os_environments.{target}.workloads (confirm product use)",
            )
            require(ose.host_id is not None, f"os_environments.{target}.host_id (fixed placement)")
            require(
                ose.cluster_id is None,
                f"os_environments.{target}.placement (cluster mobility requires expert plan)",
            )
            result.append(ose)
        return result

    def host_groups(self) -> list[tuple[Host, list[OperatingEnvironment]]]:
        oses = self.oses()
        require(self.inventory.hosts is not None, "hosts")
        hosts = {h.id: h for h in self.inventory.hosts or []}
        groups: dict[str, list[OperatingEnvironment]] = {}
        for ose in oses:
            assert ose.host_id is not None
            groups.setdefault(ose.host_id, []).append(ose)
        result = []
        for host_id, group in groups.items():
            host = hosts[host_id]
            require(host.processors is not None, f"hosts.{host_id}.processors")
            require(host.cores_per_processor is not None, f"hosts.{host_id}.cores_per_processor")
            require(host.hypervisor is not None, f"hosts.{host_id}.hypervisor")
            require(
                not any(o.kind == "virtual" for o in group) or host.hypervisor != "none",
                f"hosts.{host_id}.hypervisor (virtual OSE contradicts none)",
            )
            result.append((host, group))
        return result

    def population(self, enterprise: bool = False) -> Population:
        population = (
            self.deployment.enterprise_population
            if enterprise
            else self.deployment.population or self.inventory.users_devices
        )
        path = f"{self.prefix}.{'enterprise_population' if enterprise else 'population'}"
        require(population is not None, path)
        assert population is not None
        require(population.complete_population is True, f"{path}.complete_population")
        require(population.external_users is not None, f"{path}.external_users")
        return population

    def cal_count(self, population: Population) -> tuple[int, str]:
        require(
            population.cal_preference in ("user", "device"),
            f"{self.prefix}.population.cal_preference",
        )
        if population.cal_preference == "user":
            require(
                population.internal_users is not None,
                f"{self.prefix}.population.internal_users",
            )
            assert population.internal_users is not None
            return population.internal_users, "User CAL"
        require(population.devices is not None, f"{self.prefix}.population.devices")
        assert population.devices is not None
        return population.devices, "Device CAL"

    def item(
        self,
        rule_ids: list[str],
        license_type: str,
        quantity: int,
        rationale: str,
        edition: str | None = None,
    ) -> None:
        used = [self.rule(rule_id) for rule_id in rule_ids]
        self.estimate.line_items.append(
            LineItem(
                product=self.deployment.product,
                edition=edition or self.deployment.edition or "",
                license_type=license_type,
                quantity=quantity,
                licensing_model=self.deployment.licensing_model or "",
                rationale=rationale,
                rule_ids=rule_ids,
                citations=[r.source for r in used],
                unverified=any(not rule.verified for rule in used),
            )
        )
        for rule in used:
            if not rule.verified and rule.id not in self.estimate.unverified_rules_used:
                self.estimate.unverified_rules_used.append(rule.id)


def physical_with_ose_rights(c: Calculation, rule_id: str) -> None:
    rule = c.rule(rule_id)
    p = rule.parameters
    quantity = 0
    basis = []
    for host, oses in c.host_groups():
        assert host.processors is not None and host.cores_per_processor is not None
        cores = max(
            host.processors * max(host.cores_per_processor, p["min_per_processor"]),
            p["min_per_server"],
        )
        counted = 0
        for ose in oses:
            if (
                c.deployment.edition == "Standard"
                and ose.kind == "physical"
                and any(o.kind == "virtual" for o in oses)
            ):
                require(
                    ose.management_only is not None,
                    f"os_environments.{ose.id}.management_only",
                )
                if ose.management_only is True:
                    continue
            counted += 1
        stacks = (
            max(1, packs(counted, p["standard_oses"])) if c.deployment.edition == "Standard" else 1
        )
        host_packs = packs(cores, p["pack_size"]) * stacks
        quantity += host_packs
        basis.append(f"{host.id}: {cores} licensed cores per set x {stacks} sets")
    c.item(
        [rule_id],
        "2-core pack",
        quantity,
        "; ".join(basis) or "No deployed OSEs explicitly declared.",
    )


def windows_physical(c: Calculation) -> None:
    physical_with_ose_rights(c, "windows_physical")


def system_center_physical(c: Calculation) -> None:
    for ose in c.oses():
        require(
            ose.server_os is True,
            f"os_environments.{ose.id}.server_os (server MLs cannot license client OSes)",
        )
    physical_with_ose_rights(c, "system_center_physical")


def basic_cal(c: Calculation, rule_id: str) -> None:
    rule = c.rule(rule_id)
    if not c.oses():
        c.item([rule_id], "User CAL", 0, "No deployed OSEs explicitly declared.", "Standard")
        return
    population = c.population()
    require(
        population.external_users == 0,
        f"{c.prefix}.external_access_plan (CAL/External Connector/exemption review)",
    )
    count, license_type = c.cal_count(population)
    c.item(
        [rule_id],
        license_type,
        count * rule.parameters["per_accessor"],
        "Gross CAL requirement for the complete declared accessing population, not concurrency.",
        "Not edition-specific",
    )


def windows_cal(c: Calculation) -> None:
    basic_cal(c, "windows_cal")


def rds_cal(c: Calculation) -> None:
    basic_cal(c, "rds_cal")


def sql_physical(c: Calculation) -> None:
    rule = c.rule("sql_physical")
    quantity = 0
    basis = []
    for host, oses in c.host_groups():
        assert host.processors is not None and host.cores_per_processor is not None
        require(
            all(o.sql_role == "active" for o in oses),
            f"{c.prefix}.sql_role (passive physical failover requires expert review)",
        )
        if c.deployment.edition == "Standard":
            require(
                all(o.kind == "physical" for o in oses),
                f"{c.prefix}.licensing_model (Standard physical cores do not cover virtual OSEs)",
            )
        cores = host.processors * max(
            host.cores_per_processor, rule.parameters["min_per_processor"]
        )
        # Enterprise's physical-core OSE allowance is numerically equal to core licenses.
        cores = max(cores, len(oses))
        quantity += packs(cores, rule.parameters["pack_size"])
        basis.append(f"{host.id}: {cores} core licenses")
    c.item(["sql_physical"], "2-core pack", quantity, "; ".join(basis) or "No deployed OSEs.")


def vm_demand(c: Calculation, ose: OperatingEnvironment) -> int:
    rule = c.rule("sql_vm")
    require(ose.kind == "virtual", f"os_environments.{ose.id}.kind (virtual required)")
    require(ose.virtual_cores is not None, f"os_environments.{ose.id}.virtual_cores")
    require(ose.hardware_threads is not None, f"os_environments.{ose.id}.hardware_threads")
    assert ose.virtual_cores is not None and ose.hardware_threads is not None
    return max(ose.virtual_cores, ose.hardware_threads, rule.parameters["min_per_vm"])


def sql_failover(c: Calculation) -> None:
    rule = c.rule("sql_failover")
    oses = c.oses()
    passive = [o for o in oses if o.sql_role == "passive"]
    if not passive:
        return
    if not c.entitlement():
        return
    require(
        c.deployment.license_mobility_through_sa is False,
        f"{c.prefix}.license_mobility_through_sa (must be false for failover waiver)",
    )
    lookup = {o.id: o for o in oses}
    used: dict[tuple[str, str], int] = {}
    for ose in passive:
        require(ose.primary_ose_id in lookup, f"os_environments.{ose.id}.primary_ose_id")
        assert ose.primary_ose_id is not None
        primary = lookup[ose.primary_ose_id]
        require(primary.sql_role == "active", f"os_environments.{primary.id}.sql_role")
        require(ose.serves_data is False, f"os_environments.{ose.id}.serves_data (must be false)")
        require(ose.failover_purpose is not None, f"os_environments.{ose.id}.failover_purpose")
        purpose = ose.failover_purpose
        assert purpose is not None
        if purpose == "DR":
            require(
                ose.asynchronous_manual is True,
                f"os_environments.{ose.id}.asynchronous_manual (DR must be asynchronous/manual)",
            )
        require(
            packs(vm_demand(c, ose), c.rule("sql_vm").parameters["pack_size"])
            <= packs(vm_demand(c, primary), c.rule("sql_vm").parameters["pack_size"]),
            f"os_environments.{ose.id}.capacity (exceeds primary entitlement; review required)",
        )
        key = (primary.id, purpose)
        used[key] = used.get(key, 0) + 1
        maximum = rule.parameters["ha_oses" if purpose == "HA" else "onprem_dr_oses"]
        require(
            used[key] <= maximum,
            f"os_environments.{ose.id}.failover_plan (exceeds on-prem allowance)",
        )
        c.excluded.add(ose.id)


def sql_vm(c: Calculation) -> None:
    rule = c.rule("sql_vm")
    require(c.entitlement(), f"{c.prefix}.entitlement (per-VM requires SA/subscription)")
    oses = c.oses()
    for ose in oses:
        require(ose.sql_role is not None, f"os_environments.{ose.id}.sql_role")
    sql_failover(c)
    quantity = sum(
        packs(vm_demand(c, ose), rule.parameters["pack_size"])
        for ose in oses
        if ose.id not in c.excluded
    )
    c.item(["sql_vm"], "2-core pack", quantity, "Each active virtual OSE is rounded independently.")
    if c.excluded:
        c.item(
            ["sql_failover"],
            "Additional failover core licenses",
            c.rule("sql_failover").parameters["waived_licenses"],
            f"Eligible passive on-prem OSEs: {', '.join(sorted(c.excluded))}. "
            "Primary entitlement and all declared failover conditions checked.",
        )


def sql_unlimited(c: Calculation) -> None:
    rule = c.rule("sql_unlimited")
    require(c.entitlement(), f"{c.prefix}.entitlement (unlimited requires SA/subscription)")
    quantity = 0
    for host, _ in c.host_groups():
        assert host.processors is not None and host.cores_per_processor is not None
        cores = host.processors * max(
            host.cores_per_processor, rule.parameters["min_per_processor"]
        )
        quantity += packs(cores, rule.parameters["pack_size"])
    c.item(
        ["sql_unlimited"],
        "2-core pack",
        quantity,
        "Enterprise with SA-equivalent entitlement licenses all physical cores; unlimited OSEs.",
    )


def sql_server_cal(c: Calculation) -> None:
    rule = c.rule("sql_server_cal")
    oses = c.oses()
    require(
        all(o.sql_role == "active" for o in oses),
        f"{c.prefix}.sql_role (Server/CAL passive failover requires expert review)",
    )
    # Validate population before emitting either part of this licensing model.
    population = c.population()
    require(population.external_users == 0, f"{c.prefix}.external_access_plan")
    count, license_type = c.cal_count(population)
    c.item(
        ["sql_server_cal"],
        "Server",
        len(oses) * rule.parameters["per_ose"],
        "One Server license per SQL OSE; multiple instances in that OSE are permitted.",
    )
    c.item(
        ["sql_server_cal"],
        license_type,
        count * rule.parameters["per_accessor"],
        "All declared users/devices accessing SQL, directly or indirectly, across these OSEs.",
        "Not edition-specific",
    )


def se_entitlement(c: Calculation) -> None:
    require(c.entitlement(), f"{c.prefix}.entitlement (SE requires active SA/subscription)")
    if c.deployment.product == "Exchange Server":
        assert c.inventory.context is not None
        sa = (c.inventory.context.software_assurance or {}).get("Exchange Server")
        require(
            sa == "yes",
            f"{c.prefix}.software_assurance (Microsoft 365 Extended Use Rights need expert review)",
        )
    require(
        c.deployment.cal_entitlement_active == "yes",
        f"{c.prefix}.cal_entitlement_active (confirm active SE CAL entitlement)",
    )


def se_server(c: Calculation, rule_id: str) -> None:
    rule = c.rule(rule_id)
    se_entitlement(c)
    oses = c.oses()
    instances = c.deployment.instances_per_ose
    require(instances is not None, f"{c.prefix}.instances_per_ose")
    assert instances is not None
    c.item(
        [rule_id],
        "Server",
        sum(instances[o.id] for o in oses) * rule.parameters["per_instance"],
        "One license per explicitly declared running server software instance.",
    )


def sharepoint_server(c: Calculation) -> None:
    se_server(c, "sharepoint_server")


def exchange_server(c: Calculation) -> None:
    se_server(c, "exchange_server")


def se_cal(c: Calculation, rule_id: str) -> None:
    rule = c.rule(rule_id)
    se_entitlement(c)
    c.oses()
    d = c.deployment
    require(d.enterprise_features is not None, f"{c.prefix}.enterprise_features")
    public = False
    if d.product == "SharePoint Server":
        require(d.public_content_only is not None, f"{c.prefix}.public_content_only")
        public = d.public_content_only is True
    if public:
        c.item(
            [rule_id],
            "User CAL",
            rule.parameters["public_cals"],
            "All content explicitly declared publicly available; CAL waiver applies.",
            "Standard",
        )
        return
    population = c.population()
    count, license_type = c.cal_count(population)
    enterprise_count = 0
    if d.enterprise_features:
        enterprise = c.population(enterprise=True)
        enterprise_count, enterprise_type = c.cal_count(enterprise)
        require(
            enterprise_type == license_type and enterprise_count <= count,
            f"{c.prefix}.enterprise_population (must be a subset with the same CAL metric)",
        )
        if d.product == "Exchange Server":
            require(
                enterprise.external_users == 0,
                f"{c.prefix}.enterprise_population.external_users (external additive CAL review)",
            )
    assert population.external_users is not None
    c.item(
        [rule_id],
        license_type,
        count * rule.parameters["per_accessor"]
        + population.external_users
        * rule.parameters[
            "external_cals" if d.product == "SharePoint Server" else "external_base_cals"
        ],
        "Base CALs for internal accessors; external base access is included with the server.",
        "Standard",
    )
    if d.enterprise_features:
        c.item(
            [rule_id],
            f"Enterprise {license_type}",
            enterprise_count * rule.parameters["per_accessor"],
            "Additive Enterprise CALs only for the declared subset accessing Enterprise features.",
            "Enterprise",
        )


def sharepoint_cal(c: Calculation) -> None:
    se_cal(c, "sharepoint_cal")


def exchange_cal(c: Calculation) -> None:
    se_cal(c, "exchange_cal")


LOGIC: dict[str, Callable[[Calculation], None]] = {
    function.__name__: function
    for function in (
        windows_physical,
        windows_cal,
        rds_cal,
        sql_physical,
        sql_vm,
        sql_server_cal,
        sql_unlimited,
        sql_failover,
        sharepoint_server,
        sharepoint_cal,
        exchange_server,
        exchange_cal,
        system_center_physical,
    )
}


def selected_rules(d: ProductDeployment) -> list[str]:
    if d.product == "Windows Server" and d.licensing_model == "physical_core":
        return ["windows_physical", "windows_cal"]
    if d.product == "RDS" and d.licensing_model == "server_cal":
        return ["rds_cal"]
    if d.product == "System Center" and d.licensing_model == "physical_core":
        return ["system_center_physical"]
    if d.product == "SQL Server":
        return {
            "physical_core": ["sql_physical"],
            "per_vm": ["sql_vm"],
            "server_cal": ["sql_server_cal"],
            "unlimited_virtualization": ["sql_unlimited"],
        }.get(d.licensing_model or "", [])
    if d.licensing_model == "server_cal":
        if d.product == "SharePoint Server":
            return ["sharepoint_server", "sharepoint_cal"]
        if d.product == "Exchange Server":
            return ["exchange_server", "exchange_cal"]
    return []


def calculate(inventory: Inventory) -> LicenseEstimate:
    """Return gross requirements, never purchase deltas or an entitlement certification."""
    rules = load_rules()
    if set(rules) != set(LOGIC):
        raise ValueError("YAML rule IDs and Python logic registry differ")
    result = LicenseEstimate(
        assumptions=[
            "Gross requirements, not net purchases; existing licenses/CAL equivalents not netted.",
            "Declared populations include all direct and indirect access; placements are fixed.",
            "November 2026 EA snapshot; no downgrade, mobility, or historical rights inferred.",
        ],
        warnings=["Guidance only; not a quote or legal entitlement determination."],
    )
    if inventory.context is None:
        result.missing_inputs.append("context")
    if inventory.products is None:
        result.missing_inputs.append("products")
    if result.missing_inputs:
        result.warnings.append("Incomplete estimate: context/products are unknown.")
        return result
    for deployment in inventory.products or []:
        c = Calculation(inventory, deployment, result, rules)
        if deployment.where_deployed == []:
            result.assumptions.append(f"{deployment.product}: explicitly no deployed OSEs.")
            continue
        ids = selected_rules(deployment)
        if not ids:
            result.missing_inputs.append(f"{c.prefix}.licensing_model (supported model required)")
        for rule_id in ids:
            try:
                LOGIC[rule_id](c)
            except MissingInput as error:
                result.missing_inputs.append(str(error))
        if deployment.product in ("SQL Server", "SharePoint Server", "Exchange Server"):
            result.warnings.append(
                f"{deployment.product}: underlying Windows Server licensing/CALs, if applicable, "
                "are separate; include that product explicitly."
            )
        if deployment.product == "RDS":
            result.warnings.append(
                "RDS CALs are additive; Windows Server base licensing/CALs are separate."
            )
    result.missing_inputs = list(dict.fromkeys(result.missing_inputs))
    if result.missing_inputs:
        result.warnings.append(
            "Incomplete estimate: missing inputs prevent a complete bill of materials."
        )
    if result.unverified_rules_used:
        result.warnings.append(
            "UNVERIFIED licensing rules used: " + ", ".join(result.unverified_rules_used)
        )
    return result


def compare_editions(
    inventory: Inventory,
    product: Product,
    editions: tuple[Edition, ...] = ("Standard", "Datacenter"),
) -> LicenseEstimate:
    """Compare explicit editions by quantities; alternatives are separate complete evaluations."""
    result = calculate(inventory)
    if not any(d.product == product for d in inventory.products or []):
        result.missing_inputs.append(f"products.{product} (comparison target required)")
        result.warnings.append("Comparison incomplete: the target product is not declared.")
        return result
    for edition in editions:
        candidate = inventory.model_copy(deep=True)
        for deployment in candidate.products or []:
            if deployment.product == product:
                deployment.edition = edition
        estimate = calculate(candidate)
        result.alternatives.append(
            Alternative(
                product=product,
                edition=edition,
                line_items=[i for i in estimate.line_items if i.product == product],
                assumptions=estimate.assumptions,
                warnings=estimate.warnings,
                missing_inputs=estimate.missing_inputs,
                unverified_rules_used=estimate.unverified_rules_used,
            )
        )
    return result
