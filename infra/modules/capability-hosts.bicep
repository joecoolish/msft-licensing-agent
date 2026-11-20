param accountName string
param projectName string
param storageConnection string
param cosmosConnection string
param searchConnection string

resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = { name: accountName }
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' existing = {
  parent: account
  name: projectName
}
resource accountHost 'Microsoft.CognitiveServices/accounts/capabilityHosts@2025-04-01-preview' = {
  parent: account
  name: 'caphostacc'
  properties: { capabilityHostKind: 'Agents' }
}
resource projectHost 'Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2025-04-01-preview' = {
  parent: project
  name: 'caphostproj'
  properties: {
    vectorStoreConnections: [searchConnection]
    storageConnections: [storageConnection]
    threadStorageConnections: [cosmosConnection]
  }
  dependsOn: [accountHost]
}
output accountHostId string = accountHost.id
output projectHostId string = projectHost.id
