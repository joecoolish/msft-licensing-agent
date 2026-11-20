#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/bootstrap/bootstrap.sh --cloud AzureCloud|AzureUSGovernment --location REGION --prefix PREFIX --repo OWNER/REPO"
}
cloud=AzureCloud
location=
prefix=
repo=
while (($#)); do
  case "$1" in
    --cloud|--location|--prefix|--repo)
      [[ $# -ge 2 && -n "$2" ]] || { usage >&2; exit 2; }
      case "$1" in
        --cloud) cloud=$2 ;;
        --location) location=$2 ;;
        --prefix) prefix=$2 ;;
        --repo) repo=$2 ;;
      esac
      shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "$cloud" == AzureCloud || "$cloud" == AzureUSGovernment ]] || { usage >&2; exit 2; }
[[ "$prefix" =~ ^[a-z][a-z0-9]{1,11}$ && "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && -n "$location" ]] ||
  { usage >&2; exit 2; }
for tool in az gh jq; do command -v "$tool" >/dev/null || { echo "Missing tool: $tool" >&2; exit 1; }; done
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -f "$tmp/roles.json" "$tmp/app.json" "$tmp/entra-error"; rmdir "$tmp"' EXIT

az cloud set --name "$cloud"
az account show --output none || { echo "Run az login in $cloud and select the target subscription first." >&2; exit 1; }
gh auth status
subscription=$(az account show --query id -o tsv)
tenant=$(az account show --query tenantId -o tsv)
az bicep version >/dev/null || az bicep install
az bicep build --file "$root/infra/roles.bicep" --outfile "$tmp/roles.json"
role_ids=$(jq -er '.variables.roles | to_entries | map(.value) | sort | join(", ")' "$tmp/roles.json")
[[ -n "$role_ids" ]] || { echo "No template roles found; refusing unconstrained delegation." >&2; exit 1; }
condition="((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$role_ids})) AND ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/delete'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {$role_ids}))"

providers=(Microsoft.CognitiveServices Microsoft.Storage Microsoft.Search Microsoft.DocumentDB
  Microsoft.OperationalInsights Microsoft.Insights Microsoft.ContainerRegistry Microsoft.App
  Microsoft.ManagedIdentity Microsoft.Authorization)
for provider in "${providers[@]}"; do
  az provider register --namespace "$provider" --wait
done
for environment in dev prod; do
  az group create --name "rg-$prefix-$environment" --location "$location" \
    --tags application=licensing-agent environment="$environment" --output none
done
# The identity lives in dev but has an explicit, constrained assignment on both RGs.
identity_name="id-$prefix-github"
identity=$(az identity create --name "$identity_name" --resource-group "rg-$prefix-dev" \
  --location "$location" --output json)
client_id=$(jq -er .clientId <<<"$identity")
principal_id=$(jq -er .principalId <<<"$identity")
issuer=https://token.actions.githubusercontent.com
audience=api://AzureADTokenExchange
if [[ "$cloud" == AzureUSGovernment ]]; then audience=api://AzureADTokenExchangeUSGov; fi
existing_environments=$(gh api --paginate "repos/$repo/environments?per_page=100" --jq '.environments[].name')
for environment in dev prod; do
  az identity federated-credential create --name "github-$environment" \
    --identity-name "$identity_name" --resource-group "rg-$prefix-dev" \
    --issuer "$issuer" --subject "repo:$repo:environment:$environment" \
    --audiences "$audience" --output none
  scope="/subscriptions/$subscription/resourceGroups/rg-$prefix-$environment"
  # Contributor: deploy resources, but cannot create Azure RBAC assignments.
  contributor=b24988ac-6180-42a0-ab88-20f7382dd24c
  # Role Based Access Control Administrator: only the Bicep allow-list, on this RG.
  rbac_admin=f58310d9-a9f6-439a-9e8d-f62e7b41a168
  az role assignment create --assignee-object-id "$principal_id" --assignee-principal-type ServicePrincipal \
    --role "$contributor" --scope "$scope" --output none
  existing=$(az role assignment list --scope "$scope" --all --output json |
    jq -r --arg p "$principal_id" --arg s "$scope" --arg r "/$rbac_admin" \
      '[.[] | select(.principalId == $p and (.scope | ascii_downcase) == ($s | ascii_downcase) and (.roleDefinitionId | endswith($r)))]')
  if [[ $(jq length <<<"$existing") -gt 1 ]]; then
    echo "Multiple RBAC Administrator assignments found on $scope; resolve before retrying." >&2
    exit 1
  elif [[ $(jq length <<<"$existing") == 1 ]]; then
    az role assignment update --role-assignment "$(jq '.[0]' <<<"$existing" |
      jq --arg c "$condition" '.condition = $c | .conditionVersion = "2.0"')" --output none
  else
    az role assignment create --assignee-object-id "$principal_id" --assignee-principal-type ServicePrincipal \
      --role "$rbac_admin" --scope "$scope" --condition-version 2.0 --condition "$condition" --output none
  fi
  # Never PUT an existing environment: preserve human-configured approval rules.
  if ! grep -Fxq "$environment" <<<"$existing_environments"; then
    gh api --method PUT "repos/$repo/environments/$environment" >/dev/null
  fi
done

app_name="$prefix-licensing-api"
scope_id=987e2456-7865-42ef-9381-a86b0c88cfb4
configure_app() {
  local apps count app_id existing_scopes
  apps=$(az ad app list --display-name "$app_name" --output json) || return
  count=$(jq length <<<"$apps")
  [[ "$count" -le 1 ]] || { echo "Multiple apps named $app_name; resolve the ambiguity before retrying." >&2; return 1; }
  if [[ "$count" == 0 ]]; then
    app_id=$(az ad app create --display-name "$app_name" --sign-in-audience AzureADMyOrg --query appId -o tsv) || return
  else
    app_id=$(jq -er '.[0].appId' <<<"$apps") || return
  fi
  az ad app show --id "$app_id" -o json >"$tmp/app.json" || return
  # Merge, rather than replace, any scopes subsequently added by an administrator.
  existing_scopes=$(jq --arg id "$scope_id" '
    (.api // {}) |
    .requestedAccessTokenVersion = 2 |
    .oauth2PermissionScopes = (
      (.oauth2PermissionScopes // []) |
      if any(.value == "access_as_user") then . else . + [{
        id: $id, value: "access_as_user", type: "User", isEnabled: true,
        adminConsentDisplayName: "Access licensing advisor",
        adminConsentDescription: "Access the licensing advisor as the signed-in user.",
        userConsentDisplayName: "Access licensing advisor",
        userConsentDescription: "Access the licensing advisor as you."
      }] end)' "$tmp/app.json") || return
  az ad app update --id "$app_id" --identifier-uris "api://$app_id" \
    --set "api=$existing_scopes" --output none || return
  printf 'api://%s\n' "$app_id"
}
if app_uri=$(configure_app 2>"$tmp/entra-error"); then
  echo "API registration ready: $app_uri"
else
  cat "$tmp/entra-error" >&2
  app_uri=${API_APP_ID_URI:-}
  cat >&2 <<EOF
WARNING: API app registration is incomplete; the Azure/GitHub bootstrap will continue.
Ask an Entra Application Administrator to:
1. In tenant $tenant, create or select a single-tenant app named $app_name.
2. Set its requested access token version to 2.
3. Expose an API with Application ID URI api://<application-client-id>.
4. Add enabled delegated scope access_as_user, consent type Users and admins,
   with display name 'Access licensing advisor' and description
   'Access the licensing advisor as the signed-in user.' (for both consent forms).
5. Run both commands, substituting the application-client-id:
   gh variable set API_APP_ID_URI --repo $repo --env dev --body 'api://<application-client-id>'
   gh variable set API_APP_ID_URI --repo $repo --env prod --body 'api://<application-client-id>'
Then rerun bootstrap or verify all variables before deploying. No secret is needed.
EOF
fi

for environment in dev prod; do
  set_variable() { gh variable set "$1" --repo "$repo" --env "$environment" --body "$2"; }
  set_variable AZURE_CLIENT_ID "$client_id"
  set_variable AZURE_TENANT_ID "$tenant"
  set_variable AZURE_SUBSCRIPTION_ID "$subscription"
  set_variable AZURE_RESOURCE_GROUP "rg-$prefix-$environment"
  set_variable AZURE_LOCATION "$location"
  set_variable AZURE_CLOUD "$cloud"
  set_variable NAME_PREFIX "$prefix"
  set_variable DEPLOY_PRINCIPAL_ID "$principal_id"
  if [[ -n "$app_uri" ]]; then set_variable API_APP_ID_URI "$app_uri"; fi
done
echo "Azure resources and GitHub environments configured. Review any Entra warning above."
echo "REQUIRED: add required reviewers to the prod GitHub environment before the first prod deployment."
