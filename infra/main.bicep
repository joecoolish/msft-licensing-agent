targetScope = 'resourceGroup'

@allowed(['dev', 'prod'])
param environmentName string
param location string = resourceGroup().location

@minLength(2)
@maxLength(12)
@description('Lowercase alphanumeric prefix, starting with a letter; keep stable after bootstrap.')
param namePrefix string
param tags object = {}

param modelName string = 'gpt-5.4'
param modelVersion string = '2026-03-05'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param skuName string = 'GlobalStandard'
@minValue(1)
param capacity int = 10
@allowed(['basic', 'standard', 'standard2', 'standard3'])
param searchSku string = 'basic'

@description('Object ID of the GitHub deployment identity, not its client ID.')
param deployPrincipalId string
@description('Preserve the currently configured API image on every subsequent infra deployment.')
param apiImage string = 'docker.io/library/nginx:1.28-alpine'
param apiAppIdUri string

// ARM environment() has no AI Search suffix. Derive public DNS from Storage;
// Government Search is the documented exception rather than the Storage DNS zone.
param searchDnsSuffix string = environment().name == 'AzureUSGovernment'
  ? 'search.azure.us'
  : replace(environment().suffixes.storage, 'core.', 'search.')

var suffix = uniqueString(resourceGroup().id, namePrefix, environmentName)
var stem = '${namePrefix}-${environmentName}-${suffix}'
var resourceTags = union(tags, { environment: environmentName })

module data 'modules/data.bicep' = {
  name: 'data'
  params: {
    location: location
    tags: resourceTags
    storageName: 'st${take(namePrefix, 5)}${environmentName}${suffix}'
    cosmosName: 'cosmos-${stem}'
    searchName: 'search-${stem}'
    searchSku: searchSku
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  params: {
    location: location
    tags: resourceTags
    accountName: 'ai-${stem}'
    projectName: 'licensing'
    modelName: modelName
    modelVersion: modelVersion
    skuName: skuName
    capacity: capacity
    storageName: data.outputs.storageName
    cosmosName: data.outputs.cosmosName
    searchName: data.outputs.searchName
    searchDnsSuffix: searchDnsSuffix
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    tags: resourceTags
    stem: stem
    accountName: foundry.outputs.accountName
  }
}

// Preserve sample 41 ordering: Storage -> Cosmos Operator -> Search -> account
// capability host -> project capability host -> Blob Owner -> Cosmos data role.
module agentPrerequisites 'modules/agent-prerequisites.bicep' = {
  name: 'agent-prerequisites'
  params: {
    projectPrincipalId: foundry.outputs.projectPrincipalId
    storageName: data.outputs.storageName
    cosmosName: data.outputs.cosmosName
    searchName: data.outputs.searchName
  }
}

module capabilityHosts 'modules/capability-hosts.bicep' = {
  name: 'capability-hosts'
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    storageConnection: foundry.outputs.storageConnection
    cosmosConnection: foundry.outputs.cosmosConnection
    searchConnection: foundry.outputs.searchConnection
  }
  dependsOn: [agentPrerequisites]
}

module agentStorageRole 'modules/agent-storage-role.bicep' = {
  name: 'agent-storage-role'
  params: {
    storageName: data.outputs.storageName
    projectPrincipalId: foundry.outputs.projectPrincipalId
    workspaceId: foundry.outputs.workspaceId
  }
  dependsOn: [capabilityHosts]
}

module agentCosmosRole 'modules/cosmos-data-role.bicep' = {
  name: 'agent-cosmos-role'
  params: {
    cosmosName: data.outputs.cosmosName
    databaseName: 'enterprise_memory'
    principalId: foundry.outputs.projectPrincipalId
  }
  dependsOn: [agentStorageRole]
}

module api 'modules/api.bicep' = {
  name: 'api'
  params: {
    location: location
    tags: resourceTags
    stem: stem
    apiImage: apiImage
    apiAppIdUri: apiAppIdUri
    projectEndpoint: foundry.outputs.projectEndpoint
    modelDeploymentName: foundry.outputs.modelDeploymentName
    cosmosEndpoint: data.outputs.cosmosEndpoint
    workspaceId: monitoring.outputs.workspaceId
    appInsightsConnectionString: monitoring.outputs.connectionString
  }
}

module projectAccess 'modules/project-access.bicep' = {
  name: 'project-access'
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    apiPrincipalId: api.outputs.principalId
    deployPrincipalId: deployPrincipalId
    storageName: data.outputs.storageName
  }
}

module apiCosmosRole 'modules/cosmos-data-role.bicep' = {
  name: 'api-cosmos-role'
  params: {
    cosmosName: data.outputs.cosmosName
    databaseName: 'appstate'
    principalId: api.outputs.principalId
  }
}

output projectEndpoint string = foundry.outputs.projectEndpoint
output modelDeploymentName string = foundry.outputs.modelDeploymentName
output acrLoginServer string = api.outputs.acrLoginServer
output containerAppName string = api.outputs.containerAppName
output apiUrl string = api.outputs.apiUrl
output apiIdentityClientId string = api.outputs.clientId
output storageAccountName string = data.outputs.storageName
output cosmosEndpoint string = data.outputs.cosmosEndpoint
output appInsightsConnectionString string = monitoring.outputs.connectionString
output accountCapabilityHostId string = capabilityHosts.outputs.accountHostId
output projectCapabilityHostId string = capabilityHosts.outputs.projectHostId
