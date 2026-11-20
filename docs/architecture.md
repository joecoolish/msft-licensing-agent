# Architecture

The initial infrastructure contains a Foundry AIServices account/project and
model deployment; project-managed standard-agent Storage, Search, and Cosmos;
workspace-based Application Insights; and ACR plus a Container Apps API host.
See [setup](setup.md) for deployment ordering, role boundaries, and cloud details.

The pure Python calculator now loads schema-validated local YAML and returns
cited gross requirements with missing inputs and unverified-rule disclosures.
See [rules](rules.md) for its explicit supported scope and review requirements.

Later phases implement the current Foundry prompt agent, Entra-authenticated
FastAPI API, and Power Apps React code app. No agent or customer-facing application
is implemented yet.
