# Licensing rules

## Calculator contract

`licensing_calc` is pure Python. It reads packaged local YAML/JSON only; it has
no network, Azure SDK, LLM, clock-dependent selection, or price calculations.
`calculate(Inventory)` returns a Pydantic `LicenseEstimate`:

```python
from licensing_calc import Inventory, calculate, compare_editions

inventory = Inventory.model_validate(inventory_json)
estimate = calculate(inventory)
comparison = compare_editions(inventory, "Windows Server")
```

Use the full inventory in any [golden scenario](../evals/scenarios/calc/) as an
input example. Omitted **required** model properties are validation errors;
explicit `null` means unknown. Counts never default to zero, SA never defaults
to absent, and a CAL preference is never selected on the customer's behalf.
The enumerated `unknown` agreement/SA/CAL values are also treated as unknown.
Optional specialized facts default only to `None`, never to a licensing choice.
Invalid counts, extra properties, duplicate IDs, duplicate product families, and
broken/ambiguous references raise a Pydantic validation error, not a success-shaped estimate.

An empty deployment list explicitly means no deployment. An unknown deployment
list blocks the calculation. A product family appears once per inventory;
mixed editions/versions for one family require a reviewed allocation plan.
Do not split the same users or hardware across separate calculator calls and
then blindly sum their results.

### Input interpretation

- Host processor/core counts describe uniform physical processors, not vCPUs.
- `os_environments` contains physical and virtual OSEs. A physical OSE has its own
  ID and points to its host. Product `where_deployed` lists **OSE IDs**, not host IDs.
- `workloads` confirms which scoped products run in each OSE. For System Center,
  targets mean **managed server OSEs**, not installation of the management server.
  `server_os=true` is required; client OSes need a separate management model.
  An OSE that declares a scoped workload cannot be omitted from that product's targets.
- `management_only` must be explicit when excluding a physical OSE that exists
  alongside virtual OSEs. Unknown is not treated as management-only.
- Cluster-only placement returns `missing_inputs`: dynamic mobility, placement
  maxima, reassignment, maintenance, and failover cannot be inferred. Host-pinned
  placement in a cluster is calculated only as that declared fixed snapshot.
- Global `users_devices` is the complete population accessing each scoped product
  unless that product supplies a population override. `complete_population=true`
  attests to all direct/indirect access (including multiplexing), not concurrency.
  Supply a separate RDS population when only a subset uses RDS.
- Device counts cover every device used by **internal** accessors, including
  home/mobile devices. External access is modeled separately. User/device metrics
  are never compared as prices.
- `software_assurance` and `subscription` are product-keyed `yes/no/unknown` maps.
  A subscription `yes` means an expert has confirmed qualifying rights for that
  exact product/model, not merely that the organization has some subscription.
- SE requires active server entitlement and `cal_entitlement_active=yes` for all
  applicable base/additive CALs. Enterprise CAL features and their accessor
  subset are explicit and independent of server edition.
  Exchange's automated model additionally requires active SA; Microsoft 365
  Extended Use Rights are deferred rather than counted as traditional server licenses.
- SharePoint SE uses `edition=Standard` to label its base server license; there
  is no separately computed Enterprise server SKU. `enterprise_features=true`
  adds Enterprise CALs only for `enterprise_population`.
- SharePoint `public_content_only=true` is an explicit statement that **all**
  scoped content is publicly available; only then is the public CAL waiver applied.
- `instances_per_ose` states running instances for Exchange/SharePoint, rather
  than guessing one instance per VM. SQL Standard's product-specific term
  permits multiple SQL instances within its one licensed Server/CAL OSE.
- SQL per-VM core licensing needs mapped `hardware_threads` as well as virtual
  cores. No containers, outsourcing, or cloud entitlements are inferred.
- SQL `sql_role` distinguishes active from passive. The automated per-VM failover
  waiver supports only declared on-prem HA/DR replicas paired to an active
  primary, no data serving/active workloads, entitlement no larger than the
  primary, no License Mobility through SA, and asynchronous/manual DR.
  A zero-quantity failover line documents the waiver and cites its rule.

### Output interpretation

All line items carry rationale, rule IDs, citations, and an `unverified` flag.
The flag is true when any rule applied to that line is unverified, including
zero-quantity waiver lines and edition alternatives. It is derived by the
calculator, not supplied by the caller; estimate-level warnings and
`unverified_rules_used` remain the disclosure of all unverified rules used.
Core requirements are returned as **2-core pack counts**, rounded **per host**
or **per VM** before summing, not as individual core license counts. Standard stacks full sets for
OSE rights; Datacenter physical-core counts do not depend on virtual OSE count.
CALs are shared across the scoped servers, not multiplied by their number.
Enterprise CALs are additive, not a replacement for base CALs.

The estimate is a **gross requirement**, not net purchases: existing perpetual
licenses, CAL suites, Microsoft 365 equivalents, and other entitlements are not
deducted. Underlying Windows Server licensing is a separate product input.
External Windows/RDS/SQL access needs a reviewed access plan rather than an
automatic External Connector selection. SharePoint/Exchange external **base**
access is included with server licenses; Exchange external additional features
are deferred for review.

Independent known parts (for example Windows core packs with an unknown CAL
population) may be returned alongside `missing_inputs`. Every incomplete result
warns that it is not a complete bill of materials. No quantity is produced for a
blocked rule. `unverified_rules_used` lists only rules actually used for returned
line items, and a warning states that they are unverified.

`compare_editions` retains the primary estimate and adds separate alternatives,
each with its own quantities, warnings, missing inputs, and verification flags.
The default comparison is Standard/Datacenter for Windows Server or System Center.
SQL can explicitly compare `("Standard", "Enterprise")` under the selected
licensing model; unsupported combinations remain incomplete, not zero-cost options.
It does not compare unlike units or recommend based on cost.

## Seed scope and source dates

There are 13 seeded rules in five product-family YAML files. They cover Windows
Server/RDS 2025, SQL Server 2025, System Center 2025, and SharePoint/Exchange SE.
All are **unverified**. Their sources are official Microsoft Product Terms,
SharePoint licensing guidance, and Exchange licensing guidance/FAQs.

`effective_date: 2026-11-01` identifies the **November 2026 current-terms snapshot**
used by this seed, not a claim that the rule first came into force that date.
Sources were consulted on 2026-11-11. Live URLs change: before expert approval,
archive the applicable official guide/dated Product Terms in the knowledge store
and confirm the agreement's actual effective date. Historical use, other agreement
programs, and other versions are not inferred from the current EA snapshot.
See the [backlog](rules-backlog.md) for exclusions.

## Expert review and verification

1. Replace the literal `@<licensing-reviewers>` CODEOWNERS placeholders with the
   organization's real GitHub user/team and require their PR review in branch
   protection. **The placeholder is not a functioning review gate.**
2. Select the customer's exact agreement/program, product version/edition,
   license acquisition date, SA/subscription/CAL status, and deployment model.
   Read the corresponding official dated Product Terms and guide. Guides do
   not override the customer's agreement/Product Terms.
3. Check every YAML parameter against the cited section, including pack size,
   processor/server/VM minimums, virtualization rights, access requirements,
   and exceptions. Check applicability and the meaning of `effective_date`.
   Do not copy document text into executable logic.
4. Review the matching Python function (the rule ID is its registry key) and
   helpers. Ensure no hidden licensing thresholds or unsupported entitlement
   assumptions were added. Add missing cases to the backlog instead of guessing.
5. Inspect a unit case for the rule, the golden expected outputs, boundary and
   incomplete-input cases, and Hypothesis properties. Golden expectations must be
   independently derived by the reviewer, never accepted just because code emits them.
6. In a reviewed PR, set `verified: true`, `verified_by` to the reviewer/team
   identifier, and `verified_on` to the ISO review date. The rule schema refuses
   a true flag without a named reviewer/date. Set scenario `expert_reviewed: true`
   only after independently reviewing that scenario and update the seed-specific
   tests deliberately. Record the source snapshot/review evidence in the PR.
7. Any source, parameter, applicability, or logic change requires re-review:
   return affected rules to `verified: false` and clear reviewer/date until approval.
   Never assume a previously reviewed version covers newly introduced behavior.

## Validation and schema generation

```bash
python -m pip install -e '.[dev]'
python -m licensing_calc.schema
ruff check .
ruff format --check .
mypy
pytest
```

The generated [tool argument schema](../agent/tools/calculate_licenses.schema.json)
is `Inventory.model_json_schema()` serialized deterministically. It is the function
tool's **parameters schema**, not a full agent/tool registration envelope; later
agent deployment wraps it. A test fails on any stale schema. This phase does not
claim strict-mode compatibility with a specific Foundry tool API.

Runtime YAML is validated against [rules.schema.json](../src/licensing_calc/rules.schema.json)
and typed models. Only fixed Python functions in a checked registry execute; YAML
cannot import or execute arbitrary Python. Schema/rule corruption raises an
explicit exception. The 10 seed scenarios have `expert_reviewed: false`;
passing tests are **not** licensing-expert approval.
