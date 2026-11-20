param location string
param tags object
param storageName string
param cosmosName string
param searchName string
param searchSku string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource docs 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'licensing-docs'
  properties: { publicAccess: 'None' }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: cosmosName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    disableLocalAuth: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [
      { locationName: location, failoverPriority: 0, isZoneRedundant: false }
    ]
  }
}

resource appstate 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'appstate'
  properties: {
    resource: { id: 'appstate' }
    options: { throughput: 400 }
  }
}
var containers = [
  { name: 'conversations', partitionKey: '/userId' }
  { name: 'jobs', partitionKey: '/id' }
  { name: 'feedback', partitionKey: '/userId' }
]
resource appContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [
  for container in containers: {
    parent: appstate
    name: container.name
    properties: {
      resource: union({
        id: container.name
        partitionKey: { paths: [container.partitionKey], kind: 'Hash', version: 2 }
      }, container.name == 'jobs' ? { defaultTtl: 604800 } : {})
    }
  }
]

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: searchName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  sku: { name: searchSku }
  properties: {
    disableLocalAuth: true
    hostingMode: 'default'
    partitionCount: 1
    replicaCount: 1
    publicNetworkAccess: 'enabled'
    semanticSearch: 'disabled'
  }
}

output storageName string = storage.name
output cosmosName string = cosmos.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output searchName string = search.name
