param location string
param tags object
param accountName string
param projectName string
param modelName string
param modelVersion string
param skuName string
param capacity int
param storageName string
param cosmosName string
param searchName string
param searchDnsSuffix string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: storageName }
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = { name: cosmosName }
resource search 'Microsoft.Search/searchServices@2024-06-01-preview' existing = { name: searchName }

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}
resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: modelName
  sku: { name: skuName, capacity: capacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'On-Prem Licensing Advisor'
    description: 'Sourced licensing guidance with deterministic calculator quantities.'
  }
}
resource storageConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: storage.name
  properties: {
    category: 'AzureStorageAccount'
    target: storage.properties.primaryEndpoints.blob
    authType: 'AAD'
    metadata: { ApiType: 'Azure', ResourceId: storage.id, location: storage.location }
  }
}
resource cosmosConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: cosmos.name
  properties: {
    category: 'CosmosDB'
    target: cosmos.properties.documentEndpoint
    authType: 'AAD'
    metadata: { ApiType: 'Azure', ResourceId: cosmos.id, location: cosmos.location }
  }
}
resource searchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-04-01-preview' = {
  parent: project
  name: search.name
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${search.name}.${searchDnsSuffix}'
    authType: 'AAD'
    metadata: { ApiType: 'Azure', ResourceId: search.id, location: search.location }
  }
}

// Sample 41 relies on this RP-returned property, absent from the published schema.
#disable-next-line BCP053
var internalId = project.properties.internalId
var compactId = replace(internalId, '-', '')

output accountName string = account.name
output projectName string = project.name
output projectPrincipalId string = project.identity.principalId
output workspaceId string = '${substring(compactId, 0, 8)}-${substring(compactId, 8, 4)}-${substring(compactId, 12, 4)}-${substring(compactId, 16, 4)}-${substring(compactId, 20, 12)}'
output projectEndpoint string = '${account.properties.endpoints['AI Foundry API']}/api/projects/${project.name}'
output modelDeploymentName string = model.name
output storageConnection string = storageConnection.name
output cosmosConnection string = cosmosConnection.name
output searchConnection string = searchConnection.name
