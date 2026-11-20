# Setup

## Prerequisites

- Azure subscription in AzureCloud or AzureUSGovernment, with **GPT-5.4**
  version **2026-03-05** quota in the selected region and deployment SKU.
  Defaults are 10 capacity units and GlobalStandard in public Azure. Capacity
  units are model-specific, not a universal TPM count. Request quota before deploying.
- The human running bootstrap needs subscription **Owner** to register providers,
  create resource groups, and delegate constrained role management. Use a
  time-limited/PIM activation where possible.
- Entra permission to create an app registration (or Application Administrator
  assistance). Azure subscription Owner does **not** imply Entra app rights.
- Repository administration rights to create GitHub environments and variables,
  and permission to configure environment reviewers. GitHub OIDC must be allowed.
- Bash, Azure CLI >= 2.64 with Bicep, GitHub CLI (`gh`), and `jq`.
  Azure Cloud Shell Bash includes these tools; authenticate `gh` there.
  Local development also needs Python 3.12 and, once the web app exists, Node 22.

No Azure credentials or application client secrets are stored in the repository.
Bootstrap creates one user-assigned GitHub identity, shared by dev/prod, with
distinct environment-bound federated credentials. API runtime has a separate identity.
For stronger environment isolation, separate deployment identities can be a future change.

## Bootstrap (human, once; safe to rerun)

Select the cloud **before** signing in. Run from the repository root in Cloud Shell:

```bash
az cloud set --name AzureCloud
az login
az account set --subscription '<subscription-id>'
gh auth login
bash scripts/bootstrap/bootstrap.sh \
  --cloud AzureCloud --location eastus2 --prefix licensing --repo OWNER/REPO
```

Use a lowercase alphanumeric prefix starting with a letter, length 2-12, and keep it
stable. Bootstrap creates `rg-<prefix>-dev`, `rg-<prefix>-prod`, and
`id-<prefix>-github` in the dev RG. Do not delete the dev RG while prod uses that identity.
Names of deployed resources derive only from resource-group ID, prefix, and environment.

Bootstrap registers all template providers, compiles the exported role IDs from
[roles.bicep](../infra/roles.bicep), and uses exactly that list for an ABAC condition
on the GitHub identity's **Role Based Access Control Administrator** role on each RG.
The condition limits both assignment writes and deletes. Contributor supplies
resource provisioning, including Cosmos SQL data-role assignments (these are
Cosmos resource operations, not Azure RBAC). Neither Owner nor unrestricted
Azure role-assignment management is granted to the automation identity.
Existing RBAC Administrator assignments are updated with the current allow-list.
Allow time for newly created identities and role assignments to propagate before deployment.

An API app registration is created/reused with single-tenant access, v2 tokens,
Application ID URI `api://<application-client-id>`, and delegated scope
`access_as_user`. If Entra permissions are missing, bootstrap prints the actual
error and exact administrator steps; Azure/GitHub setup continues. Complete those
steps and set `API_APP_ID_URI` on **both** environments before deployment. An
already-provisioned URI can be supplied as `API_APP_ID_URI` when running bootstrap.
No API or web app registration credentials are needed in this phase.

Environment variables configured on both dev and prod:

| Variable | Meaning |
| --- | --- |
| `AZURE_CLIENT_ID` | GitHub managed identity client ID |
| `AZURE_TENANT_ID` | Subscription tenant |
| `AZURE_SUBSCRIPTION_ID` | Target subscription |
| `AZURE_RESOURCE_GROUP` | Environment's resource group |
| `AZURE_LOCATION` | Explicitly selected, quota-verified region |
| `AZURE_CLOUD` | `AzureCloud` or `AzureUSGovernment` |
| `API_APP_ID_URI` | Registered API audience; may require manual Entra completion |
| `DEPLOY_PRINCIPAL_ID` | GitHub identity **object ID** for project/container roles |
| `NAME_PREFIX` | Same prefix used in bootstrap |

**Before deploying prod, add required reviewers to the `prod` GitHub environment.**
The workflow selects that environment, so GitHub enforces its approval gates.
Rerunning bootstrap does not remove existing protection rules.

## First deployment (after merge)

1. Confirm all variables above, quota, regional availability, and prod reviewers.
2. Review [dev parameters](../infra/env/dev.bicepparam) and
   [prod parameters](../infra/env/prod.bicepparam). Change `capacity`, model, SKU, or
   Search SKU deliberately if required. Neither location default guarantees availability.
3. Dispatch the Infrastructure workflow with `dev`:

   ```bash
   gh workflow run infra.yml --repo OWNER/REPO -f environment=dev
   gh run list --repo OWNER/REPO --workflow infra.yml --limit 5
   ```

   Pushes to `main` that change `infra/**` also deploy dev. Bootstrap itself does
   not deploy application infrastructure. A push-only initial deployment can
   fail before bootstrap; rerun manually after the variables/identity are ready.
4. Inspect the validation result and the what-if in the job summary. The workflow
   validates, previews, then deploys in incremental mode under stable deployment
   name `licensing-agent-dev` (or `licensing-agent-prod`).
5. Account/project capability-host provisioning can take **10-20 minutes**.
   The workflow polls both for up to 30 additional minutes and fails clearly on
   terminal failure or timeout. Do not generate new names to work around delays.
6. Verify `https://<api-fqdn>/healthz` returns 200. This is only public nginx
   with an explicit health file, **not an authenticated licensing API**. It contains
   no customer data and should not receive any. Later API containers must listen
   on **8000** and expose `/healthz`; all three probes use that contract.
7. Once dev is verified, dispatch with `prod` and approve the environment gate.

The initial image is `docker.io/library/nginx:1.28-alpine`. The infrastructure workflow
first lists Container Apps; only a confirmed absence of `api` selects that image.
Otherwise it passes the existing `api` container image to the deployment.
Authorization/network errors or an empty image fail closed. Infra deployment
does not roll the API back to the placeholder. Do not override `apiImage` with the
placeholder during a direct/manual redeployment of a real API.

## Outputs and later workflows

After Azure OIDC login and checkout:

```yaml
- uses: ./.github/actions/get-infra-outputs
  with:
    environment: dev
    resource-group: ${{ vars.AZURE_RESOURCE_GROUP }}
```

This exports `PROJECT_ENDPOINT`, `MODEL_DEPLOYMENT_NAME`, `ACR_LOGIN_SERVER`,
`CONTAINER_APP_NAME`, `API_URL`, `API_IDENTITY_CLIENT_ID`, `STORAGE_ACCOUNT_NAME`,
`COSMOS_ENDPOINT`, and `APPLICATIONINSIGHTS_CONNECTION_STRING` via `GITHUB_ENV`.
Never hard-code a deployment name in agent application code.

API permissions are Foundry User on the project, Cosmos Built-in Data Contributor
only on `appstate`, and AcrPull only on its registry. The deployment identity has
Foundry User on the project and Blob Data Reader only on `licensing-docs`.
Reader is intentionally insufficient for uploading source documents: a human with
container-scoped Blob Data Contributor must upload them using Entra authentication.
Future ingestion reads those documents. No storage keys are enabled.

Agent data access and prerequisite RBAC retain official sample 41 semantics.
The sample's Blob Owner ABAC expression restricts tag/filter actions, not every
blob operation; the prerequisite Blob Contributor is storage-account-scoped.
Do not treat that expression as isolation between projects. This deployment gives
the single project its own dependent resources. `appstate` is a separate Cosmos
database, and the API's data role cannot read `enterprise_memory`.

The App Insights connection string is obtained from the deployed component, not a
stored Azure credential. The Foundry AppInsights connection uses the official
template's connection mechanism. `LOG_CONTENT` is false; future application
telemetry must not emit customer message content. Container console logs are
routed to Log Analytics with Azure Monitor diagnostic settings (no workspace keys).

## Azure Government

Use a Government subscription and authenticate in that cloud:

```bash
az cloud set --name AzureUSGovernment
az login
az account set --subscription '<government-subscription-id>'
bash scripts/bootstrap/bootstrap.sh \
  --cloud AzureUSGovernment --location usgovvirginia --prefix licensing --repo OWNER/REPO
```

Use separate environments/repositories if maintaining public and Government
deployments concurrently: rerunning bootstrap changes the selected environment variables.
Parameter files default to `usgovvirginia` and `Standard` when `AZURE_CLOUD` is
`AzureUSGovernment`; explicit `AZURE_LOCATION` from bootstrap takes precedence.
These are starting points, **not an availability or quota promise**. Before deploying verify:

- GPT-5.4 **2026-03-05**, requested capacity, and selected deployment SKU in the region.
  Do not silently substitute another model/version if unavailable.
- Foundry AIServices project support, the sample's capability-host API version,
  current prompt Agent Service, file-search/vector-store tools, and required
  Storage/Search/Cosmos connections in the region. Resource creation alone is not
  proof that the required tools are supported.
- Container Apps consumption environment, ACR, Azure Monitor and dependent
  resources/API versions are available in that Government region/subscription.
- The public placeholder registry is reachable; replace with an approved public
  placeholder or stage an approved image if policy blocks Docker Hub.
- OIDC trust issuer/audience, Azure login cloud selection, and Entra tenant align.
  GitHub federation and `azure/login` both explicitly use
  `api://AzureADTokenExchangeUSGov` in Government and `api://AzureADTokenExchange`
  in public Azure. Any tenant-specific change must be made on both sides.
- Returned Foundry, Cosmos, Blob, ACR and telemetry endpoints belong to the
  selected cloud. Bicep uses `environment()` and resource-returned endpoints.
  ARM does not expose a Search DNS suffix: public Search is derived from the
  environment's Storage suffix, while Government explicitly selects the
  documented `search.azure.us` exception.

Do not proceed in an unsupported region. Check the current
[Government comparison and service availability](https://learn.microsoft.com/azure/azure-government/compare-azure-government-global-azure).

## Validation and sources

CI runs Python lint/format/type/tests, web checks when a package manifest exists,
Bicep build/lint, both parameter-file compilations, and Bash syntax checks, without
Azure login. Compiled ARM and parameter JSON are uploaded as `compiled-arm`.
Local tests cover automation behavior using mocked Azure/GitHub commands; no cloud
changes occur. Real ARM validation, provisioning, OIDC, and health verification
are completed by the first deployment, not by offline compilation.

Infrastructure is adapted from
[official standard-agent sample 41](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/41-standard-agent-setup)
(reviewed 2026-11-11). It preserves the prerequisite/host/post-host ordering,
removes timestamp naming, disables local/key auth, and adds application resources.
The project internal ID is returned by the RP but omitted from the published
Bicep schema; the single documented diagnostic suppression matches that sample.

Current references checked before implementation (Learn MCP was unavailable;
direct official-page access was approved):

- [Agent bring-your-own resources](https://learn.microsoft.com/azure/foundry/agents/how-to/use-your-own-resources)
- [Foundry project schema](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-04-01-preview/accounts/projects)
- [Account capability host](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-04-01-preview/accounts/capabilityhosts)
- [Project capability host](https://learn.microsoft.com/azure/templates/microsoft.cognitiveservices/2025-04-01-preview/accounts/projects/capabilityhosts)
- [Container Apps schema](https://learn.microsoft.com/azure/templates/microsoft.app/containerapps)
- [Cosmos SQL data roles](https://learn.microsoft.com/azure/templates/microsoft.documentdb/2024-11-15/databaseaccounts/sqlroleassignments)
- [Constrained role delegation](https://learn.microsoft.com/azure/role-based-access-control/delegate-role-assignments-examples)
- [Azure login](https://github.com/Azure/login/tree/v2)
