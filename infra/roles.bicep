// Exported IDs are the sole allow-list source for bootstrap's delegated Azure RBAC.
@export()
var roles = {
  // Foundry User: API invocation and agent deployment, scoped to the project.
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  // Storage Blob Data Reader: ingestion reads only the licensing-docs container.
  blobReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  // Storage Blob Data Contributor: standard agent storage provisioning.
  blobContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  // Storage Blob Data Owner: standard agent containers, with the sample's ABAC condition.
  blobOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  // Cosmos DB Operator: standard agent capability-host control-plane provisioning.
  cosmosOperator: '230815da-be43-4aae-9cb4-875f7bd000aa'
  // Search Index Data Contributor: standard agent vector-store documents.
  searchDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  // Search Service Contributor: standard agent index creation.
  searchContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  // AcrPull: API user-assigned identity pulls private application images.
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}
