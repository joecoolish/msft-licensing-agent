#!/usr/bin/env bash
set -euo pipefail
: "${AZURE_RESOURCE_GROUP:?AZURE_RESOURCE_GROUP is required}"
: "${ENVIRONMENT_NAME:?ENVIRONMENT_NAME is required}"
outputs=$(az deployment group show --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "licensing-agent-$ENVIRONMENT_NAME" --query properties.outputs -o json)
ids=()
for key in accountCapabilityHostId projectCapabilityHostId; do
  id=$(jq -er --arg key "$key" '.[$key].value | select(type == "string" and startswith("/") and length > 1)' <<<"$outputs") ||
    { echo "Missing capability-host IDs in deployment outputs ($key)." >&2; exit 1; }
  ids+=("$id")
done
deadline=$((SECONDS + 1800))
while ((SECONDS < deadline)); do
  ready=true
  for id in "${ids[@]}"; do
    state=$(az resource show --ids "$id" --api-version 2025-04-01-preview --query properties.provisioningState -o tsv)
    case "${state,,}" in
      succeeded) ;;
      failed|canceled|cancelled)
        echo "::error::Capability host $id entered $state. Inspect its resource and deployment operations; do not redeploy with new names." >&2
        exit 1 ;;
      *) ready=false; echo "Waiting for $id (state: ${state:-not yet reported})" ;;
    esac
  done
  if "$ready"; then echo "Both capability hosts succeeded."; exit 0; fi
  sleep 30
done
echo "::error::Capability hosts did not succeed within 30 minutes. Provisioning commonly takes 10-20 minutes. Inspect Foundry capability hosts and deployment operations, then retry with the same stable names." >&2
exit 1
