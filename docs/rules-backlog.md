# Rules backlog

These are deliberately not inferred from the November 2026 EA seed. A missing
quantity or incomplete result must not be interpreted as no license requirement.
There are no speculative numeric rules for these items.

| Area | Missing evidence or behavior before implementation |
| --- | --- |
| CSP, MPSA, Select Plus, OEM | Obtain/review official program-specific terms, acquisition/transfer restrictions, dates, and entitlement applicability. Current EA terms alone do not establish these rights. |
| Earlier versions | Dated Product Terms/guides and downgrade/upgrade rights, SQL legacy Enterprise Server/CAL and historical core factors. |
| Windows virtual-OSE licensing | Official current terms found (8-core minimum); defer until subscription/SA, CAL coverage, server-farm reassignment, and per-customer minimums from the complete guide are expert-reviewed. No partial rule seeded. |
| System Center virtual-OSE licensing | Official current terms found; defer entitlement, server-farm mobility and managed-OS applicability review. |
| Cluster allocation/mobility | Maximum placement/HA/migration plan per host, reassignment restrictions, server farms and SA-dependent mobility; do not assume even distribution or license only the busiest host. |
| External Windows/RDS/SQL access | External Connector versus CAL eligibility, server coverage, identities/device inventory, indirect access, and exemptions. No single global external-device count is assumed. |
| CAL exemptions/equivalents | Public web/HPC workloads, administration-only access, Entra sync, licensed-server access, suites/Microsoft 365 equivalents, RDS equivalents. No netting of owned rights. |
| Exchange SE subscription equivalents | Official Exchange FAQ describes qualifying Microsoft 365 Extended Use Rights. Validate all-user coverage, program, server/CAL equivalency and subscription eligibility before calculating net server requirements. Traditional license plus SA is the supported server model. |
| Exchange external additive features | Product Terms require base plus additive CALs; collect per-user/per-device identities and feature access for external users. |
| SharePoint mixed public/private sites | Per-accessor/site scopes needed before applying partial public-content waivers. Current waiver requires all declared content to be public. |
| SE entitlement alternatives | Source snapshots for each subscription/program, all server/base/additive CAL entitlement coverage; hybrid/free recipient-management rights are not automatic. |
| SQL physical/Server+CAL failover | Current official rights found; defer primary/replica license allocation, CAL SA coverage and physical-core pairing. No waiver applied in these models. |
| SQL Azure DR, tests, maintenance | Official terms found but this calculator is on-prem only. No Azure replica waiver, brief testing overlap, or maintenance operation inference. |
| SQL containers/outsourcing | Mapped hardware threads, container/OSE boundaries, unlimited-container benefit, Authorized Outsourcers and License Mobility through SA need explicit topology/entitlement models. |
| System Center client management | Current terms found; separate user/client OSE model and managed-OS classifications required. Server MLs must not be used for clients. |
| Mixed editions/versions and current holdings | Per-host/per-OSE allocation and cross-version CAL compatibility needed to avoid duplicate counts across separate requests. |
| Effective-date history | Archive dated official Product Terms/guides, acquisition dates and amendments before supporting an as-of date other than the seed snapshot. |

Primary official references for review:

- [Windows Server terms](https://www.microsoft.com/licensing/terms/productoffering/WindowsServerStandardDatacenterEssentials/EAEAS)
- [SQL Server terms](https://www.microsoft.com/licensing/terms/productoffering/SQLServer/EAEAS)
- [System Center Server terms](https://www.microsoft.com/licensing/terms/productoffering/SystemCenterServer/EAEAS)
- [SharePoint Server terms](https://www.microsoft.com/licensing/terms/productoffering/SharePointServer/EAEAS)
- [Exchange Server terms](https://www.microsoft.com/licensing/terms/productoffering/ExchangeServer/EAEAS)
- [Exchange licensing FAQ](https://www.microsoft.com/en-ca/microsoft-365/exchange/microsoft-exchange-licensing-faq-email-for-business)
