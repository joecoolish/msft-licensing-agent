"""Strict, explicit inventory and cited estimate contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[int, Field(strict=True, gt=0)]
Count = Annotated[int, Field(strict=True, ge=0)]
Product = Literal[
    "Windows Server", "RDS", "SQL Server", "SharePoint Server", "Exchange Server", "System Center"
]
Status = Literal["yes", "no", "unknown"]
Edition = Literal["Standard", "Datacenter", "Enterprise"]
LicensingModel = Literal["physical_core", "per_vm", "server_cal", "unlimited_virtualization"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LicensingContext(Model):
    agreement_type: Literal["EA", "CSP", "MPSA", "Select Plus", "OEM", "unknown"] | None
    software_assurance: dict[Product, Status | None] | None
    subscription: dict[Product, Status | None] | None


class Host(Model):
    id: str = Field(min_length=1)
    processors: Positive | None
    cores_per_processor: Positive | None
    hypervisor: Literal["none", "Hyper-V", "VMware", "other"] | None
    cluster_id: str | None


class OperatingEnvironment(Model):
    id: str = Field(min_length=1)
    host_id: str | None
    cluster_id: str | None
    kind: Literal["physical", "virtual"] | None
    virtual_cores: Positive | None
    workloads: list[Product] | None
    management_only: bool | None = None
    hardware_threads: Positive | None = None
    sql_role: Literal["active", "passive"] | None = None
    primary_ose_id: str | None = None
    failover_purpose: Literal["HA", "DR"] | None = None
    serves_data: bool | None = None
    asynchronous_manual: bool | None = None
    server_os: bool | None = Field(
        default=None, description="True for a server OS; required for System Center server MLs."
    )

    @model_validator(mode="after")
    def placement(self) -> "OperatingEnvironment":
        if self.host_id is not None and self.cluster_id is not None:
            raise ValueError("An OSE must name a host or cluster, not both")
        return self


class Population(Model):
    internal_users: Count | None
    devices: Count | None = Field(
        description="Internal accessors' devices, including shared, home, and mobile devices."
    )
    external_users: Count | None
    cal_preference: Literal["user", "device", "unknown"] | None
    # Explicitly attest that counts describe all accessors, including multiplexed access.
    complete_population: bool | None = None


class ProductDeployment(Model):
    product: Product
    edition: Edition | None
    version: str | None
    where_deployed: list[str] | None = Field(
        description="Complete list of OSE IDs. System Center targets are managed server OSEs."
    )
    licensing_model: LicensingModel | None
    # A product override is needed when its accessing population differs from the global one.
    population: Population | None = None
    enterprise_features: bool | None = None
    enterprise_population: Population | None = None
    public_content_only: bool | None = None
    cal_entitlement_active: Status | None = None
    license_mobility_through_sa: bool | None = None
    instances_per_ose: dict[str, Positive] | None = Field(
        default=None, description="Running software instances in each targeted OSE, for SE servers."
    )


class Inventory(Model):
    context: LicensingContext | None
    hosts: list[Host] | None
    os_environments: list[OperatingEnvironment] | None
    products: list[ProductDeployment] | None
    users_devices: Population | None

    @model_validator(mode="after")
    def references(self) -> "Inventory":
        for label, ids in (
            ("host", [h.id for h in self.hosts or []]),
            ("OSE", [o.id for o in self.os_environments or []]),
            ("product", [p.product for p in self.products or []]),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} IDs are not allowed")
        hosts = {h.id: h for h in self.hosts or []}
        oses = {o.id: o for o in self.os_environments or []}
        clusters = {h.cluster_id for h in hosts.values() if h.cluster_id is not None}
        for ose in oses.values():
            if ose.host_id is not None and self.hosts is not None and ose.host_id not in hosts:
                raise ValueError(f"Unknown host reference: {ose.host_id}")
            if (
                ose.cluster_id is not None
                and self.hosts is not None
                and ose.cluster_id not in clusters
            ):
                raise ValueError(f"Unknown cluster reference: {ose.cluster_id}")
            if ose.primary_ose_id is not None and self.os_environments is not None:
                if ose.primary_ose_id not in oses or ose.primary_ose_id == ose.id:
                    raise ValueError(f"Invalid primary OSE reference for {ose.id}")
        physical_hosts = [o.host_id for o in oses.values() if o.kind == "physical"]
        if len(physical_hosts) != len(set(physical_hosts)):
            raise ValueError("Only one physical OSE may be declared per host")
        for deployment in self.products or []:
            targets = deployment.where_deployed
            if targets is not None:
                if len(targets) != len(set(targets)):
                    raise ValueError("Duplicate deployment targets are not allowed")
                if self.os_environments is not None and any(t not in oses for t in targets):
                    raise ValueError(f"Unknown deployment target for {deployment.product}")
                if self.os_environments is not None and any(
                    deployment.product in (o.workloads or []) and o.id not in targets
                    for o in oses.values()
                ):
                    raise ValueError(
                        "Deployment targets omit an OSE declaring this scoped workload"
                    )
                if deployment.instances_per_ose is not None:
                    if set(deployment.instances_per_ose) != set(targets):
                        raise ValueError(
                            "instances_per_ose must cover exactly the deployment targets"
                        )
        return self


class Citation(Model):
    document: str
    section: str
    url: str


class LineItem(Model):
    product: Product
    edition: str
    license_type: str
    quantity: Count
    licensing_model: str
    rationale: str
    rule_ids: list[str]
    citations: list[Citation]
    unverified: bool


class Alternative(Model):
    product: Product
    edition: str
    line_items: list[LineItem]
    assumptions: list[str]
    warnings: list[str]
    missing_inputs: list[str]
    unverified_rules_used: list[str]


class LicenseEstimate(Model):
    line_items: list[LineItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    unverified_rules_used: list[str] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)
