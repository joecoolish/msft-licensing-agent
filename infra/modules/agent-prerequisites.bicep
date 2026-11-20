import { roles } from '../roles.bicep'
param projectPrincipalId string
param storageName string
param cosmosName string
param searchName string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: storageName }
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = { name: cosmosName }
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = { name: searchName }

resource storageContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, projectPrincipalId, roles.blobContributor)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobContributor)
  }
}
resource cosmosOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cosmos
  name: guid(cosmos.id, projectPrincipalId, roles.cosmosOperator)
  properties: {
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cosmosOperator)
  }
  dependsOn: [storageContributor]
}
resource searchRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in [roles.searchDataContributor, roles.searchContributor]: {
    scope: search
    name: guid(search.id, projectPrincipalId, role)
    properties: {
      principalId: projectPrincipalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
    }
    dependsOn: [cosmosOperator]
  }
]
