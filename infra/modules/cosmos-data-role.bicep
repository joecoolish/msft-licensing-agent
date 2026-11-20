param cosmosName string
param databaseName string
param principalId string

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = { name: cosmosName }
// Cosmos DB Built-in Data Contributor: database-only data access; not Azure RBAC.
var roleId = '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
resource dataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, databaseName, principalId, roleId)
  properties: {
    principalId: principalId
    roleDefinitionId: roleId
    scope: '${cosmos.id}/dbs/${databaseName}'
  }
}
