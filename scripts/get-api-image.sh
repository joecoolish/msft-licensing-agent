#!/usr/bin/env bash
set -euo pipefail
: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"
# List first: only a confirmed absence may select the placeholder. Auth/network
# failures must fail the deployment instead of silently reverting an existing API.
count=$(az resource list --resource-group "$AZURE_RESOURCE_GROUP" \
  --resource-type Microsoft.App/containerApps --query "[?name=='api'] | length(@)" -o tsv)
case "$count" in
  0) image=docker.io/library/nginx:1.28-alpine ;;
  1)
    resource_id=$(az resource list --resource-group "$AZURE_RESOURCE_GROUP" \
      --resource-type Microsoft.App/containerApps --query "[?name=='api'].id | [0]" -o tsv)
    image=$(az resource show --ids "$resource_id" --api-version 2025-01-01 \
      --query "properties.template.containers[?name=='api'].image | [0]" -o tsv)
    [[ -n "$image" && "$image" != null ]] || { echo "Existing API has no api container image; refusing placeholder fallback." >&2; exit 1; }
    ;;
  *) echo "Unexpected API resource count: $count" >&2; exit 1 ;;
esac
[[ "$image" != *$'\n'* && "$image" != *$'\r'* ]] || { echo "Invalid multiline image." >&2; exit 1; }
printf 'image=%s\n' "$image" >>"$GITHUB_OUTPUT"
