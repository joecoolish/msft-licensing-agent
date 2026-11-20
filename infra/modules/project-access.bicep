import { roles } from '../roles.bicep'
param accountName string
param projectName string
param apiPrincipalId string
param deployPrincipalId string
param storageName string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = { name: accountName }
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}
resource projectUsers 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principalId in [apiPrincipalId, deployPrincipalId]: {
    scope: project
    name: guid(project.id, principalId, roles.foundryUser)
    properties: {
      principalId: principalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser)
    }
  }
]
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: storageName }
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' existing = {
  parent: storage
  name: 'default'
}
resource docs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' existing = {
  parent: blobs
  name: 'licensing-docs'
}
resource docsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: docs
  name: guid(docs.id, deployPrincipalId, roles.blobReader)
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobReader)
  }
}
